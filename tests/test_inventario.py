# -*- coding: utf-8 -*-
"""Inventario di una cartella di scavo: categorie, ruoli, destinazioni, raggruppamento dei file accessori,
archivi zip (anche uno dentro l'altro), doppioni e file da proporre all'importazione."""
import os
import time
import zipfile

import numpy as np
import pandas as pd
import pytest

from stratigrafia3d import inventario as inv


# ============================================================================ dati di prova
def _tif(path, dati, tfw=True, **kw):
    import tifffile
    tifffile.imwrite(path, dati, **kw)
    if tfw:
        with open(os.path.splitext(path)[0] + ".tfw", "w") as f:
            f.write("0.5\n0\n0\n-0.5\n1000.25\n2019.75\n")


def _gpkg(path):
    import geopandas as gpd
    from shapely.geometry import Point, Polygon
    us = gpd.GeoDataFrame({"us": [1, 2, 3]}, geometry=[Polygon([(1000 + i, 2000), (1001 + i, 2000), (1001 + i, 2001)])
                                                       for i in range(3)], crs="EPSG:32633")
    us.to_file(path, layer="us_poligoni", driver="GPKG")
    q = gpd.GeoDataFrame({"us": [1, 2, 3, 1], "quota": [10.0, 9.5, 9.2, 9.9]},
                         geometry=[Point(1000.5 + i * 0.3, 2000.2, 10.0 - i * 0.2) for i in range(4)], crs="EPSG:32633")
    q.to_file(path, layer="quote", driver="GPKG")


def _archivio(radice, tmp):
    """radice/archivio.zip -> dati/interno.zip (GeoPackage con 2 layer) + foto + __MACOSX."""
    gp = tmp / "scavo.gpkg"
    _gpkg(str(gp))
    interno = tmp / "interno.zip"
    with zipfile.ZipFile(interno, "w") as z:
        z.write(gp, "scavo.gpkg")
        z.writestr("leggimi.txt", "GeoPackage del rilievo\n")
    from PIL import Image
    foto = tmp / "IMG_0001.jpg"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)).save(foto)
    with zipfile.ZipFile(radice / "archivio.zip", "w") as z:
        z.write(interno, "dati/interno.zip")
        z.write(foto, "foto/IMG_0001.jpg")
        z.writestr("__MACOSX/foto/._IMG_0001.jpg", b"\x00" * 10)
        z.writestr("foto/.DS_Store", b"\x00" * 10)


