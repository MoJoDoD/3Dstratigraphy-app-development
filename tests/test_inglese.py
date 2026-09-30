"""Archivi in inglese (context register, relations 'fills'/'covers', Phases, Finds) e aree grandi."""
import base64
import copy

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon, box
from shapely import wkt

from stratigrafia3d import importa, ricostruisci, esporta
from stratigrafia3d.mesh import triangola


@pytest.fixture(scope="module")
def archivio(tmp_path_factory):
    """Un fossato (taglio 10) con due riempimenti (11 sopra 12) e uno strato (20), all'inglese."""
    d = tmp_path_factory.mktemp("en")
    fosso = Polygon([(0, 0), (6, 0), (6, 1.6), (0, 1.6)])
    strato = box(8, 0, 11, 3)
    crs = "EPSG:27700"
    gpkg = str(d / "site.gpkg")
    gpd.GeoDataFrame({"context": [10, 11, 12, 20]}, geometry=[fosso, fosso, fosso, strato], crs=crs) \
        .to_file(gpkg, layer="contexts", driver="GPKG")
    pts, info = [], []
    for x in np.linspace(0, 6, 13):
        for y in (0, 1.6):
            pts.append(Point(x, y, 50.0)); info.append((10, "rim"))
        pts.append(Point(x, 0.4, 49.6)); info.append((10, "cut"))
        pts.append(Point(x, 0.8, 49.2)); info.append((10, "cut"))
        pts.append(Point(x, 0.8, 50.0)); info.append((11, "top"))
        pts.append(Point(x, 0.8, 49.6)); info.append((12, "top"))
    for x in (8.5, 10.5):
        for y in (0.5, 2.5):
            pts.append(Point(x, y, 50.1)); info.append((20, "top"))
    gpd.GeoDataFrame({"context": [a for a, _ in info], "level_type": [b for _, b in info]}, geometry=pts, crs=crs) \
        .to_file(gpkg, layer="levels", driver="GPKG")
    gpd.GeoDataFrame({"name": ["trench"]}, geometry=[box(-1, -1, 12, 4)], crs=crs) \
        .to_file(gpkg, layer="excavation_area", driver="GPKG")
    gpd.GeoDataFrame({"kind": ["Base of Slope"]}, geometry=[LineString(box(1, 0.5, 5, 1.1).exterior.coords)], crs=crs) \
        .to_file(gpkg, layer="hachures_base_of_slope", driver="GPKG")
    xlsx = str(d / "site.xlsx")
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({"Context": [10, 11, 12, 20], "Type": ["negative", "positive", "positive", "positive"],
                      "Category": ["Cut", "Fill", "Fill", "Layer"],
                      "Definition": ["Ditch", "Secondary Fill", "Primary Fill", "Cobbled Surface"],
                      "Description": ["Linear cut", "Brown silt", "Grey clay", "Flint cobbles"],
                      "Phase": [1, 1, 1, 2], "Thickness (m)": [None, 0.4, 0.4, 0.15],
                      "Depth (m)": [0.8, None, None, None], "Base": ["Flat", None, None, None],
                      "Colour HEX": [None, "#8a7a63", "#6f6150", "#9ea3a3"]}).to_excel(w, sheet_name="Contexts", index=False)
        pd.DataFrame({"Context": [11, 12, 11], "Relation": ["fills", "fills", "covers"],
                      "Related context": [10, 10, 12]}).to_excel(w, sheet_name="Relations", index=False)
        pd.DataFrame({"Phase": [1, 2], "Title": ["Medieval", "Post-medieval"], "Period": ["", ""],
                      "From (year)": [1200, 1500], "To (year)": [1499, 1799]}).to_excel(w, sheet_name="Phases", index=False)
        pd.DataFrame({"Context": [11, 11], "Material": ["Pottery", "Animal Bone"], "Object": ["Sherd", "Bone"],
                      "Count": [4, 9], "Weight (g)": [40, 55]}).to_excel(w, sheet_name="Finds", index=False)
        pd.DataFrame({"ID": ["Photo 1"], "Context": [10], "Subject": ["Section of ditch"]}) \
            .to_excel(w, sheet_name="Documentation", index=False)
    return [gpkg, xlsx]


