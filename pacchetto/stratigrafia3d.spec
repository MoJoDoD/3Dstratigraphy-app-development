# -*- mode: python -*-
# Eseguibile Windows: pyinstaller pacchetto/stratigrafia3d.spec --noconfirm
# Il pacchetto «triangle» (licenza non commerciale) resta fuori: il programma usa scipy al suo posto.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ("pyogrio", "pyproj", "shapely", "webview", "tifffile", "stratigrafia3d"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h
hidden += ["openpyxl", "PIL.Image", "skimage.measure", "matplotlib.backends.backend_agg"]

a = Analysis(["avvio_app.py"], pathex=[], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["triangle", "tkinter", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Stratigrafia3D", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Stratigrafia3D")
