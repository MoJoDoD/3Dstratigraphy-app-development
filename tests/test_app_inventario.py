"""Cartelle nella procedura guidata: dialogo, inventario, scelta dei file per la proposta."""
import json
import os
import re
import shutil
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest

from stratigrafia3d.app import dialoghi
from stratigrafia3d.app import server as srv_mod
from stratigrafia3d.app.server import App, crea_server

RADICE = Path(__file__).resolve().parents[1]
HTML = RADICE / "src" / "stratigrafia3d" / "app" / "statici" / "app.html"

# ------------------------------------------------------------------ un inventario finto (stesso contratto)
CAT = {".gpkg": "gis", ".geojson": "gis", ".xlsx": "tabella", ".tif": "raster", ".jpg": "immagine",
       ".pdf": "documento", ".txt": "documento", ".db": "ignorato"}
DEST = {"gis": ("piante", "Piante e quote"), "tabella": ("schede", "Schede US"), "raster": ("dtm", "Modello del terreno"),
        "immagine": ("foto", "Foto di scavo"), "documento": ("documento", "Documenti"), "ignorato": ("", "Non usato")}


def _fake_inventario(ritardo=0.0):
    m = types.ModuleType("stratigrafia3d.inventario")
    m.chiamate = []

    def esamina_cartella(percorsi, profondita_max=8, limite_file=20000):
        m.chiamate.append(list(percorsi))
        time.sleep(ritardo)
        voci = []
        for r in percorsi:
            for rad, _, files in os.walk(r):
                for f in sorted(files):
                    p = os.path.join(rad, f)
                    ext = os.path.splitext(f)[1].lower()
                    cat = CAT.get(ext, "altro")
                    ruolo, dest = DEST.get(cat, ("", "Altro"))
                    voci.append(dict(percorso=p, origine=r, relativo=os.path.relpath(p, r), nome=f, estensione=ext,
                                     dimensione=os.path.getsize(p), categoria=cat, ruolo=ruolo, destinazione=dest,
                                     punteggio=0.9 if cat in ("gis", "tabella") else 0.4, motivo=f"estensione {ext}",
                                     usa=cat in ("gis", "tabella", "immagine"),
                                     dettagli={"exif": "x" * 3000, "us": 12} if cat == "immagine" else {"n": 1}))
        riep = {}
        for v in voci:
            riep[v["categoria"]] = riep.get(v["categoria"], 0) + 1
        return dict(radici=list(percorsi), voci=voci, riepilogo=riep, note=["nota di prova"],
                    file_proposta=[v["percorso"] for v in voci if v["usa"] and v["categoria"] in ("gis", "tabella")])

    m.esamina_cartella = esamina_cartella
    m.riassunto_testo = lambda inv: f"{len(inv['voci'])} file"
    return m


@pytest.fixture
def finto(monkeypatch):
    import stratigrafia3d
    m = _fake_inventario()
    monkeypatch.setitem(sys.modules, "stratigrafia3d.inventario", m)
    monkeypatch.setattr(stratigrafia3d, "inventario", m, raising=False)
    return m


