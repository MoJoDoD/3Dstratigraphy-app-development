# -*- coding: utf-8 -*-
"""
Server locale dell'app: serve l'interfaccia e un'API JSON al solo computer dell'utente
(127.0.0.1), protetta da un gettone casuale. Nessun dato esce dal PC.
"""
import json
import os
import secrets
import tempfile
import threading
import time
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import urlparse

from .. import __version__, esporta, importa
from ..progetto import Scavo
from ..ricostruzione import ricostruisci
from ..risorse import statico, css_font
from . import dialoghi

TIPI_MIME = {".js": "application/javascript", ".css": "text/css", ".woff2": "font/woff2",
             ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8"}
CARTELLA_CONFIG = os.path.join(os.path.expanduser("~"), ".stratigrafia3d")


def _recenti_path():
    return os.path.join(CARTELLA_CONFIG, "recenti.json")


def leggi_recenti():
    try:
        with open(_recenti_path(), encoding="utf-8") as f:
            return [p for p in json.load(f) if os.path.exists(p)][:10]
    except Exception:
        return []


def aggiungi_recente(p):
    try:
        os.makedirs(CARTELLA_CONFIG, exist_ok=True)
        r = [os.path.abspath(p)] + [x for x in leggi_recenti() if os.path.abspath(x) != os.path.abspath(p)]
        with open(_recenti_path(), "w", encoding="utf-8") as f:
            json.dump(r[:10], f, ensure_ascii=False)
    except Exception:
        pass


class Errore(Exception):
    """Errore da mostrare all'utente così com'è."""


class Stato:
    def __init__(self):
        self.lock = threading.RLock()
        self.scavo = None
        self.percorso = None
        self.modificato = False
        self.versione_modello = 0

    def descrizione(self):
        s = self.scavo
        d = dict(aperto=s is not None, percorso=self.percorso, modificato=self.modificato,
                 versione=__version__, versione_modello=self.versione_modello, recenti=leggi_recenti())
        if s is not None:
            d.update(nome=s.meta.get("nome", "scavo"), riepilogo=s.riepilogo(), crs=s.crs,
                     ha_modello=s.modello is not None,
                     n_us=len(s.schede_us()), n_usm=len(s.schede_usm()),
                     note=list(getattr(s, "note_importazione", []) or []),
                     rapporto=s.modello.rapporto if s.modello else [],
                     abbinamento=asdict(s.abbinamento) if s.abbinamento is not None else None)
        return d


def _problemi(s):
    return [dict(livello=p.livello, codice=p.codice, messaggio=p.messaggio, unita=list(p.unita)) for p in s.verifica()]


def _esamina(files):
    layers, tabelle = importa.esamina(files)
    tab = {}
    for f, fogli in tabelle.items():
        tab[f] = {n: dict(colonne=[str(c) for c in df.columns], righe=len(df),
                          esempio=json.loads(df.head(5).to_json(orient="values", date_format="iso", default_handler=str)))
                  for n, df in fogli.items()}
    abb = importa.proponi(files)
    return dict(layers=[asdict(l) for l in layers], tabelle=tab, abbinamento=asdict(abb))


class App:
    def __init__(self, progetto=None):
        self.stato = Stato()
        self.gettone = secrets.token_urlsafe(16)
        if progetto:
            self.apri(progetto)

    # ------------------------------------------------------------------ azioni
    def apri(self, percorso):
        if not percorso or not os.path.exists(percorso):
            raise Errore(f"File non trovato: {percorso}")
        with self.stato.lock:
            try:
                s = Scavo.apri(percorso)
            except Exception as e:
                raise Errore(f"Impossibile aprire il progetto: {e}")
            self.stato.scavo, self.stato.percorso, self.stato.modificato = s, percorso, False
            self.stato.versione_modello += 1
            aggiungi_recente(percorso)
        return self.stato.descrizione()

    def azione(self, nome, a):
        st = self.stato
        if nome == "stato":
            return st.descrizione()
        if nome == "dialogo":
            r = dialoghi.scegli(a.get("tipo", "apri"), a.get("filtri", ["dati"]), a.get("multiplo", False), a.get("nome"))
            return dict(percorsi=r, disponibile=r is not None)
        if nome == "esamina":
            files = [f for f in a.get("files", []) if f]
            mancanti = [f for f in files if not os.path.exists(f)]
            if mancanti:
                raise Errore("File non trovati: " + ", ".join(mancanti))
            if not files:
                raise Errore("Aggiungi almeno un file")
            return _esamina(files)
        if nome == "importa":
            if os.environ.get("S3D_DEBUG"):
                json.dump(a["abbinamento"], open(os.environ["S3D_DEBUG"], "w"), indent=1)
            abb = importa.Abbinamento.da_json(a["abbinamento"])
            with st.lock:
                s = importa.applica(abb)
                st.scavo, st.percorso, st.modificato = s, None, True
            return dict(problemi=_problemi(s), note=s.note_importazione, stato=st.descrizione())
        if nome == "verifica":
            self._serve_scavo()
            return dict(problemi=_problemi(st.scavo))
        if nome == "ricostruisci":
            self._serve_scavo()
            with st.lock:
                if any(p["livello"] == "errore" for p in _problemi(st.scavo)) and not a.get("forza"):
                    raise Errore("La verifica ha trovato errori: correggili prima di ricostruire")
                t0 = time.time()
                ricostruisci(st.scavo)
                st.modificato = True
                st.versione_modello += 1
            return dict(secondi=round(time.time() - t0, 1), stato=st.descrizione())
        if nome == "apri":
            return self.apri(a.get("percorso"))
        if nome == "salva":
            self._serve_scavo()
            p = a.get("percorso") or st.percorso
            if not p:
                raise Errore("Scegli dove salvare il progetto")
            if not p.lower().endswith(".scavo"):
                p += ".scavo"
            with st.lock:
                st.scavo.salva(p)
                st.percorso, st.modificato = p, False
            aggiungi_recente(p)
            return st.descrizione()
        if nome == "chiudi":
            with st.lock:
                st.scavo, st.percorso, st.modificato = None, None, False
            return st.descrizione()
        if nome == "esporta":
            self._serve_scavo()
            if st.scavo.modello is None:
                raise Errore("Prima ricostruisci il modello 3D")
            p = a.get("percorso")
            if not p:
                raise Errore("Scegli il file di destinazione")
            if a.get("tipo") == "glb":
                esporta.glb(st.scavo, p, esploso=float(a.get("esploso") or 0))
            else:
                esporta.visualizzatore(st.scavo, p, modo="offline")
            return dict(percorso=p)
        if nome == "profilo_salva":
            p = a.get("percorso")
            abb = importa.Abbinamento.da_json(a["abbinamento"])
            abb.salva_profilo(p)
            return dict(percorso=p)
        if nome == "profilo_carica":
            return dict(abbinamento=asdict(importa.Abbinamento.carica_profilo(a["percorso"])))
        if nome == "demo":
            from ..demo.genera import genera
            cartella = a.get("cartella") or os.path.join(tempfile.gettempdir(), "stratigrafia3d_demo")
            r = genera(cartella, anteprime_png=False, verbose=False)
            return dict(files=[r["gpkg"], r["xlsx"]], cartella=cartella)
        raise Errore(f"Azione sconosciuta: {nome}")

    def _serve_scavo(self):
        if self.stato.scavo is None:
            raise Errore("Nessun progetto aperto")

    # ------------------------------------------------------------------ pagine
    def pagina_app(self):
        html = resources.files("stratigrafia3d.app").joinpath("statici/app.html").read_text(encoding="utf-8")
        return (html.replace("/*__FONT__*/", css_font(inline=False))
                    .replace("__GETTONE__", self.gettone).replace("__VERSIONE__", __version__))

    def pagina_visualizzatore(self):
        with self.stato.lock:
            if self.stato.scavo is None or self.stato.scavo.modello is None:
                return "<!doctype html><meta charset='utf-8'><body style='font-family:sans-serif;color:#888'>Nessun modello</body>"
            return esporta.pagina_visualizzatore(self.stato.scavo, modo="app")


def crea_server(app, porta=0):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _invia(self, codice, corpo, tipo="application/json; charset=utf-8"):
            b = corpo if isinstance(corpo, bytes) else corpo.encode("utf-8")
            self.send_response(codice)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path in ("/", "/index.html"):
                    return self._invia(200, app.pagina_app(), TIPI_MIME[".html"])
                if path == "/visualizzatore":
                    return self._invia(200, app.pagina_visualizzatore(), TIPI_MIME[".html"])
                if path.startswith("/statici/"):
                    rel = path[len("/statici/"):]
                    ext = os.path.splitext(rel)[1]
                    return self._invia(200, statico(rel), TIPI_MIME.get(ext, "application/octet-stream"))
                self._invia(404, "non trovato", "text/plain")
            except FileNotFoundError:
                self._invia(404, "non trovato", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._invia(404, "{}")
            if self.headers.get("X-Gettone") != app.gettone:
                return self._invia(403, json.dumps(dict(ok=False, errore="Accesso non autorizzato")))
            n = int(self.headers.get("Content-Length") or 0)
            try:
                a = json.loads(self.rfile.read(n) or b"{}")
                r = app.azione(path[5:], a)
                self._invia(200, json.dumps(dict(ok=True, **(r or {})), ensure_ascii=False, default=str))
            except Errore as e:
                self._invia(200, json.dumps(dict(ok=False, errore=str(e)), ensure_ascii=False))
            except Exception as e:
                traceback.print_exc()
                self._invia(200, json.dumps(dict(ok=False, errore=f"Errore imprevisto: {e}"), ensure_ascii=False))

    return ThreadingHTTPServer(("127.0.0.1", porta), H)
