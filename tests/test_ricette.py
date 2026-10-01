"""Ricette di importazione: tabelle CSV collegate, colonne «padre», vocabolari, filtri, poligoni ereditati,
rapporti scritti come testo, database SpatiaLite, CSV con geometrie, archivi zip, valori nulli."""
import json
import os
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import Point, Polygon, box

from stratigrafia3d import importa, ricostruisci, Scavo
from stratigrafia3d.importa import _rapporti_da_testo

CRS = "EPSG:27700"


# --------------------------------------------------------------------------- archivio in stile Framework
@pytest.fixture(scope="module")
def framework(tmp_path_factory):
    """Due siti; nel sito A un fossato 10 con due riempimenti senza pianta (11 primario, 12 secondario),
    una buca 20 senza profondità in scheda (ma con DEPTH nel layer) e un riempimento 21; nel sito B un'altra buca."""
    d = tmp_path_factory.mktemp("fw")
    g = gpd.GeoDataFrame({
        "CONTEXT_ID": [10, 20, 30, 0], "SITECODE": ["A", "A", "B", "A"], "DEPTH": [0.9, 0.35, 0.4, 0.0]},
        geometry=[box(0, 0, 12, 2), box(14, 0, 15.2, 1.2), box(40, 40, 41, 41), box(-5, -5, -4, -4)], crs=CRS)
    g.to_file(str(d / "Stansted.shp"))
    righe = [
        (10, "Cut", 10, "Ditch", None, "Recut ditch"), (11, "Deposit", 10, "Primary Fill", 0.4, "Grey clay"),
        (12, "Deposit", 10, "Secondary Fill", 0.3, "Brown silt"), (20, "Cut", 20, "Pit", None, "Small pit"),
        (21, "Deposit", 20, "Secondary Fill", 0.2, "Dark fill"), (30, "Cut", 30, "Pit", 0.4, "Other site"),
        (31, "Deposit", 30, "Secondary Fill", 0.3, "Fill"), (99, "Deposit", 98, "Other Fill", 0.2, "Not planned"),
    ]
    cd = pd.DataFrame(righe, columns=["Context Number", "Context Type", "Fill of", "Interpretation",
                                      "Context Depth (m)", "Brief Description"])
    cd["Brief Description"] = cd["Brief Description"] + " – café"            # accento: file in Windows-1252
    cd.to_csv(d / "ContextData.csv", index=False, encoding="cp1252")
    pd.DataFrame({"Deposit": [11, 11, 21, 31], "Material": ["Pottery", "Flint", "Pottery", "Bone"],
                  "Object": ["Sherd", "Flake", "Sherd", "Bone"], "ObjectCount": [3, 1, 2, 5],
                  "Weight": [30, 2, 999999, 12]}).to_csv(d / "FindsSummaries.csv", index=False)
    pd.DataFrame({"x": [1]}).to_csv(d / "tblFFV_Version.csv", index=False)
    return [str(d / "Stansted.shp"), str(d / "ContextData.csv"), str(d / "FindsSummaries.csv"),
            str(d / "tblFFV_Version.csv")]


def test_proposta_automatica_su_archivio_relazionale(framework):
    abb = importa.proponi(framework)
    assert abb.foglio_us == "ContextData" and abb.colonne_us["US"] == "Context Number"
    assert len(abb.tabelle_extra) == 2
    assert abb.rapporti == {"modo": "colonne", "foglio": "ContextData", "colonne": {"Fill of": "riempie"}}
    assert abb.vocabolari["tipo"] == {"Cut": "negativa", "Deposit": "positiva"}
    assert abb.fogli_collegati["Materiali"]["foglio"] == "FindsSummaries"
    assert abb.poligoni_ereditati


