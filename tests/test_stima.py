"""Ricostruzione adattiva: superficie di riferimento, tagli dalla profondità, riempimenti impilati."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon, box

from stratigrafia3d import importa, ricostruisci, Scavo
from stratigrafia3d.superficie import Raster

tifffile = pytest.importorskip("tifffile")
CRS = "EPSG:27700"


def _dem(path, x0=1000.0, y0=2020.0, passo=2.0, righe=12, colonne=12, tfw=False):
    """Piano inclinato: quota = 50 + 0,1 * (x - 1000)."""
    xs = x0 + passo * (np.arange(colonne) + 0.5)
    z = np.tile(50 + 0.1 * (xs - 1000), (righe, 1)).astype("float32")
    z[0, 0] = -9999
    if tfw:
        tifffile.imwrite(path, z, extratags=[(42113, "s", 0, "-9999", False)])
        with open(path[:-4] + ".tfw", "w") as f:
            f.write(f"{passo}\n0\n0\n{-passo}\n{x0 + passo / 2}\n{y0 - passo / 2}\n")
    else:
        tifffile.imwrite(path, z, extratags=[
            (33550, "d", 3, (passo, passo, 0.0), False),
            (33922, "d", 6, (0.0, 0.0, 0.0, x0, y0, 0.0), False),
            (42113, "s", 0, "-9999", False)])
    return path


@pytest.mark.parametrize("tfw", [False, True])
def test_lettura_raster(tmp_path, tfw):
    r = Raster.leggi(_dem(str(tmp_path / "dem.tif"), tfw=tfw))
    assert r(1011.0, 2010.0) == pytest.approx(51.1, abs=1e-4)          # centro di cella
    assert r(1012.0, 2010.0) == pytest.approx(51.2, abs=1e-4)          # bilineare tra due celle
    assert r(1001.0, 2019.0) == pytest.approx(50.2, abs=0.2)           # cella vuota: il valore vicino
    d = r.descrizione()
    assert d["estensione"] == [1000.0, 1996.0, 1024.0, 2020.0] and d["passo"] == 2.0


def _scavo(d, quote=False, dem=None, fondi=False):
    """Un fossato 10 (profondità 0,8) con due riempimenti senza rapporti tra loro (11 primario,
    12 secondario, 0,5 m ciascuno: troppi per 0,8) e uno strato libero 20."""
    fosso = Polygon([(1002, 2004), (1014, 2004), (1014, 2006.4), (1002, 2006.4)])
    strato = box(1016, 2002, 1020, 2010)
    gpkg = str(d / "sito.gpkg")
    gpd.GeoDataFrame({"context": [10, 11, 12, 20]}, geometry=[fosso, fosso, fosso, strato], crs=CRS) \
        .to_file(gpkg, layer="contexts", driver="GPKG")
    if fondi:
        gpd.GeoDataFrame({"kind": ["Base of Slope"]}, geometry=[LineString([(1003, 2004.8), (1013, 2004.8)])],
                         crs=CRS).to_file(gpkg, layer="base_of_slope_lines", driver="GPKG")
    if quote:
        gpd.GeoDataFrame({"context": [20] * 4, "level_type": ["top"] * 4},
                         geometry=[Point(1016.5, 2003, 51.0), Point(1019.5, 2003, 51.0), Point(1016.5, 2009, 51.0),
                                   Point(1019.5, 2009, 51.0)], crs=CRS).to_file(gpkg, layer="levels", driver="GPKG")
    xlsx = str(d / "sito.xlsx")
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({"Context": [10, 11, 12, 20], "Type": ["negative", "positive", "positive", "positive"],
                      "Definition": ["Ditch", "Primary Fill", "Secondary Fill", "Cobbles"],
                      "Thickness (m)": [None, 0.5, 0.5, 0.15], "Depth (m)": [0.8, None, None, None]}) \
            .to_excel(w, sheet_name="Contexts", index=False)
        pd.DataFrame({"Context": [11, 12], "Relation": ["fills", "fills"], "Related context": [10, 10]}) \
            .to_excel(w, sheet_name="Relations", index=False)
    files = [gpkg, xlsx] + ([dem] if dem else [])
    return files


def test_senza_quote_e_senza_superficie_errore(tmp_path):
    abb = importa.proponi(_scavo(tmp_path))
    abb.superficie = {"tipo": "nessuna"}
    s = importa.applica(abb)
    err = [p for p in s.verifica() if p.livello == "errore"]
    assert err and err[0].codice == "senza-quote" and set(err[0].unita) == {10, 11, 12, 20}


def test_superficie_costante_proposta_senza_quote(tmp_path):
    abb = importa.proponi(_scavo(tmp_path))
    assert abb.superficie["tipo"] == "costante"
    abb.superficie = {"tipo": "costante", "quota": 52.0, "abbassa": 0.3}
    s = importa.applica(abb)
    assert not [p for p in s.verifica() if p.livello == "errore"]
    m = ricostruisci(s)
    st = {u: x.qualita["strategia"] for u, x in m.unita.items()}
    assert st == {10: "profondita", 11: "impilata", 12: "impilata", 20: "impilata"}
    taglio = m.unita[10]
    assert taglio.top.max() == pytest.approx(51.7, abs=0.02)            # orlo = 52 - 0,3
    assert taglio.top.min() == pytest.approx(51.7 - 0.8, abs=0.05)      # fondo = orlo - profondità
    # il secondario sta sopra il primario (ordine dedotto dal tipo), e i due stanno nel taglio
    sec, pri = m.unita[12], m.unita[11]
    assert sec.bot.min() > pri.bot.min() + 0.2
    assert pri.bot.min() == pytest.approx(taglio.top.min(), abs=0.05)
    assert m.unita[20].top.max() == pytest.approx(51.7, abs=0.02)
    assert m.unita[20].top.max() - m.unita[20].bot.min() == pytest.approx(0.15, abs=0.03)
    probl = {p.codice: p for p in s.verifica()}
    assert 10 in probl["stima-nota"].unita or any(10 in p.unita for p in s.verifica() if p.codice == "stima-nota")


def test_superficie_da_raster_e_salvataggio(tmp_path):
    dem = _dem(str(tmp_path / "dem.tif"))
    files = _scavo(tmp_path, dem=dem)
    abb = importa.proponi(files)
    assert abb.superficie["tipo"] == "raster" and abb.superficie["sorgente"] == dem
    s = importa.applica(abb)
    m = ricostruisci(s)
    orlo = m.unita[10]
    # la superficie è inclinata come il DEM: +0,1 m per metro verso est lungo il fossato
    V = orlo.V2
    est, ovest = V[:, 0] > V[:, 0].max() - 0.3, V[:, 0] < V[:, 0].min() + 0.3
    assert orlo.top[est].max() - orlo.top[ovest].max() == pytest.approx(1.2, abs=0.1)
    p = str(tmp_path / "prova.scavo")
    s.salva(p)
    r = Scavo.apri(p)
    assert r.raster_superficie is not None and r.parametri.superficie["tipo"] == "raster"
    assert r.raster_superficie(1011.0, 2010.0) == pytest.approx(51.1, abs=1e-4)
    m2 = ricostruisci(r)
    assert np.allclose(m2.unita[10].top, orlo.top, atol=1e-6)


def test_quote_misurate_hanno_la_precedenza(tmp_path):
    files = _scavo(tmp_path, quote=True)
    abb = importa.proponi(files)
    abb.superficie = {"tipo": "costante", "quota": 52.0}
    s = importa.applica(abb)
    m = ricostruisci(s)
    assert m.unita[20].qualita["strategia"] == "misurata"
    assert m.unita[20].top.max() == pytest.approx(51.0, abs=0.02)
    assert m.unita[10].qualita["strategia"] == "profondita"


def test_linee_di_fondo_danno_la_larghezza_delle_pareti(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    pareti = []
    for d, fondi in ((a, False), (b, True)):
        abb = importa.proponi(_scavo(d, fondi=fondi))
        if fondi:
            assert {x.layer: x.ruolo for x in abb.layers}["base_of_slope_lines"] == "fondi"
        abb.superficie = {"tipo": "costante", "quota": 52.0}
        pareti.append(ricostruisci(importa.applica(abb)).unita[10].qualita["parete_m"])
    assert pareti[0] == pytest.approx(0.48, abs=0.05)     # pendio tipico: 0,6 x profondità
    assert pareti[1] == pytest.approx(0.8, abs=0.08)      # linea di fondo a 0,8 m dal bordo


def test_demo_tutto_misurato(progetto):
    s = progetto[0]
    assert s.modello is not None
    assert {m.qualita.get("strategia") for m in s.modello.unita.values()} == {"misurata"}


def _buche(d):
    """Quattro buche di palo: tre con la profondità registrata (0,3, 0,4, 0,5), una senza."""
    polys = [box(1000 + 3 * i, 2000, 1001 + 3 * i, 2001) for i in range(4)] + [box(1020, 2000, 1024, 2004)]
    gpkg = str(d / "sito.gpkg")
    gpd.GeoDataFrame({"context": [1, 2, 3, 4, 9]}, geometry=polys, crs=CRS).to_file(gpkg, layer="contexts", driver="GPKG")
    xlsx = str(d / "sito.xlsx")
    pd.DataFrame({"Context": [1, 2, 3, 4, 9], "Type": ["negative"] * 4 + ["positive"],
                  "Definition": ["Posthole"] * 4 + ["Layer"], "Depth (m)": [0.3, 0.4, 0.5, None, None]}) \
        .to_excel(xlsx, sheet_name="Contexts", index=False)
    abb = importa.proponi([gpkg, xlsx])
    abb.superficie = {"tipo": "costante", "quota": 50.0}
    return importa.applica(abb)


def test_valori_tipici_dal_sito_ed_esclusione(tmp_path):
    s = _buche(tmp_path)
    codici = {p.codice: p for p in s.verifica()}
    assert codici["schematica-tagli"].unita == (4,) and "0,20 m" in codici["schematica-tagli"].messaggio
    assert codici["schematica-spessori"].unita == (9,)
    m = ricostruisci(s)
    assert m.unita[4].top.min() == pytest.approx(50 - 0.2, abs=0.02)
    s.parametri.tipici_dal_sito = True
    m = ricostruisci(s)
    assert m.unita[4].top.min() == pytest.approx(50 - 0.4, abs=0.02)    # mediana delle altre buche
    assert m.unita[4].qualita["strategia"] == "schematica"
    # esclusione: l'unità resta nelle schede ma non nel modello né negli avvisi
    s.parametri.escluse = [4, 9]
    codici = {p.codice: p for p in s.verifica()}
    assert "schematica-tagli" not in codici and codici["escluse"].unita == (4, 9)
    assert "scheda-senza-poligono" not in codici
    m = ricostruisci(s)
    assert set(m.unita) == {1, 2, 3}
    p = str(tmp_path / "e.scavo")
    s.salva(p)
    r = Scavo.apri(p)
    assert r.parametri.escluse == [4, 9] and r.parametri.tipici_dal_sito
