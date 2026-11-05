# M2–M5: đối chứng bằng dữ liệu đã lưu

**M0–M5 là sáu phương pháp, không phải sáu trọng số và không bắt buộc chạy theo số thứ tự.** Sau khi đã có dữ liệu chung, M2 và M3 chạy độc lập; M4/M5 được đối chiếu từ cùng lịch sử chọn tuyến. M1 còn thiếu quy tắc phân bổ được chốt, vì vậy chưa được coi là đã triển khai.

## Chọn phương pháp

| Mã | Quy tắc quyết định | Triển khai ở đâu? |
|---|---|---|
| M0 | Bốc ngẫu nhiên theo quota; không tối ưu D | [Notebook 10](../../notebooks/10_random_baseline.ipynb), module `selection_random.py` hiện có |
| M1 | Theo tỷ trọng mạng đường | Chưa triển khai; cần chốt phân bổ theo vùng × RC và xử lý tuyến nhiều RC/phần không thể đáp ứng |
| M2 | Thêm tuyến hợp lệ tạo D sau bổ sung thấp nhất | [Notebook 12](../../notebooks/12_selection_benchmarks.ipynb) và `selection_benchmarks.py` |
| M3 | Thêm tuyến hợp lệ tạo nhiều chiều dài RC mới được phủ nhất | Notebook 12 và cùng module |
| M4 | C1–C7 trước hoán đổi | Notebook 12 đọc, kiểm và xuất lại bộ trong lịch sử chọn tuyến đã lưu |
| M5 | C1–C7 sau hoán đổi | Notebook 12 đọc, kiểm và xuất lại bộ cuối trong cùng lịch sử |

M4/M5 không được chạy lại ngầm bằng cấu hình mới. Phải xác minh rằng lịch sử đã lưu khớp bộ nguồn, hash và bộ 30 cuối; nếu không khớp thì dừng. Module không chạy GIS để tái dựng lịch sử bị thiếu.

## Dữ liệu và điều kiện chung

Dùng cùng pool 60 ứng viên A20/B20/C20, cùng ma trận 12 ô ABC × RC1–RC4, graph, lớp phần đường và gate đã lưu. Chọn đúng A10/B8/C12, tương ứng 18 trong/12 ngoài LEZ theo thuộc tính trong/ngoài đã ghi; không suy ra miền LEZ chỉ từ tên ABC.

Kiểm tính liên tục/hướng đi, các gate tiền khảo sát đã lưu, quota và trùng hành lang vật lý từng cặp **nhỏ hơn 0,7**. Không nới điều kiện cho phương pháp bế tắc. Không bắt buộc các phương pháp phải đạt sẵn 11/12 ô: số ô được đại diện là kết quả đem so sánh. Giữ A×RC1 và mẫu số mạng dù chưa có tuyến ứng viên đại diện.

Các phương pháp đọc nguồn hiện có; không gọi HTTP, không khởi động QGIS, không thay đa giác ranh giới, không tạo tuyến mới hoặc ghi đè bộ 30 gốc. Clone repo chỉ có mã chưa đủ để chạy; khôi phục bundle theo [hướng dẫn máy mới](../setup/GETTING_STARTED.md).

## Công thức và thứ tự xử lý của M2

Với ô mạng $i$, gọi $N_i$ là chiều dài mạng tham chiếu và $a_{ri}$ là chiều dài theo lượt đi của tuyến $r$ trong ô đó. Chỉ xét RC1–RC4:

$$
q_i=\frac{N_i}{\sum_j N_j},\qquad
V_i(S)=\sum_{r\in S}a_{ri},\qquad
p_i(S)=\frac{V_i(S)}{\sum_jV_j(S)}.
$$

$$
D(S)=\frac12\sum_{i=1}^{12}|p_i(S)-q_i|.
$$

Khi thử thêm tuyến $r$ vào bộ hiện tại $S_t$, phải cập nhật cả tử số và mẫu số:

$$
D_t(r)=\frac12\sum_{i=1}^{12}
\left|\frac{V_i(S_t)+a_{ri}}
{\sum_jV_j(S_t)+\sum_ja_{rj}}-q_i\right|,
\qquad
r_t^*=\underset{r\in\mathcal F(S_t)}{\arg\min}D_t(r).
$$

$\mathcal F(S_t)$ chỉ chứa tuyến được phép thêm theo điều kiện chung. Không chấm D riêng cho từng tuyến một lần rồi lấy 30 tuyến đứng đầu. Có thể viết mức cải thiện là $\Delta D_t(r)=D(S_t)-D_t(r)$; chọn mức lớn nhất tương đương với chọn D sau bổ sung thấp nhất.

