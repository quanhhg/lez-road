# M0: 1.000 bộ ngẫu nhiên để đối chứng bộ 30 hiện tại

Đọc ngay [kết quả và dataset ngày 02/11/2026](../results/M0_2026_11_02.md) trên GitHub. Nếu muốn tái chạy từ nguồn, xem [máy mới](../setup/GETTING_STARTED.md); clone mã nguồn chưa có đủ bundle GIS.

Chạy bằng **Python thường**, dùng NumPy; Matplotlib vẽ biểu đồ. Notebook cần thêm Jupyter/ipykernel của môi trường đang chọn. Bước M0 đọc dữ liệu đã lưu, không gọi lại API và không cần khởi động QGIS. Phải có các bundle mạng, 60 ứng viên, bộ 30 và gate đã kiểm tra trên máy; clone mã nguồn từ GitHub chưa có các bundle này.

Mở `.../work/notebooks/10_random_baseline.ipynb`, chọn kernel Python thường có NumPy/Matplotlib và chạy từ trên xuống. Hoặc chạy trong thư mục `.../work`:

```bash
python3 scripts/lez/selection_random.py preflight
python3 scripts/lez/selection_random.py run
python3 scripts/lez/selection_random.py status
```

Thiết lập ở `.../work/config/selection_random.json`: `valid_samples=1000`, `random_seed=20261102`, `max_attempts=1000000`, lưu checkpoint mỗi 100 bộ hợp lệ. Muốn đổi số bộ hoặc seed thì sửa cấu hình **trước khi chạy**; kết quả được đưa vào bundle có hash khác. Seed và dữ liệu/mã nguồn/môi trường giống nhau tái lập cùng chuỗi bộ mẫu.

## Quy trình

CLI M0 không có tùy chọn `--force`. Thay cấu hình/đầu vào/mã hoặc môi trường tạo fingerprint khác; bundle hoàn tất bị lỗi hash được giữ để kiểm tra. `--output-root` ghi kết quả tách riêng và không cập nhật con trỏ `latest` của dự án.

1. Kiểm tra hash các bundle cố định, graph và gate G2/G3 đã có. Đối chiếu lại tất cả chỉ tiêu bộ 30 từ dữ liệu nguồn.
2. Mỗi lần bốc độc lập 10 tuyến A trong LEZ, 8 tuyến B trong LEZ, 12 tuyến C ngoài LEZ, không lặp ID trong một bộ. Dùng đúng nhóm quota giao ABC × trong/ngoài LEZ, không suy diễn trong/ngoài chỉ từ chữ A/B/C.
3. Kiểm tra các điều kiện cứng chung: tuyến thuộc pool đã qua gate tiền khảo sát, đủ quota và tầng bắt buộc, trùng hành lang vật lý từng cặp **nhỏ hơn 0,7** theo cấu hình chọn 30. Nếu vi phạm thì loại **cả bộ** rồi bốc bộ khác. Không sửa bộ ngẫu nhiên bằng greedy, swap hay chọn D tốt nhất.
4. Giữ đủ 1.000 bộ hợp lệ. Bộ giống nhau giữa các lần bốc độc lập vẫn được giữ; báo thêm số bộ khác nhau. Loại trùng giữa các lần sẽ thay đổi thiết kế lấy mẫu. Nếu hết số lần bốc cho phép thì lưu trạng thái thiếu, không xuất báo cáo hoàn tất.
5. Tính D và các chỉ tiêu đúng bằng hàm đang dùng cho bộ 30; so sánh với bộ 30 cố định. Không buộc bộ ngẫu nhiên phải có 11 ô vật chất: số ô là kết quả cần đánh giá.

Việc bốc đều trong từng nhóm quota rồi loại toàn bộ bộ vi phạm tạo phân phối đều trên các bộ đáp ứng điều kiện cứng. Không dùng D, chiều dài, độ phủ hoặc độ đa dạng làm điều kiện nhận bộ. Vì có kiểm tra trùng hành lang, tần suất được chọn của từng tuyến sau khi loại có thể khác nhau.

## Chỉ tiêu và mẫu số

