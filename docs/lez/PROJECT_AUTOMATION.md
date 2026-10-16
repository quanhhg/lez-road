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
9. Kiểm hành lang cung có hướng; xuất T2: phiếu chạy từng tuyến, chỉ dẫn, GPX và sơ đồ. Dùng đúng bộ đề xuất hoặc snapshot khảo sát được khóa ở bước 8.
10. Nhập GPS/tốc độ, chuẩn hóa đơn vị, kiểm lỗi, ghép đúng tuyến và tính chỉ tiêu vận hành.
11. T3 đối chiếu dữ liệu thực với tuyến × khung giờ × loại ngày; xuất lịch, tổ hợp thiếu và lý do chuyến chưa được đếm.

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

T2 lưu báo cáo `work/reports/routes/latest_route_instructions.json` và trang mở nhanh `work/maps/route_instructions/index.html`. Bước `route_instructions` có thời gian/trạng thái riêng; lỗi nguồn hoặc cache chặn bước sau. Đọc [ROUTE_INSTRUCTIONS.md](ROUTE_INSTRUCTIONS.md) để chạy T2 riêng.

T3 là bước `survey_coverage` sau `real_trip_qc`, dùng cùng snapshot và thư mục dữ liệu đo. Notebook 09 mục 8 chạy/xem riêng. Hiện có 180 tổ hợp, 360 lượt dự kiến, còn chờ dữ liệu và xác nhận mục tiêu số chuyến/ngày. Chuyến có dữ liệu nhưng thiếu thông tin hoặc chất lượng chưa đạt bộ lọc đề xuất vẫn được giữ, chưa làm tăng số tổ hợp đã đo. Báo cáo tổng có `survey_coverage_status`, `survey_cells_with_valid_trips`, `survey_planned_cells`; thiếu tổ hợp hay chưa chốt thiết kế vẫn được ghi trong `pending`. Xem [T3](SURVEY_COVERAGE.md).

T5 được tính trong bước `real_trip_qc`, gồm RPA/PKE/SAFD, tổng hợp có trọng số và nhật ký từng khoảng. Preflight kiểm cả cấu hình công thức/lưới. Báo cáo điều phối có `operating_metrics_status` và `operating_metrics_version`. Notebook 09 mục 9 chạy/xem riêng và kiểm tra công thức bằng ví dụ giả; nguồn thực trống vẫn báo chờ. Xem [T5](OPERATING_METRICS.md).
