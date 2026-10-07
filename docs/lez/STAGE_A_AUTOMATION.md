> Tài liệu đối chiếu lịch sử. Từ 06/10/2026, phạm vi sinh/chọn tuyến dùng LEZ-first theo [PROJECT_AUTOMATION.md](PROJECT_AUTOMATION.md); các điều chỉnh dân cư/V/N dưới đây không điều khiển ranh giới A/B/C hiện hành.

# Ranh giới và phân tầng nghiên cứu LEZ 2030

Notebook chính: `work/notebooks/03_boundaries.ipynb`. Notebook hiện dùng cùng chuẩn hóa 2030 với notebook 05; không dùng các cờ hoàn thành của cấu hình A/C cũ để đánh giá tiến độ nghiên cứu hiện tại.

Có thể chạy bằng Python thường hoặc kernel PyQGIS đã đăng ký. `work/scripts/lez/normalization_2030.py` gọi runtime PyQGIS cho xử lý hình học; `work/scripts/lez/boundary_review.py` kiểm tra các đầu ra và xuất bản đồ 15 tầng. Notebook không cần import qgis và không cài thêm thư viện.

## Chạy và tiếp tục trong notebook 03

1. Restart Kernel sau khi cập nhật module, rồi chạy từ đầu notebook.
2. Xem chính sách từ `work/config/sampling_boundary_policy.json` và `work/config/sampling_2030.json`.
3. Chạy kiểm tra đầu vào/runtime; bước này không gửi HTTP.
4. Chạy cell chuẩn hóa với `fetch=False, force=False`. Cache đúng cấu hình, manifest và hash được dùng lại. Chạy lại chính cell này để tiếp tục sau khi dừng.
5. Xem tổng kết, bản đồ phân tầng hiện tại, các gán bổ sung và bảng truy vết từng phần địa bàn.
6. Xem riêng kiểm tra phân tầng hiện tại, QA hình học OSM gốc và phần xác minh GIS chính thức.

Run All mặc định chỉ dùng dữ liệu đã lưu. Notebook không gọi Overpass, không tải lại nguồn pháp lý, không sinh 60 tuyến và không chọn lại 30 tuyến. Nếu dữ liệu dân cư/hoạt động thiếu, sửa đầu vào theo notebook 05 rồi tiếp tục; lỗi cache không được âm thầm thay bằng kết quả dự thảo cũ.

Từ folder work có thể chạy cùng bộ chuẩn hóa:

```bash
python3 scripts/lez/normalization_2030.py run
python3 scripts/lez/normalization_2030.py status
```

## Cách đọc trạng thái

| Phần kiểm tra | Ý nghĩa |
|---|---|
| `research_partition_ready` | Cache đầu ra hợp lệ, đủ 15 tầng, địa bàn nguồn đã có gán, nhóm V/N nhất quán, chứng cứ phân loại đủ và QA phân hoạch dẫn xuất đạt |
| `unassigned_admin_units` | Địa bàn nguồn chưa có trong bảng truy vết hiện tại; không lấy danh sách thiếu từ phương án dự thảo cũ |
| `pending_evidence_parts` | Phần sát ranh giới còn thiếu chứng cứ để áp dụng quy tắc phân loại |
| `raw_admin_qa` | Khoảng hở/chồng lấn của hình học địa bàn OSM gốc; vẫn giữ lại sau khi sửa trên lớp nghiên cứu dẫn xuất |
| `official_gis_verified` | Xác minh hình học GIS chính thức; hoàn thành phân tầng nghiên cứu không tự chuyển cờ này thành true |

Bản chuẩn hóa hiện có gán bổ sung cho 13 địa bàn trước đây thiếu, đủ 15 tầng và điều chỉnh 17 phần sát ranh giới. Đây là các phần địa bàn, không phải mặc định 17 xã/phường nguyên vẹn. Kết quả hiển thị được đọc từ báo cáo phiên bản hiện tại, không hardcode các số này trong cell kiểm tra.

Các gán bổ sung là vùng tham chiếu ban đầu. Sau khi cắt theo phạm vi lấy mẫu đã khóa, mỗi phần được gán vào tầng V/N phù hợp. Bảng truy vết cuối cùng là căn cứ để đọc phân tầng; không suy rằng toàn xã/phường thuộc N chỉ vì gán tham chiếu ban đầu dùng mã N.

