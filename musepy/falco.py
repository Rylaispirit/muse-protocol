"""
Báo cáo sự kiện falco (tùy chọn)

Frontend gửi hàng loạt sự kiện hành vi qua POST /api/falco. Theo ghi nhận gốc, bỏ báo cáo
không trực tiếp làm đăng ký thất bại nhưng khiến đặc điểm phiên khác với trình duyệt thực.
"""

import json
import random
import time

BASE = "https://muse.ai"


def _ms():
    return int(time.time() * 1000)


def interaction(uri, action_type, action_target, event_name, meta=None):
    m = {"surface": "onboarding", "result": "success",
         "resolution_mode": "blocking", "resolved_destination": "main_app"}
    if meta:
        m.update(meta)
    payload = {
        "is_cvm": False,
        "metadata": json.dumps(m, separators=(",", ":")),
        "uri": uri,
        "action_type": action_type,
        "action_target": action_target,
        "event_name": event_name,
        "device_locale": "ja",
    }
    return {"event": "hatch_web_interaction", "timeInMs": _ms(), "rate": 1,
            "payload": json.dumps(payload, separators=(",", ":"))}


def impression(uri, surface, subsurface, entry_point, extra=None):
    m = {"surface": surface, "subsurface": subsurface, "entry_point": entry_point}
    if extra:
        m.update(extra)
    payload = {
        "is_cvm": False,
        "metadata": json.dumps(m, separators=(",", ":")),
        "uri": uri,
        "action_type": "one_px_impression",
        "action_target": subsurface + "_ready",
        "event_name": subsurface + "_ready_impression",
        "device_locale": "ja",
    }
    return {"event": "hatch_web_impression", "timeInMs": _ms(), "rate": 1,
            "payload": json.dumps(payload, separators=(",", ":"))}


def perf(uri, nav_type="navigate", seconds=None):
    ann = {
        "tracePolicy": "hatch.chat",
        "traceType": "INITIAL_LOAD",
        "uri": uri,
        "httpProtocol": "h2",
        "navigationType": nav_type,
        "interactionClass": "responsive",
        "qpl__source": "client_js",
        "navigationTypeDetail": "normal",
        "page_load_id": "%08x-0000-4000-8000-%012x" % (
            random.getrandbits(32), random.getrandbits(48)),
    }
    payload = {
        "marker_id": random.randint(600000000, 610000000),
        "action_id": 2,
        "sample_rate": 1,
        "duration_ns": int((seconds or random.uniform(2.5, 12.0)) * 1e9),
        "annotations": ann,
    }
    return {"event": "perf", "timeInMs": _ms(),
            "payload": json.dumps(payload, separators=(",", ":"))}


def send(session, impersonate, lang, session_id, events):
    """Gửi một nhóm sự kiện; bỏ qua lỗi"""
    if not events:
        return None
    body = {"sessionId": session_id, "user": {"kind": "loggedOut"},
            "machineId": "not_set", "events": events}
    h = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": BASE,
        "referer": BASE + "/",
        "accept-language": lang,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }
    try:
        return session.post(BASE + "/api/falco", impersonate=impersonate,
                            headers=h, data=json.dumps(body, separators=(",", ":")))
    except Exception:
        return None
