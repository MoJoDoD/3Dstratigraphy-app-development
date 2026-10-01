# -*- coding: utf-8 -*-
"""Import flessibile in più «dialetti»: archivi inglesi, francesi e tedeschi, fogli Excel disordinati
(titoli, intestazione su due righe, schede trasposte, matrice di Harris come griglia), numeri di US
composti («US 1005») e punti quotati usati solo per la superficie (DPs di Heathrow). Ogni archivio deve
dare il foglio giusto, la colonna del numero, i rapporti e l'abbinamento con i poligoni senza correzioni."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from stratigrafia3d import importa, vocabolario as V
from stratigrafia3d import modifiche as md

CRS = "EPSG:32633"
N = np.nan


@pytest.fixture(autouse=True)
def vocabolario_pulito(tmp_path, monkeypatch):
    """Ogni test con un vocabolario dell'utente vuoto e suo (i termini insegnati non escono dal test)."""
    monkeypatch.setattr(V, "FILE_UTENTE", str(tmp_path / "config" / "vocabolario.json"))
    V.ricarica()
    importa._VOC_CACHE.clear()
    importa._CACHE_RAPPORTI.clear()
    yield
    V.ricarica()
    importa._VOC_CACHE.clear()
    importa._CACHE_RAPPORTI.clear()


def _pianta(d, numeri, campo="us", layer="unita", valori=None, extra=None):
    """Un poligono per unità (quadrati affiancati); ``valori`` sostituisce i numeri nel campo."""
    geom = [box(i * 3, 0, i * 3 + 2, 2) for i in range(len(numeri))]
    dati = {campo: valori if valori is not None else numeri}
    dati.update(extra or {})
    p = str(d / "pianta.gpkg")
    gpd.GeoDataFrame(dati, geometry=geom, crs=CRS).to_file(p, layer=layer, driver="GPKG")
    pts = [Point(i * 3 + 1, 1, 10.0 - i * 0.1) for i in range(len(numeri))]
    gpd.GeoDataFrame({campo: dati[campo], "z": [10.0 - i * 0.1 for i in range(len(numeri))]}, geometry=pts, crs=CRS) \
        .to_file(p, layer="quote", driver="GPKG")
    return p


def _excel(d, fogli, nome="schede.xlsx", intestazione=True):
    p = str(d / nome)
    with pd.ExcelWriter(p) as w:
        for k, df in fogli.items():
            df.to_excel(w, sheet_name=k, index=False, header=intestazione)
    return p


def _grezzo(righe):
    larghezza = max(len(r) for r in righe)
    return pd.DataFrame([list(r) + [N] * (larghezza - len(r)) for r in righe], dtype=object)


def _rapporti(s):
    return set(map(tuple, s.tabelle["Rapporti"].values.tolist()))


def _abbinati(s, numeri):
    """Ogni poligono ha la sua scheda e ogni scheda il suo poligono."""
    assert set(s.poligoni_us()) == set(numeri)
    assert set(s.schede_us()) == set(numeri)
    assert not any("ha un poligono ma nessuna scheda" in n for n in s.note_importazione)


# ------------------------------------------------------------------------------------------- (a) inglese
def test_archivio_inglese_single_context(tmp_path):
    numeri = [101, 102, 103, 104]
    gpkg = _pianta(tmp_path, numeri, campo="context", layer="contexts")
    reg = pd.DataFrame({"Context No.": numeri, "Type": ["Cut", "Fill", "Cut", "Layer"],
                        "Fill of": [N, 101, N, N], "Cut by": ["103", N, N, N],
                        "Description": ["Pit cut", "Dark fill", "Ditch cut", "Subsoil"]})
    xlsx = _excel(tmp_path, {"Sheet1": reg})
    abb = importa.proponi([gpkg, xlsx])
    assert abb.foglio_us == "Sheet1" and abb.colonne_us["US"] == "Context No."
    assert abb.colonne_us["Tipo"] == "Type" and abb.colonne_us["Descrizione"] == "Description"
    assert abb.rapporti == {"modo": "colonne", "foglio": "Sheet1",
                            "colonne": {"Fill of": "riempie", "Cut by": "tagliato da"}}
    assert abb.vocabolari["tipo"] == {"Cut": "negativa", "Fill": "positiva", "Layer": "positiva"}
    # il perché delle scelte, dal vocabolario
    assert "inglese" in abb.spiegazioni["colonna:Sheet1:Context No."]
    assert "contexts" in abb.spiegazioni["layer:contexts"]
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(102, "riempie", 101), (101, "tagliato da", 103)} <= _rapporti(s)
    tipi = s.tabelle["US"].set_index("US")["Tipo"].to_dict()
    assert tipi == {101: "negativa", 102: "positiva", 103: "negativa", 104: "positiva"}