QA phân hoạch dẫn xuất giữ dung sai 0,1 m² theo quy trình chuẩn hóa. Không tăng dung sai hoặc xóa lỗi nguồn để coi đã đạt. Bản đồ đo lại các đa giác thực tế của lớp `strata`, kiểm tra đủ 15 hình học hợp lệ, khoảng hở/chồng lấn và EPSG:3405 trước khi xuất.

## Đầu ra hiện tại

| Tệp/thư mục | Nội dung |
|---|---|
| `work/reports/sampling/latest_normalization_2030.json` | Báo cáo chuẩn hóa mới nhất; cung cấp đường dẫn phiên bản |
| `work/data/processed/normalization_2030/<version>/sampling_zones.gpkg` | Ranh giới đối chiếu, phạm vi lấy mẫu và 15 tầng nghiên cứu |
| `remaining_admin_assignments.csv` | Gán vùng tham chiếu cho các địa bàn trước đây còn thiếu |
| `strata_assignment_trace.csv` | ID/tên địa bàn, tầng tham chiếu, tầng cuối cùng, nhóm và lý do theo từng phần |
| `boundary_decisions.csv` | Chỉ báo, điểm và quyết định cho từng phần sát ranh giới |
| `work/reports/boundaries/current_2030/<version>/strata_2030.png` | Bản đồ 15 tầng hiện tại; manifest kiểm tra hash lớp nguồn và ảnh |
| `work/data/processed/sampling_2030.gpkg` | Liên kết đến lớp phạm vi lấy mẫu chuẩn hóa |
| `work/data/processed/admin_units.gpkg` | Lớp địa bàn OSM gốc, giữ riêng với đầu ra nghiên cứu |

Notebook lấy đường dẫn từ báo cáo/manifest; không hardcode tên thư mục hash. Khi cấu hình hoặc đầu vào thay đổi, chạy lại cell chuẩn hóa để lấy đúng phiên bản trước khi xem bản đồ.

## Quy trình A/C cũ và nhật ký nguồn

`work/scripts/lez/stage_a.py` vẫn được giữ để dựng/kiểm tra địa bàn nguồn, danh sách pháp lý và phương án dự thảo gốc. `work/config/boundary_project.json`, `work/config/strata_mapping.csv`, `work/data/processed/zones.gpkg` và `zones_draft.gpkg` thuộc quy trình này. Không ghi đè chúng để tự xác nhận GIS chính thức.

`work/reports/boundaries/latest_stage_a.json` và `decisions_required.csv` có thể còn báo 13 địa bàn chưa gán, 15 tầng thiếu định nghĩa và thiếu độ phủ ngoài LEZ. Các dòng này mô tả cấu hình/phương án cũ; không phải trạng thái của phân tầng 2030 đã chuẩn hóa.

Notebook 03 mặc định ẩn bảng quyết định cũ. Bật `SHOW_LEGACY=True` trong cell kiểm tra nếu muốn đối chiếu; bảng được ghi rõ là lịch sử/cấu hình A/C cũ. Nhật ký tải nguồn được hiển thị kèm thời điểm riêng; lỗi GET trang nguồn không được gộp thành lỗi phân tầng hiện tại.

Khi thực sự cần dựng lại địa bàn/dự thảo gốc từ nguồn đã lưu:

```bash
python3 scripts/lez/stage_a.py check
python3 scripts/lez/stage_a.py run --no-fetch-sources
python3 scripts/lez/stage_a.py status
```

Không dùng `stage_a_complete=false` của quy trình cũ làm cờ hoàn thành cho phạm vi nghiên cứu 2030. Nguồn pháp lý và dữ liệu OSM gốc vẫn giữ nguyên; GIS chính thức chỉ được xác nhận khi có bằng chứng tương ứng.

## Các bước tiếp theo

Notebook 05 quản lý bộ 60 ứng viên A20/B20/C20 (40 trong/20 ngoài LEZ 2030); notebook 06 quản lý 30 đề xuất: **18 trong LEZ (10 A + 8 B), 12 ngoài LEZ (12 C)**. Vùng A trong Vành đai 1, B giữa Vành đai 1–3, C ngoài Vành đai 3. Phân tầng V/N là lớp đối chiếu bổ sung; ma trận sinh/chọn tuyến hiện hành là ABC × RC1–RC4. Notebook 03 chỉ cập nhật/kiểm tra chuẩn hóa, không sinh hoặc lựa chọn lại các tuyến đó.

Xem `work/docs/lez/NORMALIZATION_2030.md`, `SAMPLING_ABC.md` và `SELECTION_30.md` để theo dõi chỉ tiêu, lựa chọn trước khảo sát và phần xác minh thực địa còn lại.
