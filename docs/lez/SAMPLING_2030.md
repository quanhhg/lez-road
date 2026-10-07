> Tài liệu đối chiếu lịch sử. Từ 06/10/2026, phạm vi sinh/chọn tuyến dùng LEZ-first theo [PROJECT_AUTOMATION.md](PROJECT_AUTOMATION.md); các điều chỉnh dân cư/V/N dưới đây không điều khiển ranh giới A/B/C hiện hành.

# Hướng dẫn sinh ứng viên LEZ2030 cũ — lịch sử

Thiết kế hiện hành từ 06/10/2026 là 60 ABC 20/20/20 và chọn 30 ABC 10/8/12, tương ứng 18 trong/12 ngoài LEZ2030. Hướng dẫn chạy mới: [work/docs/lez/SAMPLING_ABC.md](SAMPLING_ABC.md) và [work/docs/lez/SELECTION_30.md](SELECTION_30.md).

Phạm vi LEZ đã chuẩn hóa giữ nguyên; xem [work/docs/lez/NORMALIZATION_2030.md](NORMALIZATION_2030.md). ABC và trạng thái LEZ được chồng lớp riêng. Cấu hình `sampling_2030.json` phục vụ chuẩn hóa/lịch sử, không làm nguồn sinh 60 hiện hành.

Quota 20/40 và 12/18, ma trận 60 ô V/N và báo cáo `latest_sampling_2030.json` là kết quả thiết kế trước. Bundle cũ giữ truy vết; không sử dụng CSV cũ thay nguồn `latest_sampling_abc.json`. Bản tài liệu cũ nằm trong backup trước chuyển thiết kế.
