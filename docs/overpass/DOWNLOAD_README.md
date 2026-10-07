# Bộ tải Overpass tuần tự

Dữ liệu/trạng thái/truy vấn: `work/data/hanoi_tiles`. Mã nguồn: `work/scripts/overpass`. Báo cáo/nhật ký lượt chạy: `work/reports/overpass`. Bản đồ: `work/maps/hanoi_tiles`. Các đường dẫn báo cáo dưới đây tính từ `reports/overpass`.

Notebook làm việc: `work/notebooks/1_download_osm.ipynb`. Các cell đọc CSV, xem bản đồ và chọn ô được giữ; đường dẫn đã cập nhật theo cấu trúc work. Phần tải dùng `download_tiles.py`, `requests` và thư viện chuẩn; không import QGIS và không cài thêm thư viện.

## Chạy và tiếp tục trong notebook

1. Chạy các cell chuẩn bị và cấu hình `OPTIONS`. Giữ `ENABLE_PYQGIS=False` khi dùng kernel Python thường.
2. Cell **Kiểm tra cấu hình và xem tiến độ** không gửi API. Endpoint, snapshot, query và thư mục kết quả đều lấy từ dữ liệu dự án.
3. Cell **Chạy tải tất cả các ô đang hoạt động** gọi `downloader.run_download(ROOT, options=OPTIONS)`. Một Session gửi tuần tự, nghỉ ít nhất 15 giây giữa các POST mặc định; tối đa 3 lần thử mỗi ô mỗi lượt.
4. Khi muốn dừng, dùng Interrupt/Ctrl+C. Chạy lại cell tải để tiếp tục, hoặc đặt `RESUME_NOW=True` rồi chạy cell tiếp tục. Chỉ cache đúng query/snapshot/endpoint, hash khớp và kiểm tra phản hồi đạt mới được bỏ qua.
5. Cell tổng kết hiển thị pending/done/failed/heavy, lỗi từng ô, số ô tải mới/đọc cache và thời gian xử lý.

Không chạy hai bộ tải cùng dự án. Module giữ khóa `.tile_project.lock`; `verify/split` cũng dùng khóa này. Ô split không gửi request. Bộ tải không sửa bbox, query, hình học hoặc tự chia ô.

Nếu terminal đang ở thư mục chứa `work`, dùng các lệnh sau:

```bash
python3 work/scripts/overpass/download_tiles.py check
python3 work/scripts/overpass/download_tiles.py run
python3 work/scripts/overpass/download_tiles.py status
```

## Dữ liệu và tiến độ

- Mỗi `response_dir` có `response.json` giữ nguyên byte JSON nhận được và `manifest.json` ghi nhận ô/bbox/snapshot/endpoint/thời điểm/hash/counts/kiểm tra. Tệp được ghi qua tên tạm và đổi tên. Cache cũ cần thay được lưu nguyên trạng trong `archive/`.
- `errors.jsonl` và `errors/*.body` trong thư mục ô lưu lỗi và phản hồi lỗi riêng. Không dùng phản hồi lỗi làm dữ liệu hoàn chỉnh.
- `tiles.csv` và `tiles_history.json` được cập nhật sau mỗi ô. Giao dịch `.tile_state_transaction.json` khôi phục hai tệp nếu quá trình bị ngắt giữa hai lần đổi tên. Không sửa một tệp riêng lẻ trong lúc tải.
- `runs/<run_id>.events.jsonl` ghi tiến trình. `runs/<run_id>.json` và `latest_run.json` ghi tổng kết. Số tải mới/đọc cache là số của từng lượt, không phải số cộng dồn toàn dự án.
- `download_summary.json` tổng hợp các lượt đã chạy; `completion_audit.json` kiểm tra cache, CSV/lịch sử và hash hình học/query; `download_issues.csv` liệt kê ô cần xử lý. Đây là báo cáo tại thời điểm kiểm tra. `http_requests` trong từng lượt đếm số lần gọi POST, gồm thử lại; GET `/api/status` không nằm trong số này.
- `download_cooldown.json` lưu thời điểm sớm nhất được gửi tiếp khi server yêu cầu đợi; vẫn được tôn trọng sau khi dừng và tiếp tục.
- Trạng thái trong CSV/lịch sử là nguồn tiến độ tải. Trường status trong lớp GIS xuất trước đó không tự cập nhật trong bước HTTP; hình học các lớp được giữ nguyên.

## Lỗi và kiểm tra

429: đợi ít nhất Retry-After (giây hoặc HTTP-date), thời điểm slot trong `/api/status` và backoff; không đổi endpoint. 504 hoặc remark timeout/quá tải: thử hữu hạn, vẫn lỗi thì heavy. Lỗi mạng/5xx tạm thời: backoff tăng dần với jitter. Lỗi cú pháp không thử lại vô hạn. Một lỗi API ở một ô không xóa kết quả các ô khác.

Trước done, module kiểm tra JSON/count/ID theo loại/node coordinates/way nodes/relation members/version/timestamps/snapshot và không có remark lỗi. Kết quả hợp lệ không có way mang highway vẫn là done, kèm `empty_road_result=true`.

Ô heavy cần đọc last_error/errors.jsonl. Với 504 ghi máy chủ quá bận (`Dispatcher_Client` timeout), chờ server ổn định rồi chạy lại cell tải trước khi quyết định chia ô. Nếu truy vấn vẫn vượt thời gian/bộ nhớ khi server hoạt động bình thường, xem xét split bằng PyQGIS sau khi dừng tải và tải các ô con. Ô failed cần sửa lỗi cấu hình hoặc đợi server/mạng rồi tiếp tục. Không chia ô chỉ vì 429; bộ tải HTTP không tự chia ô.

Kiểm tra offline từ thư mục chứa `work`:

```bash
python3 work/tests/overpass/test_download_tiles.py
```

Các kiểm tra dùng HTTP giả lập; không gửi API. Báo cáo kiểm tra notebook là `notebook_download_checks.json`; kiểm tra phối hợp với PyQGIS trên bản sao tạm là `geometry_integration_checks.json`.

Nguồn kỹ thuật: [Overpass — Commons](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html), [Overpass — Geometries](https://dev.overpass-api.de/overpass-doc/en/full_data/osm_types.html), [Requests — Quickstart](https://requests.readthedocs.io/en/latest/user/quickstart/).

`qa_report.json` ghi kiểm tra lưới lúc tạo ô; tiến độ và số request HTTP hiện tại nằm trong `latest_run.json`, không lấy từ báo cáo lưới. Khoảng nghỉ mặc định được tăng từ 5 lên 15 giây sau khi quan sát nhiều lỗi 429 trên server.
