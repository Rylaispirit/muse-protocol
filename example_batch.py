"""Ví dụ đăng ký và đổi mã cho nhiều tài khoản.

Cách dùng: python example_batch.py [count]
Đọc config.json (xem các trường hàng loạt trong config.example.json), điều phối theo quy tắc của bộ chạy,
và in JSON tổng kết khi kết thúc. Chỉ dành cho học tập và nghiên cứu cá nhân.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musepy.runner import BatchRunner


def load_config(path="config.json"):
    if not os.path.exists(path):
        raise SystemExit(f"Thiếu file cấu hình {path}; hãy sao chép config.example.json và điền thông tin")
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    runner = BatchRunner(load_config())
    try:
        queued = runner.init(count)
    except ValueError as exc:
        raise SystemExit(f"Cấu hình chưa đầy đủ: {exc}")
    print(f"[i] queued={queued} workers={runner.workers} "
          f"max_per_ip={runner.max_per_ip}", flush=True)
    runner.run()
    print(json.dumps(runner.summary(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
