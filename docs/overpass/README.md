# Lưới tải OSM cho dự án tuyến khảo sát Hà Nội

Dự án đã đặt trong `work`, chia theo loại tệp. Dữ liệu/trạng thái/truy vấn ở `data/hanoi_tiles`; bản đồ ở `maps/hanoi_tiles`; báo cáo ở `reports/overpass`; mã nguồn ở `scripts/overpass`; notebook ở `notebooks`. Xem `work/README.md` để mở đúng tệp. Dữ liệu hiện đã tải đủ **183/183 ô**.

Đã tạo **183 ô vuông 5 × 5 km** trong hệ tọa độ **EPSG:3405**, giữ các ô có diện tích giao với đa giác ranh giới Hà Nội. Các ô phủ hết ranh giới đã tải; mỗi ô có một bbox và một truy vấn Overpass. Đây là cách chia công việc tải dữ liệu, chưa phải cách chia vùng nghiên cứu V1–V5/N1–N10 hay chọn 60 tuyến khảo sát.

## Dữ liệu đầu vào và giới hạn

- Ranh giới lấy trực tiếp qua Overpass từ [OSM relation 1903516](https://www.openstreetmap.org/relation/1903516), cùng mốc **2026-10-01T00:00:00Z** với notebook tải OSM trước đó.
- Ranh giới là dữ liệu kỹ thuật từ OSM, **chưa được đối chiếu với lớp ranh giới pháp lý chính thức**. Không dùng lớp này để tự suy ra ranh giới LEZ.
- Diện tích đa giác sau chiếu: **3351,54 km²**. Đây là diện tích hình học của ranh giới OSM đã tải, không phải số diện tích hành chính đã xác nhận.
- Các ô ven ranh giới giữ nguyên hình vuông nên tổng diện tích ô là **4575 km²**. Sau khi tải và ghép dữ liệu, mới lọc về ranh giới Hà Nội.
- Tiến độ tải mạng đường được ghi trong `tiles.csv` và `latest_run.json`; `pending` nghĩa là đang chờ tải. 5 km là kích thước khởi đầu được đề xuất, chưa được chứng minh phù hợp với tải truy vấn ở từng nơi. Xem `DOWNLOAD_README.md` để chạy bộ tải tự động trong notebook `work/notebooks/1_download_osm.ipynb`.
- Nguồn: © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).

## Mở file nào

| File | Công dụng |
|---|---|
| `02_prepare_download_tiles.ipynb` | Xem lưới, chọn ô, lấy BBOX/QUERY và kiểm tra độ phủ |
| `tiles.csv` | 183 công việc tải, mỗi dòng một ô lá đang hoạt động |
| `hanoi_download_grid.gpkg` | Mở trong QGIS; có ranh giới, ô vuông tải và phần Hà Nội trong từng ô |
| `download_tiles.geojson` | Ô tải trong EPSG:4326 để xem trong phần mềm GIS khác |
| `hanoi_boundary.geojson` | Ranh giới Hà Nội từ OSM |
| `queries/*.ql` | Truy vấn hoàn chỉnh của từng ô, cùng mốc dữ liệu |
| `hanoi_download_grid.png` | Bản đồ xem nhanh của lưới ban đầu |
| `qa_report.json`, `split_checks.json` | Kết quả kiểm tra lưới và chức năng chia ô |
| `tiles_history.json` | Toàn bộ ô, gồm ô cha đã chia; module dùng file này để quản lý việc chia |
| `tile_project.json`, `data/raw/*` | Cấu hình, dữ liệu ranh giới gốc, truy vấn và bằng chứng nguồn |

## Sử dụng trong VS Code

1. Mở notebook `02_prepare_download_tiles.ipynb`, chọn kernel **Python (PyQGIS 4.2.3)** đã chuẩn bị. Chạy các cell đọc dữ liệu. Notebook không gửi request tải đường.
2. Chọn `TILE_ID`. Ví dụ có sẵn: `HN_R011_C012`, một ô chứa điểm trung tâm Hà Nội gần 21.028°N, 105.854°E. Một ô có thể chứa nhiều đường và nhiều tuyến khảo sát.
3. Cell chọn ô tạo `BBOX`, `SNAPSHOT_UTC`, `QUERY`. Nếu tiếp tục dùng notebook `01_overpass_api_download.ipynb`, thay BBOX và snapshot trong cell cấu hình bằng giá trị vừa in, rồi chạy lại từ cell cấu hình trở xuống để tạo đúng QUERY và cache. Các QUERY đã chuẩn bị cũng có thể gửi bằng POST với form `data=QUERY` tới endpoint trong `tile_project.json`.
4. Với cả thành phố, bộ tải sẽ duyệt các dòng trong `tiles.csv`, ghi kết quả riêng từng ô, kiểm tra response và cho phép chạy tiếp các ô còn thiếu. Bộ tải tự động hiện có trong `download_tiles.py`; xem `DOWNLOAD_README.md`. Không tải đồng thời ô cha đã chia và các ô con.
5. Sau khi đủ ô, ghép các response và khử trùng theo **(type, id)**: `node/123` và `way/123` là hai đối tượng khác nhau. Nếu cùng đối tượng có dữ liệu mâu thuẫn dù cùng snapshot, cần kiểm tra nguồn/cache. Sau đó dựng mạng đường, lọc phạm vi và quyền đi xe máy.

