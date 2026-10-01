# -*- coding: utf-8 -*-
"""Avvio dell'app: server locale + finestra nativa (pywebview) o, in mancanza, il browser."""
import os
import sys
import threading
import webbrowser

from .server import App, crea_server
from . import dialoghi

_ESTENSIONI_BINARIE = (".dll", ".exe", ".pyd")


def _stampa(*righe):
    """Stampa senza mai fallire: nell'eseguibile senza console sys.stdout può essere None."""
    try:
        if sys.stdout is not None:
            for r in righe:
                print(r)
    except Exception:
        pass


def _sblocca_file_scaricati(cartella):
    """Rimuove il "Mark of the Web" dai binari dell'app (solo Windows).

    Quando lo zip della release viene scaricato da Internet ed estratto con Esplora risorse,
    ogni file riceve il flusso NTFS alternativo ``Zone.Identifier``. Il .NET Framework si rifiuta
    di caricare le DLL così marcate (es. ``Python.Runtime.dll`` di pythonnet, usata da pywebview),
    e l'avvio fallisce con "Failed to resolve Python.Runtime.Loader.Initialize". Qui si cancella
    quel flusso da .dll/.exe/.pyd; ogni errore viene ignorato in silenzio.
    """
    try:
        for radice, _cartelle, nomi in os.walk(cartella):
            for nome in nomi:
                if not nome.lower().endswith(_ESTENSIONI_BINARIE):
                    continue
                try:
                    os.remove(os.path.join(radice, nome) + ":Zone.Identifier")
                except OSError:          # comprende FileNotFoundError: flusso assente
                    pass
    except Exception:
        pass


def _cartella_app():
    """Cartella dell'eseguibile congelato (PyInstaller)."""
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(sys.executable))


def _prepara_windows():
    """Su Windows, nell'eseguibile congelato, sblocca i file estratti da uno zip scaricato."""
    try:
        if os.name == "nt" and getattr(sys, "frozen", False):
            _sblocca_file_scaricati(_cartella_app())
    except Exception:
        pass


def _attendi_fine(t, srv):
    """Tiene vivo il server finché il processo non viene interrotto (Ctrl+C)."""
    try:
        while t.is_alive():
            t.join(0.5)          # a intervalli, così Ctrl+C viene ricevuto anche su Windows
    except KeyboardInterrupt:
        srv.shutdown()


def _avvia_nel_browser(srv, t, url, browser=True):
    _stampa(f"Stratigrafia 3D è in esecuzione su {url}",
            "Chiudi questa finestra (o premi Ctrl+C) per terminare.")
    if browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    _attendi_fine(t, srv)


def _apri_finestra(url):
    """Apre la finestra nativa pywebview; ritorna quando viene chiusa. Solleva eccezione se non è possibile."""
    import webview
    w = webview.create_window("Stratigrafia 3D", url, width=1440, height=900, min_size=(900, 600),
                              confirm_close=False)
    dialoghi.FINESTRA = w
    webview.start()          # ritorna quando la finestra viene chiusa


def avvia(progetto=None, finestra=True, porta=0, browser=True):
    _prepara_windows()
    app = App(progetto)
    srv = crea_server(app, porta)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    if finestra:
        try:
            import webview  # noqa: F401
        except Exception:        # pywebview non installato (o non importabile): si usa il browser
            webview = None
        if webview is not None:
            try:
                _apri_finestra(url)
            except Exception as e:
                # es. RuntimeError di pythonnet/.NET o componenti mancanti: si ripiega sul browser
                dialoghi.FINESTRA = None
                _stampa("Impossibile aprire la finestra dell'app "
                        f"({type(e).__name__}: {e}).",
                        "Stratigrafia 3D viene aperta nel browser predefinito.")
            else:
                srv.shutdown()
                return
    _avvia_nel_browser(srv, t, url, browser)
