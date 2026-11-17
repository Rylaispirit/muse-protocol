"""
Client giao thức đăng ký và đổi mã mời muse.ai (thuần HTTP, không cần trình duyệt)

Chỉ dành cho nghiên cứu giao thức và học tập cá nhân. Xem điều khoản của dịch vụ trước khi sử dụng.
"""

import json
import random
import re
import time
import uuid
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from curl_cffi import requests as cr

BASE = "https://muse.ai"

# Endpoint khởi tạo phiên: sau khi register-completion trả frl_access_token, phải gọi bước này trước.
# Nếu bỏ qua, các API hatch tiếp theo trả về 403 theo ghi nhận thử nghiệm gốc.
BOOTSTRAP_URL = "https://auth.meta.com/hatch/session/bootstrap/"
TRUSTED_HOSTS = frozenset({"auth.meta.com", "auth.muse.ai", "muse.ai"})

# Phiên bản TOS dự phòng cho trường hợp confirm-otp không trả tos.content_version.
# Bình thường dùng phiên bản do máy chủ trả về trong confirm_otp.
TOS_VERSION = "ntm_create_account:default_v1_meta_account_v3+docs_v2"

HEADERS_JSON = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": BASE,
    "referer": BASE + "/",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}
HEADERS_GET = {
    "accept": "*/*",
    "referer": BASE + "/",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}
HEADERS_HTML = {
    # Header Accept đầy đủ của tài liệu trình duyệt, đối chiếu từ yêu cầu mạng gốc.
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8,"
               "application/signed-exchange;v=b3;q=0.7"),
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "document",
}

# Nội dung điều khoản tiếng Nhật được ghi lại để tham khảo. accept-tos dùng dữ liệu động
# disclosure_text / disclosure_version từ activate_session(); hằng số này chỉ để đối chiếu.
DISCLOSURE_TEXT_JA = (
    "次に進むことで、Muse利用規約およびMetaのAI利用規約に同意するものとします。"
    "これには利用者の権利と責任に関する重要な情報が含まれています。"
    "プライバシーに関するMuseのアプローチについて詳しくはMuseプライバシーポリシーをご覧ください。"
)


class MuseError(RuntimeError):
    """Lỗi dự kiến trong quy trình giao thức"""