# ------------------------------------------------------------------------------------------- (b) francese
def test_archivio_francese(tmp_path):
    numeri = [1, 2, 3, 4]
    gpkg = _pianta(tmp_path, numeri, campo="UE", layer="unites_stratigraphiques")
    ue = pd.DataFrame({"UE": numeri, "Type d'UE": ["Creusement", "Comblement", "Creusement", "Couche"],
                       "Recoupe": [N, N, "1", N], "Est recoupé par": ["3", N, N, N],
                       "Recouvre": [N, N, N, "1, 2, 3"], "Description": ["fosse", "remblai", "fossé", "niveau"]})
    xlsx = _excel(tmp_path, {"Fiches UE": ue})
    abb = importa.proponi([gpkg, xlsx])
    assert abb.foglio_us == "Fiches UE" and abb.colonne_us["US"] == "UE"
    assert abb.colonne_us["Tipo"] == "Type d'UE"                       # riconosciuto dai valori
    assert "Creusement" in abb.spiegazioni["colonna:Fiches UE:Type d'UE"]
    assert abb.rapporti["modo"] == "colonne"
    assert abb.rapporti["colonne"] == {"Recoupe": "taglia", "Est recoupé par": "tagliato da", "Recouvre": "copre"}
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(3, "taglia", 1), (1, "tagliato da", 3), (4, "copre", 1), (4, "copre", 2)} <= _rapporti(s)
    assert set(s.tabelle["US"].query("Tipo == 'negativa'")["US"]) == {1, 3}


# ------------------------------------------------------------------------------------------- (c) tedesco
def test_archivio_tedesco(tmp_path):
    numeri = [10, 11, 12]
    gpkg = _pianta(tmp_path, numeri, campo="Befund", layer="Befunde")
    bef = pd.DataFrame({"Befund-Nr.": numeri, "Befundart": ["Eingriff", "Verfüllung", "Schicht"],
                        "schneidet": [N, N, N], "wird geschnitten von": [N, N, N],
                        "liegt über": [N, N, "10, 11"], "Verfüllt": [N, 10, N],
                        "Beschreibung": ["Grube", "Verfüllung", "Kulturschicht"]})
    bef.loc[0, "schneidet"] = 12
    bef.loc[2, "wird geschnitten von"] = 10
    csv = str(tmp_path / "Befundliste.csv")
    bef.to_csv(csv, index=False, sep=";", encoding="cp1252")
    abb = importa.proponi([gpkg, csv])
    assert abb.foglio_us == "Befundliste" and abb.colonne_us["US"] == "Befund-Nr."
    assert abb.colonne_us["Tipo"] == "Befundart" and abb.colonne_us["Descrizione"] == "Beschreibung"
    assert abb.rapporti["modo"] == "colonne"
    assert abb.rapporti["colonne"] == {"schneidet": "taglia", "wird geschnitten von": "tagliato da",
                                       "liegt über": "copre", "Verfüllt": "riempie"}
    assert next(l for l in abb.layers if l.layer == "Befunde").ruolo == "us"
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(10, "taglia", 12), (12, "tagliato da", 10), (12, "copre", 10), (12, "copre", 11),
            (11, "riempie", 10)} <= _rapporti(s)
    assert s.tabelle["US"].set_index("US")["Tipo"].to_dict() == {10: "negativa", 11: "positiva", 12: "positiva"}