@pytest.fixture(scope="module")
def cartella(tmp_path_factory):
    import geopandas as gpd
    from shapely.geometry import Polygon
    tmp = tmp_path_factory.mktemp("lavoro")
    r = tmp_path_factory.mktemp("scavo")
    _archivio(r, tmp)
    # shapefile completo (con .cpg, .prj, metadati ArcGIS) e la stessa cosa in GML
    (r / "shp").mkdir()
    lim = gpd.GeoDataFrame({"nome": ["saggio 1"]}, geometry=[Polygon([(999, 1999), (1004, 1999), (1004, 2003)])],
                           crs="EPSG:32633")
    lim.to_file(r / "shp" / "limite_scavo.shp")
    (r / "shp" / "limite_scavo.shp.xml").write_text("<metadata/>")
    lim.to_file(r / "shp" / "limite_scavo.gml", driver="GML")
    # schede e rapporti in Excel (con una copia più in profondità)
    us = pd.DataFrame({"US": [1, 2, 3], "Tipo": ["positiva", "positiva", "negativa"],
                       "Definizione": ["strato", "riempimento", "taglio"], "Fase": [1, 1, 1],
                       "Datazione da": [100, 100, 50]})
    rap = pd.DataFrame({"US": [1, 2], "Rapporto": ["copre", "riempie"], "US correlata": [2, 3]})
    with pd.ExcelWriter(r / "schede.xlsx") as w:
        us.to_excel(w, sheet_name="US", index=False)
        rap.to_excel(w, sheet_name="Rapporti", index=False)
    (r / "vecchio" / "copia").mkdir(parents=True)
    (r / "vecchio" / "copia" / "schede.xlsx").write_bytes((r / "schede.xlsx").read_bytes())
    # punti quotati in CSV, dizionario dei dati, dBase isolato
    pd.DataFrame({"X": [1000.2, 1001.1, 1002.3], "Y": [2000.1, 2000.4, 2000.2], "Z": [10.1, 9.8, 9.6],
                  "US": [1, 2, 3]}).to_csv(r / "punti_quota.csv", index=False)
    pd.DataFrame({"Tabella": ["US", "US"], "Campo": ["US", "Tipo"],
                  "Descrizione": ["Numero dell'unità stratigrafica assegnato in scavo",
                                  "Natura dell'unità: positiva (deposito) o negativa (taglio)"]}
                 ).to_csv(r / "descrizione_campi.csv", index=False)
    # raster: modello del terreno (con .tfw e .aux.xml), ortofoto RGB, differenze negative, TIFF senza georef
    (r / "raster").mkdir()
    y, x = np.mgrid[0:40, 0:40]
    _tif(str(r / "raster" / "dtm.tif"), (10 + 0.01 * x + 0.02 * y).astype("float32"))
    (r / "raster" / "dtm.tif.aux.xml").write_text("<PAMDataset/>")
    _tif(str(r / "raster" / "ortofoto.tif"), np.random.default_rng(2).integers(0, 255, (40, 40, 3), dtype=np.uint8),
         photometric="rgb")
    _tif(str(r / "raster" / "troncamento.tif"), (-0.2 - 0.001 * x).astype("float32"))
    _tif(str(r / "raster" / "scansione_pianta.tif"), np.full((30, 30), 200, np.uint8), tfw=False)
    # immagini, documenti, file inutili
    from PIL import Image
    (r / "foto").mkdir()
    Image.fromarray(np.random.default_rng(3).integers(0, 255, (60, 80, 3), dtype=np.uint8)).save(r / "foto" / "DSC_0002.jpg")
    disegno = np.full((80, 80), 255, np.uint8)
    disegno[10:70, 40] = 0
    disegno[40, 10:70] = 0
    Image.fromarray(disegno).save(r / "foto" / "sezione_A.png")
    (r / "relazione_scavo.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n")
    (r / "LICENSE.txt").write_text("CC BY 4.0\n")
    (r / ".DS_Store").write_bytes(b"\x00\x00")
    (r / "Thumbs.db").write_bytes(b"\x00\x00")
    (r / "~$schede.xlsx").write_bytes(b"\x00\x00")
    (r / "archivio.mdb").write_bytes(b"\x00\x01Standard Jet DB")
    return r


@pytest.fixture(scope="module")
def risultato(cartella, tmp_path_factory):
    vecchio = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path_factory.mktemp("casa"))       # gli archivi si aprono qui
    try:
        yield inv.esamina_cartella([str(cartella)])
    finally:
        if vecchio is not None:
            os.environ["HOME"] = vecchio


def _voce(ris, relativo):
    trovate = [v for v in ris["voci"] if v["relativo"] == relativo]
    assert trovate, f"manca «{relativo}» tra {[v['relativo'] for v in ris['voci']]}"
    return trovate[0]


CHIAVI = {"percorso", "origine", "relativo", "nome", "estensione", "dimensione", "categoria", "ruolo", "destinazione",
          "punteggio", "motivo", "usa", "dettagli"}


# ============================================================================ prove
def test_struttura(risultato, cartella):
    assert set(risultato) == {"radici", "voci", "riepilogo", "note", "file_proposta"}
    assert risultato["radici"] == [str(cartella)]
    for v in risultato["voci"]:
        assert CHIAVI <= set(v), v
        assert v["categoria"] in inv.CATEGORIE
        assert 0 <= v["punteggio"] <= 1
        assert os.path.isabs(v["percorso"])
        for p in v.get("parti", []):
            assert CHIAVI <= set(p)
    assert sum(risultato["riepilogo"].values()) == len(risultato["voci"])
    assert risultato["note"][0].startswith("Esaminati ")