- `D_combined = 0,5 × Σ|q_i − p_i(S)|`, trên 12 ô ABC × RC1–RC4. `q_i` là chiều dài mạng đủ điều kiện của ô chia tổng chiều dài mạng RC1–RC4; `p_i(S)` là chiều dài theo lượt đi trong bộ 30 ở ô chia tổng chiều dài lượt đi RC1–RC4 của bộ. Loại connector khỏi D; phần dùng chung được đếm theo mỗi lượt đi. D càng nhỏ thì cơ cấu chiều dài càng gần mạng tham chiếu.
- D trong/ngoài dùng lớp giao LEZ tường minh và mẫu số riêng của từng miền, không lấy nhãn ABC thay miền LEZ.
- Độ phủ duy nhất: hợp các phần đường vật lý RC1–RC4, đếm một lần, chia tổng chiều dài mạng RC1–RC4 đủ điều kiện.
- Báo chiều dài toàn bộ lượt đi gồm connector, số ô vật chất, số nhóm phân vị đặc trưng, và trùng lặp lớn nhất theo lượt đi/hành lang duy nhất. Ngưỡng ô vật chất giữ nguyên cấu hình `minimum_cell_fraction` của bộ 30.

Phân phối có trung bình, độ lệch chuẩn, trung vị, min/max và các phân vị. Tỷ lệ `số bộ có D ≤ D_gốc / số bộ hợp lệ` là đối chứng thực nghiệm mô tả, **không phải p-value thông thường**. Bộ gốc đã được tối ưu trên cùng pool; kết quả không chứng minh tối ưu toàn cục hay đại diện cho mọi tuyến Hà Nội. Nếu quan sát 0/1.000, không kết luận xác suất bằng 0. Các phân vị mô tả phân phối bộ ngẫu nhiên, không phải khoảng tin cậy cho mạng Hà Nội.

Cấu hình còn định trước đối chiếu phụ trên các bộ có tổng chiều dài nằm trong ±10% bộ gốc. Đây là tập con để xem khác biệt chiều dài, không lọc khỏi 1.000 bộ chính. Báo rõ cỡ tập con; nếu không có bộ nào thì không tính tỷ lệ.

## Kết quả và chạy tiếp

Kết quả riêng ở `.../work/data/processed/selection_random/<hash>/`:

| Tệp | Nội dung |
|---|---|
| `random_sets.csv`, `random_sets.json` | ID của cả 30 tuyến và chỉ tiêu từng lần bốc hợp lệ; số lần bốc tích lũy |
| `metric_summary.csv` | Chỉ tiêu bộ gốc và thống kê phân phối M0 |
| `route_frequency.csv` | Số lần/tỷ lệ từng tuyến được chọn; có thuộc bộ gốc hay không |
| `D_distribution.png` | Histogram D, vị trí bộ gốc và quan hệ D–chiều dài |
| `REPORT.md`, `report.json` | Kết luận mô tả, số bộ hợp lệ/bị loại và giới hạn |
| `inputs.json`, `protocol.json`, `manifest.json` | Hash đầu vào/mã, phiên bản thư viện, seed, quy tắc và kiểm tra đầu ra |
| `checkpoint.json`, `progress.json` | RNG, kết quả đã nhận và tiến độ |

Con trỏ hiện hành: `.../work/reports/selection/latest_random_baseline.json`. Chạy lại cùng lệnh tự tiếp tục từ checkpoint; một lần ngắt có thể cần bốc lại phần sau checkpoint cuối, vẫn giữ cùng chuỗi ngẫu nhiên. Bundle hoàn chỉnh chỉ được dùng lại nếu hash hợp lệ. Bundle đã hoàn tất nhưng hỏng kiểm tra được giữ để xem xét, không tự ghi đè.

Bộ 30 gốc, raw OSM và các gate không bị cập nhật bởi M0. Đây chỉ là **M0**; chưa thay thế các đối chứng M1–M5, khảo sát thực địa hoặc kiểm tra đổi đa giác ranh giới. A×RC1 vẫn là giới hạn của pool cố định, không tự bổ sung bằng mô phỏng. Notebook 09 tiếp tục quy trình hiện có; M0 chạy riêng ở notebook 10.
