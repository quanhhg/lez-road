# Biểu đồ đối chứng các bộ 30 tuyến

[Notebook 11](../../notebooks/11_random_comparison_plots.ipynb) dành riêng cho việc đọc kết quả M0 và vẽ biểu đồ. Notebook 09 điều phối dự án; [notebook 10](../../notebooks/10_random_baseline.ipynb) bốc và đánh giá các bộ ngẫu nhiên. Tách phần vẽ giúp đổi khoảng D, trục X hoặc định dạng xuất mà không chạy lại GIS hay bốc mẫu.

## Chạy trong VS Code

1. Mở thư mục `work` và notebook 11.
2. Chọn Python thường có pandas, NumPy, Matplotlib và Seaborn, ví dụ kernel `Python (Hanoi work)`. Có thể dùng môi trường hiện tại nếu đủ thư viện; không cần cài lại. Máy mới dùng [hướng dẫn cài đặt](../setup/GETTING_STARTED.md) và `requirements-notebook.txt`.
3. Giữ `SOURCE="auto"`, chạy Run All. Notebook sẽ hiện rõ nguồn, fingerprint, thời điểm lượt M0 và bộ 30 được so sánh.
4. Xem thống kê, bảng khoảng D, hai biểu đồ và thư mục kết quả ở cell cuối. Sau khi đổi tham số, chạy lại từ cell đọc dữ liệu đến cuối hoặc Run All.

Notebook không import QGIS, không gọi Overpass, không bốc mẫu và không chấm/chọn lại 30 tuyến.

## Chọn đúng phiên bản nguồn

| SOURCE | Nguồn | Khi sử dụng |
|---|---|---|
| `"auto"` | M0 tại máy nếu có con trỏ; nếu không có mới đọc bản công bố | Mặc định |
| `"latest"` | `work/reports/selection/latest_random_baseline.json` và bundle được trỏ tới | Xem lượt M0 tại máy |
| `"published"` | `work/docs/results/m0_2026_11_02` | Đọc bản công bố cố định ngay sau clone; có nhãn lịch sử |

Module kiểm hash bundle/bản công bố, số bộ, các cột, quota và chỉ tiêu D so với báo cáo. Với nguồn tại máy, nếu có báo cáo chọn 30 hiện hành thì phải khớp bộ 30 của M0. Con trỏ tồn tại nhưng nguồn hỏng hoặc bộ 30 đã đổi sẽ báo lỗi, không tự chuyển sang bản cũ. Muốn xem lịch sử phải chọn `"published"` rõ ràng.

Đây là kiểm tra tính nhất quán của **kết quả dùng để vẽ**, không tái kiểm toàn bộ nguồn GIS, quyền lưu thông hoặc mọi cặp trùng hành lang. Bản công bố giữ thiết kế A10/B8/C12, seed và các điều kiện của lượt M0 gốc. Xem [protocol M0](RANDOM_BASELINE.md).

## Hình 1 — phân bố D theo khoảng

- `BIN_WIDTH=0.02` hoặc `0.05`: khoảng D cố định trên [0,1]. Các khoảng đóng bên trái, mở bên phải; khoảng cuối chứa cả D = 1.
- `HIST_STAT="percent"`: trục đứng là tỷ lệ phần trăm trên **tất cả bộ M0 hợp lệ**. `"count"` đổi sang số bộ.
- Đường đỏ là D của bộ 30 đã chọn. Bộ gốc không được thêm vào tần suất của các bộ ngẫu nhiên.
- Trục nhìn tự bao gồm cả D bộ gốc và mọi D ngẫu nhiên; bảng xuất vẫn giữ toàn bộ khoảng [0,1], kể cả khoảng không có bộ nào.
- Bảng hiển thị rút gọn các khoảng có số bộ hoặc chứa bộ gốc; `D_intervals.csv` giữ toàn bộ bảng. Khoảng D không phải mức phân loại đạt/không đạt.

D được đọc từ kết quả đã tính trên 12 ô ABC × RC1-RC4; không tính lại bằng tỷ lệ số tuyến hoặc lấy trung bình D từng vùng. Thống kê đếm bộ có D nhỏ hơn/bằng/lớn hơn dùng dung sai đã khai báo trong protocol.

## Hình 2 — D và một chỉ tiêu của bộ tuyến

