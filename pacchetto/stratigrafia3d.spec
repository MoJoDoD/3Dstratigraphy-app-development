# -*- mode: python -*-
# Eseguibile Windows: pyinstaller pacchetto/stratigrafia3d.spec --noconfirm
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hidden = [], [], []
for pkg in ("pyogrio", "pyproj", "shapely", "triangle", "webview", "stratigrafia3d"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h
hidden += ["openpyxl", "skimage.measure", "matplotlib.backends.backend_agg"]

a = Analysis(["avvio_app.py"], pathex=[], binaries=binaries, datas=datas, hiddenimports=hidden)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Stratigrafia3D", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Stratigrafia3D")
