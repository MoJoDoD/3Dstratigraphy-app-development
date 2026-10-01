# -*- coding: utf-8 -*-
"""Import di intere cartelle e archivi zip (anche zip dentro zip): inventario, file proposti, foto e disegni
collegati alle unità nella tabella «Documentazione», ricette applicate a una cartella, riga di comando."""
import json
import os
import shutil
import zipfile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from stratigrafia3d import importa, Scavo

PIL = pytest.importorskip("PIL")
FOTO = {"US1005_N.jpg": 1005, "US1005_S.jpg": 1005, "us_1012-dettaglio.jpg": 1012}


def _jpg(p, colore=(150, 90, 40)):
    from PIL import Image
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.new("RGB", (48, 32), colore).save(p, "JPEG")


def _zip_cartella(cartella, zp, prefisso=""):
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for rad, _, files in os.walk(cartella):
            for f in files:
                p = os.path.join(rad, f)
                z.write(p, prefisso + os.path.relpath(p, cartella).replace(os.sep, "/"))
    return str(zp)


@pytest.fixture(scope="module")
def archivio(tmp_path_factory):
    """Scavo dimostrativo in una cartella, con una sottocartella «foto» di immagini nominate per unità."""
    from stratigrafia3d.demo.genera import genera
    d = tmp_path_factory.mktemp("archivio") / "Podere Roveto"
    r = genera(str(d), anteprime_png=False, verbose=False)
    for nome in FOTO:
        _jpg(str(d / "foto" / nome))
    _jpg(str(d / "foto" / "panoramica_cantiere.jpg"), (20, 120, 200))
    return dict(r, cartella=str(d))


def _per_nome(abb):
    return {r.layer: r.ruolo for r in abb.layers}


def _controlla_progetto(s, rif):
    assert set(s.schede_us()) == set(rif.schede_us())
    assert len(s.layers["quote"]) == len(rif.layers["quote"])
    assert not [p for p in s.verifica() if p.livello == "errore"]


def _controlla_foto(s):
    doc = s.tabelle["Documentazione"]
    assert "Percorso file" in doc.columns and "US/USM" in doc.columns
    con_file = doc[doc["Percorso file"].notna()]
    per_file = {os.path.basename(p): set(con_file.loc[con_file["Percorso file"] == p, "US/USM"].map(int))
                for p in con_file["Percorso file"]}
    for nome, u in FOTO.items():
        assert u in per_file.get(nome, set()), (nome, per_file)
        assert os.path.isfile(con_file.loc[con_file["Percorso file"].map(os.path.basename) == nome,
                                           "Percorso file"].iloc[0])
    assert "panoramica_cantiere.jpg" not in per_file           # nessun numero di unità: non collegata
    # le schede della documentazione dell'archivio restano
    assert len(doc) > len(con_file)
    assert any(str(n).startswith("Documentazione dai file:") for n in s.note_importazione)


@pytest.fixture(scope="module")
def riferimento(archivio):
    return importa.applica(importa.proponi([archivio["gpkg"], archivio["xlsx"]]))


def test_cartella(archivio, riferimento):
    abb = importa.proponi([archivio["cartella"]])
    r = _per_nome(abb)
    assert r["us_poligoni"] == "us" and r["usm_poligoni"] == "usm" and r["quote"] == "quote"
    assert os.path.basename(abb.tabella) == os.path.basename(archivio["xlsx"])
    inv = abb.inventario
    assert inv and inv["voci"] and any(n.startswith("Inventario di «Podere Roveto»") for n in abb.note)
    nomi = {v["nome"] for v in inv["voci"]}
    assert set(FOTO) <= nomi
    assert all("dettagli" not in v and "parti" not in v for v in inv["voci"])
    # l'inventario sopravvive al JSON (ricetta, progetto salvato)
    abb2 = importa.Abbinamento.da_json(abb.a_json())
    assert abb2.inventario == json.loads(json.dumps(inv))
    s = importa.applica(abb2)
    _controlla_progetto(s, riferimento)
    _controlla_foto(s)


def test_progetto_salvato_con_la_documentazione(archivio, tmp_path):
    s = importa.applica(importa.proponi(archivio["cartella"]))      # anche una cartella sola, non in lista
    p = str(tmp_path / "c.scavo")
    s.salva(p)
    r = Scavo.apri(p)
    assert r.abbinamento.inventario["voci"]
    assert r.tabelle["Documentazione"]["Percorso file"].notna().sum() >= len(FOTO)