def test_proposta_in_inglese(archivio):
    abb = importa.proponi(archivio)
    ruoli = {r.layer: r.ruolo for r in abb.layers}
    assert ruoli == {"contexts": "us", "levels": "quote", "excavation_area": "area", "hachures_base_of_slope": "fondi"}
    lv = next(r for r in abb.layers if r.layer == "levels")
    assert lv.campo_unita == "context" and lv.campo_tipo == "level_type"
    c = abb.colonne_us
    assert c["Tipo"] == "Type" and c["Spessore medio stimato (m)"] == "Thickness (m)" and c["Fase"] == "Phase"
    assert c["Descrizione"] == "Description" and c["Colore HEX"] == "Colour HEX"
    assert "Quota base usata (rilevata o stimata)" not in c          # "Base" qui è la forma del fondo
    assert abb.rapporti["modo"] == "foglio" and abb.rapporti["foglio"] == "Relations"


def test_import_e_ricostruzione_in_inglese(archivio):
    s = importa.applica(importa.proponi(archivio))
    assert {"Fasi", "Materiali", "Documentazione"} <= set(s.tabelle)
    assert list(s.tabelle["Fasi"].columns[:3]) == ["Fase", "Titolo", "Periodo"]
    assert set(s.tabelle["Materiali"].columns) >= {"US", "Classe", "Tipo / forma", "NR", "Peso (g)"}
    rap = set(map(tuple, s.tabelle["Rapporti"].values.tolist()))
    assert (11, "riempie", 10) in rap and (11, "copre", 12) in rap
    assert s.schede_us()[10]["Tipo"] == "negativa"
    assert not [p for p in s.verifica() if p.livello == "errore"]
    m = ricostruisci(s)
    assert set(m.unita) == {10, 11, 12, 20} and m.unita[10].tipo == "taglio"
    # il riempimento inferiore poggia sul taglio, quello superiore sul riempimento inferiore
    assert m.unita[12].bot.min() == pytest.approx(m.unita[10].top.min(), abs=0.05)
    assert m.unita[11].bot.min() >= m.unita[12].bot.min() - 1e-6
    d = esporta.dati_visualizzatore(s)
    assert d["fasi"][0]["Titolo"] == "Medieval" and d["materiali"][0]["US"] == 11


def test_area_grande_quantizzazione(progetto):
    """Oltre 65 m di estensione le coordinate non traboccano: il passo di quantizzazione cresce."""
    s = copy.deepcopy(progetto[0])
    for m in s.modello.unita.values():
        m.V2 = m.V2 * 8.0
    d = esporta.dati_visualizzatore(s)
    assert d["quant"] > 0.001
    massimo = max(float(m.V2.max()) for m in s.modello.unita.values())
    dec = max(np.frombuffer(base64.b64decode(x["pos"]), "<u2").reshape(-1, 3)[:, :2].max() for x in d["meshes"])
    assert dec * d["quant"] == pytest.approx(massimo, abs=d["quant"])
    assert d["estensione"][2] == pytest.approx(massimo, abs=0.01)


def test_poligono_con_vertici_quasi_doppi():
    """Anello che si chiude con un vertice a 6 mm dal primo e parti che si toccano (dato reale):
    la triangolazione deve terminare in fretta, senza esplodere."""
    g = wkt.loads(
        "MULTIPOLYGON (((51.1739 97.2227, 51.2422 97.2446, 51.4660 97.3034, 51.5794 97.3601, 51.8216 97.4382, "
        "52.0638 97.5320, 52.3060 97.5944, 52.3647 97.3986, 51.8529 97.1883, 51.53252994699869 97.0633443260449, "
        "51.53252994688228 97.06334432598669, 51.2881 96.9897, 51.2143 97.0172, 51.1960 97.0653, 51.1845 97.1455, "
        "51.1739 97.2227)), ((52.37049 97.40103, 52.3060 97.5944, 52.4677 97.6510, 52.6718 97.7031, 53.1911 97.8359, "
        "53.7035 97.9668, 54.3540 98.1331, 54.9936 98.2966, 55.5420 98.4368, 55.5661 98.3339, 55.5687 98.1523, "
        "55.1185 98.0142, 54.7759 97.9236, 54.4957 97.8540, 54.1016 97.7652, 53.6872 97.7056, 53.3747 97.6734, "
        "53.1862 97.6244, 52.8832 97.5450, 52.5609 97.4596, 52.4262 97.4239, 52.36466 97.39863, 52.37049 97.40103)))")
    for metodo in ("triangle", "scipy"):
        if metodo == "triangle":
            pytest.importorskip("triangle")
        V, F = triangola(g, passo=0.06, area_max=0.006, metodo=metodo)
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        area = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])).sum() / 2
        assert len(F) < 5000 and abs(area - g.area) / g.area < 0.03
