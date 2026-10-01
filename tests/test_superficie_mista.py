"""Superficie di riferimento mista: modello del terreno + raster di correzione + quote rilevate
(dove la correzione non arriva, e con "quote": true per adattarsi ai punti)."""
import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, box

from stratigrafia3d import schema as sc
from stratigrafia3d.progetto import Scavo
from stratigrafia3d.superficie import Raster, combina, normalizza, punti_rilevati

tifffile = pytest.importorskip("tifffile")


def _tif(tmp_path, nome, z, passo, x0=0.0, y0=100.0):
    p = str(tmp_path / nome)
    tifffile.imwrite(p, np.asarray(z, "float32"), extratags=[
        (33550, "d", 3, (passo, passo, 0.0), False), (33922, "d", 6, (0.0, 0.0, 0.0, x0, y0, 0.0), False)])
    return p


def _griglia(passo, x0, x1, y0, y1):
    xs = np.arange(x0 + passo / 2, x1, passo)
    ys = np.arange(y0 + passo / 2, y1, passo)
    X, Y = np.meshgrid(xs, ys)
    return np.c_[X.ravel(), Y.ravel()]


@pytest.fixture
def rasters(tmp_path):
    """Terreno piano a 50 m (100 x 100 m, passo 5); troncamento -0,6 m solo sulla metà ovest (x < 50)."""
    terreno = _tif(tmp_path, "terreno.tif", np.full((20, 20), 50.0), 5.0)
    tr = np.full((200, 200), -0.6)
    tr[:, 100:] = np.nan                                     # «blanked»: oltre x = 50 niente modello
    tronc = _tif(tmp_path, "troncamento.tif", tr, 0.5)
    return terreno, tronc


def _scavo(punti=None, tipi=None):
    s = Scavo()
    s.layers[sc.L_AREA] = gpd.GeoDataFrame(geometry=[box(5, 5, 95, 95)], crs="EPSG:27700")
    if punti is not None:
        s.layers[sc.L_QUOTE] = gpd.GeoDataFrame(
            {sc.F_US: [None] * len(punti), sc.F_TIPO_QUOTA: tipi or ["sup"] * len(punti)},
            geometry=[Point(*p) for p in punti], crs="EPSG:27700")
    return s


def _punti_est(z, passo=4.0, fondi=0):
    """Quote rilevate sulla metà est (x 55-95), con qualche fondo di buca 0,8 m più in basso."""
    P = _griglia(passo, 55, 95, 5, 95)
    Z = np.full(len(P), z)
    rng = np.random.default_rng(1)
    i = rng.choice(len(P), fondi, replace=False) if fondi else []
    Z[i] -= 0.8
    return np.c_[P, Z]


def test_senza_quote_resta_il_bordo(rasters):
    terreno, tronc = rasters
    s = _scavo()
    s.imposta_superficie({"tipo": "raster", "sorgente": terreno, "correzione": tronc})
    r = s.raster_superficie
    assert r(np.array([20.0, 80.0]), np.array([50.0, 50.0])) == pytest.approx([49.4, 49.4], abs=1e-3)
    assert "punti_correzione" not in s.parametri.superficie
    assert "quote rilevate" not in r.nome


def test_fuori_copertura_correzione_dalle_quote(rasters):
    terreno, tronc = rasters
    s = _scavo(_punti_est(49.75, fondi=40))         # a est il piano di scavo è 25 cm sotto il terreno
    s.imposta_superficie({"tipo": "raster", "sorgente": terreno, "correzione": tronc})
    r, spec = s.raster_superficie, s.parametri.superficie
    assert spec["punti_correzione"] > 0 and r.nome.endswith("+ quote rilevate")
    # dentro la copertura il troncamento non cambia
    assert r(np.array([10.0, 30.0, 45.0]), np.array([50.0, 20.0, 80.0])) == pytest.approx([49.4] * 3, abs=1e-3)
    # lontano dal bordo: le quote, senza farsi tirare giù dai fondi delle buche
    assert r(np.array([70.0, 85.0]), np.array([50.0, 30.0])) == pytest.approx([49.75, 49.75], abs=0.02)
    # raccordo continuo al bordo del raster: nessun gradino tra x = 50 e x = 60
    xs = np.arange(48.0, 62.0, 0.25)
    z = r(xs, np.full(len(xs), 50.0))
    assert np.abs(np.diff(z)).max() < 0.05
    assert z[0] == pytest.approx(49.4, abs=0.01) and z[-1] == pytest.approx(49.75, abs=0.03)


