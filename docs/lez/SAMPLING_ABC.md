# Sinh 60 tuyến LEZ-first

Notebook `work/notebooks/05_sampling_2030.ipynb`; module `work/scripts/lez/sampling_abc.py`; cấu hình `work/config/sampling_abc.json` và `work/config/lez_policy.json`.

A=thí điểm LEZ 2027 KV1/KV2/KV3; B=LEZ 2030 trừ A; C=Hà Nội ngoài LEZ 2030. Nguồn pháp lý và hash được lưu; hình học dựng theo OSM là proxy chưa xác minh GIS chính thức. Toàn bộ Vành đai 1 thuộc 2028–2029. B chứa phần Vành đai 1 còn lại và phần mở rộng Vành đai 2–3.

Giữ 20 ứng viên mỗi vùng, cùng ma trận/graph có hướng/3 neo/độ dài/RC/overlap của thuật toán gốc. **A×RC1 là giới hạn được ghi nhận của thiết kế mẫu hiện tại**: mạng có khoảng 5,707 km RC1 giao với A, nhưng 3 phần vượt ranh giới và 105 phần nằm trọn A bị loại do giao dải bất định; còn 0 m đủ định tuyến. Xem [giải thích và điều kiện đánh giá lại](A_RC1_LIMITATION.md) cùng [báo cáo bằng chứng](../../reports/sampling/A_RC1_limitation.json). A chuyển mục tiêu sang RC2=6/RC3=7/RC4=7. Giữ A×RC1 trong ma trận, mẫu số mạng và D; báo bộ mẫu có tuyến ở 11/12 ô. B/C giữ 5 mục tiêu mỗi RC.

Dải đường biên 2027 và đoạn khép phía bắc Vành đai 3 chưa chắc chắn được loại khỏi sinh tuyến. Dân cư/hoạt động và V/N chỉ là lớp đối chiếu lịch sử, không dịch ranh giới hiện hành.

```bash
python3 work/scripts/lez/sampling_abc.py check
python3 work/scripts/lez/sampling_abc.py run
python3 work/scripts/lez/sampling_abc.py status
```

Không HTTP. Cache đầy đủ/hash khớp được dùng lại; sau Ctrl+C chạy lại. Báo cáo `work/reports/sampling/latest_sampling_abc.json` xác định bundle và mục tiêu thất bại thực tế. Bộ 60 đủ quota vẫn chưa xác minh G1 pháp lý/G4/G5/G6/C6. Chuyển sang notebook 06 chọn A10/B8/C12; quy trình chung ở [PROJECT_AUTOMATION.md](PROJECT_AUTOMATION.md).

Chiều dài mạng RC đếm phần vật lý một lần; chiều dài tập tuyến RC cộng lượt đi. D=0,5 tổng chênh tuyệt đối giữa hai cơ cấu chuẩn hóa. Độ phủ duy nhất đếm phần RC có ít nhất một lượt đi chia mạng RC. Connector báo riêng. Không nhầm số ô có tuyến với độ phủ mạng hoặc tính đại diện.
