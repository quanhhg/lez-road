# T5 - Chỉ tiêu vận hành từ chuỗi thời gian và tốc độ

T5 đã có mã để tính RPA, PKE và phân bố tốc độ–gia tốc (SAFD), nối với phần nhập/kiểm tra chuyến hiện có. Module tính toán là `work/scripts/lez/operating_metrics.py`; `trip_processing.py` gọi module này khi xử lý chuyến. Không cần cài thư viện mới hoặc nhập QGIS để tính các công thức. Chỉ phần lấy hình học và đổi tọa độ trong quy trình GPS dùng worker PyQGIS như trước.

## 1. Cần bổ sung thông tin nào?

Để viết và kiểm tra công thức, chưa cần thêm số đo. Để có **kết quả vận hành thực**, cần điền các chuyến và chuỗi thời gian–tốc độ của thiết bị vào `trips.csv`, `gps_points.csv`, theo [hướng dẫn nhập chuyến](TRIP_PROCESSING.md). Thời gian cần có múi giờ; tốc độ cần ghi đúng đơn vị. GPS, mã thiết bị, tuyến, hướng chạy, phiên bản nguồn và các điều kiện T3 dùng để kiểm tra bối cảnh của chuyến.

Không lấy tốc độ giới hạn OSM làm tốc độ vận hành. Các định nghĩa RPA/PKE đang dùng không cần khối lượng xe; PKE ở đây là một chỉ số động học chia theo quãng đường, không phải năng lượng thực tính bằng joule.

Trước khi dùng kết quả trong kết luận nghiên cứu, cần chốt các lựa chọn phương pháp: cách xử lý nhiễu, ngưỡng kiểm tra, ngưỡng gia tốc dương và lưới SAFD. Các lựa chọn hiện được ghi rõ là **đề xuất có phiên bản**, không tự coi là đã được tài liệu hoặc thực địa xác nhận. Không cần đợi chốt toàn bộ T1 mới có thể kiểm tra phần mềm.

## 2. Phạm vi dữ liệu được tính

Một khoảng là hai bản ghi tốc độ liên tiếp của cùng chuyến. Chỉ dùng khoảng đã qua kiểm tra, đủ hai tốc độ, thời gian tăng, không vượt khoảng trống cho phép và không có gia tốc bất thường. GPS lỗi không tự làm mất kênh tốc độ độc lập còn hợp lệ; chiều dài ghép GPS và chiều dài tích phân tốc độ vẫn xuất riêng.

Giả định tốc độ thay đổi tuyến tính **bên trong khoảng hợp lệ**, gia tốc không đổi trên khoảng đó. Không nối khoảng trống, không nội suy vào khoảng bị loại, không tự làm trơn hoặc sửa dữ liệu gốc. Mỗi khoảng dùng/loại có nhật ký, giá trị và lý do trong `kinematic_intervals.csv`.

Đơn vị bên trong: tốc độ m/s, thời gian s, gia tốc m/s², chiều dài m. Đầu vào km/h được chia 3,6. Với một khoảng:

```text
dt = thời gian cuối - thời gian đầu
a  = (v1 - v0) / dt
d  = ((v0 + v1) / 2) × dt
D  = tổng d của cùng các khoảng hợp lệ
```

Mẫu số quãng đường RPA và PKE là **D tính từ tốc độ trên các khoảng đó**. Không thay bằng chiều dài tuyến dự kiến, chiều dài GPS hay tổng hành trình kể cả phần thiếu số liệu.

## 3. Công thức RPA và PKE

RPA mô tả cường độ tăng tốc dương tương đối. Cách tích phân theo khoảng của dự án:

```text
RPA = tổng [((v0 + v1)/2) × a × dt, nếu a > ngưỡng dương] / D
```

Ngưỡng dương mặc định bằng 0 m/s². Đây là tham số riêng, không phải ngưỡng 0,1 m/s² dùng phân chia tăng tốc/giảm tốc/chạy đều của phần xử lý hiện có.

PKE dùng dạng không có hệ số một nửa:

```text
PKE = tổng max(v1² - v0², 0) / D
```