def test_zip_annidato_e_geopackage(risultato):
    g = _voce(risultato, "archivio.zip/dati/interno.zip/scavo.gpkg")
    assert g["origine"] == "archivio.zip:dati/interno.zip:scavo.gpkg"
    assert os.path.exists(g["percorso"])
    assert os.sep + os.path.join(".stratigrafia3d", "estratti") + os.sep in g["percorso"]
    assert g["categoria"] == "gis" and g["usa"]
    parti = {p["nome"]: p for p in g["parti"]}
    assert set(parti) == {"us_poligoni", "quote"}
    assert parti["us_poligoni"]["ruolo"] == "us" and parti["us_poligoni"]["destinazione"] == "Piante delle US"
    assert parti["us_poligoni"]["dettagli"]["geometria"] == "poligono" and parti["us_poligoni"]["dettagli"]["n"] == 3
    assert parti["quote"]["ruolo"] == "quote" and parti["quote"]["destinazione"] == "Quote"
    assert parti["quote"]["dettagli"]["ha_z"]
    assert _voce(risultato, "archivio.zip")["categoria"] == "archivio"
    assert _voce(risultato, "archivio.zip/dati/interno.zip")["categoria"] == "archivio"
    assert _voce(risultato, "archivio.zip/dati/interno.zip/leggimi.txt")["categoria"] == "documento"
    # la cartella di estrazione è quella di importa.espandi: l'importazione riusa i file
    from stratigrafia3d import importa
    interno = _voce(risultato, "archivio.zip/dati/interno.zip")
    file_espandi, _ = importa.espandi([interno["percorso"]])
    assert file_espandi == [g["percorso"]]


def test_raggruppamento_shapefile_e_raster(risultato):
    s = _voce(risultato, "shp/limite_scavo.shp")
    assert s["categoria"] == "gis" and s["ruolo"] == "area" and s["destinazione"] == "Limite di scavo"
    acc = {a.lower() for a in s["dettagli"]["accessori"]}
    assert {"limite_scavo.dbf", "limite_scavo.shx", "limite_scavo.prj", "limite_scavo.cpg",
            "limite_scavo.shp.xml"} <= acc
    nomi = {v["relativo"] for v in risultato["voci"]}
    assert not any(n.endswith((".dbf", ".shx", ".prj", ".cpg", ".tfw", ".aux.xml")) for n in nomi)
    d = _voce(risultato, "raster/dtm.tif")
    assert d["categoria"] == "raster" and d["ruolo"] == "dem" and d["destinazione"] == "Superficie di riferimento"
    assert {"dtm.tfw", "dtm.tif.aux.xml"} <= set(d["dettagli"]["accessori"])
    o = _voce(risultato, "raster/ortofoto.tif")
    assert o["ruolo"] == "ortofoto" and o["destinazione"] == "Ortofoto"
    t = _voce(risultato, "raster/troncamento.tif")
    assert t["ruolo"] == "differenza" and t["destinazione"] == "Correzione della superficie"
    sc = _voce(risultato, "raster/scansione_pianta.tif")
    assert sc["categoria"] == "immagine" and sc["destinazione"].startswith("Documentazione")


def test_tabelle_e_punti(risultato):
    x = _voce(risultato, "schede.xlsx")
    assert x["categoria"] == "tabella" and x["usa"]
    fogli = {p["nome"]: p for p in x["parti"]}
    assert fogli["US"]["ruolo"] == "schede_us" and fogli["US"]["destinazione"] == "Schede US"
    assert fogli["Rapporti"]["ruolo"] == "rapporti" and fogli["Rapporti"]["destinazione"] == "Rapporti stratigrafici"
    c = _voce(risultato, "vecchio/copia/schede.xlsx")
    assert not c["usa"] and "copia" in c["motivo"]
    p = _voce(risultato, "punti_quota.csv")
    assert p["categoria"] == "gis" and p["ruolo"] == "quote" and p["dettagli"]["geometria"] == "punto"
    dz = _voce(risultato, "descrizione_campi.csv")
    assert dz["categoria"] == "documento" and dz["ruolo"] == "dizionario"
    g = _voce(risultato, "shp/limite_scavo.gml")
    assert not g["usa"] and "limite_scavo.shp" in g["motivo"]
    db = _voce(risultato, "archivio.mdb")
    assert db["categoria"] == "database" and not db["usa"] and "CSV" in db["motivo"]
    assert any("database Access" in n for n in risultato["note"])


def test_immagini_documenti_e_file_inutili(risultato):
    for rel in ("foto/DSC_0002.jpg", "foto/sezione_A.png", "archivio.zip/foto/IMG_0001.jpg"):
        v = _voce(risultato, rel)
        assert v["categoria"] == "immagine" and v["ruolo"] in ("foto", "disegno", "scansione")
        assert v["destinazione"].startswith("Documentazione")
    assert _voce(risultato, "relazione_scavo.pdf")["ruolo"] == "relazione"
    assert _voce(risultato, "LICENSE.txt")["ruolo"] == "licenza"
    for rel in (".DS_Store", "Thumbs.db", "~$schede.xlsx", "archivio.zip/foto/.DS_Store", "archivio.zip/__MACOSX"):
        v = _voce(risultato, rel)
        assert v["categoria"] == "ignorato" and not v["usa"] and v["destinazione"] == "Non usato"