def test_quote_lontane_lasciano_il_bordo(rasters, tmp_path):
    terreno, tronc = rasters
    base, corr = Raster.leggi(terreno), Raster.leggi(tronc)
    lontani = np.array([[400.0, 400.0, 49.0], [404.0, 400.0, 49.0], [400.0, 404.0, 49.0], [404.0, 404.0, 49.0]])
    r = combina(base, corr, 5, 5, 95, 95, punti=lontani)
    assert r.punti_correzione == 0
    assert r(np.array([80.0]), np.array([50.0])) == pytest.approx([49.4], abs=1e-3)


def test_tipi_di_quota_usati():
    pts = [(10, 10, 50.0), (20, 20, 50.1), (30, 30, 49.0), (40, 40, 50.2)]
    s = _scavo(pts, ["sup", "orlo", "taglio", "rasatura"])
    P = punti_rilevati(s)
    assert len(P) == 3 and 49.0 not in P[:, 2]
    assert len(punti_rilevati(_scavo())) == 0


def test_adatta_alle_quote(rasters):
    terreno, _ = rasters
    # a ovest le quote sono 30 cm sotto il terreno, a est 2 m sopra (oltre il limite di 1 m); al centro nessuna
    ovest = _griglia(2.0, 5, 30, 5, 95)
    est = _griglia(2.0, 75, 95, 5, 95)
    pts = np.r_[np.c_[ovest, np.full(len(ovest), 49.7)], np.c_[est, np.full(len(est), 52.0)]]
    s = _scavo(pts)
    spec = normalizza({"tipo": "raster", "sorgente": terreno, "quote": 1})
    assert spec["quote"] is True
    s.imposta_superficie(spec)
    r = s.raster_superficie
    assert s.parametri.superficie["punti_adattamento"] > 0
    assert r(np.array([15.0]), np.array([50.0])) == pytest.approx([49.7], abs=0.02)
    assert r(np.array([85.0]), np.array([50.0])) == pytest.approx([51.0], abs=0.02)      # limitato a +1 m
    assert r(np.array([52.0]), np.array([50.0])) == pytest.approx([50.0], abs=1e-3)      # lontano: terreno


def test_quote_true_senza_quote_come_prima(rasters):
    terreno, _ = rasters
    s = _scavo()
    s.imposta_superficie({"tipo": "raster", "sorgente": terreno, "quote": True})
    assert s.raster_superficie.sx == 5.0                     # solo ritagliato, non ricampionato
    assert "punti_adattamento" not in s.parametri.superficie


def test_layer_quote_superficie(rasters):
    """Punti quotati senza US tenuti a parte (layer «quote_superficie»): usati solo per la superficie."""
    from stratigrafia3d.superficie import L_QUOTE_SUPERFICIE
    terreno, tronc = rasters
    s = _scavo()
    P = _punti_est(49.75)
    s.layers[L_QUOTE_SUPERFICIE] = gpd.GeoDataFrame(geometry=[Point(*p) for p in P], crs="EPSG:27700")
    assert len(punti_rilevati(s)) == len(P)
    s.imposta_superficie({"tipo": "raster", "sorgente": terreno, "correzione": tronc})
    assert s.raster_superficie(np.array([80.0]), np.array([50.0])) == pytest.approx([49.75], abs=0.02)