@pytest.fixture
def cartella(demo, tmp_path):
    """Una cartella di scavo: GIS e schede del dimostrativo, un GeoJSON in più, foto, un documento."""
    c = tmp_path / "scavo 2024"
    (c / "GIS").mkdir(parents=True)
    (c / "Foto").mkdir()
    shutil.copy(demo["gpkg"], c / "GIS" / os.path.basename(demo["gpkg"]))
    shutil.copy(demo["xlsx"], c / os.path.basename(demo["xlsx"]))
    (c / "GIS" / "extra.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nome": "saggio"},
         "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]]}}]}), encoding="utf-8")
    for i in range(5):
        (c / "Foto" / f"US{100 + i}.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 50)
    (c / "relazione.txt").write_text("relazione", encoding="utf-8")
    (c / "Thumbs.db").write_bytes(b"0")
    return c


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(srv_mod, "CARTELLA_CONFIG", str(tmp_path / "config"))
    app = App()
    s = crea_server(app, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield app, s.server_address[1]
    s.shutdown()


def _api(server, nome, dati=None):
    app, porta = server
    req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/{nome}", data=json.dumps(dati or {}).encode(),
                                 headers={"X-Gettone": app.gettone})
    return json.load(urllib.request.urlopen(req, timeout=300))


def _sorgenti(r):
    return {os.path.basename(l["sorgente"]) for l in r["abbinamento"]["layers"]}


# ------------------------------------------------------------------ azione «inventario»
def test_inventario_della_cartella(server, finto, cartella):
    r = _api(server, "inventario", {"percorsi": [str(cartella), "/non/una/cartella.gpkg"]})
    assert not r["ok"] and "non trovati" in r["errore"]
    r = _api(server, "inventario", {"percorsi": [str(cartella)]})
    assert r["ok"] and r["disponibile"] and r["radici"] == [str(cartella)] and r["cartelle"] == [str(cartella)]
    assert r["riepilogo"] == {"gis": 2, "tabella": 1, "immagine": 5, "documento": 1, "ignorato": 1}
    assert r["note"] == ["nota di prova"] and len(r["file_proposta"]) == 3
    foto = [v for v in r["voci"] if v["categoria"] == "immagine"]
    assert all(v["_radice"] == str(cartella) for v in r["voci"])
    assert foto and all(v["dettagli"] == {"us": 12} for v in foto)      # i dettagli voluminosi restano sul server
    # la seconda volta l'inventario viene dalla memoria; «forza» lo rifà
    _api(server, "inventario", {"percorsi": [str(cartella)]})
    assert len(finto.chiamate) == 1
    _api(server, "inventario", {"percorsi": [str(cartella)], "forza": True})
    assert len(finto.chiamate) == 2


def test_inventario_ignora_i_file_semplici(server, finto, demo):
    r = _api(server, "inventario", {"percorsi": [demo["gpkg"], demo["xlsx"]]})
    assert r["ok"] and r["radici"] == [] and r["voci"] == [] and not finto.chiamate


def test_inventario_lungo_non_blocca_il_server(server, monkeypatch, cartella):
    monkeypatch.setitem(sys.modules, "stratigrafia3d.inventario", _fake_inventario(ritardo=2.0))
    t = threading.Thread(target=_api, args=(server, "inventario", {"percorsi": [str(cartella)]}))
    t.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    assert _api(server, "stato")["ok"]
    assert time.monotonic() - t0 < 1.0
    t.join()


# ------------------------------------------------------------------ dalla cartella alla proposta
def test_esamina_cartella_con_i_soli_file_spuntati(server, finto, cartella, demo):
    inv = _api(server, "inventario", {"percorsi": [str(cartella)]})
    per_nome = {v["nome"]: v["percorso"] for v in inv["voci"]}
    scelti = [per_nome[os.path.basename(demo["gpkg"])], per_nome[os.path.basename(demo["xlsx"])]]
    foto = per_nome["US100.jpg"]
    r = _api(server, "esamina", {"files": [str(cartella)], "scelti": scelti, "usa": {foto: False},
                                 "ruoli": {foto: "disegno"}})
    assert r["ok"], r.get("errore")
    assert sorted(map(os.path.basename, r["files"])) == sorted(map(os.path.basename, scelti))
    assert r["cartelle"] == [str(cartella)]
    assert "extra.geojson" not in _sorgenti(r) and os.path.basename(demo["gpkg"]) in _sorgenti(r)
    assert r["abbinamento"]["tabella"] == scelti[1]
    # l'inventario resta con l'abbinamento, con le spunte e le destinazioni cambiate a mano
    voci = {v["nome"]: v for v in r["abbinamento"]["inventario"]["voci"]}
    assert voci["US100.jpg"]["usa"] is False and voci["US100.jpg"]["ruolo"] == "disegno"
    assert voci["US101.jpg"]["usa"] is True and "_radice" not in voci["US101.jpg"]
    assert r["abbinamento"]["inventario"]["riepilogo"]["immagine"] == 5


def test_esamina_cartella_proposta_e_ruoli(server, finto, cartella):
    # senza «scelti» valgono i file proposti dall'inventario
    r = _api(server, "esamina", {"files": [str(cartella)]})
    assert r["ok"] and "extra.geojson" in _sorgenti(r)
    extra = next(l for l in r["abbinamento"]["layers"] if l["sorgente"].endswith("extra.geojson"))
    # la destinazione cambiata nell'inventario vale per i layer di quel file
    r = _api(server, "esamina", {"files": [str(cartella)], "ruoli": {extra["sorgente"]: "area"}})
    extra = next(l for l in r["abbinamento"]["layers"] if l["sorgente"].endswith("extra.geojson"))
    assert extra["ruolo"] == "area" and extra["motivo"] == "scelto a mano nell'inventario"
    # «insegna» rifà la proposta con gli stessi file
    assert _api(server, "esamina", {"files": [str(cartella)], "scelti": []})["errore"].startswith("Nessun file di dati")


def test_file_semplici_come_prima(server, finto, demo):
    r = _api(server, "esamina", {"files": [demo["gpkg"], demo["xlsx"]]})
    assert r["ok"] and r["files"] == [demo["gpkg"], demo["xlsx"]] and r["cartelle"] == []
    assert not finto.chiamate and not r["abbinamento"].get("inventario")


def test_senza_modulo_inventario(server, monkeypatch, cartella):
    monkeypatch.setattr(srv_mod, "_modulo_inventario", lambda: None)
    r = _api(server, "inventario", {"percorsi": [str(cartella)]})
    assert r["ok"] and r["disponibile"] is False and r["cartelle"] == [str(cartella)] and r["voci"] == []
    r = _api(server, "esamina", {"files": [str(cartella)]})        # la cartella si legge per intero
    assert r["ok"] and "extra.geojson" in _sorgenti(r) and r["abbinamento"]["tabella"]


# ------------------------------------------------------------------ dialogo per le cartelle
def test_dialogo_cartella_senza_interfaccia(monkeypatch):
    monkeypatch.setattr(dialoghi, "FINESTRA", None)

    class Esito:
        returncode = 1
        stdout = ""
    argomenti = []
    monkeypatch.setattr(dialoghi.subprocess, "run", lambda a, **k: argomenti.append(a) or Esito())
    assert dialoghi.scegli("cartella") is None
    assert json.loads(argomenti[0][-1])["tipo"] == "cartella"

    def guasto(*a, **k):
        raise OSError("nessun interprete")
    monkeypatch.setattr(dialoghi.subprocess, "run", guasto)
    assert dialoghi.scegli("cartella") is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="senza schermo solo su Linux")