# --------------------------------------------------------------------- (d) titoli e intestazione su due righe
def test_excel_con_titoli_e_intestazione_su_due_righe(tmp_path):
    numeri = [1001, 1002, 1003]
    gpkg = _pianta(tmp_path, numeri)
    righe = [["Scavo di Poggio Rosso – schede US"], ["Campagna 2024"], [N],
             ["US", "Tipo", "Spessore", "Rapporti", N, "Descrizione"],
             [N, N, "(cm)", "copre", "taglia", N],
             [1001, "strato", 20, "1002", N, "humus"],
             [1002, "riempimento", 35, N, N, "terra scura"],
             [1003, "taglio", N, N, N, "fossa"],
             ["Totale", N, 55, N, N, N]]
    p = str(tmp_path / "schede.xlsx")
    _grezzo(righe).to_excel(p, header=False, index=False, sheet_name="Schede")
    abb = importa.proponi([gpkg, p])
    assert abb.foglio_us == "Schede" and abb.colonne_us["US"] == "US"
    assert abb.colonne_us["Spessore medio stimato (m)"] == "Spessore (cm)"
    assert abb.rapporti == {"modo": "colonne", "foglio": "Schede",
                            "colonne": {"Rapporti copre": "copre", "Rapporti taglia": "taglia"}}
    assert any(n.startswith("Foglio «Schede»: Intestazione alla riga 4") for n in abb.note)
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert (1001, "copre", 1002) in _rapporti(s)
    assert s.tabelle["US"].set_index("US")["Spessore medio stimato (m)"][1002] == pytest.approx(0.35)
    # le note del riordino compaiono una volta sola, anche rileggendo i file
    abb2 = importa.proponi([gpkg, p])
    assert sum(n.startswith("Foglio «Schede»: Intestazione alla riga") for n in abb2.note) == 1
    assert sum("Intestazione alla riga" in n for n in s.note_importazione) == 1


# ------------------------------------------------------------------------------------------- (e) trasposta
def test_schede_trasposte(tmp_path):
    numeri = [1, 2, 3]
    gpkg = _pianta(tmp_path, numeri)
    righe = [["US", 1, 2, 3], ["Tipo", "taglio", "riempimento", "strato"], ["Riempie", N, 1, N],
             ["Copre", N, N, "1, 2"], ["Descrizione", "buca", "riempimento della buca", "crollo"]]
    p = str(tmp_path / "schede.xlsx")
    _grezzo(righe).to_excel(p, header=False, index=False, sheet_name="US")
    abb = importa.proponi([gpkg, p])
    assert abb.foglio_us == "US" and abb.colonne_us["US"] == "US" and abb.colonne_us["Tipo"] == "Tipo"
    assert abb.rapporti["modo"] == "colonne" and abb.rapporti["colonne"] == {"Riempie": "riempie", "Copre": "copre"}
    assert any("Tabella trasposta" in n for n in abb.note)
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(2, "riempie", 1), (3, "copre", 1), (3, "copre", 2)} <= _rapporti(s)


# ------------------------------------------------------------------------------------------- (f) matrice
def test_matrice_di_harris_come_griglia(tmp_path):
    numeri = [1, 2, 3, 4]
    gpkg = _pianta(tmp_path, numeri)
    schede = pd.DataFrame({"US": numeri, "Tipo": ["strato", "strato", "taglio", "riempimento"],
                           "Descrizione": ["a", "b", "c", "d"]})
    matrice = _grezzo([[N, 1, 2, 3, 4], [1, N, ">", N, N], [2, "<", N, N, N], [3, N, N, N, "<"], [4, N, N, ">", N]])
    p = str(tmp_path / "scavo.xlsx")
    with pd.ExcelWriter(p) as w:
        schede.to_excel(w, sheet_name="Schede US", index=False)
        matrice.to_excel(w, sheet_name="Matrix", index=False, header=False)
    abb = importa.proponi([gpkg, p])
    assert abb.foglio_us == "Schede US" and abb.colonne_us["US"] == "US"
    assert abb.rapporti == {"modo": "foglio", "foglio": "Matrix", "colonne": ["US", "Rapporto", "US correlata"]}
    assert any(n.startswith("Foglio «Matrix»: Matrice dei rapporti") for n in abb.note)
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(1, "copre", 2), (4, "copre", 3)} <= _rapporti(s)


