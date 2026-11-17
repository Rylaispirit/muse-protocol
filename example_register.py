"""Ví dụ đầy đủ quy trình đăng ký và đổi mã. Điền config.json trước khi chạy (xem config.example.json)."""

import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musepy import caa, falco
from musepy.client import MuseClient, MuseError, random_dob


def load_config(path="config.json"):
    if not os.path.exists(path):
        raise SystemExit(f"Thiếu file cấu hình {path}; hãy sao chép config.example.json và điền thông tin")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = load_config()

    email = cfg["email"]
    proxy = cfg.get("proxy") or None
    invite_code = cfg.get("invite_code") or ""
    otp_file = cfg.get("otp_file")  # Tùy chọn: đọc mã xác minh hiện tại từ file

    c = MuseClient(proxy=proxy, impersonate=cfg.get("impersonate", "chrome142"),
                   lang=cfg.get("lang", "ja"))

    print(f"[1] Mở trang chủ  {email}")
    c.open_home()

    print("[2] Khởi động lại quy trình đăng ký")
    c.restart()

    # ---- Báo cáo các bước đăng ký (tùy chọn) ----
    funnel = caa.Caa(c.fp, c.lang)
    if cfg.get("send_caa", True):
        funnel.page_shown(c.s)
        time.sleep(2)
        funnel.focus(c.s)
        time.sleep(0.5)
        funnel.continue_clicked(c.s)
        funnel.registration_start(c.s)

    print("[3] Gửi mã xác minh")
    c.send_otp(email)

    code = otp_file and open(otp_file).read().strip() or input("Nhập mã xác minh gồm 6 chữ số đã nhận: ").strip()

    if cfg.get("send_caa", True):
        funnel.otp_typed(c.s)

    print("[4] Kiểm tra mã xác minh")
    c.confirm_otp(code)

    first = cfg.get("first_name") or "三郎"    # Tên
    last = cfg.get("last_name") or "近藤"      # Họ
    dob = cfg.get("date_of_birth") or random_dob()

    if cfg.get("send_caa", True):
        funnel.otp_success(c.s)
        funnel.birthday_start(c.s)
        time.sleep(3)
        funnel.birthday_next(c.s)

    print(f"[5] Hoàn tất đăng ký  {last} {first}  {dob}")
    data = c.register_completion(dob, first, last)
    uid = (data.get("auth_meta_session") or {}).get("frl_account_id")
    print(f"    account_id = {uid}")

    if cfg.get("send_caa", True):
        funnel.create_success(c.s, uid)
        funnel.login_success(c.s, uid)

    # ---- Báo cáo falco (tùy chọn) ----
    if cfg.get("send_falco", True):
        falco.send(c.s, c.fp, c.lang, str(uuid.uuid4()), [
            falco.perf("https://muse.ai/"),
            falco.interaction("https://muse.ai/", "page_load", "main_app", "page_load"),
        ])

    print("[6] Khởi tạo phiên (session bootstrap; thiếu bước này sẽ gặp lỗi 403)")
    token = (data.get("auth_meta_session") or {}).get("frl_access_token")
    onboarding = c.activate_session(token)
    print(f"    resolved_destination = {onboarding.get('resolved_destination')}")
    print(f"    disclosure_version   = {onboarding.get('disclosure_version')}")

    print("[7] Kích hoạt phiên (accept-tos, gọi một lần với điều khoản do máy chủ trả về)")
    c.accept_tos(onboarding)
    print(f"    invite = {'200: tài khoản hợp lệ' if c.is_live() else '401/403: chưa có quyền truy cập hatch'}")

    print("[8] Đánh thức VM (wake_trigger=mount, open_id, away_ms=0)")
    vm = c.wake_vm()
    print(f"    vm_id = {vm}")

    c.stateful_sharing()

    print(f"[9] Đổi mã mời  {invite_code or '(chưa cấu hình)'}")
    if invite_code:
        ok, reason = c.redeem(invite_code)
        print(f"    redeem = {ok} / {reason}")
        if ok:
            own = c.scratch_code()
            print(f"[10] Mã mời của tài khoản (lấy qua POST invite) = {own}")
        else:
            print(f"    Ý nghĩa lỗi: already_redeemed=tài khoản đã đổi mã  "
                  f"used_up=mã đã hết lượt sử dụng  invalid=mã không tồn tại")
    else:
        print("    Bỏ qua bước đổi mã")

    sess = c.session_cookie()
    print(f"\nĐộ dài hatch_sess = {len(sess or '')}")
    c.close()


if __name__ == "__main__":
    try:
        main()
    except MuseError as e:
        if "region_waitlist" in str(e):
            # Máy chủ xác định giới hạn khu vực: tài khoản đã đăng ký và được giữ lại, chưa xác nhận vào danh sách chờ
            print(f"Bị giới hạn khu vực: {e}")
            print("    Tài khoản đã đăng ký nhưng bị giới hạn khu vực, chưa được xác nhận vào danh sách chờ; hãy kiểm tra khu vực kết nối")
        else:
            print(f"Lỗi giao thức: {e}")
        sys.exit(1)