def test_dialogo_cartella_vero_senza_schermo(monkeypatch):
    monkeypatch.setattr(dialoghi, "FINESTRA", None)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert dialoghi.scegli("cartella") is None


def test_dialogo_cartella_tk_e_finestra(monkeypatch):
    class Esito:
        returncode = 0
        stdout = '["/scavi/2024"]\n'
    monkeypatch.setattr(dialoghi, "FINESTRA", None)
    monkeypatch.setattr(dialoghi.subprocess, "run", lambda a, **k: Esito())
    assert dialoghi.scegli("cartella") == ["/scavi/2024"]
    assert "askdirectory" in dialoghi._TK

    chiamate = []

    class Finestra:
        def create_file_dialog(self, tipo, **k):
            chiamate.append((tipo, k))
            return ("/scavi/2025",)
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(
        FileDialog=types.SimpleNamespace(OPEN=10, SAVE=20, FOLDER=30)))
    monkeypatch.setattr(dialoghi, "FINESTRA", Finestra())
    assert dialoghi.scegli("cartella") == ["/scavi/2025"] and chiamate[0][0] == 30
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(OPEN_DIALOG=1, SAVE_DIALOG=2, FOLDER_DIALOG=3))
    assert dialoghi.scegli("cartella") == ["/scavi/2025"] and chiamate[1][0] == 3
    assert dialoghi.scegli("apri") == ["/scavi/2025"] and chiamate[2][0] == 1