def test_ricetta_framework(framework):
    abb, note = importa.applica_ricetta(importa.proponi(framework), importa.carica_ricetta_pronta("framework_archaeology"))
    assert abb.crs == "EPSG:27700" and abb.poligoni_ereditati and abb.solo_con_poligono
    abb.filtri.append({"dove": "layer", "layer": "Stansted", "colonna": "SITECODE", "valori": ["A"]})
    abb.superficie = {"tipo": "costante", "quota": 50.0, "abbassa": 0.3}
    s = importa.applica(abb)
    schede = s.schede_us()
    assert set(schede) == {10, 11, 12, 20, 21}                     # sito B, 0 e 99 esclusi
    assert "caf" in str(schede[11]["Descrizione"])
    assert schede[20]["Spessore/profondità max (m)"] == pytest.approx(0.35)   # dal campo DEPTH del layer
    poli = s.poligoni_us()
    assert poli[11].equals(poli[10]) and poli[21].equals(poli[20])  # riempimenti con il poligono del taglio
    rap = set(map(tuple, s.tabelle["Rapporti"].values.tolist()))
    assert (11, "riempie", 10) in rap and (21, "riempie", 20) in rap
    assert not any(a == b for a, _, b in rap)                       # "Fill of" di un taglio = se stesso: ignorato
    mat = s.tabelle["Materiali"]
    assert set(mat["US"]) == {11, 21} and np.isnan(mat.loc[mat.US == 21, "Peso (g)"].iloc[0])
    assert not [p for p in s.verifica() if p.livello == "errore"]
    m = ricostruisci(s)
    assert m.unita[10].top.min() == pytest.approx(49.7 - 0.9, abs=0.05)
    assert m.unita[20].top.min() == pytest.approx(49.7 - 0.35, abs=0.05)
    assert m.unita[12].bot.min() > m.unita[11].bot.min() + 0.2      # secondario sopra il primario
    # la ricetta salvata e riletta produce lo stesso abbinamento
    abb2 = importa.Abbinamento.da_json(abb.a_json())
    assert abb2.filtri == abb.filtri and abb2.vocabolari == abb.vocabolari


def test_vocabolario_e_filtro_sulla_scheda(framework):
    abb = importa.proponi(framework)
    abb.vocabolari["tipo"]["Cut"] = "positiva"                      # l'utente decide diversamente
    abb.filtri = [{"dove": "scheda", "colonna": "Interpretation", "valori": ["Ditch", "Primary Fill"]}]
    abb.solo_con_poligono = False
    abb.superficie = {"tipo": "costante", "quota": 50.0}
    s = importa.applica(abb)
    assert set(s.schede_us()) == {10, 11}
    assert s.schede_us()[10]["Tipo"] == "positiva"


# --------------------------------------------------------------------------- rapporti scritti come testo
def test_rapporti_da_testo():
    assert _rapporti_da_testo("copre 1002, 1003; taglia 1005") == [("copre", 1002), ("copre", 1003), ("taglia", 1005)]
    assert _rapporti_da_testo("Coperto da 12 e 13, si appoggia a 40") == \
        [("coperto da", 12), ("coperto da", 13), ("si appoggia a", 40)]
    assert _rapporti_da_testo("fills 204; cut by 210") == [("riempie", 204), ("tagliato da", 210)]
    assert _rapporti_da_testo("[['Copre', '2', '1', 'Sito'], ['Taglia', '5', '1', 'Sito']]") == \
        [("copre", 2), ("taglia", 5)]
    assert _rapporti_da_testo(None) == [] and _rapporti_da_testo("") == []


