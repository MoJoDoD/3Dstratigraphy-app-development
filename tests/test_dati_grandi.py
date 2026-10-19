# -*- coding: utf-8 -*-
"""Archivi grandi: modelli OBJ da centinaia di MB, DEM e ortofoto al millimetro, impronte dei file d'origine.
Si controlla che la lettura rapida dia gli stessi risultati di quella riga per riga e che i raster si leggano
ridotti senza passare per l'immagine intera."""
import os

import numpy as np
import pytest

from stratigrafia3d import modelli3d as M
from stratigrafia3d import cache

tifffile = pytest.importorskip("tifffile")


def _obj(path, testo):
    with open(path, "w") as f:
        f.write(testo)
    return str(path)


QUADRATI = """mtllib m.mtl
v 0 0 0
v 1 0 0
v 1 1 0.5
v 0 1 0
v 2 0 0
v 2 1 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
f 1/1 2/2 3/3 4/4
f -4/-4 5/2 6/3 3/3
"""


@pytest.mark.parametrize("testo", [
    QUADRATI,
    "v 0 0 0\nv 1 0 0\nv 0 1 0\nvn 0 0 1\nf 1//1 2//1 3//1\n",
    "v 0 0 0 1 0 0\nv 1 0 0 0 1 0\nv 0 1 0 0 0 1\nf 1 2 3\n",
    "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 1 0\nf 1 2 3\nf 2 4 3 1\n",      # numero di angoli diverso: riga per riga
])
def test_obj_rapido_uguale_al_lento(tmp_path, testo):
    from PIL import Image
    Image.new("RGB", (64, 64), (100, 80, 60)).save(tmp_path / "t.jpg")
    (tmp_path / "m.mtl").write_text("newmtl a\nmap_Kd t.jpg\n")
    p = _obj(tmp_path / "a.obj", testo)
    a, b = M._leggi_obj(p), M._leggi_obj_righe(p)
    assert len(a.F) == len(b.F)
    # stessi triangoli nello spazio (l'ordine dei vertici può cambiare)
    ta = np.sort(np.round(a.V[a.F].reshape(len(a.F), -1), 6), axis=0)
    tb = np.sort(np.round(b.V[b.F].reshape(len(b.F), -1), 6), axis=0)
    assert np.allclose(ta, tb)
    assert (a.uv is None) == (b.uv is None) and (a.colori is None) == (b.colori is None)


def test_obj_grande_rapido_e_in_cache(tmp_path):
    import time
    n = 300
    xs = np.linspace(0, 10, n)
    X, Y = np.meshgrid(xs, xs)
    with open(tmp_path / "g.obj", "w") as f:
        np.savetxt(f, np.c_[X.ravel(), Y.ravel(), np.sin(X).ravel()], fmt="v %.4f %.4f %.4f")
        i = np.arange(n * n).reshape(n, n)[:-1, :-1].ravel() + 1
        np.savetxt(f, np.vstack([np.c_[i, i + 1, i + n], np.c_[i + 1, i + n + 1, i + n]]), fmt="f %d %d %d")
    p = str(tmp_path / "g.obj")
    t = time.time()
    m = M.Modello3D.leggi(p, triangoli_max=20_000)
    primo = time.time() - t
    assert 0 < len(m.F) <= 20_000
    assert cache.leggi(cache.percorso("modelli3d", p, (0.0, 0.0, 0.0), 20_000, M.LATO_TEXTURE)) is not None
    t = time.time()
    m2 = M.Modello3D.leggi(p, triangoli_max=20_000)
    assert len(m2.F) == len(m.F) and time.time() - t < primo


def _tif(path, a, passo, x0, y1, piramide=False, **kw):
    extratags = [(33550, "d", 3, (passo, passo, 0.0), False), (33922, "d", 6, (0, 0, 0, x0, y1, 0), False)]
    with tifffile.TiffWriter(path) as t:
        t.write(a, tile=(64, 64), subifds=1 if piramide else 0, extratags=extratags, **kw)
        if piramide:
            t.write(a[::4, ::4], tile=(64, 64), subfiletype=1, **{k: v for k, v in kw.items() if k != "photometric"},
                    **({"photometric": kw["photometric"]} if "photometric" in kw else {}))
    return str(path)


@pytest.mark.parametrize("piramide", [False, True])
def test_dem_ridotto(tmp_path, piramide):
    from stratigrafia3d.superficie import leggi_griglia_ridotta, Raster
    z = (100 + np.add.outer(np.arange(800), np.arange(800)) * 0.001).astype("float32")
    p = _tif(tmp_path / "dem.tif", z, 0.005, 1000.0, 2004.0, piramide)
    r = leggi_griglia_ridotta(p, 0.02)
    assert abs(r.sx - 0.02) < 1e-9 and r.z.shape == (200, 200)
    pieno = Raster.leggi(p)
    for x, y in ((1001.0, 2003.0), (1002.5, 2001.2)):
        assert abs(float(r(x, y)) - float(pieno(x, y))) < 0.01


def test_ortofoto_grande_ridotta_in_lettura(tmp_path):
    from stratigrafia3d.ortofoto import Ortofoto
    yy, xx = np.mgrid[0:3000, 0:3000]
    img = np.stack([(xx % 256), (yy % 256), ((xx + yy) % 256)], -1).astype("uint8")
    p = _tif(tmp_path / "o.tif", img, 0.002, 500.0, 806.0, photometric="rgb", compression="zlib")
    o = Ortofoto.leggi(p, lato_max=512)
    assert max(o.larghezza, o.altezza) <= 516
    assert o.estensione[0] == pytest.approx(500.0, abs=0.05) and o.estensione[3] == pytest.approx(806.0, abs=0.05)
    o2 = Ortofoto.leggi(p, limiti=(501.0, 801.0, 502.0, 802.0), margine=0.0, lato_max=4096)
    assert o2.estensione[2] - o2.estensione[0] < 1.2


def test_impronta_rapida(tmp_path, monkeypatch):
    from stratigrafia3d import progetto as P
    monkeypatch.setattr(P, "GRANDE_IMPRONTA", 1000)
    p = tmp_path / "grande.bin"
    p.write_bytes(os.urandom(20_000))
    imp = P._sha256(str(p))
    assert imp.startswith("rapida:") and P.impronta_uguale(str(p), imp)
    b = bytearray(p.read_bytes())
    b[-1] ^= 1
    p.write_bytes(bytes(b))
    assert not P.impronta_uguale(str(p), imp)
    piccolo = tmp_path / "piccolo.bin"
    piccolo.write_bytes(b"abc")
    assert not P._sha256(str(piccolo)).startswith("rapida:")


def test_linee_curve_non_sono_sezioni():
    import geopandas as gpd
    from shapely.geometry import LineString
    from stratigrafia3d.importa import _rettilinee
    rette = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (5, 0)]), LineString([(0, 1), (2, 3)])])
    curve = gpd.GeoDataFrame(geometry=[LineString([(np.cos(t), np.sin(t)) for t in np.linspace(0, 3, 30)])])
    assert _rettilinee(rette) and not _rettilinee(curve)