# ------------------------------------------------------------------------------- (g) identificativi composti
def test_numeri_di_us_composti(tmp_path):
    numeri = [1005, 1006, 1007]
    gpkg = _pianta(tmp_path, numeri, campo="etichetta", valori=["US 1005", "US 1006", "US 1007"])
    schede = pd.DataFrame({"N. US": ["US 1005", "US 1006", "US 1007"], "Tipo": ["taglio", "riempimento", "strato"],
                           "Riempie": [N, "US 1005", N], "Copre": [N, N, "US 1005, US 1006"]})
    xlsx = _excel(tmp_path, {"Elenco": schede})
    abb = importa.proponi([gpkg, xlsx])
    assert abb.foglio_us == "Elenco" and abb.colonne_us["US"] == "N. US"
    lay = next(l for l in abb.layers if l.layer == "unita")
    assert lay.ruolo == "us" and lay.campo_unita == "etichetta"
    assert any(n.startswith("Numeri di US scritti con sigle o lettere in «N. US» (es. «US 1005»)") for n in abb.note)
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert {(1006, "riempie", 1005), (1007, "copre", 1005), (1007, "copre", 1006)} <= _rapporti(s)


def test_numeri_ripetuti_tra_saggi(tmp_path):
    numeri = [1, 2, 3]
    gpkg = _pianta(tmp_path, numeri, extra={"Saggio": ["A", "A", "A"]})
    schede = pd.DataFrame({"Saggio": ["A", "A", "A", "B", "B"], "US": [1, 2, 3, 1, 2],
                           "Descrizione": ["a", "b", "c", "d", "e"]})
    abb = importa.proponi([gpkg, _excel(tmp_path, {"US": schede})])
    assert any("Il numero di US si ripete in «Saggio» diversi" in n for n in abb.note)
    # un solo filtro senza layer vale per la pianta e per le schede, anche con altre maiuscole
    abb.filtri = [{"dove": "scheda", "colonna": "SAGGIO", "valori": ["A"]},
                  {"dove": "layer", "layer": None, "colonna": "saggio", "valori": ["A"]}]
    s = importa.applica(abb)
    _abbinati(s, numeri)
    assert s.schede_us()[1]["Descrizione"] == "a"


# ------------------------------------------------------------------------- (h) DPs: solo per la superficie
@pytest.fixture
def heathrow(tmp_path):
    tifffile = pytest.importorskip("tifffile")

    def tif(nome, z, passo, x0, y0):
        p = str(tmp_path / nome)
        tifffile.imwrite(p, np.asarray(z, "float32"), extratags=[
            (33550, "d", 3, (passo, passo, 0.0), False), (33922, "d", 6, (0.0, 0.0, 0.0, x0, y0, 0.0), False)])
        return p
    # terreno a 25 m; troncamento (-0,5 m) solo sulla metà ovest (x < 100)
    terreno = tif("topografia_1943.tif", np.full((40, 40), 25.0), 5.0, 0.0, 200.0)
    troncamento = tif("troncamento.tif", np.full((400, 200), -0.5), 0.5, 0.0, 200.0)
    crs = "EPSG:27700"
    g = gpd.GeoDataFrame({"CONTEXT_ID": [10, 20, 30], "SITECODE": ["A", "A", "B"], "DEPTH": [0.5, 0.4, 0.3]},
                         geometry=[box(40, 90, 60, 110), box(140, 90, 160, 110), box(180, 180, 185, 185)], crs=crs)
    g.to_file(str(tmp_path / "T5 Volume 2.shp"))
    rng = np.random.default_rng(3)
    xy = rng.uniform(5, 195, size=(6000, 2))
    dp = gpd.GeoDataFrame({"ZCOORD": np.where(xy[:, 0] > 100, 24.8, 24.5), "SiteCode": ["A"] * 6000},
                          geometry=[Point(x, y) for x, y in xy], crs=crs)
    dp.to_file(str(tmp_path / "DPs.shp"))
    cd = pd.DataFrame({"Context Number": [10, 11, 20, 21, 30], "Context Type": ["Cut", "Deposit", "Cut", "Deposit", "Cut"],
                       "Fill of": [10, 10, 20, 20, 30], "Context Depth (m)": [N, 0.3, N, 0.2, N]})
    cd.to_csv(tmp_path / "ContextData.csv", index=False)
    return [str(tmp_path / "T5 Volume 2.shp"), str(tmp_path / "DPs.shp"), str(tmp_path / "ContextData.csv"),
            terreno, troncamento]