def test_database_spatialite_pyarchinit(tmp_path):
    db = str(tmp_path / "pyarchinit_db.sqlite")
    us = gpd.GeoDataFrame({"scavo_s": ["Sito"] * 3, "area_s": ["1"] * 3, "us_s": [1, 2, 3]},
                          geometry=[box(0, 0, 4, 4), box(0.5, 0.5, 2, 2), box(0, 0, 4, 4)], crs="EPSG:3004")
    pyogrio.write_dataframe(us, db, layer="pyunitastratigrafiche", driver="SQLite", dataset_options={"SPATIALITE": "YES"})
    q = gpd.GeoDataFrame({"us_q": [1, 1, 1, 3, 3, 3], "quota_q": [10.0, 10.1, 10.05, 9.6, 9.55, 9.6]},
                         geometry=[Point(1, 1), Point(3, 1), Point(2, 3), Point(1, 1), Point(3, 1), Point(2, 3)],
                         crs="EPSG:3004")
    pyogrio.write_dataframe(q, db, layer="pyarchinit_quote", driver="SQLite", append=True)
    tab = pd.DataFrame({"sito": ["Sito"] * 3, "area": ["1"] * 3, "us": [1, 2, 3],
                        "d_stratigrafica": ["Strato", "Taglio", "Strato"], "d_interpretativa": ["Crollo", "Buca", "Piano"],
                        "descrizione": ["a", "b", "c"], "periodo_iniziale": ["1", "2", "2"], "fase_iniziale": ["1", "1", "2"],
                        "interpretazione": ["x", "y", "z"],        # come «Interpretazione», con la minuscola
                        "rapporti": ["[['Copre', '3', '1', 'Sito'], ['Copre', '2', '1', 'Sito']]",
                                     "[['Coperto da', '1', '1', 'Sito'], ['Taglia', '3', '1', 'Sito']]",
                                     "[['Coperto da', '1', '1', 'Sito'], ['Tagliato da', '2', '1', 'Sito']]"],
                        "profondita_max": [None, 0.4, None]})
    pyogrio.write_dataframe(tab, db, layer="us_table", driver="SQLite", append=True)
    # periodizzazione: periodo 1 il più recente, come in pyArchInit
    per = pd.DataFrame({"sito": ["Sito"] * 3, "periodo": [1, 2, 2], "fase": [1, 1, 2], "cron_iniziale": [1800, 1500, 1200],
                        "cron_finale": [2000, 1799, 1499], "datazione_estesa": ["Contemporanea", "Moderna", "Medievale"]})
    pyogrio.write_dataframe(per, db, layer="periodizzazione_table", driver="SQLite", append=True)
    usm = gpd.GeoDataFrame({"scavo_s": ["Sito"], "area_s": ["1"], "us_s": [3]}, geometry=[box(0, 0, 4, 4)], crs="EPSG:3004")
    pyogrio.write_dataframe(usm, db, layer="pyunitastratigrafiche_usm", driver="SQLite", append=True)
    import sqlite3
    con = sqlite3.connect(db)                         # una colonna binaria (come le miniature dei media)
    con.execute("CREATE TABLE media_thumb_table (id INTEGER, img BLOB)")
    con.execute("INSERT INTO media_thumb_table VALUES (1, ?)", (bytes([0xbc, 0xff, 0x00, 0x81]),))
    con.commit(); con.close()
    abb = importa.proponi([db])
    assert abb.tabella == db and abb.foglio_us == "us_table"
    abb, _ = importa.applica_ricetta(abb, importa.carica_ricetta_pronta("pyarchinit"))
    ruoli = {l.layer: l.ruolo for l in abb.layers}
    assert ruoli["pyunitastratigrafiche"] == "us" and ruoli["pyarchinit_quote"] == "quote"
    s = importa.applica(abb)
    rap = set(map(tuple, s.tabelle["Rapporti"].values.tolist()))
    assert {(1, "copre", 3), (1, "copre", 2), (2, "taglia", 3)} <= rap
    assert s.schede_us()[2]["Tipo"] == "negativa"                  # «Taglio» nella definizione
    assert len(s.layers["quote"]) == 6
    assert not [p for p in s.verifica() if p.livello == "errore"]
    # fasi composte (periodo + fase) numerate dalla più antica, con titoli e date
    fasi = s.tabelle["Fasi"].set_index("Fase")
    assert fasi.loc[1, "Titolo"] == "Medievale" and fasi.loc[3, "Titolo"] == "Contemporanea"
    assert fasi.loc[1, "Da (anno)"] == 1200
    assert {u: r["Fase"] for u, r in s.schede_us().items()} == {1: 3, 2: 2, 3: 1}
    assert "interpretazione (archivio)" in s.tabelle["US"].columns
    assert "US 3" not in str(s.layers.get("usm")) and any("sia tra le US sia tra le USM" in n for n in s.note_importazione)
    assert "media_thumb_table" not in s.tabelle or "img" not in s.tabelle["media_thumb_table"].columns
    s.salva(str(tmp_path / "p.scavo"))                   # nessun conflitto di nomi nel GeoPackage
    ricostruisci(s)


# --------------------------------------------------------------------------- formati
def test_csv_con_geometrie_wkt(tmp_path):
    p = tmp_path / "partizioni.csv"
    pd.DataFrame({"id": [1, 2], "def_ogg": ["strutture", "livello archeologico"],
                  "geometry": ["POLYGON ((0 0, 4 0, 4 3, 0 3, 0 0))", "MULTIPOLYGON (((5 0, 8 0, 8 3, 5 3, 5 0)))"]}) \
        .to_csv(p, index=False)
    layers, tabelle = importa.esamina([str(p)])
    assert layers[0].geometria == "poligono" and layers[0].n == 2
    assert "geometry" not in tabelle[str(p)]["partizioni"].columns
    abb = importa.proponi([str(p)])
    abb.crs = "EPSG:3004"
    abb.superficie = {"tipo": "costante", "quota": 20.0}
    s = importa.applica(abb)
    assert set(s.poligoni_us()) == {1, 2} and s.crs == "EPSG:3004"


