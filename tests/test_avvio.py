"""Avvio dell'app: sblocco dei file scaricati (Windows) e ripiego sul browser, senza Windows né finestre."""
import json
import sys
import threading
import time
import types
import urllib.error
import urllib.request

import pytest

from stratigrafia3d.app import avvio, dialoghi
from stratigrafia3d.app.server import App, Attivita, crea_server


def test_sblocca_file_scaricati(tmp_path, monkeypatch):
    (tmp_path / "a.dll").write_bytes(b"")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.pyd").write_bytes(b"")
    chiamate = []

    def finto_remove(p):
        chiamate.append(p)
        raise FileNotFoundError(p)       # dev'essere ignorato

    monkeypatch.setattr(avvio.os, "remove", finto_remove)
    avvio._sblocca_file_scaricati(str(tmp_path))
    attese = {str(tmp_path / "a.dll") + ":Zone.Identifier",
              str(tmp_path / "sub" / "c.pyd") + ":Zone.Identifier"}
    assert set(chiamate) == attese and len(chiamate) == 2


def test_sblocca_cartella_inesistente_non_fallisce(tmp_path):
    avvio._sblocca_file_scaricati(str(tmp_path / "non_esiste"))


class _FintoServer:
    server_address = ("127.0.0.1", 0)

    def __init__(self):
        self._stop = threading.Event()
        self.chiuso = False

    def serve_forever(self):
        self._stop.wait(5)

    def shutdown(self):
        self.chiuso = True
        self._stop.set()


def _prepara(monkeypatch, webview_modulo):
    srv = _FintoServer()
    monkeypatch.setattr(avvio, "App", lambda progetto=None: object())
    monkeypatch.setattr(avvio, "crea_server", lambda app, porta: srv)
    aperti, attese = [], []
    monkeypatch.setattr(avvio.webbrowser, "open", lambda url: aperti.append(url))
    monkeypatch.setattr(avvio, "_attendi_fine", lambda t, s, app=None: (attese.append(s), s.shutdown()))
    monkeypatch.setitem(sys.modules, "webview", webview_modulo)
    return srv, aperti, attese


def test_ripiego_sul_browser_se_la_finestra_fallisce(monkeypatch):
    finto = types.ModuleType("webview")
    finto.create_window = lambda *a, **k: object()

    def start():
        raise RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize")

    finto.start = start
    monkeypatch.setattr(dialoghi, "FINESTRA", None)
    srv, aperti, attese = _prepara(monkeypatch, finto)
    avvio.avvia()                                        # nessuna eccezione deve uscire
    assert aperti == ["http://127.0.0.1:0/"]
    assert attese == [srv] and srv.chiuso
    assert dialoghi.FINESTRA is None


def test_ripiego_senza_stdout(monkeypatch):
    finto = types.ModuleType("webview")

    def create_window(*a, **k):
        raise ImportError("clr")

    finto.create_window = create_window
    monkeypatch.setattr(sys, "stdout", None)
    srv, aperti, _ = _prepara(monkeypatch, finto)
    avvio.avvia()
    assert aperti == ["http://127.0.0.1:0/"]


def test_finestra_riuscita_non_apre_il_browser(monkeypatch):
    finto = types.ModuleType("webview")
    finestra = object()
    finto.create_window = lambda *a, **k: finestra
    finto.start = lambda: None
    monkeypatch.setattr(dialoghi, "FINESTRA", None)
    srv, aperti, attese = _prepara(monkeypatch, finto)
    avvio.avvia()
    assert aperti == [] and attese == [] and srv.chiuso
    assert dialoghi.FINESTRA is finestra


# ---------------------------------------------------------------- chiusura automatica (ripiego sul browser)