def test_zip_e_zip_annidato(archivio, riferimento, tmp_path):
    zp = _zip_cartella(archivio["cartella"], tmp_path / "scavo.zip", "Podere Roveto/")
    abb = importa.proponi([zp])
    assert abb.inventario and abb.foglio_us
    s = importa.applica(abb)
    _controlla_progetto(s, riferimento)
    _controlla_foto(s)
    # lo zip dentro un altro zip (come si scarica da alcuni archivi online)
    esterno = tmp_path / "download.zip"
    with zipfile.ZipFile(esterno, "w") as z:
        z.write(zp, "dati/scavo.zip")
        z.writestr("LEGGIMI.txt", "archivio di prova")
    s2 = importa.applica(importa.proponi([str(esterno)]))
    _controlla_progetto(s2, riferimento)
    _controlla_foto(s2)
    # passando prima per espandi (come fa l'app), proponi ritrova l'inventario
    files, note = importa.espandi([str(esterno)])
    assert {os.path.basename(f) for f in files} >= {os.path.basename(archivio["gpkg"]),
                                                    os.path.basename(archivio["xlsx"])}
    abb3 = importa.proponi(files)
    assert abb3.inventario and abb3.inventario["voci"]
    _controlla_foto(importa.applica(abb3))


def test_documentazione_con_file_mancanti(archivio, tmp_path):
    """Una tabella della documentazione che cita file spostati altrove: si ritrovano per nome nell'inventario."""
    d = tmp_path / "scavo"
    shutil.copytree(archivio["cartella"], d)
    xlsx = str(d / "02_Database" / os.path.basename(archivio["xlsx"]))
    fogli = pd.read_excel(xlsx, sheet_name=None)
    doc = fogli["Documentazione"]
    doc["File"] = None
    doc.loc[0, "File"] = "C:\\vecchio pc\\foto\\US1005_N.jpg"
    with pd.ExcelWriter(xlsx) as w:
        for k, v in fogli.items():
            v.to_excel(w, sheet_name=k, index=False)
    s = importa.applica(importa.proponi([str(d)]))
    doc = s.tabelle["Documentazione"]
    assert doc.loc[0, "Percorso file"] == str(d / "foto" / "US1005_N.jpg")
    assert any("ritrovati nelle cartelle esaminate" in n for n in s.note_importazione)
    # la stessa foto non si ripete per la stessa unità
    righe = doc[(doc["Percorso file"] == str(d / "foto" / "US1005_N.jpg")) & (doc["US/USM"] == 1005)]
    assert len(righe) == 1


# --------------------------------------------------------------------------- ricetta su una cartella
@pytest.fixture
def heathrow(tmp_path):
    """Archivio in stile Framework (Heathrow T5) estratto in una cartella con sottocartelle."""
    d = tmp_path / "T5 archive"
    os.makedirs(d / "GIS" / "Volume 2")
    os.makedirs(d / "Database")
    crs = "EPSG:27700"
    gpd.GeoDataFrame({"CONTEXT_ID": [10, 20], "SITECODE": ["A", "A"], "DEPTH": [0.5, 0.4]},
                     geometry=[box(40, 90, 60, 110), box(140, 90, 160, 110)], crs=crs) \
        .to_file(str(d / "GIS" / "Volume 2" / "T5 Volume 2.shp"))
    pd.DataFrame({"Context Number": [10, 11, 20, 21], "Context Type": ["Cut", "Deposit", "Cut", "Deposit"],
                  "Fill of": [10, 10, 20, 20], "Context Depth (m)": [None, 0.3, None, 0.2]}) \
        .to_csv(d / "Database" / "ContextData.csv", index=False)
    # registro delle foto: il numero dello scatto è il nome del file, l'unità sta nel registro
    pd.DataFrame({"Photo Number": [2231, 2232, 2240], "Context Number": [11, 21, 99],
                  "Description": ["Fill of ditch", "Pit fill", "Other site"]}) \
        .to_csv(d / "Database" / "ContextsPhotos.csv", index=False)
    for n in (2231, 2232, 2240, 2299):
        _jpg(str(d / "Photographs" / f"{n}.jpg"))
    return d