## Đọc bảng ô

- `HN_R011_C012`: hàng 11, cột 12. Hàng tăng từ nam lên bắc; cột tăng từ tây sang đông. Đếm từ 0 tại gốc lưới ghi trong `tile_project.json`.
- `south, west, north, east`: bbox theo đúng thứ tự **vĩ độ nam, kinh độ tây, vĩ độ bắc, kinh độ đông** mà Overpass dùng. Không đổi thành x,y.
- `side_m`: cạnh ô trong hệ tọa độ mét. Bbox WGS84 là hình chữ nhật bao ô sau chuyển hệ; không phải hình vuông tính bằng độ.
- `scope_fraction`: phần diện tích ô nằm trong ranh giới Hà Nội, từ 0 đến 1. Ô có tỷ lệ nhỏ vẫn được giữ nếu có diện tích giao dương.
- `parent_id`, `depth`: theo dõi ô con khi chia; ô gốc có parent rỗng, depth=0.
- `query_file`, `response_dir`: đường dẫn tương đối từ thư mục này; response_dir chứa dữ liệu gốc và manifest đã tải.

Các ô vuông trong EPSG:3405 không chồng diện tích. **Bbox sau chuyển hệ có thể chồng nhau**, và các way/relation được lấy đủ thành viên có thể vượt bbox; vì vậy bước khử trùng vẫn cần thiết.

## Chia một ô khi cần

Trong notebook, sau khi import module:

```python
result = grid.split_tile("HN_R011_C012", root=ROOT)
result["children"]
```

Lệnh này thay một ô 5 km bằng các ô 2,5 km có diện tích trong Hà Nội, cập nhật bảng, truy vấn và lớp GIS; ô cha chuyển thành `split`. Đuôi `_SW/_SE/_NW/_NE` chỉ phía tây nam/đông nam/tây bắc/đông bắc. Có thể chia tiếp xuống 1,25 km; module chặn chia nhỏ hơn.

**Không chạy lệnh chia chỉ để xem thử trên bộ dữ liệu đang dùng.** Chỉ chia ô chưa tải, hoặc ô đã xác định truy vấn quá nặng. Lỗi 429 cần đợi theo phản hồi máy chủ; không mặc định giải quyết bằng chia ô. Lỗi 504 cần xem tải máy chủ và độ nặng query trước khi quyết định. Không chia lại ô cha đã chia hoặc ô đã hoàn thành.

Bộ tải `download_tiles.py` đồng bộ trạng thái trong `tiles.csv` và `tiles_history.json` sau từng ô, có giao dịch khôi phục và khóa dùng chung với `build_tiles.py`. Dừng bộ tải trước khi verify/split; chức năng chia ô giữ tiến độ các ô khác và chặn chia ô đã hoàn thành. Bản đồ PNG là ảnh lưới ban đầu; sau khi chia, dùng lớp GPKG/GeoJSON đã cập nhật để xem lưới hiện tại.

## Kiểm tra đã hoàn thành

- Ranh giới được ghép bằng OSM node ID từ các thành viên outer/inner của relation Hà Nội; không ghép nhầm 126 relation `subarea` vào ranh giới.
- Kiểm tra SHA-256 dữ liệu ranh giới, vòng ranh giới kín và hình học hợp lệ; không tự sửa hình học ranh giới.
- Diện tích ranh giới chưa được ô lá phủ: **0 m²**; diện tích chồng lấn ô vuông: **0 m²**.
- Tổng diện tích phần ranh giới trong từng ô khớp diện tích ranh giới với sai số số học dưới 0,01 m².
- Kiểm tra mã ô duy nhất, cạnh và diện tích ô; bbox bao hình ô được lấy mẫu cạnh mỗi 100 m và làm tròn ra ngoài.
- Đọc lại CSV, GeoJSON và ba lớp GPKG, kiểm tra số đối tượng/hệ tọa độ.
- Kiểm tra chia ô đầy đủ, chia ô ven ranh giới, chia hai cấp; chặn chia dưới 1,25 km và chia lại ô cha. Các kiểm tra này chạy trên bản sao tạm, không đổi lưới 183 ô đã giao.

Các kiểm tra trên xác nhận hình học và file đầu ra. Chưa xác nhận thời gian tải đường, tính đầy đủ của dữ liệu OSM ngoài thực địa hay sự phù hợp của ranh giới với văn bản pháp lý.
