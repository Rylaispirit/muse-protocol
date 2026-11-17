"""Thăm dò mã xác minh OTP.

select_otp là hàm thuần; wait_otp thăm dò URL nguồn OTP và chỉ lấy
mã 6 chữ số mới sau mốc gửi; thử lại cùng hộp thư không dùng nhầm mã cũ.
"""

import json
import re
import time
from datetime import datetime, timezone

UTC = timezone.utc


def parse_iso8601(value):
    """Phân tích thành thời gian UTC có múi giờ; đầu vào thiếu múi giờ trả None."""
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def select_otp(records, after):
    """Chọn mã 6 chữ số mới nhất, sau after; nhiều mã khác nhau cùng thời điểm mới nhất là không rõ ràng.

    records: [{"otp": "123456", "time": "<ISO8601>"}, ...]
    after:   Mốc gửi của lần send_otp này (chuỗi ISO 8601 hoặc datetime).
    """
    boundary = parse_iso8601(after)
    if boundary is None or not isinstance(records, list):
        return None
    candidates = []
    for item in records:
        if not isinstance(item, dict):
            continue
        code = item.get("otp")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
            continue
        timestamp = parse_iso8601(item.get("time"))
        if timestamp is not None and timestamp > boundary:
            candidates.append((timestamp, code))
    if not candidates:
        return None
    newest = max(timestamp for timestamp, _ in candidates)
    codes = {code for timestamp, code in candidates if timestamp == newest}
    return next(iter(codes)) if len(codes) == 1 else None


def wait_otp(url, after, *, timeout=45, poll_interval=0.6, request_timeout=15,
             session_factory=None):
    """Thăm dò URL nguồn OTP cho đến khi có mã xác minh mới.

    - GET mỗi poll_interval giây; mỗi yêu cầu chờ tối đa request_timeout giây;
    - Tổng thời gian chờ timeout giây (mặc định 45 giây);
    - Phản hồi khác 200 hoặc không phải mảng JSON → None; lỗi mạng được ném lên (transport_error);
    - session_factory cho phép dùng phiên giả lập để kiểm thử ngoại tuyến; mặc định tạo curl_cffi Session.
    """
    if session_factory is not None:
        session = session_factory()
    else:
        from curl_cffi import requests as cr
        session = cr.Session()
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            response = session.get(url, timeout=request_timeout, headers={"accept": "*/*"})
            if response.status_code != 200:
                return None
            try:
                records = json.loads(response.text)
            except (TypeError, ValueError):
                return None
            otp = select_otp(records, after)
            if otp:
                return otp
            time.sleep(poll_interval)
        return None
    finally:
        try:
            session.close()
        except Exception:
            pass
