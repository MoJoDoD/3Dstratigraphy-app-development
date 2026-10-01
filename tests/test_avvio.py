"""Avvio dell'app: sblocco dei file scaricati (Windows) e ripiego sul browser, senza Windows né finestre."""
import sys
import threading
import types

from stratigrafia3d.app import avvio, dialoghi


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
    monkeypatch.setattr(avvio, "_attendi_fine", lambda t, s: (attese.append(s), s.shutdown()))
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