def test_dps_solo_superficie_con_la_ricetta(heathrow):
    abb, _ = importa.applica_ricetta(importa.proponi(heathrow), importa.carica_ricetta_pronta("framework_archaeology"))
    dps = next(l for l in abb.layers if l.layer == "DPs")
    assert dps.ruolo == "quote" and dps.solo_superficie and dps.quota_da == "campo:ZCOORD"
    # il flag sopravvive al salvataggio della ricetta
    assert importa.Abbinamento.da_json(abb.a_json()).layers[[l.layer for l in abb.layers].index("DPs")].solo_superficie
    # un filtro per sito senza layer: SITECODE nella pianta, SiteCode nei DPs
    abb.filtri.append({"dove": "layer", "layer": None, "colonna": "sitecode", "valori": ["A"]})
    s = importa.applica(abb)
    assert "quote" not in s.layers                       # nessuna quota di unità, nessuna assegnazione
    q = s.layers["quote_superficie"]
    assert len(q) == 6000 and "us" not in q.columns
    assert set(s.poligoni_us()) == {10, 11, 20, 21}       # sito B escluso dal filtro sulla pianta
    assert any("6000 punti quotati di «DPs» usati solo per la superficie" in n for n in s.note_importazione)
    sup = s.parametri.superficie
    assert sup.get("punti_correzione", 0) > 0
    nota = next(n for n in s.note_importazione if n.startswith("Il raster di correzione copre solo"))
    assert f"fuori si usano {sup['punti_correzione']} quote rilevate" in nota
    # a est (fuori dal troncamento) il piano di scavo viene dai DPs
    assert s.raster_superficie(np.array([170.0]), np.array([100.0]))[0] == pytest.approx(24.8, abs=0.05)


def test_dps_solo_superficie_senza_ricetta(heathrow):
    abb = importa.proponi(heathrow)
    dps = next(l for l in abb.layers if l.layer == "DPs")
    assert dps.ruolo == "quote" and dps.solo_superficie and not dps.campo_unita
    assert abb.superficie["tipo"] == "raster" and abb.superficie.get("correzione")


# ------------------------------------------------------------------------- spiegazioni, termini insegnati
def test_spiegazioni_nel_json_e_termine_insegnato(tmp_path):
    numeri = [1, 2]
    gpkg = _pianta(tmp_path, numeri, layer="Strukturen")
    schede = pd.DataFrame({"Kontekst": numeri, "Opis": ["a", "b"], "Rodzaj": ["warstwa", "wkop"]})
    xlsx = _excel(tmp_path, {"Karty": schede})
    abb = importa.proponi([gpkg, xlsx])
    assert importa.Abbinamento.da_json(abb.a_json()).spiegazioni == abb.spiegazioni
    assert abb.colonne_us.get("Descrizione") != "Opis"
    # l'utente insegna: «Opis» è la descrizione, «Kontekst» il numero di US, «Strukturen» sono murature
    importa.insegna("colonna", "Opis", "Descrizione")
    importa.insegna("colonna", "Kontekst", "US")
    importa.insegna("layer", "Strukturen", "usm")
    dati = json.loads(open(V.FILE_UTENTE, encoding="utf-8").read())
    assert dati["descrizione"]["termini"]["xx"] == ["Opis"] and dati["usm"]["termini"]["xx"] == ["Strukturen"]
    abb = importa.proponi([gpkg, xlsx])
    assert abb.colonne_us["US"] == "Kontekst" and abb.colonne_us["Descrizione"] == "Opis"
    assert "aggiunto dall'utente" in abb.spiegazioni["colonna:Karty:Opis"]
    assert next(l for l in abb.layers if l.layer == "Strukturen").ruolo == "usm"
    with pytest.raises(ValueError):
        importa.insegna("colonna", "Xyz", "colonna inesistente")


