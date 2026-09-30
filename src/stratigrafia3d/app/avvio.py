# -*- coding: utf-8 -*-
"""Avvio dell'app: server locale + finestra nativa (pywebview) o, in mancanza, il browser."""
import threading
import webbrowser

from .server import App, crea_server
from . import dialoghi


def avvia(progetto=None, finestra=True, porta=0, browser=True):
    app = App(progetto)
    srv = crea_server(app, porta)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    if finestra:
        try:
            import webview
        except ImportError:
            webview = None
        if webview is not None:
            w = webview.create_window("Stratigrafia 3D", url, width=1440, height=900, min_size=(900, 600),
                                      confirm_close=False)
            dialoghi.FINESTRA = w
            webview.start()          # ritorna quando la finestra viene chiusa
            srv.shutdown()
            return
    print(f"Stratigrafia 3D è in esecuzione su {url}")
    print("Chiudi questa finestra (o premi Ctrl+C) per terminare.")
    if browser:
        webbrowser.open(url)
    try:
        t.join()
    except KeyboardInterrupt:
        srv.shutdown()
