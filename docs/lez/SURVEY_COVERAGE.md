# T3 - Lịch, biểu mẫu và tiến độ khảo sát

T3 chuẩn bị lịch và đối chiếu các chuyến thực với lịch. Module `work/scripts/lez/survey_coverage.py` dùng Python thông thường, không cần nhập QGIS hoặc cài thêm thư viện. Module đọc kết quả kiểm tra GPS có hướng của phần xử lý chuyến; không tự ghép lại GPS, thay tuyến hoặc tạo số đo.

## 1. Đơn vị theo dõi và lịch đề xuất

Một tổ hợp là **một tuyến × một khung giờ × một loại ngày**. Bộ 30 hiện hành có A10/B8/C12. Ba khung giờ theo giờ Hà Nội là 07:00–09:00, 10:00–12:00 và 17:00–19:00. Hai loại ngày dự kiến là ngày thường và cuối tuần.

- Có **180 tổ hợp**: 30 × 3 × 2.
- Hai lượt lặp theo cấu hình chuẩn bị tạo **360 lượt dự kiến**. Mỗi lượt có `plan_id` riêng, phiên bản tuyến và nguồn đi kèm.
- Các cột ngày đo, mã chuyến, xe, người lái và thiết bị trong lịch ban đầu để trống. Một dòng lịch không được đếm là chuyến thực.
- Số chuyến hợp lệ và số ngày khác nhau cần có cho mỗi tổ hợp vẫn để `null`. Hai lượt dự kiến không tự trở thành cỡ mẫu bắt buộc.
- G5 vẫn cần bằng chứng ít nhất hai ngày theo quy tắc bằng chứng riêng. Đếm hai chuyến không tự làm G5 đạt.

Thiết kế nằm tại `work/config/field_workflow.json`, phần `survey_design`. Trạng thái hiện tại là `proposed`. Chỉ chuyển thành `approved` sau khi chốt thiết kế, cập nhật phiên bản và điền cả hai mục tiêu: `minimum_valid_trips_per_cell`, `minimum_distinct_dates_per_cell`.

## 2. Chuẩn bị và điền biểu mẫu

Chạy mục 1 notebook 07 hoặc mục 2 notebook 09 để tạo/mở chiến dịch và nâng cấp biểu mẫu. Tệp `trip_registry.csv` trong chiến dịch và `work/data/measurements/incoming/trips.csv` được bổ sung cột khi còn trống hoặc chỉ có tiêu đề. Tệp đã có dòng dữ liệu được giữ nguyên byte; báo cáo `trip_template_updates` liệt kê những cột còn thiếu để người dùng bổ sung trên bản làm việc của mình.

Sao chép lịch sang một bản làm việc để phân công ngày, xe, người lái và thiết bị. Khi thu thập thực tế, ghi vào `trips.csv` và `gps_points.csv`. Không đổi tên lịch đề xuất thành dữ liệu chuyến đo: thời gian, trạng thái và các trường quan sát phải được ghi từ chuyến thực.

Giữ các trường chuyến cũ: mã chuyến/tuyến/xe/người lái, thời gian bắt đầu/kết thúc, ngày, khung giờ, vùng nghiên cứu, trạng thái LEZ tại ngày đo, phiên bản chính sách/tuyến và hash nguồn. T3 bổ sung:

| Trường | Cách ghi |
|---|---|
| `plan_id` | Mã lượt dự kiến tương ứng, nếu có. Không bắt buộc cho chuyến phát sinh ngoài lịch. Không dùng cùng một mã lượt cho nhiều chuyến. |
| `device_id` | Mã thiết bị ghi GPS/tốc độ. Dùng mã nhất quán để đối chiếu thiết bị giữa các chuyến. |
| `travel_direction` | `as_planned`: đúng thứ tự cung của tuyến đã chọn; `deviated`: có lệch; `unknown`: chưa rõ. Không tự chạy ngược tuyến một chiều. |
| `day_type` | `weekday`: ngày thường; `weekend`: cuối tuần; `holiday`: ngày lễ. Tính ngày theo giờ Hà Nội. |
| `calendar_checked` | `yes` khi người ghi đã kiểm tra lịch áp dụng; `no` hoặc `unknown` khi chưa kiểm tra. Không tự điền `yes` từ thứ trong tuần. |
| `calendar_note`, `calendar_evidence_uri` | Ghi chú và tài liệu lịch. Ngày lễ chưa có trong cấu hình cần cả hai trường; nguồn được lưu để rà soát, không tự xác minh nội dung. |
| `weather` | `dry`: khô; `light_rain`: mưa nhẹ; `heavy_rain`: mưa lớn; `other`: khác; `unknown`: chưa rõ. `other` cần `weather_notes`. |
| `weather_notes` | Mô tả điều kiện và thay đổi thời tiết đáng chú ý. |
| `event_status` | `none_reported`: không ghi nhận sự kiện bất thường; `unusual_event`: có sự kiện; `unknown`: chưa rõ. |
| `event_notes` | Cần điền nếu có sự kiện, ví dụ lễ hội, tai nạn hoặc phân luồng bất thường. Không suy sự kiện từ tốc độ thấp. |
| `collection_stage` | `pilot`: đo thử thực tế; `main`: khảo sát chính. Dữ liệu giả dùng kiểm thử phải ở nhánh demo, không dùng nhãn này để đưa vào nhánh thực. |

