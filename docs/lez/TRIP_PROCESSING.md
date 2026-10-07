# Nhập chuyến, kiểm tra GPS và tính chỉ tiêu vận hành

Module này chuẩn bị và xử lý dữ liệu đo khi có tệp thực tế. Với thư mục đầu vào trống hoặc chỉ có dòng tiêu đề, kết quả là `awaiting_measurements`; không sinh chuyến thực hay điền giá trị tốc độ giả vào dữ liệu thực. Không có bước tách microtrip hoặc xây dựng chu trình lái.

Các lệnh sau chạy bằng Python thường. Module chỉ gọi kernel PyQGIS đã đăng ký để đọc hình học nguồn và đổi hệ tọa độ; không cài thư viện hay tải OSM mới.

```sh
cd work
python3 scripts/lez/trip_processing.py preflight --project .
python3 scripts/lez/trip_processing.py prepare --project .
python3 scripts/lez/trip_processing.py run --project .
python3 scripts/lez/trip_processing.py status --project .
```

`prepare` kiểm tra từng cung và chỗ chuyển cung của đúng graph nguồn, chiều di chuyển, điểm đầu/cuối và chiều dài hình học. GeoPackage được đọc qua bản sao tạm; bản gốc không bị sửa metadata. Cache thay đổi khi graph, hình học tuyến hoặc code thay đổi.

## Hai tệp đầu vào

Đặt `trips.csv` và `gps_points.csv` trong `data/measurements/incoming`. Có thể dùng `--input-dir` để chọn thư mục khác. File CSV dùng UTF-8; có thể có UTF-8 BOM. Ngưỡng, đơn vị và trường bắt buộc được lưu trong `config/trip_processing.json`.

| Tệp | Một dòng là | Trường chính |
|---|---|---|
| `trips.csv` | Một chuyến | `trip_id`, `route_id`, `vehicle_id`, `driver_id`, `started_at`, `ended_at`, `time_block`, `measurement_date`, `sampling_zone`, `lez_status_at_measurement`, `policy_version`, `route_version`, `source_bundle_sha256` |
| `gps_points.csv` | Một thời điểm | `trip_id`, `timestamp`, `latitude`, `longitude`, `speed`, `speed_unit`; tùy chọn `gps_accuracy_m` |

Thời gian là ISO 8601 có múi giờ, ví dụ `2026-10-06T08:00:00+07:00`. Ngày đo được đối chiếu theo `Asia/Ho_Chi_Minh`. Tọa độ là WGS84, độ; không đưa tọa độ mét vào hai cột latitude/longitude. Tốc độ chấp nhận `km/h`, `kmh`, `kph` hoặc `m/s`; giá trị chuẩn hóa xuất ra theo km/h.

`preflight` xuất `route_contracts`: phiên bản và mã nguồn của từng tuyến đang được chọn. `route_version` kiểm soát đúng thứ tự cung, graph, hình học, vùng và policy; `source_bundle_sha256` kiểm soát tập nguồn. Khi mã A01/B01/C01 được dùng lại với hình học mới, chuyến gắn phiên bản cũ sẽ có cờ lỗi và không được tính như chuyến của tuyến mới. Giữ phiên bản đúng từ biểu mẫu chiến dịch; không sửa hash của một chuyến cũ để làm mất lỗi.

`sampling_zone` và `policy_version` mô tả thiết kế nghiên cứu. `lez_status_at_measurement` ghi riêng trạng thái được xác minh tại thời điểm đo; dùng `unknown` khi chưa xác minh. Phân vùng A/B/C không tự xác nhận việc thực thi hạn chế phương tiện.

## Lưu dữ liệu và lỗi

Mỗi lần nhập lưu bản sao nguyên byte và SHA256 trong `data/raw/measurements/real/<hash>`. Đầu ra nằm trong `data/processed/trip_processing/real/<hash>`, gồm:

- `trips_qc.json`: metadata và cờ lỗi từng dòng chuyến.
- `points_qc.json`: từng dòng GPS/tốc độ, giá trị chuẩn hóa, tính hợp lệ riêng cho GPS/tốc độ và kết quả ghép tuyến.
- `operating_metrics.json`, `operating_metrics.csv`: chỉ tiêu từng chuyến cùng mẫu số thời gian hợp lệ.
- `qa.json`, `manifest.json`: nguồn, hash, ngưỡng, số dòng, trạng thái và kiểm tra toàn vẹn.

Không xóa hoặc sắp xếp ngầm dòng lỗi. Trùng thời gian, thời gian giảm, tọa độ sai, đơn vị sai, tốc độ bất thường, GPS nhảy, độ chính xác thấp và khoảng cách thời gian lớn đều có cờ. CSV không thể phân tích vẫn giữ bản byte gốc và lỗi schema. Thư mục phiên bản chỉ được công bố khi mọi đầu ra đã ghi xong; cache lỗi bị từ chối, không ghi đè. Thay đổi đầu vào/config/source tạo phiên bản mới.

GPS và tốc độ được đánh giá độc lập: GPS nhảy không tự làm mất tốc độ hợp lệ từ thiết bị. Khoảng trống dài hơn 5 giây không được nối để tích phân; điểm sau khoảng trống có thể bắt đầu một đoạn hợp lệ mới. Không nội suy khoảng trống. Ngưỡng mặc định là lựa chọn kỹ thuật cần hiệu chỉnh theo thiết bị, không phải thông số đã đo ở Hà Nội.