def test_file_proposta_e_importazione(risultato, cartella):
    fp = risultato["file_proposta"]
    assert len(fp) == len(set(fp))
    nomi = [os.path.basename(f) for f in fp]
    assert sorted(nomi) == sorted(["scavo.gpkg", "limite_scavo.shp", "punti_quota.csv", "schede.xlsx", "dtm.tif",
                                   "ortofoto.tif", "troncamento.tif"])
    assert str(cartella / "schede.xlsx") in fp          # la copia meno profonda
    from stratigrafia3d import importa
    abb = importa.proponi(fp)
    assert abb.foglio_us == "US"
    ruoli = {r.layer: r.ruolo for r in abb.layers}
    assert ruoli["us_poligoni"] == "us" and ruoli["quote"] == "quote"
    assert abb.superficie["tipo"] == "raster" and abb.superficie.get("correzione", "").endswith("troncamento.tif")
    assert abb.ortofoto.endswith("ortofoto.tif")


def test_cache_e_velocita(risultato, cartella):
    t = time.time()
    di_nuovo = inv.esamina_cartella(str(cartella))
    assert time.time() - t < 2.0
    assert di_nuovo["file_proposta"] == risultato["file_proposta"]
    assert di_nuovo["riepilogo"] == risultato["riepilogo"]


def test_archivio_grande_di_foto(tmp_path, monkeypatch):
    """Molte foto in un archivio grande: si elencano tutte ma se ne estrae solo un campione."""
    from PIL import Image
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    monkeypatch.setattr(inv, "GRANDE_ZIP", 1000)
    buf = tmp_path / "f.jpg"
    Image.fromarray(np.random.default_rng(4).integers(0, 255, (40, 40, 3), dtype=np.uint8)).save(buf)
    (tmp_path / "dati").mkdir()
    with zipfile.ZipFile(tmp_path / "dati" / "foto_scavo.zip", "w") as z:
        for i in range(30):
            z.write(buf, f"Foto/IMG_{i:04d}.jpg")
    ris = inv.esamina_cartella(str(tmp_path / "dati"))
    foto = [v for v in ris["voci"] if v["categoria"] == "immagine"]
    assert len(foto) == 30
    estratte = [v for v in foto if v["dettagli"]["estratto"]]
    assert 0 < len(estratte) <= inv.CAMPIONE_IMMAGINI
    assert sum(os.path.exists(v["percorso"]) for v in foto) == len(estratte)
    assert all(v["ruolo"] in ("foto", "disegno", "scansione") for v in foto)
    assert any("senza estrarle tutte" in n for n in ris["note"])


def test_limite_e_profondita(tmp_path):
    d = tmp_path / "a" / "b" / "c"
    d.mkdir(parents=True)
    for i in range(5):
        (tmp_path / f"n{i}.txt").write_text("nota\n")
    (d / "profondo.txt").write_text("x\n")
    ris = inv.esamina_cartella(str(tmp_path), limite_file=3)
    assert len([v for v in ris["voci"] if v["categoria"] == "documento"]) == 3
    assert any("Trovati più di 3 file" in n for n in ris["note"])
    ris = inv.esamina_cartella(str(tmp_path), profondita_max=1)
    assert not any(v["nome"] == "profondo.txt" for v in ris["voci"])
    assert any("oltre la profondità massima" in n for n in ris["note"])


def test_demo_da_capo_a_fondo(demo):
    cart = os.path.dirname(os.path.dirname(demo["gpkg"]))
    ris = inv.esamina_cartella(cart)
    assert ris["file_proposta"] == [demo["gpkg"], demo["xlsx"]]
    g = next(v for v in ris["voci"] if v["percorso"] == demo["gpkg"])
    parti = {p["nome"]: p for p in g["parti"]}
    assert parti["us_poligoni"]["ruolo"] == "us" and parti["usm_poligoni"]["ruolo"] == "usm"
    assert parti["profili_us"]["ruolo"] == "profili" and parti["sezioni_disegno"]["ruolo"] == "sezioni_disegno"
    assert not parti["griglia_2m"]["usa"]
    x = next(v for v in ris["voci"] if v["percorso"] == demo["xlsx"])
    fogli = {p["nome"]: p["ruolo"] for p in x["parti"]}
    assert fogli["US"] == "schede_us" and fogli["USM"] == "schede_usm" and fogli["Rapporti"] == "rapporti"
    assert fogli["Materiali"] == "materiali" and fogli["Fasi"] == "fasi" and fogli["Campioni"] == "campioni"
    from stratigrafia3d import importa
    abb = importa.proponi(ris["file_proposta"])
    assert abb.foglio_us == "US" and abb.rapporti["modo"] == "foglio"