def test_ricetta_framework_su_cartella(heathrow):
    abb, note = importa.applica_ricetta(importa.proponi([str(heathrow)]),
                                        importa.carica_ricetta_pronta("framework_archaeology"))
    t5 = next(l for l in abb.layers if l.layer == "T5 Volume 2")
    assert t5.ruolo == "us" and t5.campo_unita == "CONTEXT_ID"
    assert abb.foglio_us == "ContextData"
    abb.superficie = {"tipo": "costante", "quota": 25.0}
    s = importa.applica(abb)
    assert set(s.poligoni_us()) == {10, 11, 20, 21}
    doc = s.tabelle["Documentazione"]
    auto = doc[doc["Percorso file"].notna()]
    assert {(os.path.basename(p), int(u)) for p, u in zip(auto["Percorso file"], auto["US/USM"])} >= \
        {("2231.jpg", 11), ("2232.jpg", 21)}
    assert not auto["Percorso file"].map(os.path.basename).isin(["2240.jpg", "2299.jpg"]).any()


def test_ricetta_trova_nell_inventario_i_file_non_proposti(heathrow):
    """Se la proposta non ha preso la pianta o la tabella, la ricetta le cerca tra tutti i file dell'inventario."""
    abb = importa.proponi([str(heathrow / "Database" / "ContextData.csv")])
    abb.inventario = importa._inventario_compatto(importa.inventaria([str(heathrow)]))
    assert not any(l.layer == "T5 Volume 2" for l in abb.layers)
    abb, note = importa.applica_ricetta(abb, importa.carica_ricetta_pronta("framework_archaeology"))
    t5 = next(l for l in abb.layers if l.layer == "T5 Volume 2")
    assert t5.ruolo == "us" and t5.campo_unita == "CONTEXT_ID"
    assert any("trovati nell'inventario" in n for n in note)
    # e anche la tabella delle schede, quando manca
    abb = importa.proponi([str(heathrow / "GIS" / "Volume 2" / "T5 Volume 2.shp")])
    abb.inventario = importa._inventario_compatto(importa.inventaria([str(heathrow)]))
    abb, note = importa.applica_ricetta(abb, importa.carica_ricetta_pronta("framework_archaeology"))
    assert abb.foglio_us == "ContextData" and os.path.basename(abb.tabella) == "ContextData.csv"


# --------------------------------------------------------------------------- riga di comando
def test_riga_di_comando(archivio, tmp_path, capsys):
    from stratigrafia3d.cli import main
    assert main(["inventario", archivio["cartella"]]) == 0
    out = capsys.readouterr().out
    assert "US1005_N.jpg" in out or "foto" in out
    zp = _zip_cartella(archivio["cartella"], tmp_path / "scavo.zip")
    assert main(["inventario", zp, "--json", str(tmp_path / "inv.json")]) == 0
    assert json.load(open(tmp_path / "inv.json", encoding="utf-8"))["voci"]
    capsys.readouterr()
    p = str(tmp_path / "roveto.scavo")
    assert main(["importa", archivio["cartella"], "-o", p]) == 0
    assert "Progetto salvato" in capsys.readouterr().out
    s = Scavo.apri(p)
    assert s.modello is not None and s.tabelle["Documentazione"]["Percorso file"].notna().sum() >= len(FOTO)


# --------------------------------------------------------------------------- scelte fatte a mano nell'inventario
def _percorso(inv, nome):
    return next(v["percorso"] for v in inv["voci"] if v["nome"] == nome)


def _file_collegati(s):
    doc = s.tabelle["Documentazione"]
    return {os.path.basename(p): t for p, t in zip(doc["Percorso file"], doc["Tipo"]) if isinstance(p, str)}


