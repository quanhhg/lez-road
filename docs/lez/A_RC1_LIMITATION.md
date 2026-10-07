# Giới hạn A×RC1 trong thiết kế mẫu LEZ

**Ghi nhận ngày 06/10/2026:** chưa sinh được tuyến A×RC1 đủ điều kiện theo mạng, ranh giới và quy tắc định tuyến hiện hành. Ô này vẫn được giữ trong ma trận và mẫu số đánh giá. Đây là giới hạn được ghi nhận của thiết kế mẫu hiện tại.

A là vùng thí điểm LEZ 2027 KV1/KV2/KV3 trong cấu hình LEZ-first của dự án. RC1 được ánh xạ từ các giá trị OSM `primary` và `primary_link`; không đồng nhất RC1 với một kết luận pháp lý về cấp đường hoặc quyền đi xe máy.

## Phạm vi của kết luận

Kết luận áp dụng cho snapshot OSM **01/10/2026 00:00:00 UTC**, chính sách `LEZ2027_2030_LEZ_FIRST_v1` và bundle sinh tuyến `work/data/processed/sampling_abc/87994b561209e33f58dc`.

**Có đường RC1 giao với vùng A.** Kết luận chính xác là không còn phần đường RC1 nguyên vẹn đủ điều kiện cho bộ sinh tuyến sau các bộ lọc hiện tại. Không suy ra rằng A không có đường RC1, toàn bộ RC1 bị cấm xe máy, hoặc mọi thiết kế tuyến khác đều không khả thi. Quyền đi thực tế vẫn cần được xác minh theo ngày, giờ và hướng đi.

## Bằng chứng từ dữ liệu hiện hành

| Chỉ tiêu | Kết quả |
|---|---:|
| Chiều dài mạng RC1 sau giao cắt với A | 5.707,46 m, khoảng 5,707 km |
| Tổng chiều dài mạng RC1–RC4 trong A | 51.448,04 m |
| Tỷ trọng RC1 trong chiều dài mạng RC của A | 11,09% |
| Phần đường vật lý RC1 có chiều dài giao với A | 108 phần |
| Phần không nằm trọn trong A | 3 phần |
| Phần nằm trọn trong A trước khi loại dải bất định | 105 phần |
| Trong 105 phần trên, phần giao dải bất định và bị loại | 105 phần |
| Chiều dài phần đường RC1 còn đủ điều kiện sinh tuyến trong A | **0 m** |
| Chiều dài RC1 trong A được bộ 60 ứng viên đi qua | **0 m** |

Các phần cắt qua ranh giới cũng giao dải bất định; bảng dùng lý do loại chính theo thứ tự kiểm tra để không đếm trùng 3 phần này. Tổng cộng cả 108 phần đều giao dải bất định.

Nguồn số liệu:

- `work/data/processed/sampling_abc/87994b561209e33f58dc/network_matrix.csv`: chiều dài mạng sau giao cắt, đếm phần vật lý một lần.
- `work/data/processed/sampling_abc/87994b561209e33f58dc/routing_network_matrix.csv`: chiều dài phần đường nguyên vẹn còn đủ điều kiện định tuyến.
- `network_parts.gpkg`, `policy_boundaries.gpkg` trong cùng bundle và lớp `scope_parts` của mạng nguồn: đối chiếu từng `part_id`, chiều dài trong A và giao với dải bất định bằng EPSG:3405.
- [Báo cáo bằng chứng A×RC1](../../reports/sampling/A_RC1_limitation.json): số liệu, 108 phần đường, lý do loại và SHA-256 của nguồn. Đây là báo cáo bổ sung, không sửa bundle dẫn xuất đã đóng phiên bản.

## Vì sao chưa sinh được tuyến đủ điều kiện

