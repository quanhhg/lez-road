"""Set up a project-local macOS PyQGIS notebook interpreter and kernel.

The installed QGIS Python is hardened and rejects third-party native modules.
This script copies only its interpreter executable into the project, adds the
QGIS library path and signs that copy locally as a normal Python interpreter.
It does not change the installed QGIS application or system security settings.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path,
                        default=Path(__file__).resolve().parents[2],
                        help="Project folder; defaults to the work folder containing this script")
    parser.add_argument("--qgis-app", type=Path,
                        default=Path("/Applications/QGIS-final-4_2_3.app"))
    parser.add_argument("--packages-dir", type=Path,
                        help="Reuse notebook packages in an existing directory")
    parser.add_argument("--kernel-prefix", type=Path,
                        help="Optional alternative kernel install prefix")
    args = parser.parse_args()
    project = args.project_dir.expanduser().resolve()
    contents = args.qgis_app.expanduser().resolve() / "Contents"
    source = contents / "MacOS/python3.12"
    if not source.exists():
        raise SystemExit(f"QGIS Python not found: {source}")
    for tool in ("install_name_tool", "codesign"):
        if shutil.which(tool) is None:
            raise SystemExit(f"Required macOS tool missing: {tool}")
    runtime = project / ".pyqgis-runtime"
    binary_dir = runtime / "bin"
    binary_dir.mkdir(parents=True, exist_ok=True)
    executable = binary_dir / "python3.12"
    with tempfile.TemporaryDirectory(prefix="interpreter-", dir=binary_dir) as temp:
        prepared = Path(temp) / "python3.12"
        shutil.copy2(source, prepared)
        subprocess.run(["install_name_tool", "-add_rpath", str(contents / "Frameworks"),
                        str(prepared)], check=True)
        subprocess.run(["codesign", "--force", "--sign", "-", "--options=0",
                        str(prepared)], check=True)
        prepared.replace(executable)
    packages = (args.packages_dir.expanduser().resolve() if args.packages_dir
                else runtime / "packages")
    env = os.environ.copy()
    env.update({
        "PYTHONHOME": str(contents / "Frameworks"),
        "PYTHONPATH": str(packages) + os.pathsep + str(contents / "Resources/qgis/python/plugins"),
        "QT_QPA_PLATFORM": "offscreen",
        "QT_PLUGIN_PATH": str(contents / "PlugIns"),
        "QT_QPA_PLATFORM_PLUGIN_PATH": str(contents / "PlugIns/platforms"),
        "PROJ_DATA": str(contents / "Resources/qgis/proj"),
        "GDAL_DATA": str(contents / "Resources/qgis/gdal"),
        "QGIS_PREFIX_PATH": str(contents / "Resources/qgis"),
        "PYQGIS_APP_CONTENTS": str(contents),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    check = subprocess.run([str(executable), "-c", "import ipykernel, zmq, jupyter_client"],
                           env=env, capture_output=True, text=True)
    if check.returncode == 0:
        print(f"Reusing notebook dependencies in {packages}", flush=True)
    elif args.packages_dir:
        raise SystemExit("Existing notebook packages failed to import:\n" + check.stderr)
    else:
        # Use a fresh directory to avoid mixing partial installs on retries.
        packages = Path(tempfile.mkdtemp(prefix="packages-", dir=runtime))
        env["PYTHONPATH"] = str(packages) + os.pathsep + str(contents / "Resources/qgis/python/plugins")
        print(f"Installing notebook dependencies in {packages}", flush=True)
        subprocess.run([str(executable), "-m", "pip", "install", "--ignore-installed",
                        "--target", str(packages), "ipykernel"], env=env, check=True)
    smoke = """
import ipykernel, zmq
from qgis.core import QgsApplication, Qgis, QgsVectorLayer, QgsFeature, QgsGeometry
from qgis.analysis import QgsNativeAlgorithms
import os
QgsApplication.setPrefixPath(os.environ['QGIS_PREFIX_PATH'], True)
app = QgsApplication([], False)
app.initQgis()
registry = QgsApplication.processingRegistry()
if registry.providerById('native') is None:
    registry.addProvider(QgsNativeAlgorithms())
import processing
line = QgsVectorLayer('LineString?crs=EPSG:3405', 'test', 'memory')
f = QgsFeature()
f.setGeometry(QgsGeometry.fromWkt('LINESTRING (500000 2300000, 500100 2300000)'))
line.dataProvider().addFeatures([f])
buffer = processing.run('native:buffer', {
    'INPUT': line, 'DISTANCE': 10, 'SEGMENTS': 8, 'END_CAP_STYLE': 0,
    'JOIN_STYLE': 0, 'MITER_LIMIT': 2, 'DISSOLVE': False, 'OUTPUT': 'memory:'
})['OUTPUT']
assert buffer.isValid() and buffer.featureCount() == 1
print('Import and GIS checks passed:', Qgis.QGIS_VERSION, 'ipykernel', ipykernel.__version__)
del buffer, line, f
app.exitQgis()
"""
    subprocess.run([str(executable), "-c", smoke], env=env, check=True)
    kernel_env = {k: env[k] for k in (
        "PYTHONHOME", "PYTHONPATH", "QT_QPA_PLATFORM", "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH", "PROJ_DATA", "GDAL_DATA", "QGIS_PREFIX_PATH",
        "PYQGIS_APP_CONTENTS", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")}
    prefix = str(args.kernel_prefix.expanduser().resolve()) if args.kernel_prefix else None
    register = r"""
import json
from pathlib import Path
from ipykernel.kernelspec import install
folder = Path(install(user=PREFIX is None, prefix=PREFIX, kernel_name='pyqgis-423',
                      display_name='Python (PyQGIS 4.2.3)'))
spec_path = folder / 'kernel.json'
spec = json.loads(spec_path.read_text())
spec['argv'][0] = EXECUTABLE
spec['env'] = KERNEL_ENV
spec_path.write_text(json.dumps(spec, indent=2) + '\n')
print('Registered kernel:', spec_path)
"""
    register = ("EXECUTABLE = " + repr(str(executable)) + "\n"
                + "KERNEL_ENV = " + repr(kernel_env) + "\n"
                + "PREFIX = " + repr(prefix) + "\n" + register)
    subprocess.run([str(executable), "-c", register], env=env, check=True)
    print("In VS Code select kernel: Python (PyQGIS 4.2.3)")


if __name__ == "__main__":
    main()