1. Lấy đúng 10 cặp khởi đầu cố định của quy trình M4/M5, mỗi cặp trong/ngoài hợp lệ.
2. Mỗi lượt thử toàn bộ ứng viên hợp lệ, dùng lại hàm `D` và các phép kiểm chung, chọn D sau bổ sung thấp nhất.
3. Cho phép D tăng nếu mọi lựa chọn hợp lệ đều làm D tăng; khi đó chọn phương án tăng ít nhất để tiếp tục đủ quota.
4. Khi hòa trong sai số D `1e-10`, dùng mã tuyến, không thêm độ phủ/C1–C7 làm mục tiêu phụ. Sai số chiều dài của M3 là `1e-8` mét, tách riêng khỏi sai số D.
5. Không hoán đổi trong M2 chính. Lưu từng lượt và cả các khởi đầu không thể hoàn thành.
6. Trong các bộ 30 hoàn thành, giữ bộ có D cuối thấp nhất; báo đầy đủ số khởi đầu thành công/thất bại. Đây là kết quả tốt nhất tìm thấy theo quy trình, chưa chứng minh tối ưu toàn cục.

Số 10 khởi đầu là cấu hình để đối chiếu cùng ngân sách tìm kiếm của dự án, không phải ngưỡng hội tụ hoặc cỡ mẫu được bảo đảm khoa học.

## M3 và độ phủ không trùng

Gọi $U(S)$ là tập phần đường vật lý đã được bộ $S$ phủ. Gọi $w_p$ là tổng chiều dài RC1–RC4 của phần $p$ theo lớp phân vùng đã lưu. Mức bổ sung của tuyến $r$:

$$
\Delta L_t(r)=\sum_{p\in U(\{r\})\setminus U(S_t)}w_p,
\qquad
r_t^*=\underset{r\in\mathcal F(S_t)}{\arg\max}\Delta L_t(r).
$$

Cùng 10 cặp khởi đầu được xếp theo D như M2/M4/M5 để kiểm soát cách bắt đầu. Vì vậy M3 vẫn kế thừa ảnh hưởng của D ở khởi đầu; cần công bố giới hạn này khi trình bày. Sau khởi đầu, các lựa chọn và việc chọn bộ hoàn chỉnh tốt nhất chỉ tối đa độ phủ RC. Giữ cùng điều kiện và quy tắc hòa theo mã tuyến như M2. Sau bước khởi đầu, không dùng D để chọn tuyến hoặc phân thắng thua trong M3. Lấy bộ hoàn chỉnh có chiều dài RC phủ duy nhất lớn nhất; không hoán đổi. D chỉ được tính để đánh giá sau đó.

D và độ phủ khác mẫu số: D đếm chiều dài theo mỗi lượt đi, còn độ phủ hợp các phần vật lý và đếm một lần. Connector được tính vào tổng chiều dài hành trình, loại khỏi D và độ phủ RC.

## Chạy trong notebook

1. Mở `work` bằng **File → Open Folder** trong VS Code.
2. Mở `work/notebooks/12_selection_benchmarks.ipynb` và chọn kernel **Python thường** có NumPy, pandas và ipykernel trong `requirements-notebook.txt`.
3. Chạy cell thiết lập rồi cell kiểm tra đầu vào. Nếu thiếu bundle hoặc hash sai, dừng và khôi phục nguồn tương ứng.
4. Giữ `METHODS = ["M2", "M3", "M4", "M5"]` để chạy tất cả phần đã có thể triển khai; chọn một phần bằng `["M2"]` hoặc `["M3"]`. Không đưa M1 vào danh sách.
5. Chạy cell gọi module, xem bảng chung, 30 ID từng bộ, kết quả khởi đầu và đường dẫn báo cáo.

Lời gọi tương đương trong Python, sau khi thư mục `work/scripts` đã nằm trên đường dẫn import:

```python
from lez import selection_benchmarks as bench

check = bench.preflight_benchmarks(ROOT)
report = bench.run_benchmarks(ROOT, methods=["M2", "M3", "M4", "M5"], progress=print)
status = bench.benchmark_status(ROOT)
```

`ROOT` là đối tượng `Path` trỏ đến `work`; cell thiết lập trong notebook tự tìm nó. Notebook dùng `importlib.import_module` để tránh cảnh báo phân tích tĩnh khi đường dẫn module được thêm lúc chạy.

## Tiếp tục và đọc đầu ra

Ctrl+C/Interrupt giữ kết quả của từng phương pháp đã hoàn thành. Chạy lại cùng cell gọi `run_benchmarks` để dùng lại kết quả có hash hợp lệ hoặc chạy phần còn thiếu. Phương pháp đang dở có thể chạy lại các khởi đầu từ đầu; không cam kết tiếp tục đúng giữa một lượt chọn. Không thêm tùy chọn ép ghi đè chỉ để tiếp tục. Sau khi sửa mã hoặc đổi kernel, dùng **Restart Kernel** và chạy lại cell thiết lập trước.

