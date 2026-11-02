# Bắt đầu trên máy mới

Repo gồm mã, notebook, cấu hình và tài liệu. `.../work` chỉ thư mục gốc repo; các lệnh dưới chạy ngay tại đó. Pipeline GIS có script cài runtime riêng cho **macOS, QGIS 4.2.3/Python 3.12**; chưa có bộ cài đã kiểm chứng cho mọi phiên bản/hệ điều hành.

## 1. Clone và chọn mục tiêu

```bash
git clone https://github.com/quanhhg/lez-road.git work
cd work
```

| Mục tiêu | Cần gì ngoài repo? | Đi tiếp |
|---|---|---|
| Đọc phương pháp/kết quả M0 | Không | [Tổng quan](../PROJECT_OVERVIEW.md), [kết quả M0](../results/M0_2026_11_02.md) |
| Kiểm lại thống kê M0 đã công bố | Python thường | Các CSV trong bản kết quả; không cần graph/GIS để đọc lại thống kê |
| Bốc lại M0 từ dữ liệu nguồn | Python + NumPy/Matplotlib và các nguồn/bundle tương ứng | Mục 2–3, rồi notebook 10 |
| Dựng lại hình học, ứng viên, chọn tuyến, bản đồ | Nguồn OSM/cache phụ trợ và runtime PyQGIS hoạt động | Mục 2–4, rồi hướng dẫn sử dụng |
| Xử lý đo thực tế | Bộ tuyến/corridor, schema và CSV thực | Notebook 07–09; không dùng ví dụ giả làm dữ liệu thật |

