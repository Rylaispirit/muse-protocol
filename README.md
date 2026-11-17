# muse-protocol — Tài liệu tiếng Việt

Nghiên cứu giao thức đăng ký và đổi mã mời của [muse.ai](https://muse.ai), triển khai bằng Python qua HTTP, không cần trình duyệt. Các chi tiết bên dưới được tác giả gốc ghi nhận bằng cách bắt và đối chiếu từng trường trong yêu cầu mạng.

Mã nguồn gốc: [duwqijlk/muse-protocol](https://github.com/duwqijlk/muse-protocol). Bản này Việt hóa tài liệu, chú thích và thông báo dòng lệnh. Các endpoint, khóa cấu hình và mã trạng thái của giao thức được giữ nguyên.

Ghi nhận của tác giả gốc: kết nối qua Nhật Bản (JP) từng không yêu cầu liên kết thẻ. Đây là hành vi được quan sát tại thời điểm nghiên cứu; điều kiện truy cập do dịch vụ quyết định.

## Bắt đầu nhanh

Cần Python 3.10 trở lên và các thư viện trong `requirements.txt`.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.json
# Sửa config.json theo hướng dẫn bên dưới trước khi chạy.
.\.venv\Scripts\python.exe example_register.py
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.example.json config.json
# Sửa config.json theo hướng dẫn bên dưới trước khi chạy.
python example_register.py
```

### Cấu hình cho một tài khoản

Mở `config.json` và điền thông tin của bạn:

| Trường | Ý nghĩa |
|---|---|
| `email` | Địa chỉ email nhận mã xác minh |
| `proxy` | URL proxy, ví dụ `http://user:pass@host:port`; đặt `""` để kết nối trực tiếp |
| `invite_code` | Mã mời cần đổi; đặt `""` để bỏ qua bước đổi mã |
| `first_name` / `last_name` | Tên / họ |
| `date_of_birth` | Ngày sinh dạng `YYYY-MM-DD`; nếu bỏ trống, mã nguồn gốc sinh ngẫu nhiên trong khoảng 1970–1999 |
| `lang` | Ngôn ngữ gửi qua `Accept-Language`; mặc định `ja`, độc lập với thông báo tiếng Việt của chương trình |
| `impersonate` | Hồ sơ trình duyệt của `curl_cffi`; mặc định `chrome142` |
| `send_caa` / `send_falco` | Bật hoặc tắt báo cáo sự kiện; ví dụ đơn mặc định bật cả hai |
| `otp_file` | Với `example_register.py`: file chỉ chứa mã OTP hiện tại gồm 6 chữ số; đặt `null` hoặc bỏ trường này để nhập thủ công |

**Chú ý `otp_file`:** mẫu cấu hình dùng `"otp-urls.txt"` cho chế độ hàng loạt. Khi chạy ví dụ đơn và muốn tự nhập OTP, hãy đổi thành `"otp_file": null`. Hai chế độ không dùng chung định dạng file này.

## Cấu trúc thư mục

```text
musepy/
  client.py    Client giao thức đăng ký và đổi mã mời
  runner.py    Điều phối nhiều tài khoản, proxy cố định và điều kiện dừng
  otp.py       Thăm dò OTP, chỉ chọn mã mới sau mốc gửi
  falco.py     Báo cáo sự kiện hành vi và hiệu năng (tùy chọn)
  caa.py       Báo cáo các bước đăng ký (tùy chọn)
example_register.py        Ví dụ đầy đủ cho một tài khoản
example_batch.py           Ví dụ xử lý hàng loạt
config.example.json        Mẫu cấu hình
test_onboarding_smoke.py   Kiểm thử ngoại tuyến bộ phân tích trang khởi tạo
test_runner_smoke.py       Kiểm thử ngoại tuyến bộ điều phối với mạng giả lập
```

## Luồng giao thức

```text
GET  /                                    Lấy cookie ban đầu
POST /api/auth/native/restart             → 201 {csrf_token}
POST /api/auth/native/send-otp            → 201
POST /api/auth/native/confirm-otp         → 200 {registration_state:"completion_required",
                                                tos:{content_version}}
POST /api/auth/native/register-completion → 200 {auth_meta_session:{frl_access_token, frl_account_id}}
POST auth.meta.com/hatch/session/bootstrap/ → 302…→ muse.ai 200 HTML
     └ Phân tích disclosure_text/disclosure_version và trạng thái giới hạn khu vực
POST /api/hatch/accept-tos                → 200, dùng nội dung điều khoản do máy chủ trả về
GET  /api/hatch/invite                    → 200 nếu tài khoản có quyền truy cập
POST /api/hatch/vm/wake                   → 200, đánh thức VM trước khi đổi mã
POST /api/hatch/stateful-sharing          → 200
POST /api/hatch/invite-code/redeem        → 200 {redemptionStatus:"redeemed"}
POST /api/hatch/invite                    → 200 {code}, lấy mã mời của tài khoản
```

## Những điểm cần chú ý

### 1. `confirm-otp` phải có `supports_muse_link_transparency: true`

```json
{"otp_code":"123456","remember_device":true,"supports_muse_link_transparency":true}
```

### 2. Trường họ tên và ngày sinh của `register-completion`

```json
{
  "date_of_birth": "1993-11-14",
  "first_name": "Minh",
  "last_name": "Nguyen",
  "tos_content_version": "ntm_create_account:default_v1_meta_account_v3+docs_v2",
  "remember_device": true
}
```

`first_name` là **tên**, `last_name` là **họ**. Tác giả gốc ghi nhận HTTP 403 với ngày sinh chưa đủ khoảng 18 tuổi. Phiên bản điều khoản được lấy động từ `tos.content_version` của phản hồi `confirm-otp`; hằng số trong mã chỉ là giá trị dự phòng.

### 3. Body của `restart`

Yêu cầu có trường `resume`:

```json
{"resume": false}
```

### 4. Khởi tạo phiên trước khi gọi `accept-tos`

Sau khi đăng ký, phải gọi `POST https://auth.meta.com/hatch/session/bootstrap/` bằng form chỉ chứa `frl_access_token`. Client tự theo các chuyển hướng 301/302/303 đến trang HTML của muse.ai; bỏ bước này có thể khiến các API hatch tiếp theo trả về 403.

Trang đích chứa dữ liệu Next Flight với `disclosureText` và `disclosureVersion`. Hiện bộ phân tích chỉ hỗ trợ `HATCH_ROW_v0`. Body của `accept-tos` phải dùng đúng nội dung và phiên bản do máy chủ trả về; `Referer` là URL trang chứa nội dung đó. Client gọi một lần, không thử lại; khi gặp 403, thông báo lỗi kèm tối đa 200 ký tự đầu của phản hồi.

Nếu `resolvedDestination == "waitlist"` hoặc `isGeoGated == true`, chương trình báo `region_waitlist`: tài khoản đã đăng ký nhưng bị giới hạn khu vực, chưa xác nhận đã được đưa vào danh sách chờ.

### 5. Cần gọi `vm/wake` trước khi đổi mã

Theo ghi nhận của tác giả, bỏ qua bước đánh thức VM có thể khiến cả mã hợp lệ cũng bị báo `invalid`:

```json
{"success":false,"reason":"invalid","detail":"この招待コードは存在しません"}
```

`detail` là phản hồi nguyên gốc bằng tiếng Nhật, nghĩa là “Mã mời này không tồn tại”. Client lấy `vmId` từ trang đã đăng nhập:

```python
re.search(r'vmId[\\"]*:[\\"]*([0-9a-fA-F-]{36})', html)
```

Body của `wake` dùng `wake_trigger: "mount"` cho kết nối đầu tiên, `open_id` là UUID mới và `away_ms: 0`.

### 6. Ý nghĩa kết quả đổi mã

| Mã kết quả | Ý nghĩa |
|---|---|
| `redeemed` | Đổi mã thành công |
| `already_redeemed` | Tài khoản đã đổi một mã trước đó |
| `used_up` | Mã đã đạt giới hạn sử dụng; tác giả ghi nhận giới hạn 30 lượt |
| `invalid` | Mã không tồn tại hoặc chưa gọi `vm/wake` |

`POST /api/hatch/invite` lấy mã đã cấp cho tài khoản. Thao tác này không tương đương việc cào để hiện mã (`reveal`) trên giao diện.

## Cookie

Theo ghi nhận gốc, header phản hồi của `register-completion` cấp `hatch_sess` sau khi đăng ký thành công (khoảng 886 ký tự). Đây là thông tin xác thực cho các API hatch tiếp theo. `hatch_vml` bị xóa trong giai đoạn đăng ký (`Max-Age=0`) và không phải cookie bắt buộc.

## Xử lý hàng loạt

`example_batch.py` đọc `config.json`. Tham số số lượng là tùy chọn; mặc định **30**:

```powershell
.\.venv\Scripts\python.exe example_batch.py 3
```

Trên Linux / macOS, sau khi kích hoạt môi trường ảo, dùng `python example_batch.py 3`.

| Trường | Ý nghĩa |
|---|---|
| `otp_file` | Danh sách hộp thư, mỗi dòng `email----URL_nguon_OTP` |
| `proxy_file` | Danh sách proxy cố định, mỗi dòng `host:port:user:pass` hoặc `host:port`; chế độ hàng loạt yêu cầu danh sách này |
| `codes_file` | Danh sách mã mời, mỗi dòng một mã; nếu thiếu mã, tài khoản hiện tại được ghi nhận đang chờ đổi mã và cả đợt dừng |
| `output_dir` / `tried_file` | Thư mục JSON kết quả từng tài khoản / file email đã thử |
| `workers` / `max_per_ip` | Số luồng xử lý (mặc định 5) / số lượt xác minh thành công tối đa trên mỗi dòng proxy trước khi chuyển proxy (mặc định 6) |
| `resolve_ip` | Dùng ipify để xác định IP đầu ra; mặc định `true` |
| `send_caa` | Báo cáo các bước đăng ký; bộ điều phối mặc định `false`, mẫu cấu hình đặt `true` |

Ví dụ định dạng `otp-urls.txt`:

```text
ban@example.com----https://otp.example.com/mailbox
```

Nguồn OTP cần trả về một mảng JSON có dạng:

```json
[{"otp":"123456","time":"2026-11-17T03:00:30Z"}]
```

Thời gian phải theo ISO 8601 và có múi giờ. Bộ chọn chỉ nhận mã 6 chữ số có thời gian **sau** mốc gửi, chọn mã mới nhất và từ chối khi nhiều mã khác nhau có cùng thời điểm mới nhất. Thăm dò mặc định tối đa 45 giây, cách nhau 0,6 giây, mỗi yêu cầu có thời gian chờ 15 giây.

Quy tắc điều phối được giữ theo mã nguồn gốc:

- Mỗi worker giữ riêng một dòng proxy (`claim/release`). Khi cạn danh sách, bộ điều phối mới chia sẻ proxy và ghi nhật ký.
- `max_per_ip` đếm lượt xác minh thành công; đạt giới hạn thì nhả proxy và chọn dòng khác.
- Lỗi mạng ở giai đoạn **trước khi gửi OTP** (`initialized/bootstrap/restart`) được thử lại tối đa 3 lần với cùng email và proxy khác. Email vẫn được đánh dấu đã thử nếu tiếp tục thất bại.
- Máy chủ từ chối, trạng thái `pending` hoặc lỗi sau khi gửi OTP sẽ dừng cả đợt, không chuyển proxy hay lấy email bù.
- `region_waitlist` được lưu thành `registered_waitlist`; tài khoản đã đăng ký được giữ lại và cả đợt dừng.
- Giới hạn số lượng tính theo số email khác nhau đã nhận xử lý, không bù email thất bại.

Kết thúc, chương trình in JSON tổng kết với các trường `queued`, `started`, `remaining`, `ok`, `pending`, `server_rejected`, `transport_error`, `failed`, `ip_switches`, `stopped`, `stop_reason`.

Kết quả từng tài khoản nằm trong `output_dir/<email>.json`, gồm `email`, `status`, `stage`, `registered`, `own_code`, `own_code_status`, `reveal_status`, `is_revealed`, `ip`, `last_error` và `updated_at`. `frl_access_token` và `hatch_sess` chỉ tồn tại trong bộ nhớ, không được lưu vào các file kết quả này. Tên trường và mã trạng thái giữ nguyên để tương thích với công cụ đọc JSON.

## Báo cáo sự kiện

Frontend của trang gửi hai loại dữ liệu đo lường:

- **falco** (`POST /api/falco`): hiệu năng và tương tác; `machineId` cố định là `not_set`.
- **caa-events** (`POST /api/auth/caa-events`): các bước đăng ký, dùng cùng một `waterfall_id` xuyên suốt quy trình.

Theo nghiên cứu gốc, hai loại sự kiện này không quyết định kết quả đăng ký. Có thể tắt bằng cấu hình; `musepy/falco.py` và `musepy/caa.py` giữ phần triển khai tương ứng. Bộ điều phối hàng loạt chỉ dùng `send_caa`.

## Kiểm thử ngoại tuyến

Sau khi cài thư viện, chạy trên Windows:

```powershell
.\.venv\Scripts\python.exe test_onboarding_smoke.py
.\.venv\Scripts\python.exe test_runner_smoke.py
```

Trên Linux / macOS, dùng `python` trong môi trường ảo thay cho đường dẫn `.exe`. Hai bộ kiểm thử dùng dữ liệu và mạng giả lập, không đăng ký tài khoản thực.

## Điều kiện sử dụng

Theo tuyên bố của tác giả gốc, dự án chỉ dành cho học tập và nghiên cứu cá nhân, phi thương mại; không áp dụng giấy phép nguồn mở như MIT. Không được dùng cho mục đích thương mại hoặc phân phối lại. Khi sử dụng, cần tuân thủ điều khoản của dịch vụ và pháp luật địa phương. Bản Việt hóa giữ nguyên tuyên bố này.

Nhóm trao đổi của tác giả: [t.me/muihbb](https://t.me/muihbb).