def test_azione_insegna_del_server(tmp_path):
    from stratigrafia3d.app.server import App, Errore
    numeri = [1, 2]
    gpkg = _pianta(tmp_path, numeri, layer="punti_vari")
    xlsx = _excel(tmp_path, {"US": pd.DataFrame({"US": numeri, "Beschrijving": ["a", "b"]})})
    app = App()
    r = app.azione("insegna", {"ambito": "colonna", "termine": "Beschrijving", "valore": "Descrizione",
                                "files": [gpkg, xlsx]})
    assert r["concetto"] == "descrizione" and r["abbinamento"]["colonne_us"]["Descrizione"] == "Beschrijving"
    assert r["abbinamento"]["spiegazioni"]["colonna:US:Beschrijving"]
    r = app.azione("insegna", {"ambito": "layer", "termine": "punti_vari", "valore": "ignora", "files": [gpkg, xlsx]})
    assert next(l for l in r["abbinamento"]["layers"] if l["layer"] == "punti_vari")["ruolo"] == "ignora"
    with pytest.raises(Errore):
        app.azione("insegna", {"ambito": "colonna", "termine": "", "valore": "Descrizione"})


# --------------------------------------------------------------------- riordino e riscrittura nei file
def test_colonna_in_centimetri_resta_riscrivibile(tmp_path):
    numeri = [1, 2, 3]
    gpkg = _pianta(tmp_path, numeri)
    schede = pd.DataFrame({"US": numeri, "Tipo": ["strato", "taglio", "riempimento"],
                           "Spessore (cm)": [20, N, 35], "Peso": ["1,5", "2,25", "0,5"]})
    xlsx = _excel(tmp_path, {"US": schede})
    t = importa.leggi_tabelle(xlsx)["US"]
    assert "Spessore (cm)" in t.columns and t["Spessore (cm)"].tolist()[0] == 20       # nome e valori del file
    assert t["Peso"].tolist() == pytest.approx([1.5, 2.25, 0.5])                        # virgola decimale
    abb = importa.proponi([gpkg, xlsx])
    assert abb.colonne_us["Spessore medio stimato (m)"] == "Spessore (cm)"
    s = importa.applica(abb)
    assert s.schede_us()[3]["Spessore medio stimato (m)"] == pytest.approx(0.35)
    md.applica_modifica(s, 3, {"Spessore medio stimato (m)": "0,40"})
    esito = md.riscrivi(s, copie=str(tmp_path / "copie"))
    assert esito["scritte"] == 1 and not esito["saltate"], esito["saltate"]
    assert pd.read_excel(xlsx, sheet_name="US").set_index("US")["Spessore (cm)"][3] == 40


def test_tabelle_lette_una_volta(tmp_path, monkeypatch):
    xlsx = _excel(tmp_path, {"US": pd.DataFrame({"US": [1, 2], "Descrizione": ["a", "b"]})})
    letture = []
    vero = pd.read_excel
    monkeypatch.setattr(pd, "read_excel", lambda *a, **k: letture.append(a) or vero(*a, **k))
    importa.leggi_tabelle(xlsx)
    t = importa.leggi_tabelle(xlsx)
    t["US"].loc[0, "Descrizione"] = "cambiata"                     # le copie non toccano la memoria
    assert len(letture) == 1 and importa.leggi_tabelle(xlsx)["US"].loc[0, "Descrizione"] == "a"
