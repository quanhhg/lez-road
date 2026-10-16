# T2 - Hướng dẫn chạy cho 30 tuyến khảo sát

T2 đọc đúng bộ tuyến do báo cáo lựa chọn hiện hành chỉ tới. Không sinh/chọn lại tuyến, không gọi API và không tạo dữ liệu đo. Hướng dẫn giữ cả đoạn đi lặp và đối chiếu hash nguồn trước/sau khi xuất.

## Chạy từ notebook

Notebook 09 có mục **7. Hướng dẫn chạy 30 tuyến (T2)** để kiểm tra, xuất/tiếp tục và xem các điểm cần rà soát. Cell chỉ gọi module, không chứa logic dựng chỉ dẫn.

```python
from lez import route_instructions
check = route_instructions.preflight(WORK)
result = route_instructions.run(WORK, force=False)
print(result["route_count"], result["instruction_count"])
```

Chạy lại cùng cấu hình dùng bundle có hash hợp lệ. Muốn xem nhanh, mở `work/maps/route_instructions/index.html` bằng trình duyệt. Tệp là trang cục bộ, không yêu cầu máy chủ, Internet, bản đồ nền trực tuyến hoặc API key.

## Chạy riêng bằng Terminal

Từ folder work:

```bash
python3 scripts/lez/route_instructions.py check
python3 scripts/lez/route_instructions.py run
python3 scripts/lez/route_instructions.py status
```

Controller chạy bằng Python thường. Chỉ bước lấy hình học và đổi EPSG:3405 sang WGS84 dùng runtime PyQGIS đã đăng ký, giống phần xử lý chuyến đo. Không cài thư viện mới.

## Đầu vào và phiên bản

- `work/reports/selection/latest_selection_30.json`: báo cáo hiện hành và đường dẫn bộ dữ liệu.
- `selected_routes.csv`: mã tuyến, nhóm, chiều dài và thông tin tổng hợp.
- `selected_walks.json` và `selected_route_arcs.csv`: chuỗi cung chính xác, thứ tự và chiều đi.
- Graph và GeoPackage được chọn từ provenance của bộ tuyến; không lấy một mạng mới không liên quan thay cho mạng đã dùng để chọn tuyến.
- `work/config/route_instructions.json`: ngưỡng góc hình học, khoảng lấy hướng và sai số kiểm tra.

Nếu đã có snapshot khảo sát được khóa, bộ điều phối tự truyền `reports/field/latest_survey_revision.json`. Khi chạy riêng muốn dùng bộ đó, truyền rõ:

```python
result = route_instructions.run(
    WORK, selection_report="reports/field/latest_survey_revision.json"
)
```

Không dùng lẫn hướng dẫn của bộ đề xuất với phiên bản khảo sát mới. Mỗi tuyến có `route_version` và mã tập nguồn để đối chiếu.

## Các tệp đầu ra

Báo cáo ổn định: `work/reports/routes/latest_route_instructions.json`. Thư mục bản đồ dễ mở: `work/maps/route_instructions`, là liên kết tương đối tới bundle có phiên bản trong `work/data/processed/route_instructions`.

| Tệp | Nội dung |
|---|---|
| `index.html` | Danh sách, lọc A/B/C và liên kết của đủ 30 tuyến |
| `routes/A01.html`, tương tự các mã khác | Phiếu từng tuyến, bảng các bước, tọa độ, sơ đồ có hướng, chọn/highlight bước, in hoặc lưu PDF |
| `maps/A01.svg` | Sơ đồ tuyến có mũi tên, điểm bước, hướng Bắc và thước khoảng cách |
| `gpx/A01.gpx` | Chuỗi hình học WGS84 đầy đủ và các điểm chỉ dẫn |
| `gpx_30_routes.zip` | Gói 30 tệp GPX |
| `route_summary.csv` | Số bước, chiều dài, điểm đầu/cuối và số bước cần rà soát |
| `route_steps.csv` | Chỉ dẫn, góc chuyển hướng, khoảng cách lũy kế, tọa độ và cung nguồn của từng bước |
| `route_arcs.csv` | Toàn bộ lượt đi qua cung, giữ thứ tự, chiều đi và tên OSM |
| `review_points.csv` | Điểm thiếu tên, nhiều cung ra, vòng xuyến, chuyển hướng gấp, quay đầu và điểm đầu/cuối |
| `route_instructions.json` | Dữ liệu đầy đủ để tái kiểm tra hoặc xuất định dạng khác |
| `qa.json`, `manifest.json` | Kiểm tra hình học, nguồn, hash và tính hoàn chỉnh |