def test_zip_e_access(tmp_path, framework):
    z = tmp_path / "archivio.zip"
    with zipfile.ZipFile(z, "w") as f:
        for p in framework[:2]:
            base = os.path.splitext(p)[0]
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".csv"):
                if os.path.exists(base + ext):
                    f.write(base + ext, "dati/" + os.path.basename(base + ext))
        f.writestr("foto/1.jpg", b"x")
    files, note = importa.espandi([str(z), str(tmp_path / "vecchio.mdb")], cartella=str(tmp_path / "estratti"))
    assert sorted(os.path.basename(x) for x in files) == ["ContextData.csv", "Stansted.shp"]
    assert any("Access" in n for n in note)
    assert os.path.exists(os.path.splitext(files[-1])[0] + ".dbf") or \
        any(os.path.exists(os.path.splitext(x)[0] + ".dbf") for x in files)


def test_quote_nulle_scartate(tmp_path):
    gpkg = str(tmp_path / "s.gpkg")
    gpd.GeoDataFrame({"us": [1]}, geometry=[box(0, 0, 3, 3)], crs=CRS).to_file(gpkg, layer="us_poligoni")
    gpd.GeoDataFrame({"us": [1] * 4, "tipo_quota": ["sup"] * 4},
                     geometry=[Point(0.5, 0.5, 10.0), Point(2.5, 0.5, 10.1), Point(1.5, 2.5, -99.99), Point(1, 1, 10.05)],
                     crs=CRS).to_file(gpkg, layer="quote")
    s = importa.applica(importa.proponi([gpkg]))
    assert len(s.layers["quote"]) == 3
    assert any("nulla" in n for n in s.note_importazione)


def test_ricette_pronte_elencate():
    r = importa.ricette_pronte()
    assert {"framework_archaeology", "pyarchinit"} <= set(r)
    for k in r:
        importa.carica_ricetta_pronta(k)          # si leggono senza errori


def test_troncamento_sommato_al_terreno(framework, tmp_path):
    """Heathrow: piano di scavo = topografia storica + modello di troncamento (raster di valori negativi)."""
    tifffile = pytest.importorskip("tifffile")

    def tif(nome, z, passo):
        p = str(tmp_path / nome)
        tifffile.imwrite(p, np.asarray(z, "float32"), extratags=[
            (33550, "d", 3, (passo, passo, 0.0), False), (33922, "d", 6, (0.0, 0.0, 0.0, -20.0, 20.0, 0.0), False)])
        return p
    terreno = tif("topografia_1943.tif", np.full((20, 20), 50.0), 5.0)          # 100 x 100 m a 5 m
    tronc = np.full((160, 320), -0.6)
    tronc[:, 120:] = -1.0                                                          # più troncato a est di x = 10
    troncamento = tif("troncamento.tif", tronc, 0.25)
    abb = importa.proponi(framework + [terreno, troncamento])
    assert abb.superficie["sorgente"] == terreno and abb.superficie["correzione"] == troncamento
    abb, _ = importa.applica_ricetta(abb, importa.carica_ricetta_pronta("framework_archaeology"))
    assert abb.superficie["abbassa"] == 0.0                   # il troncamento sostituisce i 30 cm della ricetta
    abb.filtri.append({"dove": "layer", "layer": "Stansted", "colonna": "SITECODE", "valori": ["A"]})
    s = importa.applica(abb)
    assert any("troncamento" in n for n in s.note_importazione)
    m = ricostruisci(s)
    assert m.unita[20].top.max() == pytest.approx(49.0, abs=0.05)                 # buca a x 14-15: -1 m
    assert m.unita[20].top.min() == pytest.approx(49.0 - 0.35, abs=0.05)
    s.salva(str(tmp_path / "t.scavo"))
    r = Scavo.apri(str(tmp_path / "t.scavo"))
    assert r.raster_superficie(np.array([2.0, 14.5]), np.array([1.0, 0.5])) == pytest.approx([49.4, 49.0], abs=0.01)
