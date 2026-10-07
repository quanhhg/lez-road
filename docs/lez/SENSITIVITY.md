# Kiểm tra độ nhạy trước khảo sát

Notebook `work/notebooks/09_automate_project.ipynb` tự chạy bước độ nhạy sau khi chọn 30 và hiển thị kết quả ở mục **4**. Mục **7a–7c** notebook 06 vẫn dùng để chạy riêng. Module `work/scripts/lez/selection_sensitivity.py` dùng Python thường + NumPy đã có, không cần import QGIS hoặc gửi API. Phân tích đọc bộ 60, graph, bảng biến và cổng GIS đã kiểm tra; không dựng lại hình học.

Đầu ra riêng: `work/reports/selection/latest_sensitivity.json`. Luôn lấy đường dẫn bundle từ trường `paths` trong báo cáo; báo cáo chi tiết là `REPORT.md` trong bundle. Giữ nguyên bộ 30 công bố ở `latest_selection_30.json`.

## Chạy và tiếp tục

Trong notebook, sau cell tìm folder work:

```python
from lez.selection_sensitivity import (
    preflight_sensitivity, run_sensitivity, sensitivity_status,
)

check = preflight_sensitivity(WORK)
result = run_sensitivity(WORK, force=False, progress=print)
report = sensitivity_status(WORK)
```

Hoặc từ folder chứa work:

```bash
python3 work/scripts/lez/selection_sensitivity.py preflight
python3 work/scripts/lez/selection_sensitivity.py run
python3 work/scripts/lez/selection_sensitivity.py status
```

Mỗi kịch bản ghi bằng tệp tạm rồi đổi tên, có hash kết quả và fingerprint đầu vào/mã/cấu hình. Ctrl+C giữ các kịch bản hoàn tất. Chạy lại cùng cell/lệnh để tiếp tục; `force=False` chỉ đọc cache hợp lệ. Đổi đầu vào, cấu hình hoặc mã tạo bundle khác. `progress.json` là tiến độ đang chạy; `latest_sensitivity.json` chỉ trỏ tới kết quả đã hoàn tất và xác minh, có thể vẫn là phiên bản cũ nếu lượt mới bị ngắt.

Không cần `force=True` để tiếp tục. Kết quả chỉ được công bố khi hash đầu vào cuối lượt vẫn khớp. Nếu cache hỏng, chạy lại xử lý phần bị hỏng. Không chạy đồng thời hai lượt phân tích vào cùng folder đầu ra.

## Phạm vi thử đã định trước

Cấu hình ở `work/config/selection_sensitivity.json`. Giữ **A10/B8/C12 = 18 trong/12 ngoài**, ma trận 12 ô, 10 seed, greedy C1–C7 và swap giảm D như bộ gốc. Tái lập đúng cả thứ tự tuyến của baseline trước khi so sánh. Không đổi quota hoặc ranh giới để cải thiện kết quả.

| Nhóm | Thay đổi |
|---|---|
| Chuẩn hóa X | Min–max và z-score, fit đủ 60 ứng viên ở mỗi kịch bản; z-score dùng độ lệch chuẩn quần thể (`ddof=0`) |
| Trọng số | ±20% tương đối cho từng C1–C7 và hai nhóm C1/C2, C4/C5; chuẩn hóa tổng trở lại 100% |
| Tiêu chí hằng | Quy tắc cơ sở giữ trọng số và nhận 1, so với bỏ tiêu chí hằng và chuẩn hóa lại trọng số |
| P_ô | 25%, 30% cơ sở và 40% |
| Làn/tốc độ thiếu | Bỏ lần lượt hoặc cả hai biến; dịch phần chiều dài thiếu ±1 làn và ±10 km/h; không dịch phần quan sát |
| C6 còn khả thi | Bỏ trọng số C6; gán đối nghịch 1/5; 16 giả lập có seed cho mỗi loại chuẩn hóa X, từng tuyến có C6 giả định 1–5 |
| Kết hợp | 16 kịch bản có seed cùng đổi C6, phần làn/tốc độ thiếu, trọng số, ngưỡng ô và scale X |
| C6=0 giả lập | Lần lượt loại từng tuyến trong bộ 30 khỏi tập khả dụng, tìm tuyến thay thế giữ quota; swap cũng không được đưa tuyến bị loại trở lại |
| Không đủ quota | Cố ý loại 9 ứng viên C để chỉ còn 11, xác nhận thuật toán báo không thể đủ 12 C |
| Cờ overlap | Đếm cặp có overlap lượt đi ≥40%/50%/60%; chỉ là cờ rà soát, không phải ba phép chọn lại |

Tổng **114 kịch bản thuật toán**, gồm baseline, 82 phép thử chấm điểm, 30 phép loại một tuyến và một ca thiếu quota có chủ đích. Có 48 giả lập có seed trong số 82 phép thử chấm điểm. Seed cơ sở `20261007`; từng giá trị giả định, seed con và trọng số hiệu lực được lưu. Số kịch bản không phải cỡ mẫu khảo sát hoặc số tuyến mới.

