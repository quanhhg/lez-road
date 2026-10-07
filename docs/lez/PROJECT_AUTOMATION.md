# Chạy và tiếp tục toàn bộ quy trình

Notebook chính: `work/notebooks/09_automate_project.ipynb`. Module: `work/scripts/lez/project_automation.py`. Controller chạy bằng Python thường; chỉ tác vụ GIS dùng worker PyQGIS đã đăng ký. Không cài thư viện mới, không tải lại OSM và không xây chu trình lái.

Từ folder chứa work:

```bash
python3 work/scripts/lez/project_automation.py check
python3 work/scripts/lez/project_automation.py run
python3 work/scripts/lez/project_automation.py status
```

Các bước chạy tuần tự:

1. Kiểm nguồn pháp lý/hash, OSM, snapshot, quota và runtime.
2. Dựng/đọc cache LEZ 2027/2030, sinh đủ 60 ứng viên từ ma trận ABC×RC.
3. Kiểm graph/chiều/rẽ/GIS; chuẩn hóa X; chọn 30 bằng C1–C7, nhiều khởi đầu và hoán đổi.
4. Chạy độ nhạy mở rộng bằng `selection_sensitivity.py`; dùng cache đã xác minh, đối chiếu với bundle 30 vừa chọn.
5. Xuất bản đồ 30/60 có tên tuyến, danh sách đường và manifest nguồn.
6. Tạo registry/checklist/câu hỏi/lịch đo dự kiến và xếp ưu tiên xác minh.
7. Nhập CSV quan sát khi được cung cấp; kiểm schema/đơn vị/ngày/bằng chứng/phiên bản.
8. Cập nhật thuộc tính trong overlay riêng; chấm lại, loại tuyến lỗi và chọn lại với đúng A10/B8/C12. Tính lại toàn bộ chỉ tiêu. Tạo snapshot khảo sát kỹ thuật khi đủ bằng chứng.
9. Kiểm hành lang cung có hướng, nhập GPS/tốc độ, chuẩn hóa đơn vị, kiểm lỗi, ghép đúng tuyến và tính chỉ tiêu vận hành.

Khi chưa có quan sát/chuyến đo, kết quả là `automated_pre_survey_complete_awaiting_field_evidence`. Các bước nhập, cập nhật, kiểm GPS đã có mã nhưng chưa thể tạo kết quả thực địa. Lịch dự kiến không được đếm là chuyến thực.

Để nhập và xử lý khi có dữ liệu:

```python
from lez.project_automation import run
result = run(WORK, force=False,
             observations=WORK / "data/measurements/incoming/observations.csv",
             input_dir=WORK / "data/measurements/incoming")
```

Sau Ctrl+C chạy lại cùng lệnh/cell; độ nhạy tiếp tục từ checkpoint từng kịch bản đã có hash hợp lệ. Cache chỉ dùng khi fingerprint và mọi hash khớp. Phiên bản thiếu/hỏng không được coi là xong. Báo cáo `work/reports/automation/latest_project_automation.json` ghi sau từng bước và lưu lỗi cuối; không mất bundle đã hoàn chỉnh.

Nguồn hiện hành: `work/reports/sampling/latest_sampling_abc.json`, `work/reports/selection/latest_selection_30.json`, `work/reports/selection/latest_sensitivity.json`, `work/reports/field/latest_field_workflow.json`, `work/reports/field/latest_survey_revision.json`, `work/reports/trips/latest_real.json`. Các nhánh demo tách riêng, không đưa vào số chuyến thực.

Ranh giới dùng LEZ-first, không điều chỉnh theo dân cư để đủ quota. A là thí điểm 2027, không phải toàn Vành đai 1; B=LEZ 2030 trừ A; C=ngoài LEZ 2030. A×RC1 chưa có hành lang đủ điều kiện sau dải bất định; báo ô thiếu thay vì nới điều kiện. Xác minh GIS chính thức, quyền đi/công trình/an toàn và dữ liệu đo vẫn cần đầu vào đúng thực tế.

Notebook 09 có mục 4 để xem số kịch bản, nhóm thử, bảng so sánh và thay tuyến giả lập. Bước `selection_sensitivity` ghi riêng trong báo cáo điều phối cùng thời gian thực của lượt hiện tại. Ca cố ý thiếu quota không chặn hoàn tất; kịch bản chưa giải quyết hoặc baseline không khớp sẽ báo lỗi và giữ kết quả các bước trước.

Phân tích hiện tại dùng pool 60 và bộ 30 đề xuất trước khảo sát, giữ quota A10/B8/C12. Quy trình cập nhật sau khảo sát vẫn chạy riêng ở bước sau; độ nhạy này chưa đại diện cho bộ tuyến đã cập nhật bằng dữ liệu thực địa. Xem [SENSITIVITY.md](SENSITIVITY.md).
