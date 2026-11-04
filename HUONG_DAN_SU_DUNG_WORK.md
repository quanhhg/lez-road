# Hướng dẫn sử dụng dự án Hà Nội OSM — LEZ từ A đến Z

Cập nhật theo các tệp hiện có ngày **02/11/2026**. Thư mục gốc được viết là **`.../work`**. Tài liệu này hướng dẫn chạy dự án hiện tại trên macOS, đọc kết quả và chuẩn bị khảo sát.

**Thiết kế đang dùng:** sinh 60 ứng viên **A20/B20/C20**, chọn 30 đề xuất **A10/B8/C12**, tương ứng **18 trong / 12 ngoài LEZ 2030**. Bộ 30 đã được đề xuất từ dữ liệu bản đồ; khảo sát thực địa và xây dựng hai chu trình lái còn ở phía sau.

Đọc nhanh [tổng quan](docs/PROJECT_OVERVIEW.md), [mục lục tài liệu](docs/README.md) hoặc [bắt đầu trên máy mới](docs/setup/GETTING_STARTED.md). `.../work` là thư mục gốc repo, không bắt buộc phải có tên `work`. Các liên kết mã/tài liệu tính tương đối từ đây; vị trí đầu ra dưới `data/processed`, `reports` và `maps` cần được tạo hoặc khôi phục tại máy, không phải tệp luôn có sau clone. Trong các lệnh Terminal, dấu `...` chỉ là cách viết rút gọn vị trí thư mục, **không phải ký tự để chép vào lệnh**.

## Mục lục