Cả hai xuất theo m/s² với tốc độ đã đổi sang m/s. Nếu D bằng 0 hoặc nhỏ hơn ngưỡng kỹ thuật `distance_epsilon_m`, kết quả là `null`, không phải 0. Chạy đều với quãng đường dương cho RPA = PKE = 0; đứng yên có D = 0 cho hai tỷ số chưa xác định.

**Quan hệ phụ thuộc:** khi ngưỡng dương bằng 0 và dùng cùng mô hình khoảng tuyến tính, PKE = 2 × RPA. Đây là hệ quả đại số của cách tính, không phải hai phép đo độc lập. T6 sau này cần tránh đếm chúng thành hai bằng chứng độc lập hoặc gán trọng số trùng mà không giải thích.

Ví dụ tính tay: tốc độ ở giây 0/2/4/6 lần lượt là 0/2/2/0 m/s. Ba khoảng dài 2 giây cho D = 2 + 4 + 2 = 8 m; tử số RPA = 2 m²/s²; tử số PKE = 4 m²/s². Kết quả RPA = 0,25 m/s² và PKE = 0,50 m/s².

## 4. SAFD: phân bố đồng thời tốc độ và gia tốc

Lưới mặc định đề xuất:

- Tốc độ: 0–180 km/h, bước 5 km/h.
- Gia tốc: −8 đến +8 m/s², bước 0,5 m/s².
- Khoảng nhóm dạng `[cận dưới, cận trên)`; nhóm cuối nhận cả cận trên cuối cùng. Giá trị nằm đúng một biên chỉ thuộc một nhóm.

Với mỗi khoảng hợp lệ, tính thời gian nằm trong từng nhóm tốc độ–gia tốc. Nếu tốc độ đi qua nhiều nhóm, chia thời gian ở đúng các biên nhóm theo giả định tuyến tính; không dồn toàn bộ thời gian vào tốc độ trung bình. Gia tốc của khoảng giữ cố định.

```text
Tỷ trọng ô SAFD = thời gian thuộc ô / tổng thời gian tốc độ hợp lệ
```

Dùng thời gian, không dùng số điểm, nên các lần lấy mẫu cách nhau 1 giây và 3 giây không có trọng số bằng nhau. Khoảng đứng yên hợp lệ vẫn đóng góp thời gian vào ô tốc độ 0, gia tốc 0.

Nếu lưới được sửa hẹp hơn miền dữ liệu, thời gian ngoài lưới được ghi riêng. Không ép vào ô biên hoặc chuẩn hóa lại phần còn lại thành 100%. Vì vậy tổng tỷ trọng trong lưới có thể nhỏ hơn 1. Không có khoảng hợp lệ thì tỷ trọng chưa xác định.

Bảng được lưu dạng thưa: chỉ xuất các ô có thời gian dương. Ô không có dòng được hiểu là 0 **chỉ khi mẫu số thời gian của chuyến/nhóm dương**. Khi chưa có dữ liệu, không dùng bảng trống để kết luận tần suất bằng 0.

## 5. Tổng hợp theo tuyến, vùng, khung giờ và loại ngày

Các bảng tổng hợp gồm toàn bộ dữ liệu mô tả, từng tuyến, vùng A/B/C, khung giờ, vùng × khung giờ và các tổ hợp có loại ngày. Nhãn `pilot`, `main` và `unknown` được giữ tách riêng trong mọi nhóm. Chuyến có thông tin phiên bản không hợp lệ không được đưa vào tổng.

- RPA nhóm = tổng tử số RPA / tổng D; PKE tương tự.
- SAFD nhóm = cộng thời gian từng ô / tổng thời gian hợp lệ; không lấy trung bình tỷ trọng của các chuyến.
- Gia tốc dương/âm trung bình được lấy theo trọng số thời gian của những khoảng tương ứng, kể cả khi khoảng lấy mẫu không đều. Dấu âm của giảm tốc được giữ nguyên.
- Tốc độ trung bình và tỷ lệ thời gian hợp lệ tiếp tục dùng mẫu số đã công bố trong phần xử lý chuyến. Không gọi trung bình trên phần dữ liệu hợp lệ là tốc độ của toàn bộ thời gian bị thiếu.

