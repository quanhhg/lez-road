# Bằng chứng, cập nhật thuộc tính và chọn lại tuyến

Mở `work/notebooks/07_field_workflow.ipynb`. `field_workflow.prepare(WORK)` tạo một chiến dịch có phiên bản tại `work/data/processed/field_workflow/<hash>`, gắn đúng nguồn 60/30. Chạy lại không xóa ledger đã nhập. Registry của 60 ứng viên cho phép kiểm cả tuyến dự phòng.

| Tệp | Dùng để |
|---|---|
| route_registry.csv, route_part_registry.csv | ID/vùng/phiên bản/hash, đoạn/cung và thứ tự đi |
| attributes_osm.csv | Giá trị/tỷ lệ thiếu từ OSM, không gọi là thực địa |
| attributes_models.csv | Ước tính chấm điểm, giả định C6 tách riêng |
| field_observations.csv | Ledger quan sát ban đầu chỉ có header |
| survey_checklist.csv, evidence_questionnaires.csv | Câu hỏi và bằng chứng cần thu |
| desk_review_priority.csv | Ưu tiên kiểm làn/tốc độ/C6/độ nhạy; không thêm trọng số chọn tuyến |
| trip_schedule_template.csv | 30 tuyến ×3 khung giờ ×2 lượt dự kiến =180 dòng kế hoạch |
| trip_registry.csv, gps_points.csv | Mẫu schema chuyến/điểm, chưa phải dữ liệu đo |

Tạo CSV nhập theo header ledger. Một dòng là một giá trị/đánh giá có ngày, người ghi, bằng chứng và phạm vi. `evidence_source=field` cần bằng chứng thực địa; `desk` được giữ riêng và không làm G thực địa passed. `unknown/pending` phải để value trống. ID trùng đúng nội dung được bỏ qua; ID trùng khác nội dung bị từ chối. Batch lỗi chưa nhập vào ledger; lỗi xuất `last_import_validation.json`. Bản nhập hợp lệ được lưu nguyên byte trong imports.

- `lanes`: số làn đồng nhất trên phạm vi quan sát, số nguyên dương, unit=count.
- `maxspeed`: tốc độ giới hạn biển báo, km/h, không phải tốc độ chạy được đo.
- `junction_count`, `signal_count`: số nguyên không âm; whole_route mới thay mật độ toàn tuyến.
- `coverage=part/segment`: dùng ID trong registry. Whole_route chỉ dùng khi quan sát đủ toàn hành lang; point không suy ra thuộc tính cho toàn đoạn/tuyến.
- `observed_at`: ISO có offset, `survey_date`: ngày tương ứng tại Hà Nội. Không chấp nhận ngày tương lai.
- route_version/source_bundle_sha256 và policy_version phải đúng chiến dịch. Trạng thái LEZ có hiệu lực ngày khảo sát ghi riêng; nếu chưa rõ dùng unknown.

G1 kiểm quyền đi; G4 kiểm công trình; G5 cần passed trên ít nhất hai ngày sau lần failed gần nhất; G6 cần riêng điểm đầu/điểm cuối. C6 theo rubric 0–5 từ tài liệu gốc: đủ năm đánh giá thành phần cùng ngày chấm và các G đã passed; chấm C6 sau lần G failed gần nhất. Mã không tự tạo điểm C6 hay suy quyền đi từ OSM. URI từ xa mới được kiểm cú pháp, chưa xác minh độc lập nội dung; bằng chứng địa phương kiểm sự tồn tại.

```python
from lez import field_workflow as field, survey_revision
campaign = field.prepare(WORK)
directory = Path(campaign["directory"])
result = field.import_observations(directory, incoming_csv)
state = field.status(directory)
plan = field.build_update_plan(directory)
revision = survey_revision.run(directory, WORK)
```

Revision tính làn/tốc độ theo chiều dài các phần đã đi, giữ OSM/mô hình riêng, áp C6 đủ chứng cứ và dựng lại X trên cả 60. Dùng cùng weighted greedy + nhiều seed + swap C1–C7; loại G failed/C6=0/xung đột hình học/chiều/rẽ khỏi khả dụng. Tính lại toàn tập ma trận/D/độ phủ/overlap/đa dạng, giữ A10/B8/C12. Không đủ ứng viên thì `quota_infeasible_after_field_evidence`.

Nguồn OSM, graph và hình học gốc không bị sửa. Sai chiều/rẽ/hình học được chặn đến khi có graph mới được kiểm; mô tả tự do không đủ để tự vẽ đường hay suy hạn chế rẽ mới. Thuộc tính đo nằm trong bundle `survey_revision/<hash>`, gồm overlay, bằng chứng từng phần, tuyến bị chặn, bộ chọn mới và lịch sử thuật toán.

Chỉ khi cả 30 đủ G/C6/bằng chứng chính sách theo ngày, revision công bố snapshot `surveyed_technical_set_frozen`; vẫn `official_gis_verified=false`. Đây là khóa phiên bản kỹ thuật để truy vết, không xác nhận quyền pháp lý từ một giá trị proxy. Bộ điều phối chuyển xử lý chuyến sang snapshot đó, giữ hợp đồng phiên bản của graph/tuyến trong cùng chiến dịch. Còn thiếu dữ liệu thì `reselected_awaiting_field_evidence` hoặc `awaiting_field_observations`.