| X_METRIC | Trục X hiển thị | Mẫu số hoặc cách tính |
|---|---|---|
| `"unique_rc_coverage_fraction"` | Độ phủ mạng RC không trùng (%) | Hợp chiều dài phần đường vật lý RC được đi qua / chiều dài mạng RC tham chiếu, nhân 100 |
| `"traversed_length_m"` | Tổng chiều dài lượt đi (km) | Cộng chiều dài hành trình có thể lặp, gồm phần nối, chia 1.000 |

Mỗi chấm là một bộ 30 ngẫu nhiên. Ngôi sao là bộ 30 đã chọn. `FIT_LINE=True` thêm đường hồi quy tuyến tính mô tả **chỉ khớp trên M0**, không đưa bộ gốc vào dữ liệu khớp. `False` chỉ vẽ phân tán. Nếu X không biến thiên hoặc thiếu số bộ, không dựng đường hồi quy giả.

Hệ số góc được báo theo một điểm phần trăm độ phủ hoặc một km, tùy trục X. R² là mức phù hợp mô tả trong các bộ M0 đã bốc; không chứng minh quan hệ nhân quả hay chất lượng ngoài thực địa. Không vẽ khoảng tin cậy mặc định của regplot. Đường khớp chỉ nằm trong khoảng X của M0; báo cáo ghi bộ gốc có nằm trong khoảng này hay không.

Không hồi quy “D ngẫu nhiên” theo một giá trị “D bộ gốc” lặp lại, hoặc theo số thứ tự bộ bốc. Để hỏi bộ gốc có D tốt hơn bao nhiêu bộ ngẫu nhiên, dùng hình 1 và thống kê đếm.

## Đầu ra và truy vết

Cell cuối ghi dưới `work/reports/selection/plots/<hash>/`:

| Tệp | Nội dung |
|---|---|
| `D_histogram.png/svg` | Phân bố D và mốc bộ gốc; PNG 240 dpi, SVG dạng vectơ |
| `D_relationship.png/svg` | D theo chỉ tiêu X, có/không đường hồi quy |
| `D_intervals.csv` | Biên khoảng, số bộ, tỷ lệ và khoảng chứa bộ gốc |
| `plot_report.json` | Nguồn, fingerprint lượt M0, tham số, thống kê, hệ số mô tả, runtime và hash đầu vào |
| `manifest.json` | Hash của các đầu ra đã hoàn tất |

Đổi nguồn, tham số, mã vẽ hoặc phiên bản thư viện tạo thư mục hash khác. Thư mục reports được bỏ qua trong Git theo quy tắc sẵn có. Không ghi thêm hình vào bundle M0 bất biến hoặc bản công bố trong docs/results. Nếu nguồn thay trong lúc mở notebook, đọc lại từ đầu. Nếu chỉ đổi tham số nhưng chưa vẽ lại, cell xuất sẽ yêu cầu chạy lại hình.

## Cách diễn giải và xử lý lỗi

Quan sát 0/1.000 bộ có D không lớn hơn bộ gốc là thống kê mô tả có điều kiện trên pool và protocol; không phải p-value bằng 0, xác suất thật bằng 0 hay chứng minh tối ưu toàn cục. Bộ gốc đã được tối ưu trên cùng pool. Các bộ ngẫu nhiên độc lập được phép trùng tập ID giữa các lần bốc; không tự bỏ trùng khi vẽ.

- Thiếu Seaborn/pandas/Matplotlib: kiểm đúng kernel trước; dùng môi trường đã cài `requirements-notebook.txt`.
- M0 tại máy thiếu/hỏng: kiểm hoặc chạy notebook 10 khi đã có dữ liệu nguồn; dùng `SOURCE="published"` nếu chủ động muốn xem bản lịch sử.
- Bộ 30 hiện tại khác M0: chạy lại M0 theo bộ mới, không trộn CSV với D bộ gốc của phiên bản khác.
- Đã đổi tham số nhưng xuất báo lỗi: chạy lại từ cell tham số đến cuối hoặc Run All.

Nguồn kỹ thuật: [Seaborn histplot](https://seaborn.pydata.org/generated/seaborn.histplot.html), [Seaborn regplot](https://seaborn.pydata.org/generated/seaborn.regplot.html). Dữ liệu nền: © OpenStreetMap contributors, theo [ODbL](https://opendatacommons.org/licenses/odbl/1-0/). Các hình vẫn là phân tích tiền khảo sát.
