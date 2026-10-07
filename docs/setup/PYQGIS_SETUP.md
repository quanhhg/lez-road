# Cài môi trường PyQGIS cho notebook trong work

Hướng dẫn dành cho macOS với QGIS 4.2.3 đang có trên máy. PyQGIS là API Python đi kèm QGIS; phần thiết lập ở đây giúp VS Code/Jupyter dùng đúng Python và thư viện của QGIS.

## Tài liệu, script và runtime nằm ở đâu?

```text
work/
├── docs/setup/PYQGIS_SETUP.md          Hướng dẫn này
├── scripts/setup/setup_pyqgis_kernel.py
├── notebooks/                        Notebook làm việc
└── .pyqgis-runtime/                  Được tạo khi cài theo mục 3
    ├── bin/python3.12                Bản sao interpreter của QGIS
    └── packages hoặc packages-...    Thư viện notebook
```

Hiện kernel đã đăng ký dùng runtime ở `../.pyqgis-runtime`, tính từ `work`. Khi kiểm tra ngày 04/10/2026, môi trường này import thành công QGIS 4.2.3, Python 3.12.11, ipykernel 7.4.0 và pyzmq 27.2.0. Việc thêm tài liệu chưa chuyển runtime hay đăng ký lại kernel.

Tạo runtime bên trong `work` bằng mục 3. QGIS vẫn là ứng dụng cài trong `/Applications`; bản sao interpreter và thư viện notebook nằm trong dự án và tiếp tục sử dụng thư viện của ứng dụng QGIS đó.

## 1. Chuẩn bị

- QGIS hiện tại: `/Applications/QGIS-final-4_2_3.app`.
- VS Code có các extension Python và Jupyter; mở thư mục `work` làm workspace.
- Terminal có `python3`, `install_name_tool` và `codesign`. Hai công cụ cuối được script dùng để cấu hình bản sao interpreter trên macOS.
- Có mạng nếu cần tải thư viện notebook bằng pip. Việc cài này không gọi Overpass hoặc tải dữ liệu đường.