Các kết quả này là mô tả dữ liệu đã thu được; không tự trở thành trung bình đại diện toàn Hà Nội. T3 vẫn kiểm tra độ đầy đủ thông tin/lịch; T6 vẫn cần quy tắc riêng về mức đủ dữ liệu.

## 6. Cấu hình, chạy và kết quả

Cấu hình: `work/config/trip_processing.json`, phần `operating_metrics`. Phiên bản hiện hành: `T5_linear_interval_SI_v1`, trạng thái `proposed`. Sửa lưới/ngưỡng sẽ tạo phiên bản kết quả xử lý mới; dùng lại bản lưu byte gốc đã kiểm hash. Thay định nghĩa PKE hoặc mô hình khoảng phải triển khai một phiên bản thuật toán rõ ràng; không chỉ đổi nhãn trong cấu hình.

Trong folder `work`:

```bash
python3 scripts/lez/trip_processing.py run --project .
python3 scripts/lez/operating_metrics.py self-check --work . --report reports/trips/t5_self_check.json
```

Notebook 08 có phần T5 sau bảng chỉ tiêu. Notebook 09 mục 9 chạy riêng T5, xem bảng kết quả và kiểm tra công thức bằng các ví dụ giả. Mục 2 notebook 09 tự tính T5 trong bước `real_trip_qc`, rồi cập nhật bảng T3. Khi cập nhật mã trong notebook đang mở, khởi động lại kernel và chạy từ cell thiết lập.

Khi đầu vào thực trống, `latest_real.json` giữ `awaiting_measurements`, số chuyến/điểm bằng 0, không sinh giá trị RPA/PKE hay ma trận SAFD giả. Báo cáo kiểm tra công thức có `is_test_data=true`, tách khỏi dữ liệu thực.

Khi có dữ liệu, bundle xử lý ngoài các tệp cũ còn có:

| Tệp | Nội dung |
|---|---|
| `operating_metrics.csv/json` | Chỉ tiêu từng chuyến, RPA/PKE, tử số, mẫu số, thời gian ngoài lưới và phiên bản. |
| `operating_summary.csv/json` | Tổng hợp có trọng số theo nhóm, tách giai đoạn đo. |
| `safd_by_trip.csv/json` | Các ô SAFD có thời gian dương theo chuyến. |
| `safd_by_group.csv/json` | SAFD gộp theo cùng các nhóm tổng hợp. |
| `kinematic_intervals.csv` | Từng khoảng dùng/loại, dòng nguồn, thời gian, tốc độ, gia tốc và lý do. |
| `operating_protocol.json` | Công thức, đơn vị, lưới, giả định, nguồn và quy tắc thiếu dữ liệu. |

Các tệp nằm trong cùng manifest/hash bất biến. Tệp thiếu/hỏng không được dùng như cache hoàn chỉnh. Bản OSM, bộ 30 và nguồn đo không bị sửa để tính các chỉ tiêu này.

## 7. Căn cứ và phần lựa chọn của dự án

- [TRL PPR354, A Reference Book of Driving Cycles, Version 3](https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/4247/ppr-354.pdf): Phụ lục B, phần chỉ tiêu động học (Dynamics oriented), hai mục RPA/PKE. Dùng để đối chiếu ý nghĩa RPA/PKE. Cách tính SI và tích phân tuyến tính của dự án được ghi riêng; không khẳng định sao chép mọi cách rời rạc hóa hoặc giá trị số trong bảng của TRL.
- [Nguyen và cộng sự (2022)](https://doi.org/10.47869/tcsj.73.4.6): bảng 2–3, trang 417–419, cung cấp các chỉ tiêu vận hành xe máy Hà Nội, gồm PKE. Nguồn hỗ trợ định nghĩa; không tự xác nhận bộ tuyến hoặc lưới SAFD của dự án.
- Yêu cầu bổ sung SAFD đến từ tài liệu phương pháp và kế hoạch T5 đã trao đổi. Lưới 5 km/h × 0,5 m/s², cách phân bổ thời gian theo khoảng và ngưỡng kỹ thuật nhỏ được gắn nhãn lựa chọn dự án. Không gán những chi tiết này cho toàn văn Nguyen (2024) khi chưa kiểm chứng được toàn văn.

T5 không kiểm tra hội tụ, không xác nhận đã đo đủ và không xây dựng chu trình lái.