def test_azione_dialogo_cartella(server, monkeypatch):
    monkeypatch.setattr(srv_mod.dialoghi, "scegli", lambda tipo, filtri, multiplo, nome: ["/x"] if tipo == "cartella" else None)
    assert _api(server, "dialogo", {"tipo": "cartella", "filtri": []}) == {"ok": True, "percorsi": ["/x"], "disponibile": True}


# ------------------------------------------------------------------ pagina
def test_controlli_nella_pagina():
    h = HTML.read_text(encoding="utf-8")
    for x in ('id="bCartella"', ">Aggiungi cartella…<", 'id="invBox"', 'id="invChips"', 'id="invGruppi"',
              'id="invCerca"', 'api("inventario"', 'scegli("cartella"', "richiestaFile()", "data-usa", "data-ruolo"):
        assert x in h, x
    # le richieste del passo 1 portano i file spuntati
    assert re.search(r'api\("esamina",richiestaFile\(\)\)', h)


# ------------------------------------------------------------------ prova nel browser (facoltativa)
def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


@pytest.mark.skipif(_chromium() is None, reason="playwright non installato")
def test_procedura_con_cartella_nel_browser(server, finto, cartella, demo):
    for i in range(300):                                     # tante foto: il gruppo resta chiuso
        (cartella / "Foto" / f"F{i:04d}.jpg").write_bytes(b"\xff\xd8")
    app, porta = server
    sync_playwright = _chromium()
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                                # chromium non scaricato
            pytest.skip(f"chromium non disponibile: {e}")
        pg = b.new_page()
        errori = []
        pg.on("pageerror", lambda e: errori.append(str(e)))
        richieste = []
        pg.on("request", lambda r: richieste.append(r.post_data) if r.url.endswith("/api/esamina") else None)
        pg.route(re.compile(r".*(cdnjs|jsdelivr|unpkg).*"), lambda r: r.abort())
        pg.goto(f"http://127.0.0.1:{porta}/")
        pg.click("#cNuovo")
        pg.fill("#percorsoFile", f'"{cartella}"')            # con le virgolette, come da «Copia come percorso»
        pg.press("#percorsoFile", "Enter")
        pg.wait_for_selector("#invBox:not([hidden])")
        chips = pg.inner_text("#invChips")
        assert "piante GIS" in chips and "305" in chips and "foto" in chips and "ignorati" in chips
        assert "cartella" in pg.inner_text("#flist").lower() and "310 file" in pg.inner_text("#flist")
        # il gruppo delle foto è chiuso; aperto mostra 200 righe e il pulsante per le altre
        gruppo = pg.locator(".igr", has_text="Foto di scavo")
        assert gruppo.locator("tr").count() == 0
        gruppo.locator("[data-gapri]").click()
        gruppo = pg.locator(".igr", has_text="Foto di scavo")
        assert gruppo.locator("tbody tr").count() == 200
        assert "Mostra altri 105" in gruppo.inner_text()
        gruppo.locator("[data-gusa]").uncheck()               # nessuna foto
        # il GeoJSON in più non si usa; la tabella diventa «Rapporti» (suggerimento)
        riga = pg.locator("tr", has_text="extra.geojson")
        riga.locator("[data-usa]").uncheck()
        assert "off" in riga.get_attribute("class")
        pg.locator("tr", has_text=os.path.basename(demo["xlsx"])).locator("[data-ruolo]").select_option("rapporti")
        pg.fill("#invCerca", "relazione")
        pg.wait_for_function("document.querySelectorAll('#invGruppi tbody tr').length===1")
        pg.fill("#invCerca", "")
        pg.click("#n1")
        pg.wait_for_selector("#s2:not([hidden])", timeout=120000)
        corpo = json.loads(richieste[-1])
        assert corpo["files"] == [str(cartella)]
        assert sorted(map(os.path.basename, corpo["scelti"])) == sorted([os.path.basename(demo["gpkg"]), os.path.basename(demo["xlsx"])])
        assert list(corpo["ruoli"].values()) == ["rapporti"]
        assert sum(1 for v in corpo["usa"].values() if v is False) == 306
        assert "extra" not in pg.inner_text("#tLayer")
        # «Nuovo» con i soli file: nessun pannello
        pg.click("#bNuovo")
        assert pg.locator("#invBox").is_hidden()
        assert not errori, errori
        b.close()


