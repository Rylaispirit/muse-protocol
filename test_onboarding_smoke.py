"""Kiểm thử ngoại tuyến hàm thuần musepy.client.parse_onboarding, không chạy script của trang.

Chạy: python test_onboarding_smoke.py
Trường hợp: điều khoản bình thường, waitlist, xung đột và script không phải push để kiểm tra nhiễu.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musepy.client import parse_onboarding


def _html(*push_chunks):
    """Tạo tài liệu kiểu muse.ai có self.__next_f.push."""
    scripts = []
    for chunk in push_chunks:
        scripts.append(
            "<script>self.__next_f.push(%s);</script>" % json.dumps([1, chunk])
        )
    noise = "<script>function notAFlightRecord(){return 0;}</script>"
    return "<html><body>" + noise + "".join(scripts) + "</body></html>"


def _row(row_id, payload):
    # Flight chunk thực kết thúc bằng ký tự xuống dòng; giữ nguyên cấu trúc đó
    return row_id + ":" + json.dumps(payload) + "\n"


def case_normal():
    status = {"result": "success", "resolvedDestination": "main_app",
              "status": {"isGeoGated": False, "hasHatchAccess": True, "waitlistStatus": None}}
    disclosure = {"disclosureText": "次に進むことで同意します。", "disclosureVersion": "HATCH_ROW_v0"}
    doc = _html(_row("1a2b", status), _row("3c4d", disclosure))
    out = parse_onboarding(doc)
    assert out["state"] == "disclosure", out
    assert out["disclosure_text"] == disclosure["disclosureText"], out
    assert out["disclosure_version"] == "HATCH_ROW_v0", out
    assert out["resolved_destination"] == "main_app", out
    assert out["is_geo_gated"] is False and out["has_hatch_access"] is True, out


def case_waitlist():
    status = {"result": "success", "resolvedDestination": "waitlist",
              "status": {"isGeoGated": False, "hasHatchAccess": False, "waitlistStatus": "pending"}}
    doc = _html(_row("a1b2", status),
                _row("c3d4", {"disclosureText": "任意正文", "disclosureVersion": "HATCH_ROW_v0"}))
    out = parse_onboarding(doc)
    assert out["state"] == "waitlist", out
    assert out["resolved_destination"] == "waitlist", out
    assert out["waitlist_status"] == "pending", out


def case_geo_gated():
    status = {"result": "success", "resolvedDestination": "main_app",
              "status": {"isGeoGated": True, "hasHatchAccess": False, "waitlistStatus": None}}
    doc = _html(_row("aa11", status),
                _row("bb22", {"disclosureText": "任意正文", "disclosureVersion": "HATCH_ROW_v0"}))
    out = parse_onboarding(doc)
    assert out["state"] == "waitlist", out
    assert out["is_geo_gated"] is True, out


def case_conflict():
    doc = _html(
        _row("1a2b", {"disclosureText": "版本A的正文", "disclosureVersion": "HATCH_ROW_v0"}),
        _row("3c4d", {"disclosureText": "版本B的正文", "disclosureVersion": "HATCH_ROW_v0"}),
    )
    out = parse_onboarding(doc)
    assert out["state"] == "unresolved", out


def case_missing():
    doc = _html(_row("1a2b", {"unrelated": True}))
    out = parse_onboarding(doc)
    assert out["state"] == "unresolved", out


def case_unknown_version():
    doc = _html(_row("1a2b", {"disclosureText": "正文", "disclosureVersion": "HATCH_UNKNOWN_v9"}))
    out = parse_onboarding(doc)
    assert out["state"] == "unresolved", out
    assert out["reason"] == "disclosure_version_unsupported", out


def main():
    tests = [("normal_disclosure", case_normal), ("waitlist", case_waitlist),
             ("geo_gated", case_geo_gated), ("disclosure_conflict", case_conflict),
             ("disclosure_missing", case_missing), ("unknown_version", case_unknown_version)]
    for name, fn in tests:
        fn()
        print(f"[PASS] {name}")
    print(f"Kiểm thử đạt {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