1. **Chiều dài giao cắt không đồng nghĩa với một phần đường được phép dùng để định tuyến.** Ma trận vẫn đếm chiều dài của đường nằm trong A. Bộ sinh tuyến sử dụng các phần đường nguyên vẹn của graph hiện có; phần vượt ranh giới A bị loại để giữ toàn tuyến đúng vùng. Có 3 phần RC1 thuộc trường hợp này.
2. **Các phần RC1 còn lại giao dải bất định.** Quy tắc hiện hành loại toàn bộ phần đường nếu hình học của nó giao dải bất định, kể cả khi chỉ một đoạn nhỏ giao dải. Có 105 phần nằm trọn trong A nhưng bị loại ở bước này. Cấu hình quanh biên thí điểm dùng dải 50 m dọc đường biên và 200 m tại đoạn khớp nối. Đây là lựa chọn bảo thủ của mô hình nghiên cứu, không phải quy định pháp lý về khoảng lùi. Dải 2.000 m cho đoạn khép phía bắc Vành đai 3 được lưu riêng trong cùng chính sách toàn dự án; không dùng con số đó làm khoảng lùi của vùng A.
3. **Không còn đoạn RC1 hợp lệ để đạt tiêu chí tuyến.** Chiều dài RC1 đủ định tuyến là 0 m, nên tuyến không thể đạt tỷ lệ tối thiểu 30% chiều dài thuộc ô A×RC1 theo cấu hình hiện hành. Đây là giới hạn phát sinh trước bước tìm đường và chấm điểm, không phải lỗi tải API hoặc một tuyến bị loại do điểm thấp.

Các quy tắc được thực hiện trong `work/scripts/lez/sampling_abc.py` và `work/scripts/lez/policy_boundaries.py`; ngưỡng được lưu tại `work/config/sampling_abc.json` và `work/config/lez_policy.json`.

## Cách xử lý trong dự án

- Giữ **12 ô A/B/C × RC1–RC4** trong ma trận. Báo bộ mẫu hiện tại có tuyến ở **11/12 ô**, thiếu A×RC1.
- Giữ chiều dài RC1 của A trong mẫu số mạng, cơ cấu mục tiêu, độ phủ và D. Chiều dài mẫu của ô này vẫn là 0; không loại ô hoặc đổi mẫu số để làm đẹp kết quả.
- Giữ 60 ứng viên **A20/B20/C20**; 20 mục tiêu A hiện được phân bổ **RC2=6, RC3=7, RC4=7**. B và C giữ 5 mục tiêu mỗi RC. Đây là phân bổ số ứng viên, không phải ước lượng tỷ trọng chiều dài mạng.
- Giữ bộ 30 theo **A10/B8/C12 = 18 trong/12 ngoài LEZ2030** và giữ các tiêu chí, trọng số, thuật toán chọn tuyến hiện hành.
- Ghi A×RC1 như một hạn chế về tính đại diện của vùng A. Không coi đạt quota tuyến là đã phủ đầy đủ mọi loại đường hoặc đã xác minh thực địa.

## Khi nào cần đánh giá lại

Đánh giá lại nếu có ranh giới đã xác minh, căn cứ điều chỉnh dải bất định, snapshot OSM mới, phân loại RC được kiểm chứng, hoặc graph/hạn chế đi và rẽ được sửa bằng bằng chứng.

Việc ranh giới trùng với chính quyền không tự động bỏ các dải bất định trong cấu hình. Nếu dải 50/200 m được rà soát và điều chỉnh có căn cứ, 105 phần từng nằm trọn trong A cần được kiểm tra lại; vẫn chưa thể suy ra chúng tạo được một tuyến đạt toàn bộ điều kiện về hướng đi, kết nối, chiều dài, tỷ lệ RC và thực địa.

Khi đầu vào hoặc quy tắc thay đổi, chạy lại giao cắt và ma trận định tuyến, rồi sinh lại ứng viên và tính lại ma trận mẫu, D, độ phủ, trùng lặp và bộ chọn 30. Chỉ cập nhật trạng thái A×RC1 sau khi có đầu ra hợp lệ mới.