`travel_direction` mô tả việc bám chuỗi cung có hướng, không phải một góc phương vị cố định. Tuyến có thể đổi hướng hoặc đi lặp theo đúng chuỗi đã chọn. GPS sai chiều vẫn bị chặn dù người ghi khai `as_planned`.

Không tự tra lịch ngày lễ qua mạng. Nếu có ngày làm bù hoặc lịch đặc biệt đã đối chiếu, thêm vào `calendar_overrides`, dạng ngày ISO và đối tượng có `day_type`, `source`. Ví dụ cấu trúc: `{"YYYY-MM-DD": {"day_type": "weekday", "source": "tài liệu đã đối chiếu"}}`; phải thay bằng ngày thật hợp lệ. Cuối tuần thông thường là thứ Bảy/Chủ nhật; thông tin ngày lễ cần kiểm tra riêng.

## 3. Chuyến nào được tính vào tổ hợp?

T3 dùng kết quả kiểm tra dữ liệu **thực** do `trip_processing.py` xuất, kiểm hash nguồn, bản byte lưu trữ và phiên bản tuyến. CSV mới hoặc đổi ngưỡng kiểm tra sẽ yêu cầu xử lý chuyến lại trước khi đếm. Kết quả demo, nguồn hỏng hoặc khác bộ tuyến không được đưa vào số liệu thực.

Để được đếm, chuyến cần:

1. Mã chuyến không trùng; đúng tuyến, vùng, phiên bản và nguồn hiện hành.
2. Đủ thông tin xe, người lái, thiết bị, hướng, loại ngày đã kiểm lịch, thời tiết, sự kiện và giai đoạn thu thập.
3. Ngày đo khớp ngày Hà Nội; thời gian có múi giờ, không ở tương lai, không qua nửa đêm và nằm trong khung giờ khai báo. Chuyến được kết thúc đúng giờ đóng khung; không bắt đầu tại giờ đóng khung.
4. Đã qua kiểm tra GPS có hướng. Không có điểm bị xác định đi ngược chiều. Cả phần thời gian tốc độ, thời gian GPS, thời gian ghép rõ tuyến và chiều dài ghép tuyến đều đạt ngưỡng cấu hình.
5. Một thiết bị, xe hoặc người lái không được gắn với các chuyến có thời gian chồng nhau. Nếu có xung đột, giữ các dòng và liệt kê lý do để sửa; không tự chọn một dòng thay cho người dùng.
6. Thuộc giai đoạn `main` và loại ngày nằm trong thiết kế. Chuyến đo thử và ngày lễ chưa nằm trong thiết kế được báo riêng, không bù vào ngày thường/cuối tuần.

Mặc định bốn ngưỡng chất lượng ở mục 4 là **90%**, nằm trong `survey_design.quality_rules`. Đây là **bộ lọc kỹ thuật đề xuất có thể chỉnh**, không phải ngưỡng được tài liệu khoa học hay thực địa xác nhận. Mẫu số thời gian là toàn thời gian khai báo của chuyến; mẫu số chiều dài là chiều dài tuyến nguồn. Một giây hợp lệ trong chuyến 60 giây không làm tổ hợp được ghi nhận là đã đo hợp lệ.

Thời tiết và sự kiện được lưu, phân nhóm riêng, chưa tự loại theo một loại thời tiết/sự kiện. Nếu chiến dịch cần quy tắc loại các điều kiện này, phải bổ sung quy tắc có phiên bản trước khi kết luận về mức đại diện. Các cổng G1/G4/G5/G6 và C6 vẫn đánh giá riêng qua bằng chứng thực địa.

