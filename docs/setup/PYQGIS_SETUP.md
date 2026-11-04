# Tải, cài và chạy PyQGIS trong work — hướng dẫn từng bước

Hướng dẫn dành cho **macOS**, theo script hiện có của dự án: **QGIS 4.2.3, Python đi kèm QGIS 3.12, kernel `Python (PyQGIS 4.2.3)`**. Đối chiếu mã thiết lập và trang tải chính thức ngày **04/11/2026**. Đây không phải bộ cài chung cho mọi phiên bản QGIS hoặc cho Windows/Linux.

**Có hai việc phải làm:** cài ứng dụng QGIS vào máy, sau đó nối Python của QGIS với notebook trong VS Code. Script của dự án chỉ làm việc thứ hai. Khi hoàn tất, môi trường chạy nằm trong `work/.pyqgis-runtime`, nhưng vẫn cần ứng dụng QGIS trong `/Applications`.

## Đọc trước: các tên gọi và nơi nhập lệnh

| Tên gọi | Hiểu và sử dụng thế nào? |
|---|---|
| QGIS | Ứng dụng GIS được tải về và cài vào máy. |
| PyQGIS | Các công cụ Python đi kèm QGIS để đọc, tính toán và xử lý bản đồ; không phải ứng dụng tải riêng. |
| Python thường | Dùng cho gọi HTTP, bảng dữ liệu, thống kê, biểu đồ và các notebook điều khiển. |
| Kernel | Môi trường Python thực sự chạy các ô lệnh trong notebook. Chọn sai kernel có thể gây lỗi thiếu `qgis`. |
| Runtime | Trình thực thi Python và các thư viện cần để chạy. Ở đây được tạo trong `work/.pyqgis-runtime`. |
| Terminal | Cửa sổ nhập lệnh mở bằng **Terminal → New Terminal** trong VS Code. Các khối ghi `bash` được chạy ở đây. |
| Cell Code | Ô lệnh Python trong notebook `.ipynb`. Ví dụ ghi rõ “trong notebook” được chạy tại đây bằng **Shift + Enter** hoặc nút tam giác. |
| Python Console của QGIS | Cửa sổ Python bên trong ứng dụng QGIS; khác Terminal và notebook. Chỉ dùng ở mục 2. |

`work` là thư mục gốc dự án. Không chép dấu `...` của cách viết rút gọn `.../work` vào lệnh. Không chép dấu bao khối mã hoặc ký hiệu nhắc lệnh như `$` và `>>>`.

