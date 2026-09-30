"""API del server locale dell'app, senza browser."""
import json
import threading
import urllib.request

import pytest

from stratigrafia3d.app.server import App, crea_server


@pytest.fixture(scope="module")
def server(tmp_path_factory, monkeypatch_module):
    app = App()
    srv = crea_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, srv.server_address[1]
    srv.shutdown()


@pytest.fixture(scope="module")
def monkeypatch_module(tmp_path_factory):
    import stratigrafia3d.app.server as s
    old = s.CARTELLA_CONFIG
    s.CARTELLA_CONFIG = str(tmp_path_factory.mktemp("config"))
    yield
    s.CARTELLA_CONFIG = old


def _api(server, nome, dati=None, gettone=None):
    app, porta = server
    req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/{nome}", data=json.dumps(dati or {}).encode(),
                                 headers={"X-Gettone": gettone or app.gettone})
    try:
        return json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        return dict(ok=False, codice=e.code)


def test_senza_gettone_rifiuta(server):
    assert _api(server, "stato", gettone="sbagliato")["codice"] == 403


def test_percorso_completo(server, demo, tmp_path):
    files = [demo["gpkg"], demo["xlsx"]]
    e = _api(server, "esamina", {"files": files})
    assert e["ok"] and len(e["layers"]) >= 9
    i = _api(server, "importa", {"abbinamento": e["abbinamento"]})
    assert i["ok"] and not [p for p in i["problemi"] if p["livello"] == "errore"]
    r = _api(server, "ricostruisci")
    assert r["ok"] and r["stato"]["ha_modello"]
    p = str(tmp_path / "app.scavo")
    s = _api(server, "salva", {"percorso": p})
    assert s["ok"] and not s["modificato"] and s["recenti"][0] == p
    assert _api(server, "chiudi")["aperto"] is False
    a = _api(server, "apri", {"percorso": p})
    assert a["ok"] and a["ha_modello"] and a["n_us"] == 39
    g = _api(server, "esporta", {"tipo": "glb", "percorso": str(tmp_path / "m.glb")})
    assert g["ok"]
    h = _api(server, "esporta", {"tipo": "html", "percorso": str(tmp_path / "m.html")})
    assert h["ok"]
    app, porta = server
    html = urllib.request.urlopen(f"http://127.0.0.1:{porta}/visualizzatore").read().decode()
    assert "/statici/vendor/three.min.js" in html


def test_errori_leggibili(server):
    r = _api(server, "apri", {"percorso": "/non/esiste.scavo"})
    assert not r["ok"] and "non trovato" in r["errore"].lower()