# ------------------------------------------------------------------ le scelte dell'inventario fino al progetto
def test_foto_tolte_non_collegate_e_scelte_nell_abbinamento(server, finto, cartella):
    """Una foto tolta nell'inventario non finisce nella documentazione; le scelte restano con l'abbinamento."""
    app, _ = server
    for nome in ("US1005_a.jpg", "US1005_b.jpg", "US1012_c.jpg"):
        (cartella / "Foto" / nome).write_bytes(b"\xff\xd8\xff" + b"0" * 50)
    inv = _api(server, "inventario", {"percorsi": [str(cartella)]})
    per_nome = {v["nome"]: v["percorso"] for v in inv["voci"]}
    scelti = [v["percorso"] for v in inv["voci"] if v["categoria"] in ("gis", "tabella") and v["nome"] != "extra.geojson"]
    tolta, disegno = per_nome["US1005_a.jpg"], per_nome["US1012_c.jpg"]
    r = _api(server, "esamina", {"files": [str(cartella)], "scelti": scelti, "usa": {tolta: False},
                                 "ruoli": {disegno: "disegno"}})
    assert r["ok"], r.get("errore")
    assert r["abbinamento"]["inventario"]["scelte"] == {tolta: {"usa": False}, disegno: {"ruolo": "disegno"}}
    r = _api(server, "importa", {"abbinamento": r["abbinamento"]})
    assert r["ok"], r.get("errore")
    doc = app.stato.scavo.tabelle["Documentazione"]
    coll = {os.path.basename(p): t for p, t in zip(doc["Percorso file"], doc["Tipo"]) if isinstance(p, str)}
    assert "US1005_a.jpg" not in coll and coll["US1005_b.jpg"] == "Foto" and coll["US1012_c.jpg"] == "Disegno"
    assert app.stato.scavo.abbinamento.inventario["scelte"][tolta] == {"usa": False}


def test_file_tolto_senza_scelti_dal_wizard(server, finto, cartella, tmp_path):
    """Le scelte le applica importa anche senza l'elenco dei file spuntati: il file tolto non si legge."""
    r = _api(server, "esamina", {"files": [str(cartella)]})
    extra = next(l["sorgente"] for l in r["abbinamento"]["layers"] if l["sorgente"].endswith("extra.geojson"))
    r = _api(server, "esamina", {"files": [str(cartella)], "usa": {extra: False}})
    assert r["ok"] and "extra.geojson" not in _sorgenti(r)
    assert r["abbinamento"]["inventario"]["scelte"] == {extra: {"usa": False}}
    assert srv_mod._scelte({"a": False, "b": None}, {"a": "foto", "c": ""}) == {"a": {"usa": False, "ruolo": "foto"}}


def test_file_spuntato_estratto_dall_archivio(server, demo, tmp_path, monkeypatch):
    """Un file di dati spuntato che non è (più) nella cartella di lavoro si estrae dall'archivio quando serve."""
    import zipfile
    from stratigrafia3d import inventario
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    app, _ = server
    zp = str(tmp_path / "scavo.zip")
    with zipfile.ZipFile(zp, "w") as z:
        z.write(demo["gpkg"], "dati/" + os.path.basename(demo["gpkg"]))
        z.write(demo["xlsx"], "dati/" + os.path.basename(demo["xlsx"]))
    inv = app.inventario([zp])
    scelti = [v["percorso"] for v in inv["voci"] if v["categoria"] in ("gis", "tabella")]
    assert len(scelti) == 2 and all(os.path.isfile(p) for p in scelti)
    shutil.rmtree(inventario.cartella_estratti())
    dati, inv_abb = app.dati_da_esaminare([zp], scelti)
    assert sorted(dati) == sorted(scelti) and all(os.path.isfile(p) for p in dati)
    assert all(v["archivio"] == zp for v in inv_abb["voci"] if v["categoria"] in ("gis", "tabella"))