## 2. Tạo Python thường cho notebook

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-notebook.txt
python3 -m ipykernel install --user --name hanoi-work --display-name "Python (Hanoi work)"
```

Mở repo bằng VS Code, cài extension Python/Jupyter nếu chưa có, chọn kernel **Python (Hanoi work)**. Xem [hướng dẫn kernel của VS Code](https://code.visualstudio.com/docs/datascience/jupyter-kernel-management). Terminal và notebook có thể dùng hai interpreter khác nhau; kiểm `sys.executable` trong notebook.

`requirements-notebook.txt` liệt kê phụ thuộc, không khóa phiên bản. Lượt M0 được lưu ngày 02/11 dùng Python **3.14.2**, NumPy **2.4.4**, Matplotlib **3.11.0**. Chạy bằng phiên bản khác tạo fingerprint khác; khi cần lặp đúng lượt này, dùng thông tin trong [provenance](../results/m0_2026_11_02/provenance.json), không xem seed đơn lẻ là đủ tái lập.

Môi trường thường không có `qgis.core`. M0 không cần import QGIS; các controller có bước GIS vẫn cần worker PyQGIS bên ngoài.

## 3. Khôi phục hoặc dựng dữ liệu

Không có liên kết tải tự động một bản sao toàn bộ dữ liệu trong repo. Để tái lập kết quả đã lưu, dùng bản sao dữ liệu tương ứng của dự án và giữ cấu trúc dưới thư mục gốc; không dùng dữ liệu đo cá nhân của người khác làm ví dụ.

| Phần cần có tại máy | Mục đích |
|---|---|
| `data/hanoi_tiles`: CSV, query, response và manifest từng ô | Raw OSM theo cùng snapshot và kiểm tải |
| `maps/hanoi_tiles/hanoi_boundary.geojson` và nguồn liên quan | Hình học Hà Nội được các cấu hình tham chiếu |
| `data/raw/sampling`, `data/interim/sampling` khi được cấu hình tham chiếu | Nguồn/cache dân cư, hoạt động, địa bàn cho chuẩn hóa phụ trợ |
| `data/processed/network/<hash>` và các alias mạng/graph | Mạng xe máy và chuỗi cung |
| `data/processed/normalization_2030/<hash>` | Cache phụ trợ cần cho `sampling_abc`; không thay định nghĩa LEZ-first |
| `data/processed/sampling_abc/<hash>` | Pool 60, ma trận, overlap, walk và lớp mạng |
| `data/processed/selection_30/<hash>` | Bộ 30, gate, biến và manifest |
| Báo cáo `reports/network`, `reports/sampling`, `reports/selection` tương ứng | Định vị đúng phiên bản và kiểm chứng đầu vào |

M0 kiểm các bundle/hash và các tệp nguồn mà chúng tham chiếu, không chỉ một CSV 60 tuyến. Cách ít sai nhất là khôi phục nguyên bản sao dự án phù hợp rồi áp dụng mã nguồn; chỉ chép `candidate_routes.csv` hoặc các symlink không đủ. Các tài liệu nguồn nhỏ đã theo dõi có trong Git; kiểm lại hash thay vì tự thay bằng một bản cùng tên.

Các báo cáo có thể chứa đường dẫn `work/...` hoặc đường dẫn tuyệt đối của lần chạy cũ. `input_path` xử lý được tiền tố `work/`; đường dẫn tuyệt đối trên máy khác cần được xử lý bằng quy trình khôi phục/chạy lại phù hợp. Không sửa đồng loạt raw/manifest để bỏ kiểm hash. Nếu chưa có bản sao, dựng lại từng nguồn theo cấu hình; kết quả mới phải được coi là một lượt mới, không tự nhận giống lượt đã lưu.

Khi cần tải OSM từ đầu, dùng notebook 01 và [bộ tải](../overpass/DOWNLOAD_README.md): kiểm query, bbox, endpoint và snapshot trước khi `run`. Tích hợp hiện tại dùng Overpass HTTP đọc dữ liệu, không cần API key. Giữ retry/cooldown và tải tuần tự; không tải lại chỉ để chạy M0. [Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) là dịch vụ truy vấn đọc dữ liệu, khác API chỉnh sửa OSM.

## 4. Thiết lập runtime GIS khi cần

Đọc [PYQGIS_SETUP.md](PYQGIS_SETUP.md). Bản sao interpreter trong `.pyqgis-runtime` vẫn phụ thuộc ứng dụng QGIS gốc. Nếu chỉ còn kernelspec/interpreter mà ứng dụng hoặc framework đã mất, phải khôi phục ứng dụng tương thích rồi đăng ký lại.

```bash
python3 scripts/setup/setup_pyqgis_kernel.py --help
python3 scripts/setup/setup_pyqgis_kernel.py --project-dir .
```

Lệnh thứ hai chỉ áp dụng khi ứng dụng nằm đúng vị trí mặc định mà script hỗ trợ. Nếu vị trí khác, truyền `--qgis-app` với đường dẫn thực tế; kiểm Python 3.12/thư viện tương thích trước. Script không tự cài ứng dụng QGIS và không bảo đảm bản QGIS bất kỳ có cùng cấu trúc. Không dùng `pip install qgis` thay cho QGIS/PyQGIS.

Sau cài đặt, chọn kernel PyQGIS và kiểm `from qgis.core import Qgis`, phiên bản, Processing. Tài liệu [PyQGIS standalone](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/intro.html#using-pyqgis-in-standalone-scripts) giải thích vai trò thư viện/môi trường; thông số thực tế phải khớp ứng dụng của máy.

## 5. Kiểm trước khi xử lý

Từ gốc repo, trong Python thường:

```bash
python3 scripts/lez/selection_random.py preflight
python3 scripts/lez/selection_random.py run
```

Chỉ chạy `run` sau khi preflight đạt. Xem [M0](../lez/RANDOM_BASELINE.md) hoặc mở notebook 10. Thiếu bundle/hash là thiếu điều kiện dữ liệu, không phải yêu cầu cài API key hoặc tự thêm số vào CSV.

Muốn dựng mới, đi theo nguồn → **04 mạng → 03 phạm vi/cache phụ trợ cần thiết → 05 → 06**, rồi 10 hoặc 07–09. Notebook 09 cần mạng/cache chuẩn hóa trước, không tự bootstrap mọi nguồn sau clone. Phần chuẩn hóa V/N phụ trợ có thể cần nguồn ngoài OSM; đọc [hướng dẫn toàn bộ](../../HUONG_DAN_SU_DUNG_WORK.md).

Các lệnh `status` chỉ đọc báo cáo đã lưu, có thể hiển thị kết quả cũ; kiểm phiên bản/timestamp. Với thư mục đo riêng, đặt `MEASUREMENTS_DIR` trong notebook 09 và chạy lại các cell T3/T5 dùng cùng nguồn.

## 6. Kiểm thử và giới hạn tái lập

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_selection_random.py'
python3 tests/overpass/test_download_tiles.py
```

Các kiểm thử trên dùng dữ liệu giả lập, không gửi truy vấn tải OSM. Có thể kiểm toàn bộ nhánh LEZ bằng `PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_*.py'` từ gốc repo. Kiểm thử cần QGIS có thể bị bỏ qua khi chạy bằng Python thường. Phần GIS thật phải được kiểm riêng trong runtime thích hợp; test giả không xác nhận quyền lưu thông hoặc khảo sát đã hoàn tất.

Repo không kèm đầy đủ dữ liệu lớn, runtime hay mọi phiên bản thư viện. Hash/manifest chứng minh sự nhất quán của một bộ dữ liệu cụ thể, không chứng minh tính đúng pháp lý hoặc chất lượng thực địa. Dữ liệu nền: © OpenStreetMap contributors, theo [điều kiện OSM](https://www.openstreetmap.org/copyright).