Tài liệu nghiên cứu nêu z-score/min–max cho X ở mục 7.2, ±20% trọng số ở mục 5.1, ngưỡng ô/cờ overlap và Jaccard ở mục 9.4. C6=0 phải loại/đổi tuyến theo Phụ lục A.2. **Biên ±1 làn, ±10 km/h, khoảng mô hình 1–8 làn/10–90 km/h và số lượt giả lập là giả định stress của phân tích**, không phải thông số do tài liệu hoặc hiện trường xác nhận.

X đổi scale để tính khoảng cách Euclid C5; **C1–C5 vẫn dùng min–max theo ứng viên khả dụng mỗi vòng**. Nhóm quartile của C3 giữ thứ hạng khi chỉ đổi scale, tránh thay đổi do sai số số học tại điểm bằng nhau. Bỏ biến/đổi mô hình sẽ tính lại nhóm phù hợp.

Đối với phần dữ liệu thiếu, mô hình tuyến được tách thành đóng góp quan sát cộng đóng góp của chiều dài được ước tính. Chỉ dịch đóng góp thứ hai, chặn giá trị ước tính trong biên thử đã công bố, sau đó chuẩn hóa lại X. Cột quan sát OSM không bị thay. Đây là phép thử của ước tính, chưa thay được bằng chứng về số làn/tốc độ.

C6 thật vẫn NULL. Các giả lập 1–5 giả định tuyến chưa bị loại vì không khả thi; C6=0 thử riêng bằng thay đổi tập khả dụng. Không gán mô phỏng thành dữ liệu thực địa, không sửa G1/G4/G5/G6 và không tuyên bố các cổng đó đã vượt qua. Engine chạy trong namespace riêng, tránh thay hàm chấm điểm của notebook đang dùng.

## Đọc kết quả

| Tệp trong bundle | Nội dung |
|---|---|
| `REPORT.md`, `report.json` | Kết luận, nhóm thử, giới hạn và đường dẫn |
| `scenario_summary.csv` | Tuyến giữ/bỏ/thêm, Jaccard, D, độ phủ, số ô và kết quả trước/sau swap |
| `results.json`, `scenarios/*.json` | Tập tuyến, seed runs, swap, trọng số, thông số chuẩn hóa và giả định từng kịch bản |
| `families.csv` | So sánh riêng từng nhóm phép thử |
| `route_frequency.csv` | Tần suất từng tuyến trong từng nhóm và toàn bộ phép thử chấm điểm |
| `simulated_replacements.csv` | Kết quả khi giả lập từng tuyến cơ sở có C6=0 |
| `input_completeness.csv` | Làn/tốc độ quan sát, tỷ lệ thiếu và trạng thái thực địa thật |
| `protocol.json`, `inputs.json`, `manifest.json` | Quy trình, seed, hash nguồn/mã/kết quả và xác minh hoàn tất |
| `overlap_review_only.json` | Cặp bị gắn cờ theo ngưỡng rà soát |

`retained` = số tuyến còn trong bộ 30 cơ sở. Jaccard = số tuyến chung chia số tuyến trong hợp hai tập; đổi một tuyến thì J=29/31, không phải 29/30. Tần suất là số lần tuyến được chọn chia số kịch bản trong nhóm đã thiết kế; **không phải xác suất chọn hoặc khoảng tin cậy**. Các ca cố ý loại từng tuyến không được gộp vào mẫu số ổn định chấm điểm.

So sánh D và độ phủ theo cùng mạng mục tiêu. “Chiều dài mạng” là tổng chiều dài các phần đường RC vật lý trong phạm vi mục tiêu, mỗi phần một lần; “chiều dài tập tuyến” cộng lượt đi có thể lặp phần đường giữa tuyến. D dùng cơ cấu lượt đi RC, còn độ phủ RC duy nhất dùng hợp phần đường vật lý chia chiều dài mạng. D thấp hơn không chứng minh đạt điều kiện thực địa.

Khi đổi số biến hoặc ngưỡng P_ô, xem thêm `material_cells_common_30pct`, `quantile_groups_common_9_features` và `metrics_common_basis` để so trên cùng cơ sở. Kiểm riêng từng nhóm; không lấy tần suất gộp làm bảng xếp hạng tự động thay tuyến. Chưa đặt ngưỡng “đạt” mặc định cho Jaccard.

Ưu tiên khảo sát tuyến thay đổi giữa kịch bản, tỷ lệ thiếu làn/tốc độ cao và quyền đi/neo/C6 chưa rõ. Gợi ý thay thế khi giả lập C6=0 chưa chứng minh tuyến dự phòng chạy được thực tế. Độ ổn định chỉ có ý nghĩa trong **pool 60 và phạm vi kỹ thuật cố định hiện tại**; không kiểm được ranh giới pháp lý, sai số OSM chưa mô hình hóa hoặc tối ưu toàn cục. A×RC1 vẫn là giới hạn cần báo.