Nếu đã có kernel hoạt động, kiểm theo [mục 6](#kiem-tra-notebook) trước; không cần cài lại mỗi ngày. Nếu mới cài máy hoặc chỉ còn kernel cũ bị lỗi, đi từ mục 1.

<a id="tai-cai-qgis"></a>

## 1. Tải và cài ứng dụng QGIS

1. Mở [trang tải QGIS chính thức](https://qgis.org/download/). Nếu trang hiện phần quyên góp, có thể chọn **Skip it and go to download** để đến phần tải.
2. Tìm mục **macOS**. Với script hiện tại, chọn bản **4.2.3**; tại thời điểm đối chiếu, nút tương ứng là **Regular Version for macOS (4.2)**. Kiểm tên tệp trước khi tải vì nút này có thể trỏ sang phiên bản mới về sau. Liên kết bộ cài 4.2.3 được trang QGIS dẫn tới là [qgis_pr_final-4_2_3.dmg](https://download.qgis.org/downloads/macos/pr/qgis_pr_final-4_2_3.dmg).
3. Không chọn Nightly/Testing cho quy trình này. Bản LTR hoặc bản mới hơn không tự tương thích với script đang cố định Python 3.12 và tên kernel 4.2.3. Nếu 4.2.3 không còn tại nút chính, xem [kho phiên bản cũ](https://qgis.org/archive/) thay vì đổi phiên bản mà vẫn dùng nguyên lệnh.
4. Chờ tải xong tệp `.dmg`, thường nằm trong **Downloads**. Nhấp đúp để mở.
5. Kéo biểu tượng ứng dụng QGIS vào **Applications**. Đợi chép xong, rồi mở **Finder → Applications** và chạy QGIS từ đó. Không chạy bản còn nằm trong cửa sổ bộ cài.
6. Ghi lại đúng tên ứng dụng. Script mặc định tìm `/Applications/QGIS-final-4_2_3.app`; nếu tên hoặc vị trí khác, cần truyền đường dẫn thật ở mục 5. Không đổi tên ứng dụng chỉ để che việc cài sai phiên bản.

Cách mở DMG và kéo ứng dụng vào Applications được mô tả trong [hướng dẫn cài QGIS trên macOS](https://qgis.org/resources/installation-guide/#mac-os-x-macos). Nếu macOS báo chặn ứng dụng từ nhà phát triển chưa xác định, xem mục 10.

**Kết quả cần có:** mở được cửa sổ QGIS từ Applications. Có tệp `.dmg` trong Downloads chưa có nghĩa là đã cài xong.

## 2. Kiểm tra PyQGIS ngay trong ứng dụng QGIS

1. Trong QGIS, xem **About QGIS** — thông tin về ứng dụng — để kiểm phiên bản.
2. Mở **Plugins → Python Console**. Đây là cách chạy PyQGIS trực tiếp trong QGIS, theo [tài liệu PyQGIS](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/intro.html#scripting-in-the-python-console).
3. Nhập từng dòng dưới đây vào Console, nhấn Enter sau mỗi dòng:

```python
import sys
from qgis.core import Qgis, QgsApplication
print("QGIS:", Qgis.QGIS_VERSION)
print("Python:", sys.version.split()[0])
print("Thư mục QGIS:", QgsApplication.prefixPath())
```

**Kết quả cần có cho bộ thiết lập này:** QGIS **4.2.3** và Python **3.12.x**. Phần đuôi số bản dựng có thể xuất hiện sau phiên bản QGIS. Nếu QGIS không mở được, xử lý việc cài ứng dụng trước; nếu phiên bản khác, cần đối chiếu hoặc điều chỉnh script trước khi nối notebook.

Chạy được Console mới xác nhận PyQGIS trong ứng dụng; vẫn cần các bước dưới để notebook sử dụng được nó. Trong notebook không có sẵn biến `iface` điều khiển giao diện QGIS như trong Console.

<a id="chuan-bi-vscode"></a>

## 3. Chuẩn bị VS Code, thư mục work và Terminal

1. Nếu chưa có VS Code, tải bản macOS từ [trang chính thức](https://code.visualstudio.com/download), giải nén nếu là `.zip`, rồi đưa ứng dụng vào Applications và mở lên.
2. Trong VS Code, mở mục **Extensions** ở thanh bên trái. Tìm và cài hai phần mở rộng **Python** và **Jupyter**, đều do **Microsoft** phát hành. Nếu đã cài thì bỏ qua.
3. Chọn **File → Open Folder…**, chọn thư mục **work** của dự án. Bên trái cần thấy `notebooks`, `scripts`, `config` và `requirements-notebook.txt`.
4. Chọn **Terminal → New Terminal**. Chạy lần lượt hai lệnh:

```bash
pwd
ls
```

`pwd` cho biết thư mục hiện tại; `ls` liệt kê nội dung. Terminal cần đang ở gốc `work`, không phải ở `notebooks` hay `scripts`. Nếu sai, mở Terminal mới sau khi mở đúng thư mục; hoặc nhập `cd `, kéo thư mục `work` từ Finder vào Terminal rồi nhấn Enter.

5. Kiểm Python dùng để khởi chạy script thiết lập:

```bash
python3 --version
```

Nếu hiện phiên bản Python thì có thể tiếp tục. Đây là Python khởi chạy bộ cài, không nhất thiết trùng Python 3.12 đi kèm QGIS. Nếu báo `command not found`, tải bộ cài `.pkg` tại [Python cho macOS](https://www.python.org/downloads/macos/), mở và làm theo trình cài; sau đó mở Terminal mới và kiểm lại. Bản cài từ python.org có bước **Install Certificates.command** được giải thích trong [hướng dẫn Python trên macOS](https://docs.python.org/3/using/mac.html#installation-steps).

6. Kiểm hai công cụ macOS mà script sử dụng:

```bash
command -v install_name_tool
command -v codesign
```

Mỗi lệnh cần in ra đường dẫn công cụ. Nếu thiếu, chạy `xcode-select --install` trong Terminal, chọn **Install** trong cửa sổ của Apple, chờ hoàn tất rồi kiểm lại. Không cần cài toàn bộ ứng dụng Xcode chỉ cho bước này.

**Kết quả cần có:** Terminal ở `work`, gọi được `python3` và có hai công cụ trên. Các bước này chưa tải dữ liệu OSM.

## 4. Kiểm đường dẫn ứng dụng trước khi thiết lập

Trong Terminal ở `work`, chép cả khối dưới đây. Dòng `PY` cuối cùng cũng phải được chép:

```bash
python3 - <<'PY'
from pathlib import Path

qgis_app = Path("/Applications/QGIS-final-4_2_3.app")
checks = {
    "Ứng dụng QGIS": qgis_app.is_dir(),
    "Python 3.12 của QGIS": (qgis_app / "Contents/MacOS/python3.12").is_file(),
    "Thư viện nền QGIS": (qgis_app / "Contents/Frameworks").is_dir(),
    "Tài nguyên QGIS": (qgis_app / "Contents/Resources/qgis").is_dir(),
}
for name, ok in checks.items():
    print(name, "OK" if ok else "CHƯA TÌM THẤY")
PY
```

Nếu ứng dụng có tên khác, sửa **chỉ chuỗi đường dẫn ở dòng `qgis_app = ...`** cho đúng tên đã thấy trong Finder. Trong Finder có thể chọn ứng dụng, nhấn **Command + I** để xem tên và vị trí. Đường dẫn ứng dụng phải kết thúc bằng `.app`.

**Chỉ tiếp tục khi cả bốn dòng đều OK và phiên bản ở mục 2 khớp.** Dòng “CHƯA TÌM THẤY” có thể là sai đường dẫn hoặc thiếu ứng dụng, không phải lỗi dữ liệu tuyến. Khối trên chỉ đọc cấu trúc tệp; chưa kiểm được việc nạp thư viện.

<a id="tao-kernel"></a>

## 5. Tạo môi trường PyQGIS bên trong work

Đóng hoặc dừng các kernel PyQGIS đang chạy trước khi đăng ký lại. Trong Terminal ở `work`, với đúng ứng dụng mặc định đã kiểm ở mục 4, chạy:

```bash
python3 scripts/setup/setup_pyqgis_kernel.py --project-dir .
```

Dấu `.` nghĩa là thư mục Terminal hiện tại, tức gốc `work`. Nếu **cùng bản QGIS/Python tương thích** nhưng ứng dụng có tên khác, dùng `--qgis-app`. Ví dụ sau chỉ áp dụng nếu đã xác nhận ứng dụng thật sự là `/Applications/QGIS.app`:

```bash
python3 scripts/setup/setup_pyqgis_kernel.py --project-dir . --qgis-app "/Applications/QGIS.app"
```

Không chạy cả hai lệnh khi lệnh đầu đã dùng đúng ứng dụng. Đổi đường dẫn không tự làm script tương thích phiên bản QGIS khác.

Script sẽ lần lượt:

1. Kiểm Python đi kèm QGIS và công cụ macOS.
2. Sao chép tệp thực thi Python vào `work/.pyqgis-runtime/bin/python3.12`, cấu hình đường dẫn thư viện và ký bản sao bằng `codesign`.
3. Cài `ipykernel` cùng các phụ thuộc notebook vào thư mục riêng dưới `.pyqgis-runtime` nếu chưa dùng lại được thư viện có sẵn. Bước này cần mạng khi phải tải gói; dòng `Installing notebook dependencies...` là thông báo tiến độ, không tự nó là lỗi.
4. Thiết lập các đường dẫn cần để nạp QGIS, Qt, PROJ và GDAL.
5. Thử import và chạy thuật toán tạo vùng đệm `native:buffer` trên một đường thử trong bộ nhớ.
6. Đăng ký kernel tên nội bộ `pyqgis-423`, tên hiển thị **Python (PyQGIS 4.2.3)**.

**Chỉ coi là hoàn tất khi lệnh kết thúc thành công và có các dòng sau:**

```text
Import and GIS checks passed: ...
Registered kernel: ...
In VS Code select kernel: Python (PyQGIS 4.2.3)
```

Ở đây `...` thay cho thông tin phiên bản/đường dẫn được in thực tế. Nếu cuối cùng có Traceback hoặc lỗi, chuyển đến mục 10; đừng coi dòng “Installing…” là đã cài thành công.

Cấu trúc sau khi tạo:

```text
work/
├── scripts/setup/setup_pyqgis_kernel.py
├── notebooks/
└── .pyqgis-runtime/
    ├── bin/python3.12
    └── packages hoặc packages-...
```

Thư mục bắt đầu bằng dấu chấm có thể bị Finder ẩn; nhấn **Command + Shift + .** để hiện. Đăng ký kernel còn tạo tệp `kernel.json` trong thư mục Jupyter của tài khoản. Tệp này giữ đường dẫn Python và các biến môi trường; không cần tự sửa nó.

Script cập nhật kernel cùng tên nếu đã có. Nó không tải/cài ứng dụng QGIS, không dựng mạng, không gửi truy vấn Overpass. Ứng dụng QGIS gốc vẫn phải được giữ nguyên vị trí. Runtime từng nằm ở `work/../.pyqgis-runtime` không được mang theo khi chỉ sao chép `work`; lệnh trên tạo runtime mới bên trong `work`.

Để chỉ xem tham số mà không cài, dùng `python3 scripts/setup/setup_pyqgis_kernel.py --help`. `--packages-dir` dành cho dùng lại thư viện đã có; `--kernel-prefix` đổi nơi đăng ký kernel. Người mới nên để mặc định vì controller của dự án tìm kernel ở vị trí tài khoản thông thường.

<a id="kiem-tra-notebook"></a>

## 6. Chọn kernel trong VS Code và chạy thử

1. Mở một notebook `.ipynb` trong `work/notebooks`.
2. Bấm **Select Kernel** hoặc tên kernel ở góc trên bên phải.
3. Nếu chưa thấy lựa chọn cần dùng, chọn **Select Another Kernel… → Jupyter Kernels → Python (PyQGIS 4.2.3)**. Chọn kernel đã đăng ký này để có đủ biến môi trường; không chọn riêng tệp Python trong `.pyqgis-runtime/bin` như một Python thường.
4. Nếu vừa thiết lập lại, bấm **Restart Kernel**. Nếu danh sách chưa cập nhật, nhấn **Command + Shift + P**, tìm **Developer: Reload Window**, chạy rồi chọn lại.
5. Thêm một cell **Code**, chép đoạn sau và nhấn **Shift + Enter**:

```python
import os
import sys
import ipykernel
from pathlib import Path
from qgis.core import Qgis

print("Python đang chạy:", sys.executable)
print("Phiên bản Python:", sys.version.split()[0])
print("Phiên bản QGIS:", Qgis.QGIS_VERSION)
print("ipykernel:", ipykernel.__version__)
print("Thư mục hiện tại:", Path.cwd())
print("Thư mục ứng dụng:", os.environ.get("PYQGIS_APP_CONTENTS"))
```

**Kết quả cần có:** không có Traceback; Python 3.12.x và QGIS 4.2.3; đường dẫn Python chỉ đến `.pyqgis-runtime/bin/python3.12` trong `work` vừa thiết lập. Nếu vẫn chỉ đến runtime bên ngoài `work`, notebook đang dùng đăng ký cũ hoặc kernel chưa khởi động lại.

Việc chọn kernel độc lập với Python trong Terminal và Python được trình soạn thảo chọn để gợi ý mã. Chọn kernel có cùng tên chưa đủ: kết quả chạy cell mới xác nhận môi trường hoạt động. Xem [cách VS Code quản lý kernel](https://code.visualstudio.com/docs/datascience/jupyter-kernel-management).

### Kiểm thêm một phép xử lý GIS

Sau cell trên, chạy cell dưới. Nó tạo một đường và vùng đệm trong bộ nhớ, không đọc/sửa dữ liệu dự án hoặc gọi API:

```python
import os
from qgis.core import QgsApplication, QgsVectorLayer, QgsFeature, QgsGeometry
from qgis.analysis import QgsNativeAlgorithms

qgis_app = QgsApplication.instance()
if qgis_app is None:
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    qgis_app = QgsApplication([], False)
    qgis_app.initQgis()

registry = QgsApplication.processingRegistry()
if registry.providerById("native") is None:
    registry.addProvider(QgsNativeAlgorithms())

import processing

demo_line = QgsVectorLayer("LineString?crs=EPSG:3405", "duong_thu", "memory")
demo_feature = QgsFeature()
demo_feature.setGeometry(
    QgsGeometry.fromWkt("LINESTRING (500000 2300000, 500100 2300000)")
)
demo_line.dataProvider().addFeatures([demo_feature])
demo_buffer = processing.run("native:buffer", {
    "INPUT": demo_line, "DISTANCE": 10, "SEGMENTS": 8,
    "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
    "DISSOLVE": False, "OUTPUT": "memory:",
})["OUTPUT"]
assert demo_buffer.isValid() and demo_buffer.featureCount() == 1
print("Đạt: tạo được 1 vùng đệm cách đường thử 10 m.")
```

Nếu hiện dòng “Đạt…” thì Processing đã chạy được phép thử. Giữ biến `qgis_app` trong lúc làm việc; không gọi `exitQgis()` giữa notebook còn dùng đối tượng GIS. Khi xong có thể **Restart Kernel** để đóng môi trường thử, rồi chạy notebook dự án từ cell đầu. Bản đồ không tự xuất hiện trong cửa sổ QGIS; ví dụ dùng lớp tạm trong bộ nhớ của notebook.

<a id="chon-moi-truong"></a>

## 7. Chọn môi trường cho đúng notebook dự án

| Notebook/công việc | Chọn gì? | Cần biết |
|---|---|---|
| 01 — HTTP Overpass, CSV và tiến độ | Python thường có thư viện dự án | Giữ `ENABLE_PYQGIS=False` nếu không chạy phần GIS tùy chọn. |
| 02 — kiểm tra/chia lưới bằng `build_tiles` | **Python (PyQGIS 4.2.3)** | Import PyQGIS trực tiếp; module tải đi kèm còn cần `requests`. |
| 03/04/05/06 — ranh giới, mạng và chọn tuyến | Python thường có thư viện dự án; hoặc PyQGIS nếu đủ thư viện | Bộ điều khiển gọi tiến trình PyQGIS đã đăng ký cho phần GIS. |
| 07/08/09 — bằng chứng, GPS và điều phối | Python thường có thư viện dự án; hoặc PyQGIS nếu đủ thư viện | Những bước GIS vẫn cần runtime PyQGIS; cài xong môi trường chưa thay cho khôi phục dữ liệu. |
| 10 — đối chứng M0 trên dữ liệu lưu sẵn | Python thường | Cần NumPy/Matplotlib; không khởi động QGIS. |
| 11 — biểu đồ đối chứng | Python thường | Dùng thư viện trong `requirements-notebook.txt`; không khởi động QGIS. |
| Cell tự viết import `qgis.core` hoặc `processing` | Kernel PyQGIS | Cell phải chạy ngay trong môi trường có QGIS. |

Để tạo Python thường **Python (Hanoi work)**, làm [mục 2 của hướng dẫn máy mới](GETTING_STARTED.md#2-tạo-python-thường-cho-notebook). Đây là môi trường riêng với `.pyqgis-runtime`; không cài cả `requirements-notebook.txt` vào ứng dụng QGIS để thay cho bước đó.

### Nếu kernel PyQGIS thiếu requests

Script thiết lập cài phụ thuộc notebook (`ipykernel`), không cam kết cài mọi thư viện phân tích của dự án. Trong kernel PyQGIS, chạy `import requests` trước khi dùng notebook 02. Chỉ khi báo thiếu `requests`, chạy cell sau để bổ sung vào **thư mục gói của runtime trong work**, rồi restart và kiểm lại:

```python
import os
import subprocess
import sys
from pathlib import Path

runtime_dir = Path(sys.executable).resolve().parents[1]
packages_dir = Path(os.environ["PYTHONPATH"].split(os.pathsep)[0]).resolve()
assert runtime_dir.name == ".pyqgis-runtime"
assert (runtime_dir.parent / "scripts/setup/setup_pyqgis_kernel.py").is_file(), "Runtime không thuộc thư mục work."
assert packages_dir.is_relative_to(runtime_dir), "Đường dẫn gói không nằm trong runtime mới."
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "--target", str(packages_dir), "requests"
])
```

Cell cần mạng để tải gói Python; không gửi truy vấn OSM. Nếu assert không đạt, quay lại mục 5–6 để dùng đúng runtime trong `work`. Với notebook điều khiển thiếu `pandas`, NumPy hoặc thư viện biểu đồ, dùng **Python (Hanoi work)** đã cài `requirements-notebook.txt`.

<a id="kiem-tra-du-an"></a>

## 8. Kiểm dữ liệu dự án sau khi môi trường chạy được

Chỉ làm bước này khi đã khôi phục dữ liệu/cấu hình cần thiết theo [hướng dẫn máy mới](GETTING_STARTED.md#3-khôi-phục-hoặc-dựng-dữ-liệu). Từ Terminal ở `work`:

```bash
python3 scripts/lez/pipeline.py check
```

Lệnh dùng kernel PyQGIS đã đăng ký để kiểm phiên bản và `requests`, đồng thời đối chiếu nguồn OSM, cấu hình, hash và manifest. Nó không gửi HTTP, không dựng lại mạng. Kết quả thành công cần có phiên bản `qgis`, số ô `selected_tiles` và `raw_hashes_and_manifests_match: true`.

Nếu cell ở mục 6 chạy được nhưng lệnh này báo thiếu dữ liệu/hash, hãy xử lý đúng tệp được báo ở bước khôi phục dữ liệu. Không cài lại QGIS để chữa một CSV hoặc bundle còn thiếu.

## 9. Cách dùng hằng ngày và khi chuyển máy

1. Mở VS Code → **Open Folder → work**.
2. Mở notebook cần dùng, chọn kernel theo mục 7.
3. Chạy cell thiết lập đầu notebook, sau đó cell kiểm tra/trạng thái và các bước cần làm. Khi đổi kernel, restart rồi chạy lại từ đầu.
4. Không cần mở giao diện QGIS trong lúc notebook chạy qua kernel đã đăng ký. Tuy vậy, ứng dụng QGIS vẫn phải còn trên máy và đúng đường dẫn.
5. Không chạy lại bộ cài mỗi lần làm việc. Chỉ thiết lập lại khi mới cài, kernel lỗi, hoặc chuyển/đổi thư mục `work`, ứng dụng QGIS hay phiên bản tương ứng.

Không chạy trực tiếp `.pyqgis-runtime/bin/python3.12` như một Python thường rồi kết luận runtime hỏng: bản sao cần các biến môi trường đã được kernel khai báo. Với lệnh GIS trong Terminal, dùng các bộ điều khiển của dự án như mục 8.

Khi chuyển máy, sao chép/clone `work`, khôi phục dữ liệu cần thiết, cài QGIS tương thích trên máy mới rồi chạy lại mục 3–6. Đường dẫn tuyệt đối trong đăng ký kernel cũ không tự đổi theo thư mục mới. Giữ bản cũ cho đến khi môi trường mới kiểm thành công; không cần xóa runtime để bắt đầu thử sửa.

<a id="xu-ly-loi"></a>

## 10. Những lỗi thường gặp và việc cần làm

| Biểu hiện | Cách xử lý |
|---|---|
| `can't open file ...setup_pyqgis_kernel.py` | Terminal đang sai thư mục hoặc repo thiếu script. Kiểm `pwd`, `ls`, mở đúng `work` theo mục 3. |
| `QGIS Python not found` | Kiểm bốn dòng ở mục 4. Cài/khôi phục ứng dụng và dùng đúng `--qgis-app`; script không tự tải QGIS. |
| Có tên kernel nhưng kernel không khởi động | Kiểm ứng dụng QGIS và trình thực thi Python còn tồn tại. Tên kernel có thể là đăng ký cũ; khôi phục ứng dụng tương thích, thiết lập lại mục 5 rồi chọn lại. |
| `No module named 'qgis'` | Cell import GIS đang chạy sai kernel hoặc cài QGIS chưa hoàn chỉnh. Kiểm Console ở mục 2, sau đó chọn đúng **Jupyter Kernel** ở mục 6. |
| `No module named 'ipykernel'`, `zmq` hoặc lỗi tải pip | Bộ cài notebook chưa hoàn tất. Kiểm mạng và phần lỗi cuối, chạy lại mục 5 sau khi sửa nguyên nhân. Dòng “Installing…” chưa xác nhận thành công. |
| `No module named 'requests'` trong PyQGIS | Làm phần bổ sung `requests` ở mục 7. Với Python thường, cài requirements theo hướng dẫn máy mới. |
| Thiếu `pandas`, `numpy`, `matplotlib` hoặc `seaborn` | Với notebook điều khiển/biểu đồ, chọn **Python (Hanoi work)** đã cài requirements. Không mặc định mọi kernel có cùng thư viện. |
| `No module named 'processing'` hoặc không tìm thấy `native:buffer` | Chọn kernel do script đăng ký; nó khai báo thư mục plugin QGIS. Chạy đầy đủ cell Processing ở mục 6 để khởi tạo QGIS và bộ thuật toán native. |
| `dyld`, `Library not loaded`, thiếu `libpython3.12.dylib` | Bản sao Python còn nhưng thư viện QGIS thiếu/đổi chỗ hoặc không tương thích. Khôi phục đúng ứng dụng rồi thiết lập lại. Cài thêm ipykernel không thay được thư viện QGIS. |
| `failed to get the Python codec of the filesystem encoding`, thiếu `encodings` | Thường do chạy bản sao Python thiếu `PYTHONHOME` hoặc ứng dụng QGIS bị mất. Dùng kernel đã đăng ký; nếu vẫn lỗi, kiểm ứng dụng rồi thiết lập lại. |
| `different Team IDs` khi nạp thư viện notebook | Lỗi từng gặp với Python trong ứng dụng QGIS. Dùng bản sao trình thực thi Python được script cấu hình/ký và kernel tương ứng; không sửa chữ ký ứng dụng QGIS bằng tay. |
| Không thấy kernel mới | Dùng **Select Another Kernel → Jupyter Kernels**, rồi **Developer: Reload Window**; bảo đảm đang làm việc trên máy đã cài, không phải phiên SSH/remote khác. |
| Pylance gạch đỏ nhưng cell vẫn chạy | Gợi ý mã và kernel là hai phần riêng. Mở đúng workspace, giữ cấu hình `python.analysis.extraPaths` của dự án; ưu tiên kết quả chạy cell để xác nhận lỗi thực thi. |
| `No module named 'project_paths'` hoặc module dự án khác | Chạy lại cell thiết lập đường dẫn đầu notebook, mở đúng `work`, kiểm script còn đủ. Đây không tự động là lỗi thiếu QGIS. |
| macOS chặn mở ứng dụng | Với ứng dụng đã tải từ QGIS chính thức, thử mở rồi vào **System Settings → Privacy & Security → Open Anyway** nếu nút xuất hiện, theo [hướng dẫn Apple](https://support.apple.com/en-ie/102445). Nếu báo phần mềm gây hại, không dùng quy trình này để bỏ qua cảnh báo. |

Không đặt tên tệp tự viết là `qgis.py` vì có thể che module QGIS thật. Không dùng `pip install qgis` để thay cho bộ QGIS/PyQGIS đi kèm ứng dụng.

Nếu cần nhờ xử lý lỗi, giữ phần thông báo từ **Traceback/lỗi đầu tiên đến dòng cuối**, tên kernel đã chọn và kết quả mục 4 hoặc cell mục 6 chạy được. Chỉ ảnh tên kernel không đủ để xác định môi trường đang dùng.

## 11. Mã và tài liệu liên quan

- [Script thiết lập trong dự án](../../scripts/setup/setup_pyqgis_kernel.py): nguồn xác định tham số, thư viện được cài và tên kernel.
- [Hướng dẫn sử dụng work](../../HUONG_DAN_SU_DUNG_WORK.md#moi-truong): chọn notebook và thứ tự chạy toàn bộ quy trình.
- [Bắt đầu trên máy mới](GETTING_STARTED.md): Python thường và các dữ liệu cần khôi phục.
- [PyQGIS chạy ngoài ứng dụng](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/intro.html#using-pyqgis-in-standalone-scripts): giải thích khởi tạo và đường dẫn QGIS. Trang được dẫn là tài liệu 3.44 về cơ chế chung; không thay kiểm tương thích bản 4.2.3 của script này.
- [Đăng ký kernel IPython](https://ipython.readthedocs.io/en/stable/install/kernel_install.html): tên kernel, tên hiển thị và nơi đăng ký.

**Điều kiện để bắt đầu bước GIS của dự án:** ứng dụng QGIS mở được, bộ thiết lập kết thúc thành công, cell import và phép thử Processing chạy được, rồi mới kiểm đầu vào dự án. Việc cài môi trường không tự xác nhận dữ liệu tuyến hoặc kết quả khảo sát đã hoàn tất.