## Ghép GPS vào tuyến

Tọa độ được đổi sang EPSG:3405. Các đoạn ứng viên thuộc đúng thứ tự cung có hướng của tuyến dự kiến. Bộ ghép dùng bán kính 40 m, tối đa 12 ứng viên, hướng chuyển động khi dịch chuyển GPS từ 5 m và liên tục theo vị trí dọc tuyến. Những cung nguồn được kiểm tra hạn chế rẽ trước khi tạo cache.

Trạng thái gồm `matched`, `ambiguous`, `opposite_direction`, `off_route`, `continuity_unresolved`, `unknown_bad_gps`. Điểm đứng yên hoặc điểm đầu có `heading_unknown`. Nhiều vị trí dọc tuyến phù hợp hoặc quá giới hạn ứng viên được ghi mơ hồ. Chỉ số `match_confidence` là độ phù hợp hình học từ 0 đến 1; không phải xác suất đã hiệu chỉnh.

Đây là bộ ghép giới hạn trong hành lang kế hoạch. Nó không tìm một tuyến thay thế toàn mạng nếu xe chạy lệch. Điểm mơ hồ, sai chiều hoặc GPS không sử dụng được không đóng góp chiều dài ghép tuyến. Khoảng cách hình học cũng không xác minh quyền xe máy, biển báo, công trình hay an toàn dừng xe.

## Chỉ tiêu và mẫu số

`declared_duration_s` là thời gian kết thúc trừ bắt đầu chuyến. `speed_valid_duration_s` là tổng các khoảng thời gian đủ dữ liệu tốc độ; `gps_valid_duration_s` được tính riêng. Tỷ lệ bao phủ bằng thời gian hợp lệ chia thời gian khai báo. Chuyến chỉ có 1 giây hợp lệ trong 60 giây có tỷ lệ 1/60, dù tốc độ trung bình trên giây đó có thể tính được.

Với hai điểm liên tiếp hợp lệ, tốc độ khoảng bằng trung bình hai tốc độ đầu/cuối; quãng đường tốc độ bằng tốc độ khoảng đổi sang m/s nhân thời gian. Tốc độ trung bình dùng quãng đường tích phân chia thời gian tốc độ hợp lệ. Khoảng có tốc độ trung bình ≤1 km/h là idle; khoảng còn lại là moving. Tốc độ moving loại phần quãng đường idle và chia thời gian moving.

Gia tốc bằng chênh lệch tốc độ m/s chia thời gian s. Khi moving: gia tốc >0,1 m/s² là tăng tốc; <−0,1 là giảm tốc; khoảng ở giữa là cruise. Thời gian idle + moving bằng thời gian tốc độ hợp lệ; tăng tốc + giảm tốc + cruise bằng moving. Gia tốc vượt 8 m/s² bị gắn lỗi và loại khỏi khoảng tích phân. Trung bình gia tốc/giảm tốc là trung bình các khoảng tương ứng, có đơn vị m/s²; không phải gia tốc của toàn chuyến.

Khoảng cách GPS dùng khoảng cách cầu giữa điểm hợp lệ; xuất riêng với quãng đường tích phân tốc độ. Khoảng cách ghép tuyến dùng chênh lệch vị trí dọc tuyến khi hai điểm đều ghép rõ và tiến theo hướng. Không trộn ba nguồn khoảng cách.

## Kiểm thử riêng

```sh
python3 -m unittest discover -s tests/lez -p 'test_trip_processing.py' -v
python3 scripts/lez/trip_processing.py generate-demo --project .
python3 scripts/lez/trip_processing.py run --project . \
  --input-dir tests/fixtures/trip_processing_demo --demo
python3 scripts/lez/trip_processing.py status --project . --demo
```

Demo tạo đúng 31 điểm với tốc độ tùy ý 10 m/s trên hình học tuyến hiện tại để kiểm tra CSV/đổi hệ tọa độ/chiều ghép. Nó không mô phỏng giao thông hay đại diện vận hành Hà Nội. `is_test_data=true`; lưu raw/processed/report ở nhánh `demo` riêng. Thư mục fixtures/demo bị từ chối nếu không có `--demo`. Sinh lại fixture khi phiên bản tuyến thay đổi, vì fixture cũ phải bị chặn bởi hash phiên bản.

API Python: `preflight(project, config, input_dir)`, `prepare(project, config, output_root)`, `run(project, config, input_dir, output_root, demo=False)`, `status(project, output_root, demo=False)`. Khi chạy kiểm tra ở workspace khác, `output_root` giữ mọi ghi dữ liệu trong workspace đó; project nguồn chỉ được đọc.

Bộ điều phối chuyển sang `selection_report` của snapshot khảo sát kỹ thuật khi đã đủ điều kiện. Khi dùng module riêng, truyền config có `selection_report` nếu muốn đọc snapshot đó; mặc định dùng bộ 30 đề xuất.

`operating_summary.json/csv` tổng hợp mô tả theo tuyến, A/B/C và khung giờ: tốc độ bằng tổng quãng đường tích phân chia tổng thời gian tốc độ hợp lệ; coverage dùng toàn thời gian khai báo của chuyến có metadata hợp lệ. Dòng metadata lỗi bị loại khỏi tổng. Không lấy trung bình giản đơn các tốc độ chuyến hoặc gọi kết quả là trung bình đại diện toàn Hà Nội.
