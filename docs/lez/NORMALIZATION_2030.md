> Tài liệu đối chiếu lịch sử. Từ 06/10/2026, phạm vi sinh/chọn tuyến dùng LEZ-first theo [PROJECT_AUTOMATION.md](PROJECT_AUTOMATION.md); các điều chỉnh dân cư/V/N dưới đây không điều khiển ranh giới A/B/C hiện hành.

# Hoàn thiện 15 tầng, điều chỉnh 17 phần sát ranh giới và chuẩn hóa mạng

## Thiết kế hiện hành — 06/10/2026

Bộ 60 ứng viên hiện hành là **A20/B20/C20**, tương ứng 40 trong/20 ngoài LEZ 2030. Bộ 30 đề xuất có **18 trong LEZ (10 A + 8 B) và 12 ngoài LEZ (12 C)**. A trong Vành đai 1, B giữa Vành đai 1–3, C ngoài Vành đai 3. Ma trận sinh/chọn tuyến chính là 12 ô ABC × RC1–RC4; 15 tầng V/N và ma trận chuẩn hóa 60 ô ở tài liệu này giữ vai trò đối chiếu bổ sung.

Nguồn hiện hành: `work/reports/sampling/latest_sampling_abc.json` và `work/reports/selection/latest_selection_30.json`. D của bộ 60 là 0,540380; bộ 30 là 0,332245; bộ 30 có đóng góp đáng kể ở 12/12 ô ma trận ABC. Xem `work/docs/lez/SAMPLING_ABC.md` và `SELECTION_30.md`. Các kết quả quota/số ô cũ bên dưới chỉ mô tả lịch sử, không dùng để đọc tiến độ hiện tại.

Chuẩn hóa phạm vi/mạng đã hoàn tất; bước chọn 30 cũng đã chạy riêng bằng module lựa chọn. Notebook 05 mặc định đọc cache chuẩn hóa bằng `normalization_status`; đặt `REBUILD_LEZ_SCOPE=True` mới gọi `run_normalization` khi cần dựng lại. Logic nằm trong `work/scripts/lez/normalization_2030.py`; không đặt toàn bộ xử lý vào notebook.

`run_normalization(WORK, fetch=False, force=False, progress=print)` chỉ dựng phạm vi/phân tầng và overlay mạng. Lần chạy này dùng nguồn dân cư/hoạt động đã lưu, không HTTP, không gọi bộ sinh lại 60 tuyến và không chọn 30. `run_sampling` là lệnh riêng để chạy cả bộ 60; không cần chạy lệnh đó khi chỉ hoàn thiện chuẩn hóa.

## Phạm vi và phân tầng

Đã chọn kịch bản LEZ 2030. Lớp đối chiếu hợp 36 địa bàn theo danh sách văn bản bằng hình học OSM được giữ nguyên, chưa là GIS chính thức đã được cơ quan nhà nước xác nhận. Phạm vi lấy mẫu nghiên cứu được dựng riêng; điều chỉnh của nghiên cứu không làm thay đổi quy định lưu thông hoặc ranh giới pháp lý.

Chỉ phần nằm trong dải 1 km mỗi phía của đường bao đối chiếu được phép đổi nhóm. Dân cư là WorldPop mô hình hóa năm 2025 ở 1 km; hoạt động là đối tượng OSM thương mại/dịch vụ, văn phòng, giáo dục tại snapshot đường đã lưu. Điểm bằng 50% phân vị mật độ dân cư + 50% phân vị mật độ hoạt động; từ 0,5 vào nhóm trong, thấp hơn vào nhóm ngoài. Dữ liệu thiếu giữ nhóm tham chiếu và ghi chờ chứng cứ. **1 km, 50:50 và 0,5 là tham số nghiên cứu khởi đầu**, không phải quy định ranh giới LEZ.

Quyết định nhóm áp dụng thống nhất cho mỗi phần đa giác, không thay theo tuyến để làm đủ quota. 17 phần thay đổi gồm 8 phần ngoài → trong và 9 phần trong → ngoài; không phải chuyển toàn bộ 17 xã/phường. 13 địa bàn trước đây chưa có tầng được gán theo phương án nghiên cứu trong cấu hình rồi cắt theo nhóm hiện tại. Bảng dấu vết ghi ID/diện tích/tầng trước/sau/lý do; phân hoạch có đủ V1–V5/N1–N10 nhưng chưa tự trở thành xác nhận pháp lý.

## Chuẩn hóa chiều dài và mẫu số

Mạng được cắt theo phạm vi trong/ngoài và 15 tầng, tính lại chiều dài trong CRS mét và kiểm tra bảo toàn. Chiều dài mạng đếm mỗi phần đường vật lý đủ điều kiện một lần; hai cung của đường hai chiều không nhân đôi. Các đoạn nguồn, phản hồi OSM, lưới tải và văn bản pháp lý không bị sửa.

Hai mẫu số phải tách rõ:

- **Chiều dài toàn mạng:** gồm RC1–RC4 và các đường nối đủ điều kiện. Dùng để kiểm tra bảo toàn toàn bộ phần đường.
- **Chiều dài mạng RC:** chỉ RC1–RC4. Đây là mẫu số tỷ trọng mạng và D; connector báo riêng, không tạo RC thứ năm hoặc chèn dòng connector vào ma trận 60 ô.

`network_matrix.csv` có đúng 60 dòng: 20 ô V × RC và 40 ô N × RC. `connector_summary.csv` báo phần đường nối theo 15 tầng riêng. Tổng tỷ trọng RC toàn mạng bằng 1; tổng tỷ trọng RC trong/ngoài cũng bằng 1 trong mỗi nhóm khi mẫu số lớn hơn 0. Một ô không có RC có thể có chiều dài 0; không xóa ô hoặc dùng đường nối để lấp ô.