def test_foto_tolte_nell_inventario_non_vanno_in_documentazione(archivio):
    inv = importa.inventaria([archivio["cartella"]])
    tolta, disegno = _percorso(inv, "US1005_N.jpg"), _percorso(inv, "US1005_S.jpg")
    # una chiave può essere anche il percorso dentro la cartella
    scelte = {tolta: {"usa": False}, disegno: {"ruolo": "disegno"}, "foto/us_1012-dettaglio.jpg": False}
    abb = importa.proponi([archivio["cartella"]], scelte=scelte)
    terza = _percorso(inv, "us_1012-dettaglio.jpg")
    assert abb.inventario["scelte"] == {tolta: {"usa": False}, disegno: {"ruolo": "disegno"}, terza: {"usa": False}}
    voci = {v["nome"]: v for v in abb.inventario["voci"]}
    assert voci["US1005_N.jpg"]["usa"] is False and voci["US1005_S.jpg"]["ruolo"] == "disegno"
    assert voci["US1005_S.jpg"]["destinazione"] == "Documentazione (disegni)"
    # le scelte restano nella ricetta e nel progetto (JSON)
    abb2 = importa.Abbinamento.da_json(abb.a_json())
    assert importa.scelte_inventario(abb2) == abb.inventario["scelte"]
    s = importa.applica(abb2)
    coll = _file_collegati(s)
    assert "US1005_N.jpg" not in coll and "us_1012-dettaglio.jpg" not in coll
    assert coll["US1005_S.jpg"] == "Disegno"
    assert any("esclusi nell'inventario" in n for n in s.note_importazione)
    # senza scelte tutte e tre le foto sono collegate (e sono foto)
    assert _file_collegati(importa.applica(importa.proponi([archivio["cartella"]])))["US1005_S.jpg"] == "Foto"
    # le scelte si possono applicare anche dopo, a un abbinamento già proposto
    abb3 = importa.proponi([archivio["cartella"]])
    importa.applica_scelte_inventario(abb3, {tolta: {"usa": False}})
    assert "US1005_N.jpg" not in _file_collegati(importa.applica(abb3))


def test_scelte_della_ricetta_su_un_altra_copia(archivio, tmp_path):
    inv = importa.inventaria([archivio["cartella"]])
    ricetta = importa.proponi([archivio["cartella"]], scelte={_percorso(inv, "US1005_N.jpg"): False})
    copia = tmp_path / "copia dello scavo"
    shutil.copytree(archivio["cartella"], copia)
    abb, note = importa.applica_ricetta(importa.proponi([str(copia)]), importa.Abbinamento.da_json(ricetta.a_json()))
    assert importa.scelte_inventario(abb) == {str(copia / "foto" / "US1005_N.jpg"): {"usa": False}}
    coll = _file_collegati(importa.applica(abb))
    assert "US1005_N.jpg" not in coll and "US1005_S.jpg" in coll


def _tif(path, dati, **kw):
    import tifffile
    tifffile.imwrite(path, dati, **kw)
    with open(os.path.splitext(path)[0] + ".tfw", "w") as f:
        f.write("0.5\n0\n0\n-0.5\n999.25\n2019.75\n")


@pytest.fixture(scope="module")
def misto(tmp_path_factory):
    """Cartella con piante, un poligono senza nome riconoscibile, schede, due tabelle, due modelli del
    terreno e un'ortofoto."""
    import numpy as np
    from shapely.geometry import Polygon
    d = tmp_path_factory.mktemp("misto") / "Scavo misto"
    for c in ("GIS", "tabelle", "raster"):
        os.makedirs(d / c)
    crs = "EPSG:32633"
    gpd.GeoDataFrame({"us": [1, 2, 3]}, geometry=[box(1000 + 2 * i, 2000, 1002 + 2 * i, 2003) for i in range(3)],
                     crs=crs).to_file(str(d / "GIS" / "us_poligoni.shp"))
    gpd.GeoDataFrame({"nome": ["b"]}, geometry=[Polygon([(999, 1999), (1008, 1999), (1008, 2004), (999, 2004)])],
                     crs=crs).to_file(str(d / "GIS" / "poligoni_vari.shp"))
    with pd.ExcelWriter(d / "tabelle" / "schede.xlsx") as w:
        pd.DataFrame({"US": [1, 2, 3], "Tipo": ["positiva", "positiva", "negativa"],
                      "Definizione": ["strato", "riempimento", "taglio"], "Spessore": [0.2, 0.3, 0.4]}) \
            .to_excel(w, sheet_name="US", index=False)
        pd.DataFrame({"US": [1, 2], "Rapporto": ["copre", "riempie"], "US correlata": [2, 3]}) \
            .to_excel(w, sheet_name="Rapporti", index=False)
    pd.DataFrame({"US": [1, 1, 2, 9], "Classe": ["ceramica", "ossa", "ceramica", "vetro"], "NR": [12, 3, 5, 1]}) \
        .to_csv(d / "tabelle" / "elenco.csv", index=False)
    pd.DataFrame({"Numero": [1, 2, 3], "Natura": ["Layer", "Fill", "Cut"], "Spessore": [0.5, 0.6, 0.7]}) \
        .to_csv(d / "tabelle" / "varie.csv", index=False)
    y, x = np.mgrid[0:40, 0:40]
    _tif(str(d / "raster" / "dtm.tif"), (10 + 0.01 * x + 0.02 * y).astype("float32"))
    _tif(str(d / "raster" / "rilievo_2019.tif"), (9 + 0.01 * x).astype("float32"))
    _tif(str(d / "raster" / "ortofoto.tif"), np.random.default_rng(2).integers(0, 255, (40, 40, 3), dtype=np.uint8),
         photometric="rgb")
    return d