QGIS chạy ngoài ứng dụng cần đúng đường dẫn module, thư viện và dữ liệu hệ tọa độ. Script thiết lập các đường dẫn theo ứng dụng hiện có, theo cơ chế [PyQGIS trong script độc lập](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/intro.html#using-pyqgis-in-standalone-scripts).

## 2. Kiểm tra kernel đang có

Mở notebook bất kỳ, chọn kernel **Python (PyQGIS 4.2.3)** và chạy:

```python
import sys
import ipykernel
from qgis.core import Qgis

print("Python:", sys.version.split()[0])
print("QGIS:", Qgis.QGIS_VERSION)
print("ipykernel:", ipykernel.__version__)
```

Nếu cell chạy thành công, kernel hiện có dùng được. Chỉ tạo lại khi cần cài mới, sửa môi trường hoặc chuyển vị trí runtime vào `work`.

## 3. Tạo runtime trong work

Trong VS Code mở Terminal và bảo đảm thư mục hiện tại là `work`. Chạy:

```bash
python3 scripts/setup/setup_pyqgis_kernel.py --project-dir .
```

Script thực hiện tuần tự:

1. Kiểm tra Python 3.12 đi kèm QGIS và các công cụ macOS.
2. Sao chép interpreter vào `work/.pyqgis-runtime/bin`, thêm đường dẫn framework QGIS và ký bản sao bằng `codesign`.
3. Kiểm tra thư viện notebook đã có; nếu cần, cài `ipykernel` cùng các phụ thuộc vào thư mục riêng dưới `work/.pyqgis-runtime`.
4. Thiết lập `PYTHONHOME`, `PYTHONPATH`, `QGIS_PREFIX_PATH`, cùng đường dẫn Qt/PROJ/GDAL.
5. Thử import PyQGIS, ipykernel, pyzmq và chạy Processing `native:buffer` trên một đường dài 100 m.
6. Đăng ký kernel **Python (PyQGIS 4.2.3)** với interpreter và môi trường vừa tạo.

Script cập nhật kernel tên `pyqgis-423` đã có. Các notebook đang mở cần **Restart Kernel** và chọn lại kernel sau khi lệnh hoàn tất. Metadata kernel được Jupyter lưu trong thư mục kernel của tài khoản; trong file này, `argv` chỉ đến interpreter mới trong `work`. Cơ chế tên kernel và tên hiển thị được mô tả trong [hướng dẫn đăng ký kernel của IPython](https://ipython.readthedocs.io/en/stable/install/kernel_install.html).

Lệnh chỉ được xem là thành công khi kết thúc với mã thoát 0 và có các dòng:

```text
Import and GIS checks passed: ...
Registered kernel: ...
In VS Code select kernel: Python (PyQGIS 4.2.3)
```

Để xem tham số mà không cài đặt:

```bash
python3 scripts/setup/setup_pyqgis_kernel.py --help
```

`--qgis-app` chọn vị trí ứng dụng, còn `--packages-dir` dùng lại một thư mục thư viện notebook đã có. Script hiện được viết cho QGIS 4.2.3/Python 3.12 trên máy này; khi đổi phiên bản QGIS phải kiểm tra lại tên interpreter, đường dẫn và tên kernel trong script.

## 4. Chọn kernel và kiểm tra dự án

Trong notebook ở VS Code, bấm **Select Kernel** ở góc phải, rồi chọn **Python (PyQGIS 4.2.3)**. Nếu chưa thấy, dùng **Select Another Kernel → Jupyter Kernels**; có thể chạy **Developer: Reload Window** sau khi đăng ký. Đây là cách chọn kernel theo [hướng dẫn VS Code](https://code.visualstudio.com/docs/datascience/jupyter-kernel-management).

Chạy lại cell kiểm tra ở mục 2. Sau đó, từ Terminal đang ở `work`:

```bash
python3 scripts/lez/pipeline.py check
```

Lệnh đối chiếu runtime, cấu hình và cache dữ liệu hiện có; không gửi HTTP và không dựng lại mạng. Kết quả cần có phiên bản QGIS, số ô đã chọn và `raw_hashes_and_manifests_match: true`.

## 5. Notebook nào cần kernel nào?

| Công việc | Môi trường |
|---|---|
| Gọi Overpass bằng `requests`, đọc CSV/JSON | Python thường có các thư viện notebook cần dùng |
| Cell import trực tiếp `build_tiles`, `qgis.core` hoặc `processing` | Kernel PyQGIS |
| `03_boundaries.ipynb`, `04_build_motorcycle_network.ipynb` | Python thường hoặc PyQGIS; module tự gọi runtime PyQGIS đã đăng ký cho phần hình học |

Notebook 03/04 cần môi trường điều khiển có `pandas`. Chọn PyQGIS đã có trên máy nếu muốn dùng một kernel chung; Python thường có `pandas` cũng chạy được bộ điều khiển.

## 6. Các lỗi đã gặp trong dự án

| Lỗi | Kiểm tra và xử lý |
|---|---|
| `ModuleNotFoundError: No module named 'qgis'` | Cell import trực tiếp PyQGIS đang dùng sai kernel. Chọn PyQGIS, restart và chạy lại từ cell thiết lập. |
| `different Team IDs` khi import pyzmq | Lỗi từng gặp với interpreter QGIS gốc. Script dùng bản sao interpreter đã cấu hình và ký riêng để nạp thư viện notebook. Chọn kernel đã được script đăng ký. |
| Import được `qgis` nhưng thiếu `processing` | Kiểm tra `PYTHONPATH` trong kernel có thư mục plugin của QGIS; script đã khai báo đường dẫn này. |
| Gạch đỏ Pylance nhưng cell chạy được | Kiểm tra interpreter của trình soạn thảo và kernel notebook. Với module dự án, mở đúng workspace `work` và giữ `python.analysis.extraPaths` hiện có. |
| Đã đổi vị trí runtime nhưng kernel vẫn lỗi | Đăng ký lại từ vị trí mới, restart kernel rồi đọc lại `sys.executable` để biết interpreter thực sự đang chạy. |

Không đặt tên script là `qgis.py`, vì tên này che module QGIS khi import; lưu ý này cũng có trong [tài liệu PyQGIS](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/intro.html#python-applications).