1. [Chọn việc cần làm ngay](#bat-dau)
2. [Hiểu cấu trúc và nguồn dữ liệu](#cau-truc)
3. [Thiết kế hiện tại và mức hoàn thành](#hien-trang)
4. [Mở dự án, chọn kernel và cài môi trường](#moi-truong)
5. [Sử dụng lần lượt các notebook](#notebook)
6. [Các lệnh Terminal tương ứng](#terminal)
7. [Tìm và đọc đúng đầu ra hiện hành](#dau-ra)
8. [Xem dữ liệu trong QGIS và bản đồ tuyến](#ban-do)
9. [Hiểu các biến, điều kiện và điểm chọn tuyến](#chi-tieu)
10. [Đổi cấu hình, chạy lại và tiếp tục](#chay-lai)
11. [Chuẩn bị khảo sát và phần việc tiếp theo](#khao-sat)
12. [Xử lý lỗi thường gặp](#loi)
13. [Sao lưu và chuyển thư mục](#sao-luu)
14. [Tài liệu chuyên sâu và checklist](#checklist)

<a id="bat-dau"></a>

## 1. Chọn việc cần làm ngay

| Bạn muốn làm gì? | Mở hoặc chạy gì? | Cần gọi API không? |
|---|---|---|
| Xem 30 tuyến được chọn, tên đường và trong/ngoài LEZ | `.../work/maps/routes/30_tuyen_LEZ2030.html` | Không cần tải lại dữ liệu |
| Xem toàn bộ 60 ứng viên | `.../work/maps/routes/60_tuyen_LEZ2030.html` | Không cần tải lại dữ liệu |
| Đọc ảnh hoặc danh sách tuyến | PNG và CSV trong `.../work/maps/routes` | Không |
| Xem tiến độ OSM | Notebook 01: thiết lập → kiểm tra cấu hình/tiến độ → tổng kết | Không |
| Xem ranh giới và phân tầng đã chuẩn hóa | Notebook 03 | Mặc định không |
| Xem hoặc chạy lại bộ 60 bằng cache | Notebook 05, giữ `REBUILD_LEZ_SCOPE=False`, `FORCE=False` | Không |
| Xem hoặc chạy lại lựa chọn 30 | Notebook 06, giữ `force=False` | Không |
| Điều phối các bước đã tích hợp sau khi có mạng/cache chuẩn hóa | Notebook 09 | Không |
| So 1.000 bộ ngẫu nhiên với bộ 30 cố định | Notebook 10 hoặc `selection_random.py run` | Không; không cần QGIS đang chạy |
| Vẽ/đổi khoảng D và xem hồi quy mô tả | Notebook 11; đọc M0 có sẵn hoặc bản công bố trong repo | Không; không cần QGIS hoặc bốc lại mẫu |
| Chuẩn bị/nhập bằng chứng, cập nhật và chọn lại | Notebook 07 | Không |
| Nhập chuyến/GPS, kiểm chất lượng và T5 | Notebook 08 hoặc 09 | Không |
| Dựng lại mạng sau khi thay dữ liệu hoặc quy tắc xe máy | Notebook 04 | Không khi dùng nguồn đã lưu và `fetch_sources=False` |
| Tải các ô OSM còn thiếu/hỏng | Notebook 01: kiểm tra trước → cell tải | Có, nếu có ô cần tải |
| Kiểm tra/chia ô tải nặng | Notebook 02 hoặc phần PyQGIS tùy chọn trong 01 | Thao tác chia không gọi API; tải ô con là bước riêng |

**Với dự án đang có, không cần bắt đầu bằng tải lại 183 ô.** Nếu chỉ muốn xem bộ tuyến, mở bản đồ và notebook 06. Nếu muốn tái chạy phần sinh/chọn tuyến, dùng 05 → 06 với cache.

Trình duyệt có thể không hiện bản đồ khi mở HTML qua chế độ xem mã của VS Code. Mở tệp bằng trình duyệt thông thường; trên macOS có thể dùng Terminal đang ở `.../work`:

~~~bash
open maps/routes/30_tuyen_LEZ2030.html
open maps/routes/60_tuyen_LEZ2030.html
~~~

<a id="cau-truc"></a>

## 2. Hiểu cấu trúc và nguồn dữ liệu

~~~text
.../work/
├── HUONG_DAN_SU_DUNG_WORK.md       Hướng dẫn tổng hợp này
├── README.md                      Giới thiệu và tiến độ thiết kế hiện hành
├── .vscode/settings.json          Cấu hình trình soạn thảo
├── notebooks/                    Mười notebook 01–10
├── scripts/
│   ├── overpass/                  HTTP, cache, trạng thái và lưới tải
│   ├── lez/                       Mạng, ranh giới, chuẩn hóa, sinh/chọn tuyến
│   └── setup/                     Thiết lập kernel PyQGIS
├── config/                       Các quy tắc và tham số nghiên cứu
├── data/
│   ├── hanoi_tiles/               Dữ liệu OSM theo ô và lịch sử tải
│   ├── raw/                       Tài liệu nghiên cứu, nguồn pháp lý, nguồn bổ sung
│   ├── measurements/incoming/     CSV quan sát, chuyến và GPS để nhập
│   ├── interim/                   Chỉ mục và dữ liệu trung gian
│   └── processed/                 Mạng, vùng và bộ tuyến theo phiên bản
├── reports/                      Báo cáo tiến độ, kiểm tra, nhật ký
├── maps/
│   ├── hanoi_tiles/               Lưới tải và ảnh kiểm tra phạm vi tải
│   └── routes/                    Bản đồ và danh sách 30/60 tuyến
├── docs/                         Hướng dẫn chuyên sâu từng phần
├── tests/                        Kiểm tra mã bằng dữ liệu kiểm thử
└── backups/                      Các bản lưu trước những lần sửa/sắp xếp
~~~

### 2.1. Vai trò của từng loại tệp

| Loại | Dùng để làm gì? | Cách mở |
|---|---|---|
| `.ipynb` | Chạy từng cell, xem bảng/bản đồ/tiến độ | VS Code với Jupyter |
| `.py` | Logic xử lý được notebook gọi; một số module có CLI | VS Code; chạy đúng lệnh ở mục 6 |
| `.json` | Cấu hình, báo cáo, manifest hoặc dữ liệu OSM | VS Code hoặc Python |
| `.csv` | Bảng ô tải, biến, ma trận, tuyến, checklist | Python/pandas hoặc trình xem CSV |
| `.gpkg` | GeoPackage: hình học và bảng GIS, có thể chứa nhiều lớp | QGIS |
| `.json.gz` | Graph nén, chứa cung và quy tắc rẽ | Module của dự án; không cần giải nén thủ công |
| `.html` | Bản đồ tương tác đã xuất | Trình duyệt |
| `.png` | Ảnh bản đồ tĩnh | Trình xem ảnh |
| `.md` | Tài liệu hướng dẫn | VS Code, bật Markdown Preview nếu cần |

**Notebook** là giao diện điều khiển. **Module** trong `scripts` thực hiện công việc. **Kernel** là tiến trình Python chạy cell. **Worker PyQGIS** là tiến trình riêng xử lý GIS mà controller có thể gọi từ Python thường.

Một **bundle** là thư mục kết quả của một phiên bản xử lý, chứa dữ liệu và `manifest.json`. **Cache** chỉ được dùng lại khi đầu vào/cấu hình/mã và hash đầu ra đáp ứng kiểm tra của module. **Symlink** là đường dẫn trỏ đến một tệp khác, không phải bản sao độc lập.

### 2.2. Những nguồn cần đọc đúng

| Câu hỏi | Nguồn chính |
|---|---|
| Ô OSM nào đã tải xong? | [.../work/data/hanoi_tiles/tiles.csv](data/hanoi_tiles/tiles.csv), manifest từng ô và `.../work/reports/overpass/completion_audit.json` |
| Lịch sử ô và trạng thái được lưu ở đâu? | [.../work/data/hanoi_tiles/tiles_history.json](data/hanoi_tiles/tiles_history.json) |
| Endpoint/snapshot/CRS của bộ tải? | [.../work/data/hanoi_tiles/tile_project.json](data/hanoi_tiles/tile_project.json) |
| Báo cáo/bản đồ lưới được đặt ở đâu? | [.../work/data/hanoi_tiles/project_layout.json](data/hanoi_tiles/project_layout.json) và module `project_paths.py` |
| Mạng xe máy hiện tại có gì? | `.../work/reports/network/latest_network_report.json` |
| Hồ sơ chuẩn hóa V/N lịch sử, nguồn phụ trợ của bộ ABC? | `.../work/reports/sampling/latest_normalization_2030.json` |
| Bộ 60 ABC hiện hành? | `.../work/reports/sampling/latest_sampling_abc.json` |
| Bộ 30 hiện hành và chỉ tiêu? | `.../work/reports/selection/latest_selection_30.json` |
| Đối chứng M0 mới nhất? | `.../work/reports/selection/latest_random_baseline.json` |
| Độ nhạy trên pool cố định? | `.../work/reports/selection/latest_sensitivity.json` |
| Bằng chứng/quan sát đã đủ chưa? | `.../work/reports/field/latest_field_workflow.json`, `latest_survey_revision.json` |
| Chuyến/GPS thực, T3? | `.../work/reports/trips/latest_real.json`, `reports/field/latest_survey_coverage.json` |
| Bản đồ đang dùng bộ dữ liệu nào? | `.../work/maps/routes/route_maps_manifest.json` |

`.../work/data/tiles.csv` là liên kết tới CSV trong `data/hanoi_tiles`. Không tạo một bảng tiến độ riêng cạnh notebook.

Trong `tiles.csv`, `query_file` và `response_dir` được tính tương đối từ **`.../work/data/hanoi_tiles`**. Trong các báo cáo LEZ, đường dẫn có dạng `work/data/processed/...` lại tính từ **thư mục gốc dự án**, xử lý bằng `lez.common.input_path`. Hai cách định vị này khác nhau.

### 2.3. Mã nguồn nào cần biết?

| Tệp/module trong `.../work/scripts` | Vai trò |
|---|---|
| `overpass/download_tiles.py` | Tải HTTP tuần tự, kiểm phản hồi, lưu raw, cache và cập nhật tiến độ |
| `overpass/audit_download.py` | Kiểm toàn bộ cache/trạng thái và ghi báo cáo kiểm tra |
| `overpass/project_paths.py` | Định vị dữ liệu, báo cáo và bản đồ theo layout |
| `overpass/build_tiles.py` | Verify/split lưới bằng PyQGIS |
| `overpass/render_grid.py` | Vẽ lưới tải |
| `lez/pipeline.py` | Controller/worker chuẩn hóa OSM và dựng mạng |
| `lez/access.py`, `network.py`, `graph.py`, `routing.py` | Quyền xe máy, hình học, graph có hướng, tìm đường |
| `lez/policy_boundaries.py` | Đa giác ranh giới LEZ-first hiện hành và nguồn chính sách |
| `lez/normalization_2030.py`, `boundary_review.py` | Chuẩn hóa/phân tầng V/N phụ trợ, truy vết lịch sử |
| `lez/abc_boundaries.py`, `sampling_abc.py` | Vùng ABC, ma trận và sinh 60 ứng viên |
| `lez/selection_30.py`, `selection_metrics.py`, `selection_gates.py` | Kiểm điều kiện, tính biến/điểm, chọn 30 và dự phòng |
| `lez/export_route_maps.py` | Xuất bản đồ có tên đường cho 30/60 tuyến |
| `lez/project_automation.py` | Điều phối từ pool 60 đến khảo sát/chuyến đo; cần nguồn mạng/chuẩn hóa trước |
| `lez/selection_sensitivity.py` | Độ nhạy trên pool và bộ 30 cố định |
| `lez/selection_random.py` | M0: bốc đều theo quota, checkpoint và so sánh bộ 30 |
| `lez/field_workflow.py`, `survey_revision.py`, `trip_processing.py` | Bằng chứng, cập nhật, chọn lại và kiểm chuyến/GPS |
| `lez/route_instructions.py` | T2: chỉ dẫn chạy, sơ đồ, GPX và điểm cần rà soát |
| `lez/survey_coverage.py` | T3: lịch theo loại ngày, điều kiện đo và tiến độ tổ hợp |
| `lez/operating_metrics.py` | T5: RPA/PKE, phân bố tốc độ–gia tốc và tổng hợp có trọng số |
| `setup/setup_pyqgis_kernel.py` | Tạo runtime và đăng ký kernel PyQGIS |

Người sử dụng thông thường chạy notebook hoặc CLI đã hướng dẫn, không cần chạy riêng từng module nội bộ như `network.py` hay `selection_metrics.py`.

<a id="hien-trang"></a>

## 3. Thiết kế hiện tại và mức hoàn thành

### 3.1. ABC và LEZ là hai thuộc tính riêng

| Nhóm | Không gian nghiên cứu | Ứng viên 60 | Đề xuất 30 | Nhóm LEZ dùng cho bộ tuyến hiện tại |
|---|---|---:|---:|---|
| A | KV1/KV2/KV3 thí điểm LEZ 2027 tại Hoàn Kiếm/Cửa Nam | 20 | 10 | Trong LEZ 2030 |
| B | LEZ 2030 trừ A: phần Vành đai 1 chưa thuộc A và phần mở rộng đến Vành đai 3 | 20 | 8 | Trong LEZ 2030 |
| C | Phần Hà Nội ngoài LEZ 2030 của phiên bản nghiên cứu | 20 | 12 | Ngoài LEZ 2030 |
| Tổng | | 60 | 30 | Bộ 60: 40 trong/20 ngoài; bộ 30: 18 trong/12 ngoài |

A **không phải toàn Vành đai 1**. B gồm cả phần Vành đai 1 chưa thuộc A và phần đến Vành đai 3; không chỉ các tuyến trên đường Vành đai 2. Định nghĩa theo nguồn đóng băng trong `config/lez_policy.json`, không phải tra cứu chính sách cập nhật theo ngày đọc. Trong dữ liệu, `sampling_zone` giữ A/B/C; `group` và `lez2030_group` giữ trạng thái LEZ. Pool hiện tại lấy A/B giao phần trong LEZ và C giao phần ngoài LEZ; hình học toàn tuyến phải đáp ứng cả hai lớp.

Ma trận sinh/chọn chính có **12 ô = 3 nhóm ABC × 4 loại RC**. Các tầng V1–V5, N1–N10 và ma trận chuẩn hóa 60 ô vẫn được giữ để đối chiếu chi tiết; chúng không còn là quota bắt buộc phải có đủ 15 tầng trong bộ 30 ABC.

### 3.2. Trạng thái đã đối chiếu ngày 02/11/2026

| Phần việc | Kết quả hiện có | Giới hạn cần nhớ |
|---|---|---|
| OSM theo ô | 183/183 ô `done`, audit không còn pending/failed/heavy | Đây là dữ liệu gốc theo snapshot, không phải số liệu khảo sát hiện tại |
| Mạng xe máy | Graph có 306.525 node, 708.233 cung, 192 quy tắc rẽ | Quyền đi còn mang tính dự kiến theo OSM; mạng pháp lý cuối chưa được xác nhận |
| Chuẩn hóa LEZ/V/N | Có bundle và báo cáo chuẩn hóa nghiên cứu | Hình học đối chiếu chưa được xác nhận là GIS pháp lý chính thức |
| Sinh 60 ABC | A20/B20/C20; không còn mục tiêu sinh tuyến thất bại | 60 tuyến vẫn cần kiểm tra thực địa |
| Chọn 30 | A10/B8/C12, đúng 18 trong/12 ngoài; có 30 tuyến dự phòng | Trạng thái `proposed_for_survey`, chưa khóa bộ cuối |
| Bản đồ | Có HTML/PNG/CSV cho cả 30 và 60 | Đọc manifest để đối chiếu với bộ tuyến sau mỗi lần chạy mới |
| M0 | 1.000 bộ hợp lệ, seed 20261102; 0/1.000 bộ có D ≤ bộ gốc | Đối chứng mô tả trên cùng pool; không phải p-value bằng 0 |
| Độ nhạy | 114 kịch bản: 113 hoàn thành, 1 ca thiếu quota định trước | Chưa bao gồm đầy đủ thay đa giác ranh giới và benchmark M1–M5 |
| Khảo sát / T2 / T3 | Có mã, phiếu/GPX, lịch 180 tổ hợp / 360 lượt đề xuất | Chưa có tổ hợp được đếm đã đo; mục tiêu số chuyến/ngày còn chờ chốt |
| GPS / T5 / chu trình | Có xử lý chuyến và công thức; báo cáo thực 0 chuyến / 0 điểm GPS | Chưa có kết quả đo hoặc chu trình thực nghiệm |

Snapshot OSM đang dùng là **`2026-10-01T00:00:00Z`**. Tính chiều dài/diện tích trong CRS mét **EPSG:3405**; tọa độ truy vấn Overpass dùng WGS84.

Hình học Vành đai 1/3 là **proxy kỹ thuật có truy vết nguồn**. Phần khép kín phía bắc Vành đai 3 có dải bất định 2.000 m được loại khỏi tuyến. Các kết quả “thuần vùng” hiện tại được kiểm theo phạm vi nghiên cứu đã lưu, không tự xác nhận một đa giác pháp lý.

Các số ở mục này là ảnh chụp kiểm tra ngày 02/11/2026. Ngày cập nhật hướng dẫn không đổi ngày snapshot OSM hoặc ngày kiểm chính sách nguồn. Pool còn thiếu A×RC1; giữ đủ 12 ô/mẫu số và báo 11/12 ô có tuyến. Xem [giới hạn A×RC1](docs/lez/A_RC1_LIMITATION.md). Sau khi thay đầu vào hoặc chạy phiên bản mới, đọc lại các báo cáo `latest_*.json`.

<a id="moi-truong"></a>

## 4. Mở dự án, chọn kernel và cài môi trường

### 4.1. Mở đúng workspace

1. Trong VS Code, chọn **File → Open Folder**, mở **`.../work`**.
2. Mở notebook từ `.../work/notebooks`.
3. Chọn kernel ở góc trên bên phải notebook.
4. Sau khi đổi kernel, chuyển thư mục hoặc sửa module đã import, dùng **Restart Kernel**, rồi chạy lại từ cell thiết lập.
5. Mở Terminal tích hợp. Các lệnh ở hướng dẫn này giả định Terminal đang ở **`.../work`**; kiểm tra bằng `pwd` và `ls`. Bạn cần thấy `notebooks`, `scripts`, `config`, `data`.

Khi mới đọc dự án, chạy cell thiết lập và cell xem trạng thái trước. Nút **Run All** sẽ đi qua cả các cell xử lý; trong notebook 01, cell tải có thể gửi HTTP nếu có ô cần xử lý.

### 4.2. Notebook nào cần PyQGIS?

| Notebook/công việc | Kernel có thể dùng | Điều kiện |
|---|---|---|
| 01 — đọc/tải OSM | Python thường hoặc PyQGIS | Cần `requests`, `pandas`, Jupyter; giữ `ENABLE_PYQGIS=False` khi dùng Python thường |
| 02 — verify/split lưới | PyQGIS | Import trực tiếp `build_tiles` → `qgis.core` |
| 03/04/05/06 — điều khiển quy trình | Python thường hoặc PyQGIS | Controller dùng thư viện phân tích; worker GIS cần runtime PyQGIS đã đăng ký |
| 07/08/09 — bằng chứng, GPS và điều phối | Python thường hoặc PyQGIS | Một số bước GIS/map matching/bản đồ cần worker PyQGIS; dữ liệu phải có trước |
| 10 — M0 trên dữ liệu đã lưu | Python thường | NumPy và Matplotlib; notebook cần ipykernel; không khởi động QGIS |
| 11 — biểu đồ đối chứng | Python thường | Thư viện trong `requirements-notebook.txt`; chỉ đọc kết quả M0, không khởi động QGIS |
| Cell do bạn viết có `from qgis.core import ...` | PyQGIS | Kernel đang chạy cell phải nạp được QGIS |
| Mở PNG/HTML/CSV kết quả | Không cần kernel GIS | Chỉ xem tệp đã xuất |

Chỉ chọn **Python (PyQGIS 4.2.3)** khi đã kiểm interpreter và ứng dụng QGIS tương ứng còn hoạt động. Kernel đã đăng ký không tự chứng minh runtime dùng được. Python thường vẫn dùng được cho HTTP và controller; việc này không làm mất yêu cầu runtime PyQGIS ở phần hình học.

Kiểm thư viện notebook bằng một cell:

~~~python
import sys
import requests
import pandas as pd
import numpy as np

print("Python:", sys.version.split()[0])
print("Thư viện HTTP và phân tích đã import được.")
~~~

Kiểm kernel PyQGIS bằng cell riêng, sau khi chọn đúng kernel:

~~~python
from qgis.core import Qgis
print("QGIS:", Qgis.QGIS_VERSION)
~~~

### 4.3. Runtime hiện có và cách thiết lập lại

**Hướng dẫn đầy đủ cho người mới:** [Tải, cài và chạy PyQGIS từng bước](docs/setup/PYQGIS_SETUP.md). Tài liệu có đường dẫn tải chính thức, thao tác trong Finder/VS Code, nơi nhập lệnh, kết quả cần thấy và cách xử lý lỗi.

PyQGIS đi kèm ứng dụng QGIS. Việc nối với notebook có hai khâu: **cài QGIS vào máy → tạo môi trường chạy trong `work`**. Script của dự án chỉ làm khâu thứ hai, không tự tải QGIS. Bộ thiết lập hiện tại dành cho **macOS, QGIS 4.2.3/Python 3.12**; không dùng nguyên lệnh cho mọi bản QGIS hoặc hệ điều hành.

Nếu chưa có môi trường hoạt động, làm theo thứ tự:

1. **Tải và cài QGIS:** vào [trang QGIS chính thức](https://qgis.org/download/), chọn bộ cài macOS **4.2.3** phù hợp script; mở `.dmg`, kéo ứng dụng vào **Applications**, rồi chạy ứng dụng từ đó. Xem [hướng dẫn tải/cài chi tiết](docs/setup/PYQGIS_SETUP.md#tai-cai-qgis); không chỉ tải tệp rồi bỏ qua bước cài.
2. **Kiểm phiên bản:** trong QGIS mở **Plugins → Python Console**, kiểm QGIS 4.2.3 và Python 3.12.x theo mục 2 của tài liệu trên. Ghi lại tên/vị trí thật của ứng dụng; mặc định script tìm `/Applications/QGIS-final-4_2_3.app`.
3. **Chuẩn bị VS Code:** cài phần mở rộng **Python** và **Jupyter** của Microsoft, mở **File → Open Folder → work**, rồi **Terminal → New Terminal**. Kiểm `pwd`, `ls`, `python3 --version` và công cụ macOS theo [mục chuẩn bị](docs/setup/PYQGIS_SETUP.md#chuan-bi-vscode). Lệnh dưới chạy trong Terminal ở `work`, không phải cell notebook.
4. **Tạo môi trường:** sau khi kiểm đường dẫn ứng dụng, chạy lệnh sau nếu dùng đúng vị trí mặc định:

~~~bash
python3 scripts/setup/setup_pyqgis_kernel.py --project-dir .
~~~

5. **Đợi hoàn tất và chọn kernel:** cần thấy cả `Import and GIS checks passed`, `Registered kernel` và dòng hướng dẫn chọn kernel. Trong notebook chọn **Select Kernel → Select Another Kernel → Jupyter Kernels → Python (PyQGIS 4.2.3)**, rồi restart. Nếu ứng dụng ở đường dẫn khác, dùng `--qgis-app` theo [mục tạo kernel](docs/setup/PYQGIS_SETUP.md#tao-kernel), sau khi xác nhận phiên bản tương thích.
6. **Chạy cell kiểm tra:** làm [mục kiểm tra notebook và Processing](docs/setup/PYQGIS_SETUP.md#kiem-tra-notebook). Kiểm `sys.executable`, phiên bản và phép tạo vùng đệm trong bộ nhớ; chỉ thấy tên kernel trong menu chưa xác nhận môi trường chạy được. Sau đó mới kiểm dữ liệu dự án.

Lệnh tạo `work/.pyqgis-runtime`, kiểm import/Processing và cập nhật kernel `pyqgis-423`. Nó có thể tải phụ thuộc notebook qua pip nếu thiếu, không gọi Overpass hoặc dựng mạng. Không dùng `pip install qgis` để thay thế ứng dụng QGIS. Nếu notebook 02 thiếu `requests`, có [hướng dẫn bổ sung vào đúng runtime](docs/setup/PYQGIS_SETUP.md#chon-moi-truong).

Một bản cài trước đây dùng **`work/../.pyqgis-runtime`**. Trên máy mới hoặc sau khi chuyển/xóa ứng dụng QGIS, phải kiểm lại ứng dụng và đường dẫn kernel; bản sao Python vẫn phụ thuộc thư viện QGIS gốc. Chỉ thiết lập lại khi cần, không cài lại mỗi lần mở notebook. Khi dùng hằng ngày không cần mở giao diện QGIS, nhưng phải giữ ứng dụng đúng vị trí.

Nếu muốn một môi trường Python thường riêng cho HTTP/controller và máy chưa có các thư viện cần thiết, có thể tạo môi trường tùy chọn:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-notebook.txt
python3 -m ipykernel install --user --name hanoi-work --display-name "Python (Hanoi work)"
~~~

Chỉ cần thực hiện nhánh này khi thiếu môi trường Python thường. Kernel **Python (Hanoi work)** không chứa PyQGIS; vẫn cần runtime GIS đăng ký ở trên cho bước hình học/routing/bản đồ và chọn kernel PyQGIS cho 02. M0 ở notebook 10 và biểu đồ ở notebook 11 chạy bằng môi trường thường này. Danh sách thư viện không khóa phiên bản; muốn lặp đúng M0 đã lưu cần đối chiếu Python/NumPy/Matplotlib trong bản kết quả.

### 4.4. Có cần SQL hoặc API key?

Không cần viết SQL để chạy quy trình hiện tại. SQLite/GeoPackage được module sử dụng nội bộ.

Bộ tải dùng Overpass HTTP trực tiếp từ cấu hình; không yêu cầu API key OSM. Phần sinh/chọn tuyến hiện tại dùng nguồn đã lưu. Chưa có bộ tích hợp Google Maps trong quy trình này; không cần key Google để chạy các notebook.

<a id="notebook"></a>

## 5. Sử dụng lần lượt các notebook

### 5.1. Thứ tự theo phụ thuộc

Khi dựng lại từ dữ liệu nguồn đã có:

~~~text
Thiết lập môi trường + khôi phục/kiểm tra các nguồn
        ↓
02 kiểm tra lưới nếu cần → 01 kiểm tra/tải OSM nếu cần
        ↓
04 dựng mạng xe máy
        ↓
03 xem/kiểm đa giác LEZ-first; có cache chuẩn hóa phụ trợ cần thiết
        ↓
05 sinh 60 → 06 chọn 30
        ├── 10: M0 trên pool và bộ 30 cố định
        ├── Độ nhạy tiền khảo sát
        └── 07: bằng chứng/cập nhật → 08: GPS/QC/T5 → T3
~~~

**04 đứng trước phần hình học 03 trong một lượt dựng mới.** Notebook 09 điều phối các bước đã tích hợp từ pool 60 đến dữ liệu đo; nó cần mạng và cache chuẩn hóa tồn tại trước, không tự thay toàn bộ bước tải/khởi tạo nguồn. M0 chạy riêng, chưa tích hợp vào 09.

`sampling_abc` vẫn đọc bundle `normalization_2030` làm nguồn Hà Nội và kiểm tra bổ trợ. Nếu cache này thiếu thì phải khôi phục hoặc dựng theo cấu hình nguồn. Việc dùng bundle phụ trợ không có nghĩa phân A/B/C lại theo dân cư hoặc theo phạm vi LEZ điều chỉnh cũ.

### 5.2. Notebook 01 — tải và theo dõi OSM

Tệp: [.../work/notebooks/01_download_osm.ipynb](notebooks/01_download_osm.ipynb).

**Đầu vào:** `tiles.csv`, `tile_project.json`, truy vấn theo `query_file`, manifest và response đã lưu. Module tải nằm ở `.../work/scripts/overpass/download_tiles.py`.

Thao tác:

1. Chạy cell thiết lập, đọc CSV, xem bản đồ và chọn ô. `TILE_ID` chỉ phục vụ xem chi tiết ô, không có nghĩa bạn phải gọi API thủ công cho từng ô.
2. Giữ `ENABLE_PYQGIS=False` cho công việc HTTP bằng Python thường. Phần kiểm tra/chia lưới là tùy chọn riêng.
3. Chạy cell cấu hình `OPTIONS`. Mặc định nghỉ 15 giây; timeout kết nối 10 giây/đọc 240 giây; tối đa 3 lần thử; backoff và jitter đã có trong module.
4. Chạy cell **Kiểm tra cấu hình và xem tiến độ**. Không HTTP; cần kiểm tra đạt trước khi tải.
5. Chỉ khi cần tải, chạy cell **Chạy tải tất cả các ô đang hoạt động**. Module đọc các query có sẵn, tải tuần tự bằng một Session và bỏ qua cache hợp lệ.
6. Xem cell tổng kết: done/pending/failed/heavy, lỗi từng ô, số tải mới, số đọc cache, thời gian của lượt.

**Tiếp tục:** dùng Interrupt/Ctrl+C để dừng; chạy lại cell tải hoặc đặt `RESUME_NOW=True` trong cell tiếp tục. Giữ cấu hình/snapshot/truy vấn; dữ liệu hoàn chỉnh không bị tải lại.

Mỗi `response_dir` chứa:

- `response.json`: nguyên dữ liệu nhận được, không làm sạch hoặc sửa thủ công.
- `manifest.json`: ô/bbox/snapshot/endpoint/thời gian/count/hash và kết quả kiểm tra.
- `errors.jsonl`, `errors/*.body` khi có lỗi: nhật ký và nội dung phản hồi lỗi.

Trước `done`, module kiểm HTTP/JSON, remark, count, tọa độ node, tham chiếu way/relation, metadata/snapshot. Ô hợp lệ không có đường vẫn được ghi nhận riêng, không tự coi là lỗi.

429 phải đợi Retry-After/thời gian server; lỗi tạm thời có backoff; 504/timeout lặp lại có thể thành `heavy`. Không đổi endpoint để né giới hạn, không chạy nhiều bộ tải cùng dự án. Hiện audit ghi **183 done, 0 pending/failed/heavy**.

### 5.3. Notebook 02 — kiểm tra lưới tải

Tệp: [.../work/notebooks/02_prepare_download_tiles.ipynb](notebooks/02_prepare_download_tiles.ipynb).

Dùng khi cần kiểm phạm vi Hà Nội/lưới, đọc bbox/query một ô hoặc xử lý một ô nặng thật sự. Chọn kernel **PyQGIS**.

Chạy các cell đọc dữ liệu/xem bản đồ/chọn ô, rồi cell gọi `grid.verify(ROOT)` khi muốn kiểm lại độ phủ bằng hình học. Cell định nghĩa `split_heavy_tile(...)` **chỉ tạo hàm**, chưa tự chia ô.

Chỉ gọi split sau khi đọc lỗi và xác nhận truy vấn quá nặng, bộ tải đã dừng, server hoạt động bình thường. Split thay đổi cấu trúc ô; sau đó cần quay lại 01 để preflight và tải ô con. Không chia vì một lần 429 hoặc vì muốn gọi song song.

Tiến độ tải đọc từ CSV/audit, không từ trường status trong ảnh/lớp GIS xuất lúc tạo lưới. Lưới 183 ô hiện có không cần tạo lại để dùng bộ tuyến.

### 5.4. Notebook 04 — chuẩn hóa OSM và dựng mạng xe máy

Tệp: [.../work/notebooks/04_build_motorcycle_network.ipynb](notebooks/04_build_motorcycle_network.ipynb).

**Đầu vào:** các response OSM hợp lệ, nguồn ranh giới đã lưu, [.../work/config/access_rules.json](config/access_rules.json). Controller là `lez.pipeline`.

1. Chạy cell thiết lập và kiểm tra đầu vào/runtime.
2. Giữ `TILE_IDS=None` để dùng toàn bộ phạm vi. Danh sách một vài tile dành cho chạy thử một phần, không thay bộ mạng toàn Hà Nội.
3. Chạy cell xử lý với `stage="network"`, `fetch_sources=False`.
4. Xem số đối tượng khử trùng, đoạn, cung có hướng, hạn chế rẽ, thành phần liên thông và các danh sách cần rà soát.
5. Đọc `network.gpkg`, graph và CSV từ `NETWORK_DIR` mà báo cáo trả về.

Module khử trùng đối tượng giữa các ô, dựng đoạn vật lý, xử lý cầu/hầm/layer, hướng đi và hạn chế rẽ, phân RC và trạng thái quyền đi. Các đoạn/ràng buộc `review_required` không tự trở thành đoạn hợp lệ để routing.

Đầu ra công bố: `.../work/data/processed/network.gpkg`, `motorcycle_graph.json.gz`; báo cáo ở `.../work/reports/network`.

Hiện còn 27.597 đoạn và 212 quan hệ hạn chế cần rà soát; `final_legal_network_ready=false`. Dựng xong graph chưa xác nhận quyền xe máy trên thực địa.

Một số thông báo cuối 04 như `stage_a_complete` thuộc hồ sơ A/C cũ; đọc tiến độ ABC từ báo cáo 05/06. Đoạn Markdown cũ về quota 20/40 ở cuối 04 không phải quota hiện hành.

### 5.5. Notebook 03 — đa giác ranh giới LEZ-first

Tệp: [.../work/notebooks/03_boundaries.ipynb](notebooks/03_boundaries.ipynb).

Phần đầu notebook đọc `config/lez_policy.json`, kiểm nguồn/hash, gọi worker `policy_boundaries` để dựng và xem đa giác A/B/C trong thư mục tạm; hiển thị diện tích, dải bất định và cờ `official_gis_verified`. Không sinh 60 hoặc chọn 30, không tự thay nguồn pháp lý bằng một hình vẽ.

1. Kiểm mạng/nguồn và runtime; hoàn thiện 04 trước nếu mạng thiếu.
2. Chạy phần LEZ-first để xem nguồn, hình học và giới hạn.
3. Chuyển sang 05 để sinh ứng viên theo phiên bản chính sách cấu hình.
4. Phần **đối chiếu lịch sử V/N, dân cư/hoạt động** có guard riêng. Chỉ dùng khi cần kiểm hoặc dựng cache phụ trợ `normalization_2030`; giữ phần này tách khỏi phân vùng hiện hành.

Nếu cache phụ trợ thiếu, đọc [chuẩn hóa](docs/lez/NORMALIZATION_2030.md), kiểm nguồn mạng/dân cư/hoạt động trước khi dựng. Không sửa `config/lez_policy.json` để cho phép dịch ranh giới theo dân cư nhằm đủ quota.

### 5.6. Notebook 05 — sinh 60 ứng viên ABC

Tệp: [.../work/notebooks/05_sampling_2030.ipynb](notebooks/05_sampling_2030.ipynb).

Tên tệp còn chứa “2030”; logic sinh tuyến hiện tại gọi **`lez.sampling_abc`**. Cấu hình chính là [.../work/config/sampling_abc.json](config/sampling_abc.json).

1. Chạy thiết lập, đọc cấu hình và preflight.
2. Giữ `REBUILD_LEZ_SCOPE=False`: đọc cache chuẩn hóa phụ trợ đã lưu. Cờ này còn tên lịch sử; chỉ bật True khi chủ động dựng lại cache phụ trợ và các kết quả phụ thuộc. Phân A/B/C hiện hành vẫn theo `lez_policy.json`, không theo phạm vi điều chỉnh dân cư cũ.
3. Xem ma trận mạng; có 12 ô ABC×RC và bảng chi tiết V/N bổ sung.
4. Giữ `FORCE=False`, chạy cell sinh 60.
5. Xem CSV, số tuyến theo A/B/C và LEZ, mục tiêu thất bại, overlap, D và bản đồ.
6. Nếu bị ngắt, chạy cell tiếp tục với `force=False`.

Kết quả cần đạt: 60 ID duy nhất, **A20 trong/B20 trong/C20 ngoài**, đúng nguồn/hash, toàn tuyến thuần nhóm, liên tục và đúng hướng/rẽ. Mục tiêu RC của một tuyến không đồng nghĩa toàn tuyến chỉ có một loại đường.

Hình học và chuỗi cung/neo được lưu cùng bộ 60. Trạng thái `geometry_quota_achieved_pending_validation` nói đã đủ quota hình học, phần xác minh thực địa vẫn còn.

### 5.7. Notebook 06 — chọn 30, đọc điểm và chuẩn bị khảo sát

Tệp: [.../work/notebooks/06_select_30_routes.ipynb](notebooks/06_select_30_routes.ipynb).

**Đầu vào:** `latest_sampling_abc.json` và [.../work/config/selection_30.json](config/selection_30.json).

1. Chạy thiết lập và đọc cấu hình. `parent_report` phải là `reports/sampling/latest_sampling_abc.json`.
2. Chạy preflight kiểm bundle 60, nguồn/hash, quota và runtime.
3. Chạy lựa chọn với `force=False`; cell tiếp tục cũng dùng giá trị này.
4. Xem bảng **thực tế** từ `selected_routes.csv`: 30 ID duy nhất, **18 trong/12 ngoài**, giao chéo **A-trong 10/B-trong 8/C-ngoài 12**.
5. Xem biến thô/mô hình/X chuẩn hóa, điều kiện G1–G6, phân loại toàn bộ 60 và 30 dự phòng.
6. Xem lịch sử lựa chọn, swap, độ nhạy, ma trận mạng–mẫu và checklist khảo sát.
7. Notebook 09 tự chạy độ nhạy mở rộng sau khi chọn 30 và xem kết quả ở mục 4; mục 7a–7c notebook 06 dùng để chạy riêng bằng Python + NumPy. Chạy lại cùng cell để tiếp tục cache từng kịch bản. Đọc [work/docs/lez/SENSITIVITY.md](docs/lez/SENSITIVITY.md) và `work/reports/selection/latest_sensitivity.json`; kết quả giả lập không cập nhật thực địa hoặc tự thay bộ 30.

Cell kiểm quota kiểm CSV thật, không chỉ in mục tiêu từ cấu hình. Trạng thái cần đọc là `proposed_for_survey`; `measurement_verified=false` hiện vẫn đúng.

`final_context_score` đánh giá tuyến trong bối cảnh tập cuối; `score_at_greedy_selection` là điểm lúc tuyến được chọn trong vòng greedy. Không so hai cột như cùng một bảng xếp hạng tĩnh.

### 5.8. Notebook 07 — bằng chứng và cập nhật sau khảo sát

Tệp: [.../work/notebooks/07_field_workflow.ipynb](notebooks/07_field_workflow.ipynb). Tạo/mở chiến dịch, biểu mẫu và registry; nhập CSV quan sát, kiểm đơn vị/ngày/chứng cứ, lập kế hoạch cập nhật hoặc thay tuyến, rồi chấm lại trên overlay riêng. Cập nhật phải giữ quota và tính lại chỉ tiêu toàn bộ 30. Không nhập trực tiếp vào CSV trong bundle đã hash.

Khi chưa có bằng chứng, trạng thái tiếp tục chờ; công cụ không tự gán G1/G4/G5/G6/C6 là đạt. Xem [workflow thực địa](docs/lez/FIELD_WORKFLOW.md).

### 5.9. Notebook 08 — chuyến/GPS và chỉ tiêu vận hành

Tệp: [.../work/notebooks/08_process_measurements.ipynb](notebooks/08_process_measurements.ipynb). Chuẩn bị schema CSV, nhập `trips.csv`/`gps_points.csv`, kiểm đơn vị/thời gian/GPS, ghép hành lang có hướng và tính chỉ tiêu/T5. Ghi `route_id`, `trip_id`, thiết bị và điều kiện theo biểu mẫu; không đổi tên cột tùy ý.

Giữ đo thử, ví dụ giả và khảo sát chính theo nhãn riêng. Đầu vào trống không tạo chuyến đo. Xem [GPS/QC](docs/lez/TRIP_PROCESSING.md), [T3](docs/lez/SURVEY_COVERAGE.md), [T5](docs/lez/OPERATING_METRICS.md).

### 5.10. Notebook 09 — điều phối các bước hiện có

Tệp: [.../work/notebooks/09_automate_project.ipynb](notebooks/09_automate_project.ipynb). Chạy cell thiết lập → kiểm tra → chạy toàn bộ → xem tiến độ. Bộ điều phối dùng cache 60/30, chạy độ nhạy mở rộng, bản đồ, biểu mẫu/bằng chứng/cập nhật, T2, dữ liệu thực và T3/T5. Nguồn mạng/cache chuẩn hóa và runtime GIS phải có trước.

Ở mục 2, `MEASUREMENTS_DIR = None` dùng thư mục từ `config/trip_processing.json`; hoặc chọn một thư mục chứa `trips.csv` và `gps_points.csv`. Mục 8/9 dùng lại nguồn này qua `T3_MEASUREMENTS_DIR` và `T5_MEASUREMENTS_DIR`; sau khi đổi nguồn, chạy lại các cell phụ thuộc hoặc restart từ đầu. `OBSERVATIONS_CSV` là nguồn bằng chứng quan sát riêng.

Mục 4 xem độ nhạy; mục 7 T2; mục 8 T3; mục 9 T5. Chưa có dữ liệu/bằng chứng thì báo chờ, không tính là khảo sát xong. Xem [điều phối](docs/lez/PROJECT_AUTOMATION.md).

### 5.11. Notebook 10 — M0, 1.000 bộ ngẫu nhiên

Tệp: [.../work/notebooks/10_random_baseline.ipynb](notebooks/10_random_baseline.ipynb). Chọn Python thường, chạy từ trên xuống: kiểm dữ liệu/hash → bốc và đánh giá → đọc thống kê → xem biểu đồ/CSV. Không gọi HTTP hoặc khởi động QGIS; cần bundle mạng, pool 60, bộ 30 và gate tương ứng đã lưu.

Mỗi bộ gồm A-trong 10/B-trong 8/C-ngoài 12; không lặp ID trong bộ. Loại toàn bộ bộ vi phạm điều kiện chung rồi bốc lại đến đủ 1.000 bộ hợp lệ. Không ép số ô vật chất, không tối ưu D và không loại các bộ giống nhau giữa các lần bốc độc lập.

Số bộ/seed ở `config/selection_random.json`; lưu checkpoint mỗi 100 bộ hợp lệ, dùng lại cache khi hash đạt. Chạy lại cùng lệnh để tiếp tục. Đổi cấu hình tạo phiên bản khác. Xem [protocol M0](docs/lez/RANDOM_BASELINE.md) và [kết quả lưu trên GitHub](docs/results/M0_2026_11_02.md).

### 5.12. Notebook 11 — biểu đồ so sánh các bộ 30

Tệp: [.../work/notebooks/11_random_comparison_plots.ipynb](notebooks/11_random_comparison_plots.ipynb). Dùng **Python thường** có pandas, NumPy, Matplotlib và Seaborn; không cần kernel PyQGIS. Chạy từ trên xuống: chọn nguồn/tham số → kiểm hash và đọc M0 → xem thống kê/bảng khoảng D → vẽ hai hình → xuất PNG/SVG và bảng.

- `SOURCE="auto"` ưu tiên `reports/selection/latest_random_baseline.json` khi có; nếu con trỏ không tồn tại thì đọc bản công bố ngày 02/11/2026. Có con trỏ nhưng dữ liệu hỏng hoặc bộ 30 tại máy đã đổi thì dừng để kiểm tra, không âm thầm chuyển bản cũ. `SOURCE="published"` dùng bản công bố có nhãn phiên bản riêng.
- `BIN_WIDTH=0.02` chia D thành các khoảng rộng 0,02; có thể dùng 0,05. `HIST_STAT` chọn `"count"` hoặc `"percent"`. Khoảng chỉ để trình bày, không phải ngưỡng đạt.
- `X_METRIC="unique_rc_coverage_fraction"` vẽ D theo độ phủ RC không trùng (%); dùng `"traversed_length_m"` để vẽ theo tổng lượt đi (km). `FIT_LINE=True` vẽ đường hồi quy mô tả chỉ từ các bộ ngẫu nhiên; bộ đã chọn là điểm tham chiếu, không tham gia khớp.
- Xuất dưới `work/reports/selection/plots/<hash>/`, tách khỏi nguồn M0. Sau khi đổi tham số, chạy lại các cell phụ thuộc hoặc Run All trước khi xuất. Bản M0 trong repo đọc được sau clone mà không có graph/GIS.

Notebook 09 giữ vai trò điều phối; notebook 10 tạo/tiếp tục M0; notebook 11 đọc và trình bày kết quả. Xem [hướng dẫn biểu đồ](docs/lez/RANDOM_COMPARISON_PLOTS.md).

<a id="terminal"></a>

## 6. Các lệnh Terminal tương ứng

**Tất cả lệnh dưới đây chạy từ `.../work`.** Nếu dùng môi trường `.venv` tùy chọn, kích hoạt nó trước. Terminal `python3` và kernel notebook có thể là hai interpreter khác nhau.

### 6.1. Kiểm tra/xem trạng thái, không gửi API

~~~bash
python3 scripts/overpass/download_tiles.py check
python3 scripts/overpass/download_tiles.py status
python3 scripts/overpass/audit_download.py
python3 scripts/lez/pipeline.py check --work .
python3 scripts/lez/normalization_2030.py status --work .
python3 scripts/lez/sampling_abc.py check --work .
python3 scripts/lez/sampling_abc.py status --work .
python3 scripts/lez/selection_30.py preflight --work .
python3 scripts/lez/selection_30.py status --work .
python3 scripts/lez/project_automation.py status --work .
python3 scripts/lez/selection_random.py preflight --work .
python3 scripts/lez/selection_random.py status --work .
~~~

`audit_download.py` **ghi lại báo cáo kiểm tra**, không gửi HTTP. Các lệnh kiểm tra có thể đọc nhiều tệp và tính hash; thời gian im lặng ngắn không tự là lỗi. Kiểm tra trạng thái sau khi một lượt xử lý kết thúc, tránh mở hai quy trình cùng sửa dự án.

### 6.2. Tiếp tục tải khi có ô cần xử lý

~~~bash
python3 scripts/overpass/download_tiles.py run --interval 15 --max-attempts 3
~~~

Đây là lệnh có thể gửi API. Giữ endpoint/snapshot/query từ dự án; không cần viết lại bbox. Chạy `check` trước và `status`/`audit_download.py` sau. Cache hợp lệ được dùng lại.

### 6.3. Xử lý lại từ nguồn đã lưu

Chạy **từng lệnh**, chỉ sang bước sau khi bước trước hoàn thành và báo cáo đạt điều kiện đầu vào:

~~~bash
python3 scripts/lez/pipeline.py run --work . --stage network --no-fetch-sources
python3 scripts/lez/normalization_2030.py run --work .
python3 scripts/lez/sampling_abc.py run --work .
python3 scripts/lez/selection_30.py run --work .
~~~

Lệnh `normalization_2030.py run` dựng **cache phụ trợ/lịch sử**, không phải thay định nghĩa LEZ-first; có thể bỏ qua nếu cache phụ trợ hợp lệ. Phần LEZ-first hiện hành được kiểm ở notebook 03 và được module sinh 60 dựng theo cấu hình. Không thêm `--force` cho một lần tiếp tục thông thường. Lệnh `normalization_2030.py run` mặc định không fetch; chỉ thêm `--fetch` khi đã chủ động cần bổ sung nguồn dân cư/hoạt động. Lệnh `pipeline.py run` không ghi `--stage` sẽ mặc định `all`; vì vậy dùng đầy đủ câu lệnh mạng ở trên.

Các lệnh `run` là controller gọi runtime đã đăng ký. `build`, `export`, `precompute` hoặc `--worker` ở một số module là nhánh xử lý chuyên sâu, có thể đòi hỏi PyQGIS trực tiếp; không dùng chúng thay cho `run` bằng Python thường.

### 6.4. Xuất lại bản đồ 30/60

Sau khi 05/06 hoàn thành, chạy cell này trong notebook đã có `WORK` và đường dẫn import `scripts`:

~~~python
from lez.export_route_maps import export_maps

MAP_RESULT = export_maps(WORK)
print(MAP_RESULT)
~~~

Hoặc từ Terminal tại `.../work`:

~~~bash
python3 - <<'PY'
from pathlib import Path
import sys
work = Path.cwd()
sys.path.insert(0, str(work / "scripts"))
from lez.export_route_maps import export_maps
print(export_maps(work))
PY
~~~

Hàm điều khiển chạy phần vẽ bằng runtime PyQGIS và xuất vào `.../work/maps/routes`. Module bảo vệ hash các nguồn và mở bản sao GeoPackage để vẽ. Không gọi trực tiếp file `export_route_maps.py` bằng Python thường, vì CLI của tệp đi thẳng vào phần PyQGIS.

### 6.5. Kiểm tra mã khi bạn sửa logic

~~~bash
python3 tests/overpass/test_download_tiles.py
PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_*.py'
~~~

Nhánh Overpass dùng HTTP giả lập. Các kiểm tra LEZ xác minh quy tắc, ma trận, chọn tuyến và dữ liệu kiểm thử; không thay thế kiểm tra bundle thực tế hoặc khảo sát. Dùng interpreter có các thư viện cần thiết. Nếu một kiểm tra GIS báo thiếu `qgis`, thực hiện bằng môi trường PyQGIS theo tài liệu cài đặt.

Muốn xem tham số mà không thực hiện xử lý, thêm `--help` vào tệp CLI, ví dụ `python3 scripts/lez/selection_30.py --help`.

### 6.6. Điều phối và đối chứng M0

Chỉ chạy `project_automation` khi đã có các nguồn/bundle và runtime cần thiết. M0 chạy độc lập bằng Python thường:

~~~bash
python3 scripts/lez/project_automation.py check --work .
python3 scripts/lez/project_automation.py run --work .
python3 scripts/lez/selection_random.py preflight --work .
python3 scripts/lez/selection_random.py run --work .
python3 scripts/lez/selection_random.py status --work .
~~~

M0 không có tùy chọn `--force`; đầu ra hoàn tất được kiểm hash trước khi dùng lại. `max_attempts` đếm cả bộ bị loại; nếu hết lượt mà chưa đủ 1.000 bộ thì không công bố báo cáo hoàn tất.

<a id="dau-ra"></a>

## 7. Tìm và đọc đúng đầu ra hiện hành

### 7.1. Đừng chép cứng tên thư mục phiên bản

Các kết quả nằm dưới:

~~~text
.../work/data/processed/network/<version>/
.../work/data/processed/normalization_2030/<version>/
.../work/data/processed/sampling_abc/<version>/
.../work/data/processed/selection_30/<version>/
.../work/data/processed/selection_random/<version>/
~~~

`<version>` là ký hiệu minh họa cho thư mục hash, không phải thư mục tên thật để bạn tạo. Dùng trường `paths` của báo cáo hiện hành, không chọn thư mục theo tên lớn nhất hoặc ngày sửa mới nhất.

Cell thiết lập gọn sau dùng được khi kernel có thư mục làm việc ở `.../work` hoặc bên trong nó. Notebook hiện tại đã có cell tương ứng, nên **không bắt buộc chèn lại**:

~~~python
from pathlib import Path
import json
import sys
import pandas as pd
from IPython.display import display

cwd = Path.cwd().resolve()
WORK = next(
    (p for p in (cwd, *cwd.parents)
     if (p / "config/selection_30.json").is_file()
     and (p / "scripts/lez").is_dir()),
    None,
)
if WORK is None:
    raise FileNotFoundError("Mở workspace .../work và chạy lại cell thiết lập.")
if str(WORK / "scripts") not in sys.path:
    sys.path.insert(0, str(WORK / "scripts"))
from lez.common import input_path
~~~

Đọc bộ 30 và kiểm quota từ CSV:

~~~python
REPORT = json.loads(
    (WORK / "reports/selection/latest_selection_30.json").read_text(encoding="utf-8")
)
SELECTED = pd.read_csv(input_path(WORK, REPORT["paths"]["selected_routes"]))
display(SELECTED[["route_id", "sampling_zone", "group", "length_m", "street_sequence"]])
print("Số tuyến:", len(SELECTED))
print("LEZ:", SELECTED["group"].value_counts().to_dict())
print("ABC × LEZ:", SELECTED.groupby(["sampling_zone", "group"]).size().to_dict())
~~~

Đọc bộ 60 và biến toàn bộ ứng viên:

~~~python
SAMPLING = json.loads(
    (WORK / "reports/sampling/latest_sampling_abc.json").read_text(encoding="utf-8")
)
CANDIDATES = pd.read_csv(input_path(WORK, SAMPLING["paths"]["route_csv"]))
VARIABLES = pd.read_csv(input_path(WORK, REPORT["paths"]["variables"]))
print("60 ứng viên:", CANDIDATES["sampling_zone"].value_counts().to_dict())
display(VARIABLES.head())
~~~

`input_path` xử lý tiền tố `work/` trong báo cáo. Nếu nối thẳng `WORK / "work/data/..."`, bạn sẽ tạo đường dẫn sai dạng `.../work/work/data/...`.

### 7.2. Bộ 60: các tệp quan trọng

Các tên sau nằm trong bundle từ `latest_sampling_abc.json`:

| Tệp | Khi nào đọc? |
|---|---|
| `candidate_routes.csv` | ID, ABC, LEZ, RC mục tiêu, chiều dài và thông tin quota |
| `candidate_routes.gpkg` | Hình học 60 tuyến và các điểm neo |
| `candidate_walks.json`, `route_arcs.csv` | Chuỗi đoạn/cung và thứ tự đường đi |
| `anchors.csv` | Tọa độ điểm neo; chưa tự là điểm dừng an toàn |
| `network_matrix.csv`, `sample_matrix.csv` | Cơ cấu mạng/mẫu ở 12 ô ABC×RC |
| `fine_network_matrix.csv` | Đối chiếu ABC×V/N×LEZ×RC chi tiết |
| `route_overlap.csv`, `overlap_review.json` | Trùng đoạn/hành lang và các cặp cần rà soát |
| `sampling_zones.gpkg`, `abc_boundaries.gpkg` | Vùng lấy mẫu và hình học vành đai |
| `network_parts.gpkg`, `connector_summary.csv` | Phần mạng sau overlay, đường nối tách riêng |
| `failed_targets.json`, `candidate_report.json` | Lý do thiếu tuyến và tổng kết sinh |
| `manifest.json` | Tính hoàn chỉnh, fingerprint và hash đầu ra |

### 7.3. Bộ 30: các tệp quan trọng

Các tên sau nằm trong bundle từ `latest_selection_30.json`:

| Tệp | Khi nào đọc? |
|---|---|
| `selected_routes.csv` | Bộ 30, biến và điểm trong bối cảnh cuối |
| `candidate_classification.csv` | Đánh giá toàn bộ 60, cờ được chọn và điều kiện |
| `reserve_routes.csv` | 30 còn lại, gợi ý thay và D nếu thay |
| `selected_routes.gpkg` | Tuyến được chọn, dự phòng, toàn bộ đánh giá, neo |
| `selected_route_arcs.csv`, `selected_walks.json` | Chuỗi đường đi để đối chiếu khi khảo sát |
| `route_variables.csv`, `route_variables.gpkg` | Biến thô, mô hình, cờ thiếu và biến GIS |
| `variable_units.json`, `feature_normalization.json` | Đơn vị, mẫu số, min/max và mô hình dùng khi chấm |
| `X_standardized.csv` | Chín biến X chuẩn hóa dùng so sánh |
| `gate_checks.json` | Kiểm quyền OSM, graph/hướng/rẽ và thuần vùng |
| `network_sample_matrix.csv` | Cơ cấu mạng–mẫu, D/độ phủ và ô có đóng góp |
| `selection_history.csv/json`, `seed_runs.json` | Lịch sử greedy và các khởi tạo |
| `swaps.csv` | Các đổi tuyến được chấp nhận |
| `sensitivity.csv/json`, `selection_frequency.csv` | Độ nhạy và mức tuyến được chọn qua kịch bản |
| `saturation.csv` | Chẩn đoán lợi ích tăng thêm theo số tuyến |
| `field_checklist.csv` | Việc phải kiểm trên từng tuyến trước đo/khóa cuối |
| `manifest.json` | Kiểm hoàn chỉnh và hash |

### 7.4. Liên kết ổn định và các tệp dễ nhầm

Các liên kết đang công bố đúng bộ ABC/30:

- `.../work/data/processed/network.gpkg`
- `.../work/data/processed/motorcycle_graph.json.gz`
- `.../work/data/processed/sampling_abc.gpkg`
- `.../work/data/processed/network_parts_abc.gpkg`
- `.../work/data/processed/candidate_routes_abc.gpkg`
- `.../work/data/processed/selected_routes_30.gpkg`

**Lưu ý cụ thể của cấu trúc hiện tại:**

| Tên/hồ sơ | Cách hiểu |
|---|---|
| `candidate_routes_2030.gpkg` | Alias tương thích hiện trỏ bộ ABC; ưu tiên tên `candidate_routes_abc.gpkg` |
| `sampling_2030.gpkg`, `network_parts_2030.gpkg` | Hiện còn trỏ bundle thiết kế trước; lấy chuẩn hóa hiện hành từ `latest_normalization_2030.json["paths"]` |
| `zones.gpkg`, `zones_draft.gpkg`, `boundary_project.json` | Hồ sơ ranh giới/quy trình A/C cũ; không thay lớp ABC/LEZ nghiên cứu hiện hành |
| `latest_pipeline.json`/`latest_stage_a.json` có `needs_input` hoặc `stage_a_complete=false` | Có thể thuộc hồ sơ A/C cũ; đọc đúng báo cáo chuẩn hóa/ABC/30 trước khi kết luận dự án lỗi |
| `1_download_osm.ipynb`, `01_overpass_api_download.ipynb` trong tài liệu cũ | Tên lịch sử; notebook đang dùng là `01_download_osm.ipynb` |
| Bộ 30 12 trong/18 ngoài, bộ 60 20 trong/40 ngoài, kết quả 55/60 ô | Kết quả thiết kế trước; không dùng làm mục tiêu/tiến độ ABC mới |

Giữ các bộ cũ để đối chiếu. Không chép CSV lịch sử vào nguồn hiện hành hoặc sửa tên/nhóm thủ công để làm quota đạt.

### 7.5. Đầu ra M0, độ nhạy và chuyến đo

| Báo cáo hiện hành tại máy | Cách đọc |
|---|---|
| `reports/selection/latest_random_baseline.json` | `valid_samples`, `attempts`, bộ bị loại, seed, phân phối D và `paths` |
| `reports/selection/latest_sensitivity.json` | Số kịch bản hoàn thành/thiếu quota và bộ gốc dùng so sánh |
| `reports/field/latest_survey_revision.json` | Overlay bằng chứng, cập nhật/chọn lại và trạng thái khóa kỹ thuật |
| `reports/trips/latest_real.json` | Chuyến/điểm thực, QC và chỉ tiêu vận hành |
| `reports/field/latest_survey_coverage.json` | Tổ hợp đã có chuyến đạt điều kiện và lý do chưa được đếm |

Bundle M0 có `random_sets.csv/json` (30 ID/chỉ tiêu từng bộ), `metric_summary.csv`, `route_frequency.csv`, `D_distribution.png`, protocol/hash và checkpoint. Bản chọn ngày 02/11 có ở [docs/results](docs/results/M0_2026_11_02.md), đọc được sau clone; nó không thay con trỏ `latest` tại máy.

<a id="ban-do"></a>

## 8. Xem dữ liệu trong QGIS và bản đồ tuyến

### 8.1. Bản đồ nhanh

Trong `.../work/maps/routes`:

| Tệp | Nội dung |
|---|---|
| `30_tuyen_LEZ2030.html` / `.png` | 30 tuyến được đề xuất, tên tuyến/đường, ABC và LEZ |
| `60_tuyen_LEZ2030.html` / `.png` | 60 ứng viên |
| `30_tuyen_danh_sach.csv`, `60_tuyen_danh_sach.csv` | Danh sách tiện đọc đối chiếu bản đồ |
| `route_maps_manifest.json`, `export_check.json` | Nguồn, hash, kết quả xuất và kiểm không sửa nguồn |

CSV ở `maps` là bản xuất phục vụ xem. CSV trong bundle và báo cáo `latest` mới là nguồn cho logic chọn tuyến. Sau khi sửa cấu hình/chọn lại, xuất lại bản đồ để chúng cùng phiên bản.

### 8.2. Xem trong QGIS mà giữ nguyên bundle nguồn

QGIS/OGR có thể ghi metadata vào GeoPackage trong một số thao tác đọc/lọc. Để giữ hash của bundle, **tạo bản sao các tệp cần xem** trước khi thêm vào QGIS. Cell tùy chọn, chạy sau cell thiết lập có `WORK`:

~~~python
import shutil

VIEW_DIR = WORK / "data/inspection/qgis_view"
VIEW_DIR.mkdir(parents=True, exist_ok=True)
for filename in (
    "sampling_abc.gpkg",
    "candidate_routes_abc.gpkg",
    "selected_routes_30.gpkg",
):
    shutil.copy2(WORK / "data/processed" / filename, VIEW_DIR / filename)
print("Đã tạo bản xem tại .../work/data/inspection/qgis_view")
~~~

`data/inspection/qgis_view` được tạo bởi cell này, không phải nguồn xử lý. Khi cần kiểm mạng, sao chép thêm `network.gpkg`; tệp mạng có thể lớn hơn nhiều so với bộ tuyến.

Trong QGIS:

1. Mở **Browser → thư mục bản sao**, kéo GeoPackage vào bản đồ.
2. Chọn lớp theo bảng dưới.
3. Bật nhãn theo `route_id`; phân loại màu theo `group` hoặc `sampling_zone`.
4. Mở bảng thuộc tính để đối chiếu chiều dài/RC/điểm; dùng **Zoom to Layer** nếu không thấy dữ liệu.
5. Đặt CRS dự án EPSG:3405 khi kiểm chiều dài/diện tích. Nếu tự cắt/overlay trên bản sao, tính lại chiều dài hình học trong CRS mét.
6. Lưu dự án QGIS riêng, ví dụ `.../work/maps/routes/review_routes.qgz` do bạn tạo; không lưu sửa vào bundle nguồn.

| GeoPackage nguồn dùng để tạo bản sao | Lớp đáng xem |
|---|---|
| `sampling_abc.gpkg` | `hanoi`, `reference_lez_2030`, `sampling_inside`, `sampling_outside`, `abc_zones`, `strata`, `added_inside`, `removed_inside` |
| `candidate_routes_abc.gpkg` | `candidate_routes`, `anchors` |
| `selected_routes_30.gpkg` | `selected_routes`, `reserve_routes`, `candidate_assessment`, `selected_anchors` |
| `network_parts_abc.gpkg` | `network_parts` |
| `network.gpkg` | `segments`, `scope_parts`, `nodes`, `controls`; bảng `arcs`, `restrictions`, `turn_rules` không phải lớp đường để vẽ |

Một tuyến có thể đi qua nhiều tên đường. `route_id` định danh tuyến nghiên cứu; `street_sequence` là chuỗi đường, không thay cho chuỗi cung hoặc hình học thật.

<a id="huong-dan-chay"></a>
### 8.3. T2 - Hướng dẫn chạy từng tuyến

Notebook 09 mục 7 gọi module T2 để xuất chỉ dẫn từ đúng chuỗi cung của bộ 30. Mở `work/maps/route_instructions/index.html` bằng trình duyệt để chọn vùng, xem từng bước, tải GPX hoặc in phiếu. Sơ đồ có mũi tên, điểm đầu/cuối, tọa độ và khoảng cách lũy kế.

```bash
python3 scripts/lez/route_instructions.py check
python3 scripts/lez/route_instructions.py run
python3 scripts/lez/route_instructions.py status
```

Đọc `work/reports/routes/latest_route_instructions.json` để tìm bundle hiện hành. Đường thiếu tên, nút nhiều nhánh, vòng xuyến/quay đầu và điểm dừng chưa xác minh được ghi riêng. Đây là chỉ dẫn dự kiến từ OSM; không phải dữ liệu chuyến đo hay xác nhận quyền lưu thông.

Chi tiết đầu vào, đầu ra, tiếp tục và phiên bản: [work/docs/lez/ROUTE_INSTRUCTIONS.md](docs/lez/ROUTE_INSTRUCTIONS.md).

### 8.4. T3 - Tổ chức và theo dõi khảo sát

Notebook 09 mục 8 đọc lịch, tiến độ và lý do từng chuyến chưa được đếm. Có 180 tổ hợp tuyến × khung giờ × ngày thường/cuối tuần; lịch hai lượt tạo 360 dòng đề xuất. Mục tiêu số chuyến/ngày mỗi tổ hợp vẫn để trống đến khi chốt thiết kế.

Chuẩn bị biểu mẫu bằng notebook 07 mục 1; ghi mã thiết bị, hướng chạy, loại ngày đã kiểm lịch, thời tiết, sự kiện và nhãn đo thử/khảo sát chính. Tệp đã có dữ liệu không tự bị viết lại để thêm cột. Sau khi nhập chuyến/GPS, chạy notebook 08 hoặc notebook 09 mục 2 rồi xem T3; dữ liệu chưa đủ chất lượng hoặc còn thiếu thông tin vẫn được giữ và báo lý do. G1/G4/G5/G6/C6 không tự đạt từ bảng này.

Xem [work/docs/lez/SURVEY_COVERAGE.md](docs/lez/SURVEY_COVERAGE.md). T3 theo dõi các tổ hợp khảo sát; đánh giá hội tụ và mức đủ dữ liệu thuộc T6.

### 8.5. T5 - Mở rộng chỉ tiêu vận hành

Notebook 09 mục 9 chạy RPA/PKE và SAFD từ cùng nguồn chuyến/GPS của bước kiểm tra dữ liệu thực; notebook 08 cũng có phần xem T5. Dùng trọng số thời gian/quãng đường đúng mẫu số, tách đo thử và khảo sát chính; không điền số đo từ OSM. Cấu hình công thức và lưới nằm ở `work/config/trip_processing.json`, phần `operating_metrics`, hiện ghi là đề xuất. Đầu vào trống vẫn chờ dữ liệu; năm ví dụ giả chỉ kiểm tra cách tính. Xem [work/docs/lez/OPERATING_METRICS.md](docs/lez/OPERATING_METRICS.md).

<a id="chi-tieu"></a>

## 9. Hiểu các biến, điều kiện và điểm chọn tuyến

### 9.1. RC, chiều dài và độ phủ

| Loại | Phân loại OSM trong dự án |
|---|---|
| RC1 | `primary`, `primary_link` |
| RC2 | `secondary`, `secondary_link` |
| RC3 | `tertiary`, `tertiary_link` |
| RC4 | `residential`, `unclassified` |
| Đường nối | Các phần đủ điều kiện còn lại, như service/living street; báo riêng, không tạo RC5 |

**Chiều dài mạng** đếm mỗi phần đường vật lý đủ điều kiện một lần, không nhân hai vì đường có hai cung ngược chiều. **Chiều dài tập tuyến để tính cơ cấu** cộng lượt đi RC; đoạn dùng trong hai tuyến được tính ở cả hai lượt. **Độ phủ chiều dài duy nhất** đếm phần đường chung một lần.

Với ô `(h,k)`, h là A/B/C, k là RC1–RC4:

~~~text
q(h,k)   = chiều dài mạng RC của ô / tổng chiều dài mạng RC
q_S(h,k) = chiều dài lượt đi RC của tập tuyến trong ô / tổng lượt đi RC của tập
D(S)     = 0,5 × tổng |q_S(h,k) − q(h,k)|
Độ phủ   = chiều dài RC duy nhất được tập tuyến chạm tới / chiều dài mạng RC
~~~

D càng nhỏ thì cơ cấu mẫu càng gần cơ cấu mạng theo chỉ tiêu này. **D không phải tỷ lệ đường đã khảo sát**. D trong/ngoài có mẫu số mạng/mẫu riêng từng nhóm LEZ. Đường nối được tách khỏi mẫu số RC của D.

Kết quả đã đối chiếu ngày 02/11/2026: D bộ 30 = **0,365187**; chiều dài lượt đi toàn bộ **274,031 km**, riêng RC **263,170 km**. Độ phủ RC duy nhất **240,899 km / 22.425,963 km = 1,074196%**; có tuyến ở **11/12 ô**, thiếu A×RC1. Đủ quota không tự chứng minh đại diện toàn diện. M0 có D trung bình **0,542052**, thấp nhất **0,414540**, 0/1.000 bộ có D ≤ bộ gốc; đây là đối chứng mô tả, không phải p-value bằng 0.

Ngưỡng `target_cell_min_fraction=0.3` là tỷ lệ chiều dài ô mục tiêu trong một tuyến, không phải yêu cầu phủ 30% mạng của ô đó.

### 9.2. Chín biến X và các cột dữ liệu thiếu

| Biến | Đơn vị/ý nghĩa | Điều cần phân biệt |
|---|---|---|
| `P_RC1`–`P_RC4` | Chiều dài RC / toàn chiều dài tuyến | Có đường nối thì tổng có thể nhỏ hơn 1 |
| `P_RC*_conditional_RC` | Chiều dài RC / chiều dài riêng RC1–RC4 | Tổng bằng 1 trên phần RC |
| `lanes` | Trung bình thẻ số làn OSM có trọng số chiều dài | Số làn toàn đường theo thẻ; trung bình có thể không nguyên; không chứng minh làn xe máy thực tế |
| `maxspeed` | Thẻ giới hạn tốc độ OSM, km/h | Không phải tốc độ chạy đo được |
| `junctions_per_km` | Nút giao bản đồ đã định nghĩa / km tuyến | Chỉ báo graph, chưa đồng nhất hoàn toàn với mọi nút giao thực địa |
| `signals_per_km` | Node tín hiệu OSM được tuyến đi qua / km | Chỉ báo bản đồ, chưa là kiểm đếm hiện trường |
| `P_oneway` | Tỷ lệ chiều dài có một hướng xe máy hiệu dụng theo graph | Tách khỏi `P_osm_oneway`, không chỉ đọc thẻ một chiều chung |

Vector X có 4 biến RC + số làn + giới hạn tốc độ + mật độ nút + mật độ tín hiệu + một chiều = **9 biến**. X chuẩn hóa min–max trên toàn bộ 60; biến hằng không đóng góp khoảng cách.

Thiếu thẻ OSM được giữ NULL/NaN. Các cột `lanes_known_length_fraction`, `maxspeed_known_length_fraction` cho biết phần chiều dài có thẻ. `lanes_scoring_model`, `maxspeed_scoring_model` là mô hình phục vụ chấm điểm, có cột tỷ lệ ước tính riêng; mô hình dùng median theo RC và fallback đã lưu.

Trong bộ 30 đã kiểm ngày 02/11: làn có 4 tuyến không có thẻ, 24 có một phần và 2 đủ thẻ theo chiều dài; maxspeed có 6 tuyến không có thẻ, 24 có một phần và 0 đủ thẻ. Đây là mức đầy đủ của bản đồ, không phải số thông số đã đo.

### 9.3. Điều kiện bắt buộc G1–G6

| Điều kiện | Phần tự động đã kiểm | Phần cần xác nhận tiếp |
|---|---|---|
| G1 — xe máy được đi | Xung đột access OSM đã biết, `G1_OSM` | Quyền pháp lý, biển báo, làn, khung giờ theo ngày khảo sát |
| G2 — liên tục/chiều/rẽ | Graph và chuỗi hình học thật | Đối chiếu thay đổi mới khi đi khảo sát |
| G3 — đúng phạm vi | Toàn tuyến đúng ABC và LEZ nghiên cứu đã lưu | Xác minh nguồn GIS pháp lý nếu cần kết luận pháp lý |
| G4 — ổn định | Chưa đủ bằng chứng công trình/phân luồng hiện tại | Rà công trình, cấm tạm, thay đổi hành lang |
| G5 — khả năng lặp | Chưa có quan sát lặp thực địa | Xem có đi/đo lặp trong điều kiện yêu cầu được không |
| G6 — an toàn neo/dừng | Có tọa độ neo, chưa xác nhận an toàn | Chỗ xuất phát/kết thúc/dừng thiết bị, quay đầu và tiếp cận |

`passed` trong tổng kết kiểm GIS không đồng nghĩa cả G1 pháp lý/G4/G5/G6 đã đạt. Đọc các cờ `legal_motorcycle_permission_verified`, `field_gates_verified`, `official_gis_verified` riêng.

### 9.4. C1–C7 và thuật toán chọn

| Tiêu chí | Ý nghĩa | Trọng số |
|---|---|---:|
| C1 | Tuyến mới giảm D của tập hiện tại bao nhiêu | 25% |
| C2 | Tuyến bổ sung phần cơ cấu còn thiếu, qua Gap | 15% |
| C3 | Bổ sung các nhóm phân vị đặc trưng chưa có | 15% |
| C4 | Hạn chế trùng phần đường với tuyến đã chọn | 15% |
| C5 | Tăng khác biệt trong không gian 9 biến X | 10% |
| C6 | Khả thi khảo sát thực địa, thang 0–5 | 10% |
| C7 | Bổ sung nhóm chính, nhóm/RC và ô có đóng góp mới | 10% |

C1–C5 được chuẩn hóa trên ứng viên khả dụng của **từng vòng**: lợi ích dùng `(x−min)/(max−min)`, chi phí dùng `(max−x)/(max−min)`. Tiêu chí hằng nhận 1 để giữ trọng số, không tạo khác biệt thứ hạng. C7 rubric 0–5 chia 5. Điểm tổng là `100 × Σ(w_c × z_c)`, với 25% viết dưới dạng 0,25.

C6 thô hiện **chưa biết**, giữ NULL. Giả định 2,5/5 chỉ dùng cho xếp hạng trước khảo sát, lưu riêng với khoảng điểm khi C6 thật thay đổi. Không điền 2,5 vào cột quan sát hoặc hiểu đó là xác nhận khả thi.

Thuật toán gồm khởi tạo → greedy có ràng buộc → tính lại lợi ích/điểm từng vòng → so các tập hoàn chỉnh → swap giảm D → kiểm độ nhạy. Quota đồng thời A10/B8/C12 và 18/12 được giữ. Đây là heuristic hữu hạn; không lấy top 30 từ bảng điểm tĩnh và không chứng minh tối ưu toàn cục.

Các giá trị overlap là chiều dài phần vật lý chung; ngưỡng 50% là cờ rà soát, ngưỡng và điều kiện hành lang còn phụ thuộc cấu hình. Đọc `overlap_review.json`, lịch sử và độ nhạy khi giải thích vì sao một tuyến không được giữ.

<a id="chay-lai"></a>

## 10. Đổi cấu hình, chạy lại và tiếp tục

### 10.1. Tệp cấu hình nào điều khiển việc gì?

| Tệp trong `.../work/config` | Việc điều khiển |
|---|---|
| `lez_policy.json` | Định nghĩa LEZ-first, nguồn chính sách và cờ không dịch ranh giới theo dân cư |
| `selection_random.json` | M0: số bộ hợp lệ, seed, số lần bốc tối đa, checkpoint và đối chiếu chiều dài phụ |
| `selection_sensitivity.json` | Các giả định độ nhạy trên pool cố định |
| `field_workflow.json`, `trip_processing.json` | Schema bằng chứng, `survey_design`/lịch T3, dữ liệu đo, QC và công thức T5 |
| `access_rules.json` | Quyền xe máy, loại đường loại trừ, xử lý conditional/barrier/rẽ |
| `sampling_boundary_policy.json` | Phạm vi nghiên cứu LEZ và chính sách phần sát ranh giới |
| `sampling_2030.json` | Nguồn dân cư/hoạt động, V/N và chuẩn hóa; không phải quota sinh ABC hiện hành |
| `ring_boundaries.json` | Proxy Vành đai 1/3, đường khép kín, vùng bất định |
| `sampling_abc.json` | 60 mục tiêu ABC, RC, chiều dài, neo và điều kiện sinh |
| `selection_30.json` | Nguồn 60, quota 18/12 và 10/8/12, C1–C7, trọng số, swap, độ nhạy |
| `boundary_sources.json`, `legal_pdf_sources.json` | Nguồn đối chiếu/lưu hồ sơ; không tự là đa giác LEZ đã xác minh |

Các dữ liệu dân cư/hoạt động trong chuẩn hóa là nguồn/mô hình theo phiên bản đã lưu, không tự trở thành quan sát thực địa trên từng tuyến.

**Quota hiện tại có kiểm tra cứng trong mã.** Nếu thật sự đổi A20/B20/C20 hoặc A10/B8/C12, chỉ sửa JSON là chưa đủ: phải cập nhật validator, test, notebook, tài liệu và xuất lại bộ phụ thuộc. Không chỉnh một CSV đầu ra để vượt kiểm tra.

### 10.2. Đổi đầu vào thì chạy lại từ đâu?

| Bạn thay đổi gì? | Trình tự cần xem xét chạy lại |
|---|---|
| Chỉ nội dung hướng dẫn hoặc cách xem bảng | Không cần dựng lại dữ liệu |
| Chỉ số bộ/seed M0 | 10; tạo bundle M0 khác, giữ bộ 30 |
| Chỉ cách vẽ/nhãn bản đồ | Xuất bản đồ |
| Trọng số hoặc chính sách điểm chọn 30 | 06 → xuất bản đồ → đối chiếu checklist |
| Mục tiêu RC/neo/chiều dài hoặc proxy vành đai ABC | 05 → 06 → xuất bản đồ |
| LEZ/V/N, quyết định sát ranh giới, nguồn dân cư/hoạt động | 03 → 05 → 06 → xuất bản đồ |
| Quyền xe máy, graph, hình học mạng | 04 → 03 → 05 → 06 → xuất bản đồ |
| Thay snapshot/raw OSM/query | Xây phiên bản nguồn nhất quán → kiểm/tải → 04 → 03 → 05 → 06 → bản đồ |

Sau khi thay pool hoặc bộ 30, chạy lại cả M0 và độ nhạy để đối chiếu đúng bộ gốc mới. Mỗi bước tự kiểm fingerprint/hash. Sau thay đổi, đọc lại báo cáo để xác nhận phiên bản mới; không giả định một báo cáo `latest` cũ tự phản ánh cấu hình vừa sửa.

### 10.3. Dừng và tiếp tục đúng cách

1. Dùng **Interrupt** trong notebook hoặc Ctrl+C ở Terminal.
2. Chờ tiến trình dừng, đọc trạng thái/lượt chạy.
3. Chạy lại từ cell thiết lập nếu kernel đã restart.
4. Dùng cùng cấu hình với `force=False`.
5. Chỉ bundle có manifest hoàn chỉnh/hash hợp lệ được dùng lại. Công việc chưa hoàn thành trong một giai đoạn có thể phải tính lại; đây không phải cơ chế tiếp tục đúng từng trạng thái tìm đường.

Nếu CSV còn pending nhưng cache hoàn chỉnh, downloader có thể khôi phục tiến độ; nếu CSV done nhưng cache hỏng/thiếu, downloader kiểm lại trước khi dùng. Không sửa `tiles.csv` và `tiles_history.json` riêng lẻ hoặc sửa hash trong manifest để “làm khớp”.

`force=True`/`--force` dành cho chủ động tính lại, không phải bước bắt buộc để tiếp tục. Không chạy song song hai bộ tải hoặc hai pipeline cùng ghi vào dự án.

<a id="khao-sat"></a>

## 11. Chuẩn bị khảo sát và phần việc tiếp theo

### 11.1. Tạo bản checklist để nhập quan sát

`field_checklist.csv` trong bundle là đầu ra được hash. Tạo bản riêng để nhập thông tin; **không nhập trực tiếp vào bundle**.

Cell dưới dùng `WORK`, `REPORT`, `input_path` từ mục 7 và tạo thư mục nhập liệu mới:

~~~python
import shutil

FIELD_DIR = WORK / "data/field"
FIELD_DIR.mkdir(parents=True, exist_ok=True)
FIELD_CSV = FIELD_DIR / "field_checklist_30.csv"
if not FIELD_CSV.exists():
    shutil.copy2(input_path(WORK, REPORT["paths"]["field_checklist"]), FIELD_CSV)
    print("Đã tạo .../work/data/field/field_checklist_30.csv")
else:
    print("Đã có bản nhập liệu; giữ nguyên để không ghi đè quan sát.")
~~~

Giữ `route_id` để nối quan sát với bộ tuyến. Ghi ngày/người kiểm, chứng cứ, G1–G6, C6 0–5, làn/giới hạn tốc độ đã xác minh, quyết định và ghi chú. Dùng `survey_date` cho mốc khảo sát tuyến; nếu lưu thêm ngày từng lượt kiểm thì thống nhất ý nghĩa với cột `date`.

### 11.2. Thay bằng dự phòng

`reserve_routes.csv` là gợi ý, chưa phải danh sách thay tự động đã xác minh thực địa. Nếu một tuyến không đi được:

1. Ghi lý do và chứng cứ trong bản nhập liệu.
2. Chọn dự phòng cùng ô quota: A-trong thay A-trong, B-trong thay B-trong, C-ngoài thay C-ngoài.
3. Kiểm G1–G6 và hình học/neo của tuyến thay.
4. Tính lại quota, D, coverage, overlap, đa dạng của **toàn tập 30**, không chỉ điểm tuyến thay.
5. Lưu phiên bản lựa chọn mới và xuất lại bản đồ/checklist.

Notebook 07 và bước cập nhật trong 09 đã có nhập/kiểm bằng chứng, tạo overlay thuộc tính, chấm lại/chọn lại và snapshot khảo sát kỹ thuật khi đủ điều kiện. Công cụ không tự tạo chứng cứ hoặc phê duyệt pháp lý; phải dùng schema đúng và xem trạng thái khóa. Không sửa trực tiếp `selected_routes.csv`.

### 11.3. Các bước sau bộ 30 đề xuất

1. Khảo sát tuyến/neo, xác minh quyền đi, công trình, khả năng lặp, an toàn; cập nhật C6 và thuộc tính còn thiếu.
2. Tính lại lựa chọn khi chứng cứ buộc phải đổi tuyến, rồi khóa bộ và phiên bản chính sách.
3. Chốt mục tiêu số chuyến/ngày của lịch T3, phân công ngày/xe/người lái/thiết bị và tổ chức đo thử ngoài thực địa theo chuyên đề.
4. Thu chuỗi tốc độ–thời gian/GPS, giữ file gốc; ghi `trip_id`, `route_id`, thời gian đo, ABC, trạng thái LEZ ở ngày đo và `policy_version`.
5. Kiểm/làm sạch chuyến, map matching khi cần, tính chỉ tiêu vận hành thực đo.
6. Xây dựng, kiểm định hai chu trình lái và hoàn thiện báo cáo nghiên cứu.

`group` hiện mô tả **kịch bản 2030**, không phải xác nhận trạng thái chính sách ở mọi ngày đo. B có thể đổi trạng thái trước/sau mở rộng; A/C làm lõi trong/ngoài, B phục vụ bổ sung/so sánh theo thời điểm. Thẻ `maxspeed` OSM không thay chuỗi tốc độ thực đo.

<a id="loi"></a>

## 12. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm | Cách xử lý |
|---|---|---|
| M0 báo thiếu bundle/gate sau clone | Repo không chứa bundle GIS lớn | Khôi phục đúng mạng + pool 60 + bộ 30 + cache/nguồn phụ thuộc; đọc hướng dẫn máy mới |
| `dyld`, `Library not loaded`, kernel không khởi động | Interpreter còn nhưng framework/ứng dụng QGIS gốc đã mất/đổi đường dẫn | Khôi phục QGIS tương thích, kiểm Python đi kèm rồi đăng ký lại; dùng Python thường cho M0 |
| M0 `max_attempts` | Chưa bốc đủ số bộ hợp lệ trong giới hạn | Xem số bộ/bộ bị loại và điều kiện; định trước cấu hình lượt mới, không nới tiêu chuẩn sau khi xem D |
| Nhật ký tổng còn `running` từ ngày cũ | Lượt trước dừng hoặc nhật ký chưa cập nhật | Xem thời gian, bước cuối và trạng thái từng module; không coi là tiến trình đang chạy |
| `No module named 'qgis'` khi chạy 02 hoặc import `build_tiles` | Kernel không có PyQGIS | Chọn PyQGIS, restart, chạy lại từ thiết lập; tải HTTP vẫn giữ nhánh không import QGIS |
| Controller báo không tìm thấy kernel `pyqgis-423` | Runtime đăng ký mất hoặc interpreter đã chuyển | Kiểm theo tài liệu setup, đăng ký lại, kiểm QGIS; sau đó chạy lại controller |
| `different Team IDs` khi import pyzmq | Native dependency và interpreter QGIS gốc không tương thích chữ ký | Dùng runtime bản sao đã cấu hình bởi script setup; không tắt bảo vệ hệ thống |
| `No module named 'project_paths'`, `download_tiles`, `lez` | Bỏ cell thiết lập, sai workspace hoặc module đã nạp từ vị trí cũ | Mở `.../work`, restart, chạy cell đầu; Overpass cần `scripts/overpass`, LEZ cần `scripts` trong đường import |
| Pylance gạch đỏ nhưng cell chạy | Static analyzer khác kernel; không hiểu việc thêm đường dẫn ở runtime | Kiểm interpreter, `python.analysis.extraPaths` và workspace; phân biệt cảnh báo với traceback thực thi |
| Thiếu `pandas`, `numpy`, `requests` | Đang chọn môi trường Python thiếu thư viện | Dùng môi trường hiện có hoặc nhánh `.venv` ở mục 4; không cài lại PyQGIS chỉ vì thiếu một thư viện HTTP |
| Không tìm thấy dữ liệu dạng `.../work/work/...` | Nối tiền tố báo cáo sai | Dùng `input_path(WORK, value)` |
| Bundle/hash không khớp | Tệp nguồn/đầu ra đã bị sửa, ghi dở hoặc cấu hình thay | Đọc lỗi, khôi phục nguồn đúng hoặc dựng lại bước tương ứng; không sửa manifest để bỏ kiểm |
| Preflight 03 thiếu dân cư/hoạt động | Cache nguồn thiếu/hỏng/snapshot không nhất quán | Kiểm `data/raw/sampling`, `data/interim/sampling` và cấu hình; bổ sung nguồn có chủ đích trước chuẩn hóa |
| 429 | Server yêu cầu giảm tải/đợi slot | Giữ khoảng nghỉ, tôn trọng Retry-After/cooldown, tiếp tục bằng cache |
| 504/`heavy` | Server quá tải hoặc query thực sự quá nặng | Đọc lỗi, chờ server/ retry hữu hạn; chỉ split khi cần và đã dừng downloader |
| Bản đồ lưới có status khác CSV | Lớp/ảnh là bản xuất lúc tạo lưới | Lấy tiến độ từ CSV/lịch sử/audit |
| 03 có hồ sơ cũ chưa gán nhưng chuẩn hóa mới đã đủ | Đang đọc báo cáo/quy trình A/C cũ | Đọc `latest_normalization_2030.json` và review của notebook 03 |
| Kết quả nói 12 trong/18 ngoài hoặc 55/60 ô | Đọc bundle/tài liệu lịch sử | Kiểm `parent_report`, `latest_sampling_abc.json`, `latest_selection_30.json`; quota hiện tại là 18/12 và 10/8/12 |
| Chọn đủ 30 nhưng G4/G5/G6/C6 còn thiếu | Chọn trước khảo sát là hành vi hiện tại | Đi khảo sát/nhập quan sát; không gán “passed” giả để xóa cờ |
| PNG/HTML không khớp CSV mới | Bản đồ chưa xuất sau lần lựa chọn mới | Gọi `export_maps(WORK)`, kiểm manifest |

Với Pylance, các đường dẫn module dự án trong `.vscode/settings.json` có thể dùng `"${workspaceFolder}/scripts"` và `"${workspaceFolder}/scripts/overpass"` khi workspace là `.../work`; giữ các cấu hình thư viện QGIS cần thiết. Cấu hình phân tích tĩnh không tự đổi kernel hoặc cài module.

<a id="sao-luu"></a>

## 13. Sao lưu và chuyển thư mục

Ưu tiên giữ:

- `data/hanoi_tiles`: query, response, manifest, CSV, lịch sử và cấu hình tải.
- `data/raw`: tài liệu nghiên cứu/pháp lý, phản hồi nguồn bổ sung và manifest.
- `config`, `scripts`, `notebooks`, `docs`, `tests` và hướng dẫn này.
- Các bundle đang được báo cáo hiện hành tham chiếu, cùng `reports` và `maps/routes`.
- Bản nhập liệu/chiến dịch trong `data/field`, `data/measurements` và các thư mục đo riêng do bạn chọn.
- Bundle M0, checkpoint và báo cáo gốc nếu cần tái kiểm đúng lượt đã chạy. GitHub chỉ giữ bản kết quả M0 được chọn trong `docs/results`, không thay toàn bộ bản sao dữ liệu.

Khi sao lưu tệp alias trong `data/processed`, phải giữ cả bundle đích; chỉ sao chép symlink sẽ không đủ. Cách đơn giản là sao lưu toàn bộ `.../work` thay vì chọn vài CSV.

`backups` chứa phiên bản trước, không phải nơi mở notebook để làm việc hằng ngày. Có thể dọn các bản thừa sau khi đã có bản sao độc lập và biết nguồn hiện hành không phụ thuộc chúng. Không xóa `data/raw` hoặc bundle hiện hành vì tưởng là backup.

Nếu runtime được đặt ở `.../work/../.pyqgis-runtime`, nó không nằm trong bản sao chỉ gồm `work`. Khi chuyển máy/thư mục, giữ runtime phù hợp hoặc dựng lại theo mục 4, cài ứng dụng QGIS cần thiết và đăng ký lại kernel. Sau khi chuyển, restart kernel, kiểm đường import/settings và chạy preflight trước.

Notebook và tài liệu có thể dùng đường dẫn tương đối, nhưng kernelspec của Jupyter vẫn cần trỏ đúng interpreter thực tế. Không sửa đồng loạt tất cả đường dẫn trong dữ liệu gốc để “rút gọn” vị trí runtime.

<a id="checklist"></a>

## 14. Tài liệu chuyên sâu và checklist

### 14.1. Đọc thêm theo công việc

| Công việc | Tài liệu |
|---|---|
| Tổng quan / máy mới | [Tổng quan](docs/PROJECT_OVERVIEW.md), [máy mới](docs/setup/GETTING_STARTED.md), [mục lục](docs/README.md) |
| Biểu đồ D và hồi quy mô tả | [Notebook 11](notebooks/11_random_comparison_plots.ipynb), [hướng dẫn biểu đồ](docs/lez/RANDOM_COMPARISON_PLOTS.md) |
| M0 và kết quả lưu trong repo | [Hướng dẫn M0](docs/lez/RANDOM_BASELINE.md), [kết quả ngày 02/11](docs/results/M0_2026_11_02.md) |
| Điều phối / khảo sát / GPS / T5 | [Điều phối](docs/lez/PROJECT_AUTOMATION.md), [bằng chứng](docs/lez/FIELD_WORKFLOW.md), [GPS](docs/lez/TRIP_PROCESSING.md), [T3](docs/lez/SURVEY_COVERAGE.md), [T5](docs/lez/OPERATING_METRICS.md) |
| Cài/chọn kernel | [.../work/docs/setup/PYQGIS_SETUP.md](docs/setup/PYQGIS_SETUP.md) |
| Bộ tải và resume/lỗi/cache | [.../work/docs/overpass/DOWNLOAD_README.md](docs/overpass/DOWNLOAD_README.md) |
| Lưới tải và cấu trúc Overpass | [.../work/docs/overpass/README.md](docs/overpass/README.md) |
| Tổng quan GIS/ABC | [.../work/docs/lez/README.md](docs/lez/README.md) |
| Chuẩn hóa LEZ/V/N | [.../work/docs/lez/NORMALIZATION_2030.md](docs/lez/NORMALIZATION_2030.md) |
| Sinh 60 ABC | [.../work/docs/lez/SAMPLING_ABC.md](docs/lez/SAMPLING_ABC.md) |
| Chọn 30 và công thức chi tiết | [.../work/docs/lez/SELECTION_30.md](docs/lez/SELECTION_30.md) |
| Kế hoạch nghiên cứu tổng thể | [.../work/docs/plans/LEZ_python_direct_api_plan.md](docs/plans/LEZ_python_direct_api_plan.md) |
| Các tài liệu chuyên đề nguồn | `.../work/data/raw/research`, kèm `source_requirements.json` |

Một số tài liệu có phần lịch sử và lệnh chạy từ **thư mục chứa work**, khác các lệnh ở đây chạy **ngay trong work**. Đọc điều kiện thư mục trước khi chép lệnh. Phần lịch sử trong tài liệu chuẩn hóa/kế hoạch không thay thiết kế ABC ở đầu tài liệu này.

### 14.2. Checklist một lần làm việc thông thường

- [ ] Mở đúng `.../work`, notebook trong `notebooks`; chọn kernel.
- [ ] Restart nếu vừa chuyển thư mục/đổi kernel/sửa module; chạy cell thiết lập.
- [ ] Đọc các báo cáo hiện hành và cấu hình; xác nhận nguồn 60 là ABC.
- [ ] Nếu dùng kết quả có sẵn, xem bảng/bản đồ; nếu chạy lại, giữ `force=False`.
- [ ] Kiểm số thật: bộ 60 A20/B20/C20; bộ 30 A10/B8/C12, 18 trong/12 ngoài.
- [ ] Đối chiếu hình học, ma trận, biến thiếu, điều kiện và các giới hạn thực địa.
- [ ] Sau thay dữ liệu/chọn tuyến, xuất lại bản đồ và kiểm phiên bản.
- [ ] Nhập quan sát vào bản riêng; giữ nguồn gốc, ID, ngày đo và trạng thái chính sách.

### 14.3. Checklist trước khi coi bộ tuyến là cuối cùng

- [ ] Nguồn và hình học nghiên cứu phù hợp mục tiêu, các bất định được giải quyết hoặc ghi rõ.
- [ ] G1 pháp lý/G4/G5/G6 và C6 có chứng cứ thực địa trên từng tuyến.
- [ ] Thuộc tính làn/tốc độ/tín hiệu/nút được đối chiếu, quan sát tách khỏi mô hình.
- [ ] Sau thay tuyến, quota, D, độ phủ, overlap và đa dạng được tính lại.
- [ ] Bundle cuối, bản đồ, checklist và báo cáo cùng phiên bản.
- [ ] Có dữ liệu đo và kiểm định trước khi tuyên bố đã xây được chu trình lái.

**Dự án hiện đã có bộ 30 đề xuất để tổ chức khảo sát.** Hướng dẫn sử dụng tệp không thay thế phần kiểm tra thực địa, thu tốc độ–thời gian và xây dựng/kiểm định chu trình còn lại.
