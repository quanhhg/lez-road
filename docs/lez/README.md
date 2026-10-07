# Quy trình hiện hành LEZ-first

Mở `work/notebooks/09_automate_project.ipynb`. Bộ điều phối chạy các bước độc lập và giữ cache/báo cáo sau từng bước. Không gửi HTTP và không xây chu trình lái.

| Notebook | Chức năng |
|---|---|
| 03_boundaries | LEZ 2027/2030, QA proxy, lịch sử V/N có guard |
| 04_build_motorcycle_network | Chuẩn hóa OSM, graph có hướng/hạn chế rẽ |
| 05_sampling_2030 | 60 ứng viên A20/B20/C20 theo LEZ-first |
| 06_select_30_routes | 30 đề xuất A10/B8/C12, C1–C7 và độ nhạy |
| 07_field_workflow | Checklist, bằng chứng, cập nhật và chọn lại |
| 08_process_measurements | CSV/GPS/tốc độ, map matching và chỉ tiêu |
| 09_automate_project | Kiểm tra/chạy/tiếp tục toàn bộ |

A=KV1/KV2/KV3 thí điểm 2027; B=LEZ 2030 trừ A; C=Hà Nội ngoài LEZ 2030. Toàn Vành đai 1 là giai đoạn 2028–2029. B chứa cả phần Vành đai 1 chưa thuộc A và phần mở rộng Vành đai 2–3. Hình học OSM là proxy kỹ thuật có dải bất định; không tự xác nhận GIS pháp lý hoặc quyền xe máy.

Giữ 60 theo A20/B20/C20 và 30 theo **18 trong/12 ngoài**, cụ thể A10/B8/C12. Ma trận có 12 ô; [giới hạn A×RC1](A_RC1_LIMITATION.md) đã được ghi nhận kèm số liệu và lý do. Có chiều dài mạng RC1 trong A nhưng chưa có phần đủ sinh tuyến theo quy tắc hiện tại; giữ ô/mẫu số và báo 11/12 ô có tuyến. V/N và điều chỉnh dân cư cũ chỉ là đối chiếu lịch sử.

Xem [điều phối](PROJECT_AUTOMATION.md), [sinh 60](SAMPLING_ABC.md), [chọn 30](SELECTION_30.md), [bằng chứng](FIELD_WORKFLOW.md), [GPS](TRIP_PROCESSING.md). Cài môi trường theo [work/docs/setup/PYQGIS_SETUP.md](../setup/PYQGIS_SETUP.md).
