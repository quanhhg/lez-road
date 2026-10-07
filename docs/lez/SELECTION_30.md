# Chọn 30 và cập nhật sau khảo sát

Notebook `work/notebooks/06_select_30_routes.ipynb`, module `work/scripts/lez/selection_30.py`. Đầu vào là bộ 60 LEZ-first A20/B20/C20; chọn **A10/B8/C12 =18 trong/12 ngoài LEZ 2030**. Không yêu cầu đã đo thực địa để chọn bộ đề xuất.

A theo vùng thí điểm 2027; B=LEZ 2030 trừ A; C=Hà Nội ngoài LEZ 2030. Kiểm toàn tuyến bằng giao hình học; không gán nhóm từ một điểm neo hoặc tên tuyến. Phạm vi kỹ thuật chưa được xác minh là GIS pháp lý.

Giữ ma trận ABC×RC và các tiêu chí gốc C1–C7 với trọng số **25/15/15/15/10/10/10**. C1=giảm D; C2=đóng góp khoảng thiếu; C3=mới nhóm hạ tầng; C4=trùng tuyến (cost); C5=khác hạ tầng; C6=khả thi thực địa; C7=vai trò không gian. Mỗi vòng tính lại theo tập hiện có, nhiều seed và swap giảm D có giữ quota/độ phủ ô/đa dạng/overlap. Không lấy top30 của bảng điểm tĩnh.

X gồm tỷ lệ RC1–RC4, làn, tốc độ giới hạn, mật độ nút/tín hiệu và tỷ lệ một chiều hiệu lực trong graph. Làn/tốc độ OSM có tỷ lệ thiếu; mô hình RC-median chỉ để chấm, không thay quan sát thô. Chuẩn hóa min/max trên cả 60 và quartile cho đa dạng; tiêu chí không đổi giữ trọng số theo cấu hình. C6 quan sát ban đầu NULL; giả định 2,5/5 tách riêng và khoảng điểm 0–5/kiểm độ nhạy dị biệt được báo. Điều kiện graph/hình học kiểm trước chấm; G thực địa còn unknown không được gọi là passed.

```bash
python3 work/scripts/lez/selection_30.py preflight
python3 work/scripts/lez/selection_30.py run
python3 work/scripts/lez/selection_30.py status
```

Báo cáo `work/reports/selection/latest_selection_30.json`, bundle có classification60, selected30, reserves30, ma trận, biến GIS/CSV, X, lịch sử từng vòng, swap, độ nhạy và checklist. Ma trận giữ A×RC1 đang không có tuyến đủ điều kiện; không tuyên bố 12/12. Bản đồ tên đường cập nhật qua bộ điều phối notebook09.

Sau khảo sát, notebook07 nhập bằng chứng và `survey_revision` cập nhật overlay/chấm lại/chọn lại bằng cùng engine. C6 đủ bằng chứng mới thay giả định; G failed hoặc xung đột graph loại khỏi khả dụng. Giữ đúng 10/8/12, tính lại toàn tập. Nếu không đủ thì báo infeasible; không tự nới quota. Snapshot được công bố riêng, không sửa nguồn/bundle đề xuất. Xem [FIELD_WORKFLOW.md](FIELD_WORKFLOW.md).

Kiểm tra độ nhạy mở rộng dùng `work/scripts/lez/selection_sensitivity.py` và `work/config/selection_sensitivity.json`, chạy độc lập bằng Python + NumPy. Xem [SENSITIVITY.md](SENSITIVITY.md); không dùng mô phỏng thay bằng chứng thực địa. Mục 7a–7c notebook 06 chạy/tiếp tục và đọc kết quả. Báo cáo hiện hành ở `work/reports/selection/latest_sensitivity.json`; phân biệt kịch bản chấm điểm, cờ overlap và giả lập tuyến không khả thi.