## 4. Chạy và tiếp tục

Trong folder `work`:

```bash
python3 scripts/lez/survey_coverage.py check --work .
python3 scripts/lez/survey_coverage.py run --work .
python3 scripts/lez/survey_coverage.py status --work .
```

- Notebook 07 mục 7: xem tiến độ khi chuẩn bị/nhập bằng chứng.
- Notebook 08: tính T3 ngay sau khi kiểm tra chuyến thực.
- Notebook 09 mục 2: tự chạy bước `survey_coverage` sau `real_trip_qc`.
- Notebook 09 mục 8: chạy riêng và xem lịch, tổ hợp thiếu, lý do từng chuyến và điều kiện đo.

Khi CSV thay đổi, chạy lại bước kiểm tra chuyến trước; nếu không, T3 báo `awaiting_trip_qc` và không dùng số đếm cũ. Khi bộ điều phối đã khóa snapshot khảo sát kỹ thuật, T3 đọc cùng snapshot với T2 và phần xử lý chuyến. Dữ liệu thuộc phiên bản khác không tự được đổi nhãn cho khớp.

Sau khi cập nhật mã trong một phiên notebook đang mở, khởi động lại kernel rồi chạy từ cell thiết lập. Chạy lại dùng phiên bản kết quả có hash hợp lệ. Ghi dở hoặc Ctrl+C không thay báo cáo hoàn chỉnh trước đó.

## 5. Đọc kết quả

Báo cáo mới nhất: `work/reports/field/latest_survey_coverage.json`. Các đường dẫn trong `paths` chỉ tới bundle có phiên bản ở `work/data/processed/survey_coverage`:

| Tệp | Một dòng là / nội dung |
|---|---|
| `trip_schedule_template.csv` | Một lượt dự kiến; không phải chuyến đã đo. |
| `coverage_matrix.csv` | Một tổ hợp tuyến × khung giờ × loại ngày; có số chuyến thử nhập, hợp lệ, số ngày khác nhau và mục tiêu còn thiếu khi đã chốt. |
| `trip_coverage_audit.csv` | Một dòng chuyến nguồn cùng trạng thái được đếm/không được đếm và lý do. |
| `condition_summary.csv` | Một nhóm loại ngày × thời tiết × sự kiện × giai đoạn đo. |
| `missing_or_incomplete_cells.csv` | Những tổ hợp chưa đạt mục tiêu được xác nhận; khi mục tiêu chưa chốt, vẫn giữ các tổ hợp để rà soát. |
| `summary.json`, `manifest.json` | Tổng hợp, cấu hình, đơn vị theo dõi, nguồn và hash các kết quả. |

Các trạng thái chính:

- `awaiting_measurements`: chưa có dữ liệu chuyến thực.
- `awaiting_trip_qc`: cần kiểm tra lại CSV/nguồn/ngưỡng hoặc thực hiện ghép GPS có hướng.
- `awaiting_main_measurements`: chỉ có chuyến đo thử/ngày ngoài thiết kế hợp lệ; vẫn chờ khảo sát chính, không coi các chuyến đó là lỗi.
- `needs_correction`: có chuyến nhưng chưa chuyến nào đủ điều kiện đếm; đọc bảng lỗi.
- `awaiting_design_confirmation`: đã có chuyến đạt bộ lọc nhưng mục tiêu/thiết kế còn là đề xuất.
- `coverage_incomplete`: thiết kế đã chốt, còn thiếu chuyến hoặc ngày ở một số tổ hợp.
- `coverage_targets_met_pending_T6`: đạt các mục tiêu lịch đã chốt; **chưa kết luận đủ dữ liệu hay hội tụ T6**.

Thiếu dữ liệu không được điền từ OSM, lịch dự kiến hoặc dữ liệu giả. Việc xuất thành công T3 cũng không xác nhận quyền xe máy, an toàn điểm dừng hay ranh giới GIS pháp lý.

## 6. Kiểm thử khi sửa mã

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_survey_coverage.py' -v
PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_field_workflow.py' -v
PYTHONPATH=scripts python3 -m unittest discover -s tests/lez -p 'test_project_automation.py' -v
```

Kiểm thử dùng dữ liệu giả trong thư mục tạm, tách khỏi thư mục số đo thực. Phần chuẩn bị T3 đã có mã; việc hiệu chỉnh thiết bị và đo thử ngoài thực địa vẫn cần thực hiện sau này. T3 chưa xây quy tắc hội tụ hoặc chu trình lái.