Nếu đọc chỉ tiêu của 60 tuyến đã lưu, chiều dài mẫu dùng D cũng chỉ cộng lượt đi **RC1–RC4**; toàn chiều dài tuyến gồm connector được giữ riêng. `P_i(h,k)` vẫn dùng toàn chiều dài tuyến ở mẫu số. Vì vậy không dùng toàn chiều dài tuyến làm mẫu số cơ cấu RC, không thêm connector như một ô thống kê thứ 61.

## Chạy và xem đầu ra

1. Chạy cell xác định `WORK` và kiểm tra đầu vào/runtime; không gửi HTTP.
2. Chạy riêng cell `run_normalization(..., fetch=False, force=False)`. Đọc tiến độ, kết quả phân tầng và QA overlay.
3. Xem quyết định từng phần sát ranh giới, dấu vết gán tầng, ma trận RC và bảng connector. Dùng lớp `sampling_zones.gpkg` để xem hình học trước/sau.
4. Sau Interrupt/Ctrl+C, chạy lại cùng cấu hình. Phiên bản đã có manifest hợp lệ được dùng lại; phần đang dở chưa được công bố hoàn chỉnh. `force=True` không phải cách tiếp tục mặc định.

Notebook 05 gọi `lez.sampling_abc.run_sampling` cho bộ 60 ABC hiện hành. Khi chỉ cần xem chuẩn hóa, giữ `REBUILD_LEZ_SCOPE=False`; các cell sinh tuyến dùng cache ABC hợp lệ và không gửi HTTP. Các cell xử lý nằm ở module, notebook chỉ điều khiển/hiển thị.

Đường dẫn phiên bản được lấy từ kết quả/báo cáo của lượt chuẩn hóa, không chép cứng hash thư mục. Các đầu ra cần đọc gồm:

| Tệp/lớp | Nội dung |
|---|---|
| `sampling_zones.gpkg` | Lớp đối chiếu, phạm vi lấy mẫu trong/ngoài, dải, phần thêm/bớt, 15 tầng và các phần quyết định |
| `boundary_decisions.csv` | Nguồn dân cư/hoạt động, điểm, nhóm trước/sau và lý do |
| `strata_assignment_trace.csv` | ID địa bàn/phần, tầng và diện tích đã gán |
| `remaining_admin_assignments.csv` | Phương án gán 13 địa bàn trước đây còn thiếu |
| `network_parts.gpkg` | Mảnh đường sau cắt, RC/tầng/nhóm và chiều dài mới |
| `network_matrix.csv` | 60 ô RC, mẫu số toàn RC và riêng từng nhóm |
| `connector_summary.csv` | Đường nối theo 15 tầng, tách khỏi mẫu số RC |
| Báo cáo/manifest | Hash đầu vào/đầu ra, cache, số lượng, cân bằng chiều dài và giới hạn phương pháp |

## Những việc còn lại

Hoàn thành chuẩn hóa kỹ thuật không tự xác minh GIS pháp lý hoặc quyền đi/an toàn thực địa. Tiếp tục rà soát nguồn ranh giới và độ nhạy dải/trọng số; ghi vấn đề quyền đi/neo/thuộc tính cần kiểm tra, giữ dữ liệu quan sát riêng với OSM.

## Kết quả thiết kế trước — 05/10/2026 (lịch sử)

Đã chuẩn hóa 15 tầng; điều chỉnh 17 phần sát ranh giới (8 ngoài→trong, 9 trong→ngoài); hoàn thiện ma trận đúng 60 ô RC và tách đường nối. Phiên bản chuẩn hóa nằm trong `work/reports/sampling/latest_normalization_2030.json`. Dữ liệu thô/hình học 60 tuyến giữ nguyên.

Đã chọn **30 tuyến đề xuất: 12 trong/18 ngoài**, có đủ 15 tầng chính V/N. `D_combined` RC-only giảm từ 0,550481 xuống 0,433933; trong từ 0,610846 xuống 0,541835; ngoài từ 0,528618 xuống 0,404310. Bộ 30 chạm 55/60 ô, có 30 ô đóng góp đáng kể theo ngưỡng 30%, phủ 269,045 km RC duy nhất trên mạng 22.425,963 km (1,1997%). D là sai lệch cơ cấu, không phải phần trăm phủ chiều dài. N4×RC3 không được bộ 60 chạm tới; N5×RC1, N7×RC2, N9×RC3 và V1×RC1 có trong bộ 60 nhưng không được bộ 30 chọn chạm tới.

Mở `work/notebooks/06_select_30_routes.ipynb` và [hướng dẫn chọn 30](SELECTION_30.md). Bảng chỉ tiêu/điểm có đủ 9 biến X và 7 trọng số nguồn 25/15/15/15/10/10/10. Làn/tốc độ quan sát được giữ riêng với mô hình ước tính phục vụ chấm điểm. C6 quan sát để trống; giả định trung tính 2,5/5 chỉ dành cho lựa chọn trước khảo sát, kèm khoảng điểm C6 chưa biết rộng 10/100 điểm. Giá trị thực địa khác nhau giữa các tuyến có thể đổi thứ hạng.

Có 51 kiểm tra mã đạt; QA độc lập xác nhận bảo toàn mạng, hình học nguồn không đổi, 30 tuyến/12–18/15 tầng, G2/G3 và 90 điểm neo. G1 pháp lý, G4–G6 và C6 thực địa vẫn chờ khảo sát; GIS pháp lý chưa được xác minh độc lập. Kết quả mang nhãn `proposed_for_survey`, chưa là bộ đã khóa cuối. Xem `work/reports/selection/latest_selection_30.json` cùng các báo cáo QA.