Đọc đường dẫn từ trường `paths` trong báo cáo, không chép cứng tên thư mục hash.

## Hiểu đúng chỉ dẫn

Góc chuyển hướng được tính trên các đoạn hình học gần nút; các ngưỡng là lựa chọn kỹ thuật có cấu hình. Đi thẳng/chếch/rẽ không tự xác nhận biển báo hoặc làn đường ngoài thực địa. Số cung ra dùng để đánh dấu bảo thủ các nút cần đối chiếu, không khẳng định mọi nhánh đều được phép đi.

Đường không có tên được ghi “Đoạn chưa có tên OSM” kèm mã way. Vòng xuyến không tự gán số thứ tự lối ra. Điểm bắt đầu/kết thúc không tự được coi là chỗ dừng an toàn.

Các mục trong `review_points.csv` là nội dung cần rà soát, **không phải danh sách lỗi khiến tuyến thất bại**. Trạng thái thành công của việc xuất là `exported_pending_field_review`; `structural_validation=passed` tách riêng với `field_verified=false`.

GPX dùng chuẩn 1.1 và WGS84; chứa tuyến dự kiến từ OSM, không gán thời gian đo cho các điểm. Một số ứng dụng có thể tự tính lại tuyến nếu nhập như tuyến điều hướng; cần đối chiếu và giữ vệt đầy đủ để tránh thay lộ trình nghiên cứu. Chuẩn định dạng: [GPX 1.1](https://www.topografix.com/GPX/1/1/).

## Kiểm tra và tiếp tục

- Đủ mã tuyến, không trùng mã, không thiếu chuỗi cung.
- Chuỗi trong CSV, walk và hình học cùng thứ tự, cùng chiều và chiều dài.
- Kiểm liên thông và hạn chế rẽ bằng graph nguồn trước khi dựng hướng dẫn.
- Tổng chiều dài bước khớp tuyến; mỗi lượt đi qua cung thuộc đúng một bước.
- Tọa độ sau chuyển đổi được đối chiếu với tọa độ node nguồn.
- Ghi qua thư mục tạm rồi công bố; Ctrl+C giữ bản đã hoàn chỉnh trước đó.
- Cache thiếu hoặc sai hash bị từ chối; không ghi đè âm thầm bundle hỏng. Giữ bản đó để kiểm tra/khôi phục trước khi chạy lại.
- `force=True` vẫn không ghi đè bundle bất biến có nội dung hợp lệ.

Mã nguồn, cấu hình, tài liệu và kiểm thử được quản lý bằng Git. Kết quả sinh trong data/reports/maps tiếp tục theo quy tắc bỏ qua dữ liệu lớn của dự án. Chạy T2 sau khi khôi phục dữ liệu khi clone sang máy khác.

## Kiểm thử khi sửa T2

Từ folder work, có thể chạy các kiểm thử Python của T2, bộ điều phối và xử lý chuyến đo. Kiểm thử logic giao diện dùng Node.js có sẵn nếu muốn chạy; không yêu cầu framework hoặc cài thư viện.

    PYTHONPATH=scripts:tests/lez python3 -m unittest test_route_instructions test_project_automation test_trip_processing
    node tests/lez/test_route_instructions_ui.js

Kiểm thử JavaScript dùng các đối tượng DOM nhỏ để kiểm logic chọn bước, chuyển bước, zoom/reset, in và lọc vùng. Nó không thay cho kiểm tra hiển thị bằng trình duyệt thật. Dữ liệu SVG có thể kết xuất độc lập để kiểm tra sơ đồ; trang HTML vẫn nên được người dùng mở và đọc trước khi xuất bản.