class MuseClient:
    """Một tài khoản dùng một Session (một IP đầu ra)"""

    def __init__(self, proxy=None, impersonate="chrome142", lang="ja", timeout=30):
        self.fp = impersonate
        self.lang = lang
        self.proxy = proxy
        self.timeout = timeout
        self.s = cr.Session(impersonate=impersonate,
                            proxies={"http": proxy, "https": proxy} if proxy else None,
                            timeout=timeout)
        self.csrf = None
        self.tos_content_version = None   # Phiên bản TOS do máy chủ trả về qua confirm-otp
        self.onboarding = None            # Nội dung điều khoản được activate_session phân tích

    # ---------- Hàm hỗ trợ ----------

    def _h(self, base, extra=None):
        h = dict(base)
        h["accept-language"] = self.lang
        if extra:
            h.update(extra)
        return h

    def _json(self, resp):
        try:
            return resp.json() or {}
        except Exception:
            return {}

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass

    # ---------- Quy trình đăng ký ----------

    def open_home(self):
        return self.s.get(BASE + "/", impersonate=self.fp,
                          headers=self._h(HEADERS_HTML))

    def restart(self, resume=False):
        """Bắt đầu quy trình đăng ký và trả về csrf_token"""
        r = self.s.post(BASE + "/api/auth/native/restart", impersonate=self.fp,
                        headers=self._h(HEADERS_JSON), data=json.dumps({"resume": resume}))
        if r.status_code != 201:
            raise MuseError(f"restart {r.status_code}: {r.text[:120]}")
        self.csrf = self._json(r).get("csrf_token")
        if not self.csrf:
            raise MuseError("restart không trả về csrf_token")
        return self.csrf

    def _auth_headers(self):
        h = self._h(HEADERS_JSON)
        if self.csrf:
            h["X-Hatch-CSRF-Token"] = self.csrf
            h["X-Hatch-Waterfall-Id"] = _uuid()
            h["X-Hatch-Caa-Reg-Entry-Point"] = "login_home"
        return h

    def send_otp(self, email):
        r = self.s.post(BASE + "/api/auth/native/send-otp", impersonate=self.fp,
                        headers=self._auth_headers(), data=json.dumps({"contact_point": email}))
        if r.status_code not in (200, 201):
            raise MuseError(f"send-otp {r.status_code}: {r.text[:120]}")
        return self._json(r)

    def confirm_otp(self, code):
        """Bắt buộc: supports_muse_link_transparency phải là true"""
        r = self.s.post(BASE + "/api/auth/native/confirm-otp", impersonate=self.fp,
                        headers=self._auth_headers(),
                        data=json.dumps({"otp_code": code,
                                         "remember_device": True,
                                         "supports_muse_link_transparency": True}))
        if r.status_code != 200:
            raise MuseError(f"confirm-otp {r.status_code}: {r.text[:120]}")
        data = self._json(r)
        tos = data.get("tos")
        if (isinstance(tos, dict) and isinstance(tos.get("content_version"), str)
                and tos["content_version"].strip()):
            # register-completion dùng phiên bản động do máy chủ trả về.
            self.tos_content_version = tos["content_version"]
        return data

    def register_completion(self, date_of_birth, first_name, last_name, remember_device=True):
        """
        Hoàn tất đăng ký. Ý nghĩa các trường:
          first_name = tên (given name)
          last_name  = họ (family name)
        Ngày sinh tương ứng với tuổi dưới khoảng 18 có thể bị máy chủ từ chối (403).
        """
        body = {
            "date_of_birth": date_of_birth,
            "first_name": first_name,
            "last_name": last_name,
            "tos_content_version": self.tos_content_version or TOS_VERSION,
            "remember_device": remember_device,
        }
        r = self.s.post(BASE + "/api/auth/native/register-completion", impersonate=self.fp,
                        headers=self._auth_headers(), data=json.dumps(body))
        if r.status_code != 200:
            raise MuseError(f"register-completion {r.status_code}: {r.text[:120]}")
        data = self._json(r)
        self.account_id = (data.get("auth_meta_session") or {}).get("frl_account_id")
        return data

    def session_cookie(self, name="hatch_sess"):
        for c in self.s.cookies.jar:
            if c.name == name:
                return c.value
        return None

    # ---------- Kích hoạt ----------

    def _trusted_location(self, location, base_url):
        """Kiểm tra và phân tích Location của phản hồi 3xx; đường dẫn tương đối dựa trên URL hiện tại.

        Chỉ chấp nhận HTTPS và các miền tin cậy (auth.meta.com / auth.muse.ai / muse.ai),
        từ chối userinfo, cổng khác 443 và đích chứa dấu gạch chéo ngược hoặc khoảng trắng.
        """
        if (not isinstance(location, str) or not location
                or "\\" in location or any(ch.isspace() for ch in location)):
            raise MuseError("activate_session có Location chuyển hướng không hợp lệ")
        parts = urlsplit(urljoin(base_url, location))
        if (parts.scheme != "https" or parts.hostname not in TRUSTED_HOSTS
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443)):
            raise MuseError("activate_session có đích chuyển hướng không đáng tin cậy")
        return urlunsplit(("https", parts.hostname, parts.path or "/", parts.query, ""))

    def activate_session(self, frl_access_token):
        """Khởi tạo phiên; bắt buộc gọi sau register-completion và trước accept-tos.

        POST https://auth.meta.com/hatch/session/bootstrap/ bằng form chỉ chứa
        frl_access_token; dùng allow_redirects=False và tự theo chuyển hướng 301/302/303,
        đến tài liệu HTML muse.ai trả 200. Phân tích điều khoản động và điều kiện truy cập:
          - resolvedDestination=="waitlist" hoặc isGeoGated=True
                → MuseError("region_waitlist") (đã đăng ký nhưng bị giới hạn khu vực, chưa xác nhận vào danh sách chờ)
          - Thiếu hoặc xung đột nội dung/phiên bản điều khoản → MuseError("disclosure_context_unresolved")
          - Chỉ hỗ trợ disclosureVersion=="HATCH_ROW_v0"; không suy đoán tham số cho phiên bản lạ
        Thành công trả về dict chứa disclosure_text / disclosure_version / source_url,
        truyền trực tiếp cho accept_tos().
        """
        if not isinstance(frl_access_token, str) or not frl_access_token.strip():
            raise MuseError("activate_session thiếu frl_access_token")
        url, method, hops = BOOTSTRAP_URL, "POST", 0
        while True:
            headers = self._h(HEADERS_HTML)
            if method == "POST":
                headers.update({
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": BASE,
                    "referer": BASE + "/",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "cross-site",
                    "upgrade-insecure-requests": "1",
                    "cache-control": "max-age=0",
                    "priority": "u=0, i",
                })
                r = self.s.post(url, impersonate=self.fp, headers=headers,
                                data=urlencode({"frl_access_token": frl_access_token}),
                                allow_redirects=False)
            else:
                r = self.s.get(url, impersonate=self.fp, headers=headers,
                               allow_redirects=False)
            if r.status_code in (301, 302, 303):
                hops += 1
                if hops > 6:
                    raise MuseError("activate_session chuyển hướng quá nhiều lần")
                url, method = self._trusted_location(r.headers.get("location"), url), "GET"
                continue
            break
        if r.status_code != 200:
            raise MuseError(f"activate_session khởi tạo thất bại {r.status_code}: {r.text[:120]}")
        final = urlsplit(url)
        if final.hostname != "muse.ai":
            raise MuseError(f"activate_session kết thúc ở miền khác muse.ai ({final.hostname})")
        onboarding = parse_onboarding(r.text)
        if onboarding["state"] == "waitlist":
            raise MuseError("region_waitlist")
        if onboarding["state"] != "disclosure":
            raise MuseError(f"disclosure_context_unresolved ({onboarding.get('reason')})")
        onboarding["source_url"] = urlunsplit(("https", final.hostname, final.path or "/", "", ""))
        self.onboarding = onboarding
        return onboarding

    def accept_tos(self, onboarding=None):
        """Bắt buộc gọi để các API hatch tiếp theo không trả 403; chỉ gọi một lần, không thử lại.

        onboarding phải là kết quả phân tích do activate_session() trả về; dùng nội dung
        disclosure_text / disclosure_version động từ máy chủ,
        và Referer là URL thực của trang điều khoản.
        """
        text = (onboarding or {}).get("disclosure_text")
        version = (onboarding or {}).get("disclosure_version")
        if not text or not version:
            raise MuseError("accept_tos thiếu điều khoản động; hãy gọi activate_session() trước")
        body = {
            "saw_meta_ai_tos": False,
            "client_request_timestamp": str(int(time.time())),
            "entry_point": "web_onboarding_flow",
            "nux_type": "ROW",
            "disclosure_version": version,
            "disclosure_text": text,
        }
        headers = self._h(HEADERS_JSON)
        referer = (onboarding or {}).get("source_url")
        if referer:
            headers["referer"] = referer
        r = self.s.post(BASE + "/api/hatch/accept-tos", impersonate=self.fp,
                        headers=headers, data=json.dumps(body))
        if r.status_code == 403:
            raise MuseError(f"accept-tos 403: {r.text[:200]}")
        if r.status_code != 200:
            raise MuseError(f"accept-tos {r.status_code}: {r.text[:200]}")
        return r

    def invite(self):
        return self.s.get(BASE + "/api/hatch/invite", impersonate=self.fp,
                          headers=self._h(HEADERS_GET))

    def is_live(self):
        """invite 200 = tài khoản hợp lệ; 401/403 = chưa có quyền truy cập hatch"""
        try:
            return self.invite().status_code == 200
        except Exception:
            return False

    def wake_vm(self):
        """Phải gọi trước khi đổi mã để tránh kết quả invalid gây hiểu nhầm.

        Kết nối đầu dùng wake_trigger="mount", body có open_id (UUID mới) và away_ms=0;
        trước wake, GET /?aymh_complete=1 để phân tích vmId từ tài liệu theo logic gốc.
        """
        r = self.s.get(BASE + "/?aymh_complete=1", impersonate=self.fp,
                       headers=self._h(HEADERS_HTML))
        m = re.search(r'vmId[\\"]*:[\\"]*([0-9a-fA-F-]{36})', r.text)
        if not m:
            return None
        vm_id = m.group(1)
        self.s.post(BASE + "/api/hatch/vm/wake", impersonate=self.fp,
                    headers=self._h(HEADERS_JSON),
                    data=json.dumps({"vm_id": vm_id,
                                     "retry_count": 0,
                                     "connect_attempt_id": _uuid(),
                                     "wake_trigger": "mount",
                                     "open_id": _uuid(),
                                     "away_ms": 0}))
        return vm_id

    def stateful_sharing(self):
        return self.s.post(BASE + "/api/hatch/stateful-sharing", impersonate=self.fp,
                           headers=self._h(HEADERS_JSON), data="")

    # ---------- Đổi mã ----------

    def redeem(self, code):
        """
        Đổi mã mời. Trả về (ok, reason).
          reason: redeemed | already_redeemed | used_up | invalid
        """
        r = self.s.post(BASE + "/api/hatch/invite-code/redeem", impersonate=self.fp,
                        headers=self._h(HEADERS_JSON),
                        data=json.dumps({"code": code, "supportsRedemptionStatus": True}))
        if r.status_code == 200 and '"success":true' in r.text:
            return True, "redeemed"
        data = self._json(r)
        return False, data.get("reason") or f"http-{r.status_code}"

    def scratch_code(self):
        """Lấy mã mời đã cấp cho tài khoản sau khi đổi mã thành công.

        POST /api/hatch/invite chỉ trả về mã mời của tài khoản,
        không thực hiện thao tác cào để hiện mã (reveal) trên giao diện.
        """
        r = self.s.post(BASE + "/api/hatch/invite", impersonate=self.fp,
                        headers=self._h(HEADERS_JSON), data="")
        if r.status_code != 200:
            return None
        return self._json(r).get("code")


