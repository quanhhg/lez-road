# Kế hoạch Python và dữ liệu OSM cho tuyến xe máy Hà Nội

Cập nhật 06/10/2026 theo yêu cầu LEZ-first và tự động hóa đến chỉ tiêu chuyến đo. Phần xây dựng chu trình lái nằm ngoài phạm vi triển khai này.

## Thiết kế và nguồn chuẩn

60 ứng viên A20/B20/C20; 30 khảo sát A10/B8/C12, tương ứng 18 trong/12 ngoài LEZ2030. A=KV1/KV2/KV3 thí điểm 2027 tại Hoàn Kiếm/Cửa Nam; B=phần LEZ2030 trừ A; C=Hà Nội ngoài LEZ2030. Toàn bộ Vành đai1 là giai đoạn2028–2029. B gồm phần Vành đai1 còn lại và phần mở rộng Vành đai2–3; không tự thay mốc để đủ quota.

Nguồn pháp lý ở `work/data/raw/legal`, quy tắc/hash ở `work/config/lez_policy.json`. Nguồn OSM ở `work/data/hanoi_tiles`, snapshot01/10/2026. Ranh giới OSM là proxy kỹ thuật; `official_gis_verified=false` đến khi có GIS pháp lý xác minh. Dân cư/hoạt động và phân tầng V/N cũ giữ làm đối chiếu lịch sử.

## 1. Thu thập và giữ nguồn

183 ô đã tải; bộ requests/Overpass vẫn hỗ trợ kiểm phản hồi, cache, retry, trạng thái/lịch sử và tiếp tục. Giữ nguyên query/bbox/response/snapshot/manifest. Không gọi API lại cho dữ liệu hợp lệ. Notebook01–02 và module HTTP độc lập với QGIS.

## 2. Chuẩn hóa và mạng xe máy

Từ cache, dựng bảng node/way/relation, đoạn/cung, thuộc tính/provenance, graph có hướng, quyền đi tạm thời và hạn chế rẽ. PyQGIS tính hình học và đổi EPSG:3405; Python kiểm dữ liệu/graph. Giữ trạng thái chưa rõ, không suy quyền pháp lý từ một tag thiếu. Tính chiều dài lại sau mỗi cắt/overlay. Notebook04 quản lý cache/mạng.

## 3. LEZ và ma trận sinh60

Dùng mốc LEZ2027/2030 trước. A/B/C phải không chồng lấn, phủ Hà Nội và A⊂2030; A∪B=2030. Đối chiếu bản đồ phụ lục chính thức, báo sai khác proxy và dải bất định. Toàn tuyến phải đúng vùng và tránh dải chưa chắc chắn. Ma trận đủ12 ô ABC×RC1–RC4, mẫu số chỉ RC; connector báo riêng.

Giữ thuật toán sinh tuyến có hướng/3 neo/chiều dài/RC/overlap. [A×RC1 được ghi nhận là giới hạn của thiết kế mẫu hiện tại](../lez/A_RC1_LIMITATION.md): có khoảng 5,707 km mạng RC1 giao với A nhưng 0 m còn đủ sinh tuyến sau kiểm tra phạm vi/dải bất định. Giữ ô/mẫu số và báo 11/12 ô có tuyến; phân bổ A20 sang 6 RC2/7 RC3/7 RC4. B/C giữ 5 mỗi RC. Khi ranh giới, dải bất định hoặc graph thay đổi có căn cứ, phải đánh giá lại giới hạn và tính lại bộ mẫu. Notebook03/05 xem chính sách, QA và tiến độ.

## 4. Chấm và chọn30

Chuẩn hóa X, tính C1–C7 với25/15/15/15/10/10/10; nhiều seed, weighted greedy và swap; tính lại toàn tập theo từng phương án. Giữ A10/B8/C12 và18/12, các điều kiện graph/hình học/overlap/đa dạng. Xuất classification60, selected30/reserve30, biến GIS, X, lịch sử, độ nhạy, ma trận và tên đường. C6 quan sát thiếu giữ NULL; ước tính2,5/5 có khoảng điểm riêng. Notebook06; không gọi bộ đề xuất là đã khảo sát.

## 5. Chuẩn bị và nhập bằng chứng

Tự động registry/checklist/câu hỏi/ưu tiên xác minh/lịch3khunggiờ×2lượt. Không sinh giá trị lane/tốc độ thực địa. CSV quan sát dùng ngày/múi giờ/người/bằng chứng/đơn vị/phạm vi/phiên bản; import nguyên byte, idempotent, lỗi batch từ chối. G1 quyền đi, G4 công trình, G5 lặp2ngày, G6 neo đầu/cuối; C6 cần đủ đánh giá thành phần và G passed. Notebook07.

## 6. Cập nhật và công bố phiên bản kỹ thuật

Áp làn/tốc độ theo chiều dài đoạn thực quan sát; không extrapolate điểm hoặc count một phần. Giữ OSM/mô hình/quan sát riêng. Chấm lại C1–C7, D/độ phủ/trùng/đa dạng và chọn lại cùng quota. Loại G failed/C6=0/xung đột graph; nếu thiếu ứng viên báo infeasible. Công bố snapshot riêng khi đủ bằng chứng. Sai hình học/chiều/rẽ cần graph mới có kiểm tra; mô tả tự do không đủ để tự vẽ hoặc bịa lệnh rẽ.

## 7. Nhập và kiểm tra chuyến đo

Khi có trips.csv/gps_points.csv, lưu raw nguyên byte và hash. Kiểm schema/ID/đơn vị/timestamp/routeversion, giữ cờ dòng lỗi. Phát hiện trùng/giảm thời gian/gap/GPS nhảy/tốc độ/gia tốc/độ chính xác. Đổi WGS84 sang EPSG:3405; ghép theo cung có hướng/tiến độ/đúng tuyến; báo mơ hồ/sai chiều/lệch thay vì gán giả. Ngưỡng QC là tham số kỹ thuật cần hiệu chỉnh thiết bị, không thông số Hà Nội đã đo.

## 8. Chỉ tiêu vận hành và báo cáo

Tính thời gian khai báo/hợp lệ/tỷ lệ bao phủ; quãng đường tốc độ/GPS/ghép riêng; tốc độ trung bình/moving, idle/moving, tăng/giảm/cruise và gia tốc. Mỗi chỉ tiêu ghi đơn vị/mẫu số; không nối gap lớn hoặc nội suy âm thầm. Chưa có dữ liệu trả awaiting_measurements. Demo tách riêng, không tính là chuyến thực. Notebook08.

## Chạy, tiếp tục và kiểm chứng

Notebook09 gọi toàn bộ module, cập nhật báo cáo sau từng bước; Ctrl+C chạy lại với force=False. Test dữ liệu lỗi/phiên bản/quota/bytecache/đơn vị/mẫu số/ghép có hướng; sohash nguồn trước/sau. Chỉ nhận cache cómanifest đầy đủ/hashkhớp. Tài liệu quy trình ở `work/docs/lez/PROJECT_AUTOMATION.md`. Không suy tỷ lệ hoàn thành dự án từ sốcell; báo riêng đã tạo/bằng chứng/chuyến/thành phần chờ.