def test_destinazioni_cambiate_nell_inventario(misto):
    p = {n: str(misto / c / n) for c, n in (("GIS", "us_poligoni.shp"), ("GIS", "poligoni_vari.shp"), ("tabelle", "schede.xlsx"),
                                           ("tabelle", "elenco.csv"), ("tabelle", "varie.csv"), ("raster", "dtm.tif"),
                                           ("raster", "rilievo_2019.tif"), ("raster", "ortofoto.tif"))}
    base = importa.proponi([str(misto)])
    assert base.foglio_us == "US" and base.superficie["tipo"] == "raster" and not base.superficie.get("correzione")
    assert base.ortofoto == p["ortofoto.tif"] and not (base.fogli_collegati or {}).get("Materiali")
    assert not any(l.sorgente == p["poligoni_vari.shp"] and l.ruolo != "ignora" for l in base.layers)
    # ---- raster: correzione della superficie, ortofoto, superficie di riferimento
    abb = importa.proponi([str(misto)], scelte={p["rilievo_2019.tif"]: {"ruolo": "differenza"}})
    assert abb.superficie["sorgente"] == p["dtm.tif"] and abb.superficie["correzione"] == p["rilievo_2019.tif"]
    abb = importa.proponi([str(misto)], scelte={p["rilievo_2019.tif"]: "ortofoto"})
    assert abb.ortofoto == p["rilievo_2019.tif"] and abb.superficie["sorgente"] == p["dtm.tif"]
    for nome in ("dtm.tif", "rilievo_2019.tif"):
        abb = importa.proponi([str(misto)], scelte={p[nome]: {"ruolo": "dem"}})
        assert abb.superficie["sorgente"] == p[nome] and abb.superficie.get("correzione") != p[nome]
    abb = importa.proponi([str(misto)], scelte={p["dtm.tif"]: False, p["ortofoto.tif"]: False})
    assert abb.superficie["sorgente"] == p["rilievo_2019.tif"] and abb.ortofoto is None
    # lo stesso, dopo la proposta
    abb = importa.proponi([str(misto)])
    note = importa.applica_scelte_inventario(abb, {p["dtm.tif"]: {"ruolo": "differenza"}, p["ortofoto.tif"]: False})
    assert abb.superficie["sorgente"] == p["rilievo_2019.tif"] and abb.superficie["correzione"] == p["dtm.tif"]
    assert abb.ortofoto is None and any("Correzione della superficie" in n for n in note)
    # ---- layer: un file non proposto, spuntato e con il ruolo scelto; un file tolto
    abb = importa.proponi([str(misto)], scelte={p["poligoni_vari.shp"]: {"usa": True, "ruolo": "area"}})
    vari = next(l for l in abb.layers if l.sorgente == p["poligoni_vari.shp"])
    assert vari.ruolo == "area" and vari.motivo == "scelto a mano nell'inventario"
    assert "area_scavo" in importa.applica(abb).layers
    abb = importa.proponi([str(misto)])
    importa.applica_scelte_inventario(abb, {p["poligoni_vari.shp"]: {"usa": True, "ruolo": "area"},
                                            p["us_poligoni.shp"]: {"usa": False}})
    ruoli = {os.path.basename(l.sorgente): (l.ruolo, l.motivo) for l in abb.layers}
    assert ruoli["poligoni_vari.shp"][0] == "area" and ruoli["us_poligoni.shp"] == ("ignora", "escluso nell'inventario")
    # ---- tabelle: materiali, schede, rapporti
    abb = importa.proponi([str(misto)], scelte={p["elenco.csv"]: {"ruolo": "materiali"}})
    assert abb.fogli_collegati["Materiali"]["foglio"] == "elenco" and abb.foglio_us == "US"
    mat = importa.applica(abb).tabelle["Materiali"]
    assert sorted(mat["US"]) == [1, 1, 2] and "Classe" in mat.columns
    abb = importa.proponi([str(misto)], scelte={p["varie.csv"]: {"usa": True, "ruolo": "schede_us"}})
    assert abb.tabella == p["varie.csv"] and abb.foglio_us == "varie" and abb.colonne_us["US"] == "Numero"
    assert p["schede.xlsx"] in abb.tabelle_extra and abb.rapporti == base.rapporti
    s = importa.applica(abb)
    assert set(s.schede_us()) == {1, 2, 3} and len(s.tabelle["Rapporti"]) == 2
    abb = importa.proponi([str(misto)])
    importa.applica_scelte_inventario(abb, {p["schede.xlsx"]: {"usa": False}})
    assert abb.tabella is None and abb.foglio_us is None and abb.rapporti == {"modo": "nessuno"}
    assert p["elenco.csv"] in abb.tabelle_extra
    assert set(importa.applica(abb).schede_us()) == {1, 2, 3}          # le schede dai poligoni
    importa.applica_scelte_inventario(abb, {p["schede.xlsx"]: {"usa": True, "ruolo": "schede_us"}})
    assert abb.tabella == p["schede.xlsx"] and abb.foglio_us == "US" and abb.rapporti["modo"] == "foglio"
    # tutto sopravvive al JSON
    assert importa.Abbinamento.da_json(abb.a_json()).inventario["scelte"][p["schede.xlsx"]] == \
        {"usa": True, "ruolo": "schede_us"}


