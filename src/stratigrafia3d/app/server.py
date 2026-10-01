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
from .. import modifiche as md
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
            from ..progetto import nome_crs
            d.update(nome=s.meta.get("nome", "scavo"), riepilogo=s.riepilogo(), crs=nome_crs(s.crs),
                     ha_modello=s.modello is not None,
                     n_us=len(s.schede_us()), n_usm=len(s.schede_usm()),
                     note=list(getattr(s, "note_importazione", []) or []),
                     rapporto=s.modello.rapporto if s.modello else [],
                     in_attesa=len(md.in_attesa(s)), riscrivibile=s.abbinamento is not None,
                     abbinamento=asdict(s.abbinamento) if s.abbinamento is not None else None)
        return d


def _parametri(s):
    P = s.parametri
    return dict(profondita_predefinita=P.profondita_predefinita, spessore_predefinito=P.spessore_predefinito,
                tipici_dal_sito=P.tipici_dal_sito, escluse=len(P.escluse))


def _problemi(s):
    return [dict(livello=p.livello, codice=p.codice, messaggio=p.messaggio, unita=list(p.unita)) for p in s.verifica()]


def _esamina(files):
    files, note_file = importa.espandi(files)
    layers, tabelle = importa.esamina(files)
    tab = {}
    for f, fogli in tabelle.items():
        tab[f] = {n: dict(colonne=[str(c) for c in df.columns], righe=len(df),
                          esempio=json.loads(df.head(5).to_json(orient="values", date_format="iso", default_handler=str)))
                  for n, df in fogli.items()}
    abb = importa.proponi(files)
    abb.note = note_file + abb.note
    return dict(files=files, layers=[asdict(l) for l in layers], tabelle=tab, raster=importa.esamina_raster(files),
                abbinamento=asdict(abb))


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
            return dict(problemi=_problemi(s), note=s.note_importazione, stato=st.descrizione(), parametri=_parametri(s))
        if nome == "verifica":
            self._serve_scavo()
            return dict(problemi=_problemi(st.scavo), parametri=_parametri(st.scavo), stato=st.descrizione())
        if nome == "modifica":
            # modifica di una scheda dal visualizzatore
            self._serve_scavo()
            with st.lock:
                try:
                    r = md.applica_modifica(st.scavo, a["unita"], a.get("campi") or {},
                                            aggiungi=[tuple(x) for x in a.get("aggiungi") or []],
                                            togli=[tuple(x) for x in a.get("togli") or []])
                except md.ErroreModifica as e:
                    raise Errore(str(e))
                if r["voci"]:
                    st.modificato = True
                u = int(a["unita"])
                nome_t, idc = md._tabella_di(st.scavo, u)
                tab = st.scavo.tabelle[nome_t]
                r["scheda"] = esporta._rec(tab[tab[idc].map(lambda v: esporta._json_val(v) == u)].iloc[0])
            return dict(r, stato=st.descrizione())
        if nome == "riscrivi":
            self._serve_scavo()
            with st.lock:
                try:
                    r = md.riscrivi(st.scavo)
                except md.ErroreModifica as e:
                    raise Errore(str(e))
                except PermissionError as e:
                    raise Errore(f"Impossibile scrivere {getattr(e, 'filename', '')}: il file è aperto in un altro "
                                 "programma (Excel?). Chiudilo e riprova")
                st.modificato = True
            saltate = [dict(unita=v.get("unita"), cosa=v.get("campo") or f"{v.get('rapporto')} {v.get('altra')}",
                            motivo=m) for v, m in r["saltate"]]
            return dict(scritte=r["scritte"], saltate=saltate, file=[os.path.basename(p) for p in r["file"]],
                        copie=r["copie"], stato=st.descrizione())
        if nome == "apri_file":
            # apre un documento (PDF, disegno) con il programma predefinito del sistema
            p = a.get("percorso") or ""
            if os.path.normcase(os.path.abspath(p)) not in self.file_documentazione():
                raise Errore("File non collegato al progetto")
            import subprocess
            import sys
            if sys.platform.startswith("win"):
                os.startfile(p)          # noqa: S606 - file scelto tra quelli del progetto
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
            return {}
        if nome == "sorgenti":
            self._serve_scavo()
            return dict(cambiate=md.sorgenti_cambiate(st.scavo) if st.scavo.abbinamento is not None else [])
        if nome == "ricarica":
            self._serve_scavo()
            with st.lock:
                try:
                    nuovo, rif, note = md.ricarica(st.scavo, scarta_modifiche=bool(a.get("scarta")))
                except md.ErroreModifica as e:
                    raise Errore(str(e))
                if rif:
                    ricostruisci(nuovo, unita=rif)
                st.scavo, st.modificato = nuovo, True
                st.versione_modello += 1
            return dict(note=note, ricostruite=len(rif), stato=st.descrizione())
        if nome == "correggi":
            # correzioni in blocco dal resoconto della verifica
            self._serve_scavo()
            with st.lock:
                P = st.scavo.parametri
                for k, v in (a.get("parametri") or {}).items():
                    if k in ("profondita_predefinita", "spessore_predefinito"):
                        v = float(str(v).replace(",", "."))
                        if not 0 < v < 20:
                            raise Errore("Indica un valore in metri maggiore di zero")
                        setattr(P, k, v)
                    elif k == "tipici_dal_sito":
                        P.tipici_dal_sito = bool(v)
                escl = set(P.escluse)
                escl |= {int(u) for u in a.get("escludi") or []}
                if a.get("includi") == "tutte":
                    escl = set()
                else:
                    escl -= {int(u) for u in a.get("includi") or []}
                P.escluse = sorted(escl)
                if a.get("superficie"):
                    st.scavo.imposta_superficie(a["superficie"])
                st.modificato = True
            return dict(problemi=_problemi(st.scavo), stato=st.descrizione(), parametri=_parametri(st.scavo))
        if nome == "ricostruisci":
            self._serve_scavo()
            with st.lock:
                if any(p["livello"] == "errore" for p in _problemi(st.scavo)) and not a.get("forza"):
                    raise Errore("La verifica ha trovato errori: correggili prima di ricostruire")
                t0 = time.time()
                parziale = [int(u) for u in a.get("unita") or []] or None
                if parziale and st.scavo.modello is None:
                    parziale = None
                ricostruisci(st.scavo, unita=parziale)
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
            from .. import elaborati as el
            tipo = a.get("tipo")
            est = {"glb": ".glb", "volumi": ".xlsx", "pianta_svg": ".svg", "pianta_dxf": ".dxf",
                   "sezioni_svg": ".svg", "sezioni_dxf": ".dxf"}.get(tipo, ".html")
            if not p.lower().endswith(est):
                p += est
            nota = ""
            try:
                if tipo == "glb":
                    esporta.glb(st.scavo, p, esploso=float(a.get("esploso") or 0))
                elif tipo == "volumi":
                    el.scrivi_tabella_volumi(st.scavo, p)
                elif tipo == "pianta_svg":
                    el.pianta_svg(st.scavo, p)
                elif tipo == "pianta_dxf":
                    el.pianta_dxf(st.scavo, p)
                elif tipo in ("sezioni_svg", "sezioni_dxf"):
                    sez = el.linee_sezione(st.scavo)
                    if not sez:
                        sez = el.sezioni_centrali(st.scavo)
                        nota = "nessuna traccia di sezione nel GIS: due sezioni centrali"
                    (el.sezioni_svg if tipo == "sezioni_svg" else el.sezioni_dxf)(st.scavo, sez, p)
                else:
                    esporta.visualizzatore(st.scavo, p, modo="offline")
            except PermissionError:
                raise Errore(f"Impossibile scrivere {os.path.basename(p)}: il file è aperto in un altro programma?")
            except ValueError as e:
                raise Errore(str(e))
            return dict(percorso=p, nota=nota)
        if nome == "valori":
            v, n = importa.valori_distinti(a["sorgente"], foglio=a.get("foglio"), colonna=a["colonna"],
                                           layer=a.get("layer"))
            prop = {}
            if a.get("proponi") == "tipo":
                prop = {x: importa._tipo_da_valore(x) for x, _ in v}
            elif a.get("proponi") == "rapporto":
                prop = {x: (importa._rapporto(x) if importa._rapporto(x) in importa.RAPPORTI_COLONNE else "")
                        for x, _ in v}
            return dict(valori=v, totale=n, proposte=prop)
        if nome == "ricette":
            return dict(ricette=importa.ricette_pronte())
        if nome == "ricetta_applica":
            abb = importa.Abbinamento.da_json(a["abbinamento"])
            if a.get("pronta"):
                ric = importa.carica_ricetta_pronta(a["pronta"])
            else:
                ric = importa.Abbinamento.carica_profilo(a["percorso"])
            nuovo, note = importa.applica_ricetta(abb, ric)
            nuovo.note = list(abb.note) + note
            return dict(abbinamento=asdict(nuovo), note=note)
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

    def file_documentazione(self):
        """I soli file che il server può mostrare: quelli citati nella documentazione del progetto."""
        s = self.stato.scavo
        t = None if s is None else s.tabelle.get("Documentazione")
        if t is None or "Percorso file" not in t.columns:
            return set()
        return {os.path.normcase(os.path.abspath(p)) for p in t["Percorso file"].dropna()}

    def media(self, p, larghezza=None):
        """(byte, tipo) di una foto o di un disegno della documentazione; ridotta se serve."""
        if not p or os.path.normcase(os.path.abspath(p)) not in self.file_documentazione() or not os.path.isfile(p):
            raise FileNotFoundError(p)
        ext = os.path.splitext(p)[1].lower()
        diretti = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
                   ".webp": "image/webp", ".svg": "image/svg+xml", ".pdf": "application/pdf"}
        if ext in (".tif", ".tiff", ".bmp") or (larghezza and ext in (".jpg", ".jpeg", ".png", ".webp")):
            try:
                from PIL import Image
                import io
                with Image.open(p) as im:
                    im.seek(0)
                    im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
                    if larghezza:
                        im.thumbnail((int(larghezza), int(larghezza) * 4))
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=85)
                    return buf.getvalue(), "image/jpeg"
            except Exception:
                if ext not in diretti:
                    raise FileNotFoundError(p)
        with open(p, "rb") as f:
            return f.read(), diretti.get(ext, "application/octet-stream")

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
                if path == "/media":
                    from urllib.parse import parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    corpo, tipo = app.media(q.get("p", [""])[0], (q.get("w") or [None])[0])
                    return self._invia(200, corpo, tipo)
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