def _post(srv, nome, gettone):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/{nome}", data=b"{}",
                                 method="POST", headers={"X-Gettone": gettone, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


@pytest.fixture
def server_vero():
    avviati = []

    def crea(app):
        srv = crea_server(app, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        avviati.append(srv)
        return srv

    yield crea
    for srv in avviati:
        srv.shutdown()
        srv.server_close()


def test_battito_registrato_dal_server(server_vero):
    app = App()
    assert app.attivita.ultimo_battito is None
    assert app.azione("battito", {}) == {}
    assert app.attivita.ultimo_battito is not None

    app = App()
    srv = server_vero(app)
    assert _post(srv, "battito", "sbagliato")[0] == 403
    assert app.attivita.ultimo_battito is None          # senza gettone non conta
    codice, r = _post(srv, "battito", app.gettone)
    assert codice == 200 and r == {"ok": True}
    assert app.attivita.ultimo_battito is not None
    assert app.attivita.in_corso == 0


def test_richieste_in_corso_contate(server_vero):
    entrata, uscita = threading.Event(), threading.Event()

    class AppLenta(App):
        def azione(self, nome, a):
            if nome == "lenta":
                entrata.set()
                uscita.wait(10)
                return {}
            return super().azione(nome, a)

    app = AppLenta()
    srv = server_vero(app)
    risultato = []
    c = threading.Thread(target=lambda: risultato.append(_post(srv, "lenta", app.gettone)), daemon=True)
    c.start()
    assert entrata.wait(10)
    assert app.attivita.istantanea() == (None, 1)       # in corso, e non ancora un battito
    uscita.set()
    c.join(10)
    assert risultato and risultato[0][0] == 200
    ultimo, in_corso = app.attivita.istantanea()
    assert in_corso == 0 and ultimo is not None         # la fine della richiesta vale come battito


def _finta_app(modificato=False):
    return types.SimpleNamespace(attivita=Attivita(), stato=types.SimpleNamespace(modificato=modificato))


def _attesa_in_corso(app):
    srv = _FintoServer()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    f = threading.Thread(target=avvio._attendi_fine, args=(t, srv, app), daemon=True)
    f.start()
    return srv, f


@pytest.fixture
def tempi_brevi(monkeypatch):
    monkeypatch.setattr(avvio, "ATTESA_BATTITO", 0.2)
    monkeypatch.setattr(avvio, "ATTESA_CON_MODIFICHE", 60)
    monkeypatch.setattr(avvio, "ATTESA_INIZIALE", 60)
    monkeypatch.setattr(avvio, "INTERVALLO_CONTROLLO", 0.02)


def test_attendi_fine_chiude_dopo_il_silenzio(tempi_brevi):
    app = _finta_app()
    srv, f = _attesa_in_corso(app)
    time.sleep(0.5)
    assert not srv.chiuso                               # nessuna pagina ancora: si aspetta ATTESA_INIZIALE
    app.attivita.battito()
    t0 = time.monotonic()
    f.join(3)
    assert srv.chiuso and not f.is_alive()
    assert time.monotonic() - t0 >= 0.2


def test_attendi_fine_non_chiude_con_battiti_regolari(tempi_brevi):
    app = _finta_app()
    srv, f = _attesa_in_corso(app)
    for _ in range(10):
        app.attivita.battito()
        time.sleep(0.05)
    assert not srv.chiuso
    f.join(3)
    assert srv.chiuso


def test_attendi_fine_non_chiude_con_richiesta_in_corso(tempi_brevi):
    app = _finta_app()
    app.attivita.battito()
    app.attivita.inizio()                               # es. una ricostruzione di alcuni minuti
    srv, f = _attesa_in_corso(app)
    time.sleep(0.6)
    assert not srv.chiuso and f.is_alive()
    app.attivita.fine()
    f.join(3)
    assert srv.chiuso


def test_attendi_fine_attende_di_piu_con_modifiche_non_salvate(tempi_brevi):
    app = _finta_app(modificato=True)
    app.attivita.battito()
    srv, f = _attesa_in_corso(app)
    time.sleep(0.5)
    assert not srv.chiuso
    app.stato.modificato = False                        # salvato: ora vale ATTESA_BATTITO
    f.join(3)
    assert srv.chiuso


def test_attendi_fine_attesa_iniziale(tempi_brevi, monkeypatch):
    monkeypatch.setattr(avvio, "ATTESA_INIZIALE", 0.2)
    srv, f = _attesa_in_corso(_finta_app())
    f.join(3)
    assert srv.chiuso


def test_attendi_fine_senza_app_non_chiude(tempi_brevi):
    srv, f = _attesa_in_corso(None)
    time.sleep(0.4)
    assert not srv.chiuso and f.is_alive()
    srv.shutdown()
    f.join(3)


def test_chiusura_automatica_solo_se_il_browser_e_aperto_da_noi(monkeypatch):
    ricevuti = []
    monkeypatch.setattr(avvio, "_attendi_fine", lambda t, s, app=None: ricevuti.append(app))
    monkeypatch.setattr(avvio.webbrowser, "open", lambda url: None)
    app = object()
    avvio._avvia_nel_browser(None, None, "http://x/", browser=True, app=app)
    avvio._avvia_nel_browser(None, None, "http://x/", browser=False, app=app)
    assert ricevuti == [app, None]