def test_foto_di_un_archivio_grande_estratte_quando_servono(archivio, riferimento, tmp_path, monkeypatch):
    """Le foto di un archivio grande si elencano senza estrarle: quelle collegate si estraggono all'importazione."""
    from stratigrafia3d import inventario
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    monkeypatch.setattr(inventario, "GRANDE_ZIP", 1000)
    zp = _zip_cartella(archivio["cartella"], tmp_path / "scavo.zip", "Podere Roveto/")
    abb = importa.proponi([zp])
    foto = [v for v in abb.inventario["voci"] if v["categoria"] == "immagine"]
    fuori = [v for v in foto if not os.path.isfile(v["percorso"])]
    assert fuori and all(v["archivio"] == zp and v["membro"].endswith(v["nome"]) for v in fuori)
    abb = importa.Abbinamento.da_json(abb.a_json())
    s = importa.applica(abb)
    _controlla_progetto(s, riferimento)
    _controlla_foto(s)                     # «Percorso file» indica file che ci sono
    doc = s.tabelle["Documentazione"]
    assert all(os.path.isfile(p) for p in doc["Percorso file"] if isinstance(p, str))
    assert any("estratti dagli archivi" in n for n in s.note_importazione)
    # la panoramica, non collegata a nessuna unità, resta nell'archivio se non era nel campione
    assert not any("non sono sul disco" in n for n in s.note_importazione)


def test_riga_di_comando_con_le_scelte(archivio, misto, tmp_path, capsys):
    from stratigrafia3d.cli import main
    assert main(["inventario", archivio["cartella"]]) == 0
    out = capsys.readouterr().out
    assert "Inventario di «Podere Roveto»" in out and "File proposti per l'importazione: 2" in out
    assert "Documentazione (foto)" in out and "Categoria " not in out
    assert main(["inventario", archivio["cartella"], "--elenco"]) == 0
    out = capsys.readouterr().out
    assert "US1005_N.jpg" in out and "Categoria" in out and "File proposti per l'importazione: 2" in out
    p = str(tmp_path / "roveto.scavo")
    assert main(["importa", archivio["cartella"], "--escludi", "foto/US1005_N.jpg", "-o", p]) == 0
    capsys.readouterr()
    s = Scavo.apri(p)
    assert "US1005_N.jpg" not in _file_collegati(s) and "US1005_S.jpg" in _file_collegati(s)
    assert list(s.abbinamento.inventario["scelte"].values()) == [{"usa": False}]
    profilo = str(tmp_path / "profilo.json")
    assert main(["importa", str(misto), "--destinazione", f"{misto / 'raster' / 'rilievo_2019.tif'}=differenza",
                 "--destinazione", "GIS/poligoni_vari.shp=area", "--salva-profilo", profilo]) == 0
    abb = importa.Abbinamento.carica_profilo(profilo)
    assert abb.superficie["correzione"].endswith("rilievo_2019.tif")
    with pytest.raises(SystemExit):
        main(["importa", str(misto), "--destinazione", "senza_ruolo"])
