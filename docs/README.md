# Mục lục tài liệu

Trước tiên đọc [tổng quan](PROJECT_OVERVIEW.md), sau đó chọn [hướng dẫn sử dụng toàn bộ](../HUONG_DAN_SU_DUNG_WORK.md) hoặc [bắt đầu trên máy mới](setup/GETTING_STARTED.md). `.../work` trong tài liệu là thư mục gốc repo.

## Hướng dẫn theo công việc

| Nhóm | Tài liệu | Mục đích |
|---|---|---|
| Thiết lập | [Máy mới](setup/GETTING_STARTED.md) · [PyQGIS](setup/PYQGIS_SETUP.md) | Clone, dữ liệu cần khôi phục, Python thường và runtime GIS |
| Nguồn OSM | [Bộ tải HTTP](overpass/DOWNLOAD_README.md) · [Lưới tải](overpass/README.md) | Query, phản hồi, cache, retry và audit |
| Quy trình | [Điều phối](lez/PROJECT_AUTOMATION.md) | Notebook 09, thư mục đo dùng chung và tiếp tục xử lý |
| Phạm vi / ứng viên | [LEZ-first](lez/README.md) · [Sinh 60](lez/SAMPLING_ABC.md) | ABC, ma trận mạng, quota và hình học |
| Chọn 30 | [Thuật toán](lez/SELECTION_30.md) | G1–G6, biến X, C1–C7, greedy và swap |
| Đối chứng | [M0](lez/RANDOM_BASELINE.md) · [Kết quả ngày 02/11](results/M0_2026_11_02.md) | Bốc đều theo quota, seed, 1.000 bộ hợp lệ và cách diễn giải |
| Biểu đồ đối chứng | [Hướng dẫn](lez/RANDOM_COMPARISON_PLOTS.md) · [Notebook 11](../notebooks/11_random_comparison_plots.ipynb) | Chia khoảng D; quan hệ D với độ phủ/chiều dài; đọc kết quả tại máy hoặc bản công bố |
| Độ nhạy | [Phân tích hiện có](lez/SENSITIVITY.md) | Các giả định trên pool cố định; phân biệt với thay đa giác ranh giới |
| Giới hạn dữ liệu | [A×RC1](lez/A_RC1_LIMITATION.md) | Ô thiếu, mẫu số được giữ và điều kiện xem xét lại |
| Khảo sát | [Bằng chứng/cập nhật](lez/FIELD_WORKFLOW.md) · [T2](lez/ROUTE_INSTRUCTIONS.md) · [T3](lez/SURVEY_COVERAGE.md) | Biểu mẫu, chỉ dẫn chạy, lịch và tổ hợp thiếu |
| Chuyến đo | [GPS/QC](lez/TRIP_PROCESSING.md) · [T5](lez/OPERATING_METRICS.md) | Schema, đơn vị, map matching, RPA/PKE và SAFD |

## Tài liệu lịch sử và đề xuất

[Chuẩn hóa V/N](lez/NORMALIZATION_2030.md), [quy tắc ranh giới trước đây](lez/SAMPLING_BOUNDARY_POLICY.md), [sinh tuyến 2030 cũ](lez/SAMPLING_2030.md), [Stage A](lez/STAGE_A_AUTOMATION.md) và [kế hoạch Python/API](plans/LEZ_python_direct_api_plan.md) được giữ để truy vết. Những phần nói A bằng toàn Vành đai 1, điều chỉnh phạm vi theo dân cư hoặc quota L/O cũ không xác định thiết kế hiện hành. Ưu tiên cấu hình LEZ-first, hướng dẫn sử dụng và báo cáo đúng phiên bản.

Các PDF/DOCX chuyên đề là tài liệu tham khảo theo ngày lập, không tự cập nhật sau khi thay đầu vào. Bản kết quả dùng để so sánh phải chỉ rõ pool, bộ 30, snapshot và hash.

## Kết quả công bố và kết quả tại máy

[M0 ngày 02/11/2026](results/M0_2026_11_02.md) mở được ngay sau clone. Các tệp `reports/latest_*`, bản đồ HTML và bundle dưới `data/processed` được tạo/khôi phục ở máy; đường dẫn đến chúng trong hướng dẫn là vị trí đầu ra, không phải tài sản luôn có trên GitHub.