def _uuid():
    return str(uuid.uuid4())


def _flight_chunks(text):
    """Trích chuỗi dữ liệu từ self.__next_f.push bằng phân tích văn bản, không thực thi script."""
    chunks = []
    if not isinstance(text, str):
        return chunks
    for script in re.findall(r"<script\b[^>]*>(.*?)</script\s*>", text, re.I | re.S):
        match = re.fullmatch(r"\s*self\.__next_f\.push\((.*)\)\s*;?\s*", script, re.S)
        if not match:
            continue
        try:
            value = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue
        if (isinstance(value, list) and len(value) == 2 and value[0] == 1
                and isinstance(value[1], str)):
            chunks.append(value[1])
    return chunks


def parse_onboarding(html):
    """Phân tích Next Flight trong tài liệu khởi tạo muse.ai; hàm thuần, ngoại tuyến, không gửi yêu cầu.

    Trả về dict: state = disclosure | waitlist | unresolved.
      - resolvedDestination=="waitlist" hoặc isGeoGated is True → state="waitlist"
      - Thiếu hoặc xung đột nội dung/phiên bản điều khoản → state="unresolved" (không suy đoán tham số)
      - Chỉ hỗ trợ disclosureVersion=="HATCH_ROW_v0"; phiên bản lạ cũng trả unresolved
    Giữ nguyên các giá trị trạng thái isGeoGated / hasHatchAccess / waitlistStatus.
    """
    states, disclosures = [], []
    objects = []

    def collect(value):
        if isinstance(value, dict):
            objects.append(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for row in "".join(_flight_chunks(html)).splitlines():
        row_id, separator, data = row.partition(":")
        if not separator or not re.fullmatch(r"[0-9a-f]+", row_id):
            continue
        try:
            collect(json.loads(data))
        except (ValueError, TypeError):
            continue  # Bỏ qua dòng dữ liệu không phải JSON, như tham chiếu module hoặc văn bản
    for obj in objects:
        if "resolvedDestination" in obj and isinstance(obj.get("status"), dict):
            status = obj["status"]
            states.append({
                "resolved_destination": obj.get("resolvedDestination"),
                "is_geo_gated": status.get("isGeoGated"),
                "has_hatch_access": status.get("hasHatchAccess"),
                "waitlist_status": status.get("waitlistStatus"),
            })
        if "disclosureText" in obj or "disclosureVersion" in obj:
            disclosures.append((obj.get("disclosureText"), obj.get("disclosureVersion")))
    if states:
        if len({json.dumps(s, sort_keys=True) for s in states}) > 1:
            return {"state": "unresolved", "reason": "onboarding_state_conflict"}
        if (states[0]["resolved_destination"] == "waitlist"
                or states[0]["is_geo_gated"] is True):
            return {"state": "waitlist", "reason": "onboarding_waitlist", **states[0]}
    texts = list(dict.fromkeys(t for t, _ in disclosures
                               if isinstance(t, str) and t.strip()))
    versions = list(dict.fromkeys(v for _, v in disclosures
                                  if isinstance(v, str) and v.strip()))
    if len(texts) != 1 or len(versions) != 1:
        return {"state": "unresolved", "reason": "disclosure_context_unresolved"}
    if versions[0] != "HATCH_ROW_v0":
        return {"state": "unresolved", "reason": "disclosure_version_unsupported",
                "disclosure_version": versions[0]}
    out = {"state": "disclosure", "reason": "disclosure_context_observed",
           "disclosure_text": texts[0], "disclosure_version": versions[0]}
    if states:
        out.update(states[0])
    return out


def random_dob(min_year=1970, max_year=1999):
    return (f"{random.randint(min_year, max_year)}-"
            f"{random.randint(1, 12):02d}-"
            f"{random.randint(1, 28):02d}")