Kết quả được lưu riêng theo phiên bản đầu vào và cấu hình. Trường `paths` của báo cáo chỉ vị trí thư mục, bảng so sánh, kết quả từng phương pháp, báo cáo và manifest. Mỗi phương pháp có `status`, `selected_route_ids`, `metrics`, `seed_runs`, `history_path` và `provenance`; M4/M5 có `seed_runs` trống vì đọc lịch sử đã lưu. `provenance.source` phân biệt lượt chọn mới (`new_objective_greedy`) và trích lịch sử (`verified_saved_selection_history`). Dùng đúng đường dẫn trong `paths` để mở kết quả. Mở `benchmark_status(ROOT)` để đọc trạng thái mới nhất. Kết quả sinh tại máy không tự có trên GitHub và không ghi đè báo cáo M0 hoặc bộ 30 gốc.

Bảng chung dùng lại hàm chỉ tiêu của bộ 30: D toàn bộ/trong/ngoài, độ phủ RC không trùng, tổng km theo lượt đi, số ô có đại diện, số nhóm phân vị và trùng hành lang lớn nhất. Cần so sánh cả chiều dài vì cùng 30 tuyến không đồng nghĩa cùng khối lượng khảo sát. M0 có thể đặt cạnh để đối chiếu theo [báo cáo riêng](RANDOM_BASELINE.md); notebook 12 không bốc lại M0. Kết quả M0 là ngữ cảnh tùy chọn, không phải điều kiện để chạy M2–M5.

## Kết quả đã chạy ngày 05/11/2026

Đối chiếu trên cùng pool 60, snapshot OSM **`2026-10-01T00:00:00Z`**, ma trận tham chiếu và quota **A10/B8/C12**. M2/M3 là lượt chọn mới; M4/M5 được trích, kiểm lại từ cùng lịch sử bộ 30 đã lưu.

| Phương pháp | D toàn bộ | RC phủ không trùng (km) | Tổng chiều dài lượt đi, gồm connector (km) | Ô có đại diện vật chất |
|---|---:|---:|---:|---:|
| M2 — chỉ D | 0,377814 | 236,092404 | 266,927830 | 10/12 |
| M3 — độ phủ | 0,485520 | 295,693278 | 338,357546 | 11/12 |
| M4 — C1–C7 trước hoán đổi | 0,368532 | 241,557840 | 274,352009 | 11/12 |
| M5 — C1–C7 sau hoán đổi | 0,365187 | 240,898856 | 274,031311 | 11/12 |

M3 phủ nhiều km nhất nhưng D cao hơn, và tổng hành trình dài hơn M5 khoảng **23,47%**. Vì vậy M3 nằm ngoài cửa sổ chiều dài ±10% dùng cho đối chiếu mô tả phụ; vẫn phải giữ M3 trong bảng kết quả chính, không coi cửa sổ này là điều kiện loại phương pháp. M4→M5 giảm D đồng thời giảm nhẹ độ phủ: phải báo cả lợi ích và đánh đổi.

M2 là lựa chọn tham lam từ hữu hạn khởi đầu, không phải bộ giải tối ưu toàn cục. Do đó M2 có D cuối cao hơn M4/M5 không mâu thuẫn với việc mỗi lượt của M2 chỉ tối thiểu D sau bổ sung. Không diễn giải kết quả này thành bằng chứng M5 tối ưu toàn cục hoặc tốt hơn toàn diện. Các số là một phiên bản chạy đã kiểm, không tự thay khi chạy lại; xem `paths` và manifest để truy vết lượt hiện hành.

## Diễn giải và phần chưa hoàn tất

- M2 với M4: xem đánh đổi khi thay mục tiêu D bằng hệ C1–C7.
- M4 với M5: xem hiệu quả của bước hoán đổi trong cùng lịch sử.
- M2 với M5: xem kết quả cuối và các đánh đổi; chưa tách riêng được tác động của hoán đổi khỏi hệ tiêu chí.
- M3: cho biết ưu tiên độ phủ tạo khác biệt gì về D, km, trùng và cơ cấu.
- M1: vẫn chờ quy tắc phân bổ, cách làm tròn quota RC, chọn tuyến nhiều RC và xử lý phần không thể đáp ứng. Không thay bằng M2 rồi gắn nhãn M1.

Gate tiền khảo sát không phải xác nhận thực địa/pháp lý. C6 chưa có quan sát vẫn giữ trạng thái chưa biết; M4/M5 phản ánh giả định C6 của lần chạy nguồn. Thiếu A×RC1, bất định của đa giác ranh giới và chưa có chuyến đo/GPS vẫn là giới hạn nghiên cứu; việc hoàn thành bảng đối chứng không giải quyết các giới hạn đó.