def test_riassunto_testo(risultato):
    testo = inv.riassunto_testo(risultato)
    righe = testo.splitlines()
    assert righe[0].startswith("Inventario di «") and righe[0].endswith(f": {len(risultato['voci'])} file")
    assert righe[1].startswith("Categorie: GIS ") and "raster 3" in righe[1] and "ignorati " in righe[1]
    assert "Destinazioni:" in righe and "  Superficie di riferimento: 1" in righe and "  Ortofoto: 1" in righe
    assert any(r.startswith("Non usati: ") for r in righe)
    i = righe.index("File proposti per l'importazione: 7")
    assert "  schede.xlsx" in righe[i + 1:i + 8] and "  raster/dtm.tif" in righe[i + 1:i + 8]
    assert "Note:" in righe and any(r.startswith("  - Esaminati ") for r in righe)
    # elenco lungo abbreviato; inventario vuoto
    assert "  … e altri 5" in inv.riassunto_testo(risultato, massimo=2).splitlines()
    assert inv.riassunto_testo({"voci": [], "radici": [], "note": [], "file_proposta": []}).splitlines() == \
        ["Inventario di file: 0 file", "File proposti per l'importazione: 0"]


def test_assicura_estratto(tmp_path, monkeypatch):
    """I file rimasti in un archivio (foto di un archivio grande, archivi annidati) si estraggono quando servono."""
    from PIL import Image
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    monkeypatch.setattr(inv, "GRANDE_ZIP", 1000)
    buf = tmp_path / "f.jpg"
    Image.fromarray(np.random.default_rng(4).integers(0, 255, (40, 40, 3), dtype=np.uint8)).save(buf)
    interno = tmp_path / "interno.zip"
    with zipfile.ZipFile(interno, "w") as z:
        for i in range(12):
            z.write(buf, f"Foto/IMG_{i:04d}.jpg")
    (tmp_path / "dati").mkdir()
    with zipfile.ZipFile(tmp_path / "dati" / "scavo.zip", "w") as z:
        z.write(interno, "archivi/interno.zip")
        z.writestr("leggimi.txt", "prova\n")
    ris = inv.esamina_cartella(str(tmp_path / "dati"))
    foto = [v for v in ris["voci"] if v["categoria"] == "immagine"]
    fuori = [v for v in foto if not os.path.exists(v["percorso"])]
    assert len(foto) == 12 and 0 < len(fuori) < 12
    v = fuori[0]
    assert v["membro"] == "Foto/" + v["nome"] and os.path.basename(v["archivio"]) == "interno.zip"
    assert inv.assicura_estratto(v) == v["percorso"] and os.path.getsize(v["percorso"]) == os.path.getsize(buf)
    assert inv.assicura_estratto(v) == v["percorso"]                       # già estratto
    assert inv.assicura_estratto(str(buf)) == str(buf)                     # un percorso che c'è
    assert inv.assicura_estratto(str(tmp_path / "manca.jpg")) is None
    # tolta la cartella di lavoro, si riestrae anche l'archivio interno (servono tutte le voci)
    import shutil
    shutil.rmtree(inv.cartella_estratti())
    w = fuori[1]
    assert inv.assicura_estratto(w) is None
    assert inv.assicura_estratto(w, ris["voci"]) == w["percorso"] and os.path.isfile(w["percorso"])
    # non si scrive fuori dalla cartella di lavoro; un membro che non c'è non si estrae
    assert inv.assicura_estratto(dict(w, percorso=str(tmp_path / "altrove.jpg"))) is None
    assert inv.assicura_estratto(dict(fuori[2], membro="Foto/non_esiste.jpg"), ris["voci"]) is None
    # i file delle cartelle non hanno archivio
    assert all("archivio" not in x for x in ris["voci"] if x["relativo"] == "scavo.zip")
