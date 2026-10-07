# Dự án tuyến xe máy Hà Nội theo LEZ

Thiết kế hiện hành: **60 ứng viên A20/B20/C20**, chọn **30 đề xuất A10/B8/C12 = 18 trong/12 ngoài LEZ 2030**. Lấy LEZ làm mốc trước; không dịch chuyển ranh giới theo dân cư để đủ quota.

- A: khu vực thí điểm LEZ **2027 KV1/KV2/KV3 tại Hoàn Kiếm/Cửa Nam**, nằm trong Vành đai 1.
- B: phần LEZ **2030 trong Vành đai 3 trừ A**, gồm phần Vành đai 1 còn lại và phần mở rộng Vành đai 2–3.
- C: phần Hà Nội ngoài phạm vi LEZ 2030.

Theo Quyết định 3273, toàn bộ Vành đai 1 thuộc giai đoạn 2028–2029; không gọi toàn bộ Vành đai 1 là LEZ 2027. Xem cấu hình nguồn, ngày, hash và dải bất định tại `work/config/lez_policy.json`. Hình học dựng từ OSM là proxy kỹ thuật, chưa được xác minh là GIS pháp lý.

Mở [work/notebooks/09_automate_project.ipynb](notebooks/09_automate_project.ipynb), chạy cell kiểm tra rồi cell chạy toàn bộ. Chạy lại cùng cell để tiếp tục; `force=False` dùng cache có hash hợp lệ. Bộ điều phối tự chạy độ nhạy mở rộng sau bước chọn 30, rồi tiếp tục đến kiểm tra chuyến đo và chỉ tiêu vận hành; **không xây chu trình lái**.

| Folder trong work | Nội dung |
|---|---|
| `notebooks` | Notebook 01–09, logic chính ở module |
| `scripts/overpass` | HTTP tải OSM, không cần import QGIS |
| `scripts/lez` | Ranh giới, graph, ma trận tuyến, chấm điểm, thực địa và GPS |
| `config` | Mốc LEZ, snapshot, quota, trọng số, đơn vị và ngưỡng |
| `data/hanoi_tiles` | Nguồn OSM theo ô, query, response và manifest |
| `data/raw` | Tài liệu nguồn và bản byte dữ liệu đo được nhập |
| `data/processed` | Bundle dẫn xuất có phiên bản/hash |
| `data/measurements/incoming` | CSV thực tế chờ nhập |
| `reports`, `maps/routes` | Tiến độ/QA và bản đồ 30/60 có tên đường |
| `tests`, `docs`, `backups` | Kiểm thử, hướng dẫn và bản trước thay đổi |

Notebook 03 xem LEZ 2027/2030; 04 quản lý mạng; 05 sinh 60; 06 chọn 30; [07](notebooks/07_field_workflow.ipynb) quản lý bằng chứng và cập nhật; [08](notebooks/08_process_measurements.ipynb) kiểm tra chuyến; 09 điều phối tất cả. Python thường chạy controller, worker GIS dùng runtime PyQGIS đã đăng ký. Hướng dẫn cài: [work/docs/setup/PYQGIS_SETUP.md](docs/setup/PYQGIS_SETUP.md).

OSM hiện có 183 ô hoàn chỉnh, snapshot 01/10/2026. Ma trận giữ 12 ô ABC×RC; **A×RC1 được ghi nhận là giới hạn của thiết kế mẫu hiện tại**. Mạng có khoảng 5,707 km RC1 giao với A nhưng còn 0 m đủ sinh tuyến sau kiểm tra nằm trọn vùng và loại dải bất định. Giữ ô/mẫu số và báo bộ mẫu có tuyến ở 11/12 ô. Xem [lý do và cách xử lý A×RC1](docs/lez/A_RC1_LIMITATION.md) cùng [bằng chứng](reports/sampling/A_RC1_limitation.json). Số hiện hành luôn lấy từ `latest_sampling_abc.json` và `latest_selection_30.json`.

Chưa có bằng chứng G1/G4/G5/G6/C6 và chuyến đo thực thì pipeline báo chờ; không sinh thông số thực địa. Giá trị OSM, mô hình và quan sát giữ riêng. D đo sai lệch cơ cấu chiều dài, không phải tỷ lệ đường đã khảo sát.

Hướng dẫn chi tiết: [quy trình](docs/lez/PROJECT_AUTOMATION.md), [thực địa](docs/lez/FIELD_WORKFLOW.md), [GPS](docs/lez/TRIP_PROCESSING.md), [sinh 60](docs/lez/SAMPLING_ABC.md), [chọn 30](docs/lez/SELECTION_30.md), [kế hoạch](docs/plans/LEZ_python_direct_api_plan.md).

Các bundle L/O, phạm vi điều chỉnh theo dân cư và phân tầng V/N cũ giữ để truy vết lịch sử. Chúng không được dùng thay ranh giới LEZ-first hiện hành. Raw OSM và tài liệu nguồn được giữ nguyên.

Kiểm tra độ nhạy mở rộng được tích hợp vào notebook 09, xem kết quả ở mục 4; mục 7a–7c notebook 06 dùng để chạy riêng: [work/docs/lez/SENSITIVITY.md](docs/lez/SENSITIVITY.md). Báo cáo riêng `work/reports/selection/latest_sensitivity.json`, có chuẩn hóa X, trọng số, phần làn/tốc độ thiếu, C6 khác nhau và thay tuyến giả lập; giữ bộ 30 đã công bố.

Bản trên GitHub giữ mã nguồn, notebook, cấu hình, truy vấn, metadata ô và tài liệu nguồn theo [`.gitignore`](.gitignore). Response OSM từng ô, bundle xử lý, dữ liệu đo, báo cáo, bản đồ và backup được giữ trên máy. Khi clone sang máy khác, cần tải hoặc khôi phục dữ liệu OSM và thiết lập PyQGIS trước khi chạy các bước phụ thuộc dữ liệu.
