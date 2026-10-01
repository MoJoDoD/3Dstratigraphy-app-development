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


# ---------------------------------------------------------------------- cartelle e inventario
CATEGORIE_DATI = ("gis", "tabella", "raster", "modello3d")    # i file che vanno a importa.proponi
RUOLI_LAYER = {"us", "usm", "quote", "profili", "fondi", "area", "sezioni", "sezioni_disegno", "reperti", "campioni",
               "ignora"}


def _modulo_inventario():
    """Il modulo dell'inventario delle cartelle, se c'è (si importa solo quando serve)."""
    import importlib
    try:
        return importlib.import_module("stratigrafia3d.inventario")
    except ModuleNotFoundError as e:
        if e.name in ("stratigrafia3d.inventario", "stratigrafia3d"):
            return None
        raise


def _e_radice(p):
    """Una cartella o un archivio .zip: si inventaria prima di proporre come usarne i file."""
    return bool(p) and (os.path.isdir(p) or (p.lower().endswith(".zip") and os.path.isfile(p)))


def _json_sicuro(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def _snella(v, soglia=400):
    """Una voce dell'inventario senza i dettagli voluminosi (restano i valori brevi)."""
    if not isinstance(v, dict):
        return v
    v = dict(v)
    d = v.get("dettagli")
    if d is not None and len(json.dumps(d, ensure_ascii=False, default=str)) > soglia:
        v["dettagli"] = ({k: x for k, x in d.items() if isinstance(x, (int, float, bool, str)) and len(str(x)) <= 80}
                         if isinstance(d, dict) else None)
    if isinstance(v.get("parti"), list):
        v["parti"] = [_snella(x, soglia) for x in v["parti"][:200]]
    return v


def _file_cartelle_semplice(cartella, profondita_max=8, limite=20000):
    """Senza il modulo dell'inventario: i file di dati di una cartella, per estensione."""
    from ..superficie import EST_RASTER
    from ..modelli3d import EST_MODELLI
    utili = importa.EST_GIS | importa.EST_TAB | EST_RASTER | EST_MODELLI | {".csv", ".zip"}
    out = []
    base = os.path.abspath(cartella)
    for rad, cartelle, files in os.walk(base):
        if rad[len(base):].count(os.sep) >= profondita_max:
            cartelle[:] = []
        cartelle[:] = sorted(c for c in cartelle if not c.startswith((".", "_", "__MACOSX")))
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext not in utili or f.lower() == "thumbs.db":
                continue
            p = os.path.join(rad, f)
            if ext in (".db", ".sqlite", ".gpkg"):          # solo i veri database SQLite
                try:
                    with open(p, "rb") as fh:
                        if fh.read(16) != b"SQLite format 3\x00":
                            continue
                except OSError:
                    continue
            out.append(p)
        if len(out) >= limite:
            break
    return out[:limite]


def _categorie_dati(mod):
    return set(getattr(mod, "CATEGORIE_DATI", None) or CATEGORIE_DATI)


def _chiave(p):
    return os.path.normcase(os.path.abspath(str(p or "")))


def _scelte(usa=None, ruoli=None):
    """Le spunte e le destinazioni cambiate a mano nell'inventario, nella forma di importa:
    {percorso: {"usa": bool, "ruolo": str}}."""
    out = {}
    for p, u in (usa or {}).items():
        if p and u is not None:
            out.setdefault(p, {})["usa"] = bool(u)
    for p, r in (ruoli or {}).items():
        if p and r:
            out.setdefault(p, {})["ruolo"] = r
    return out


def _proponi(files, scelte=None, inventario=None):
    """importa.proponi con l'inventario della procedura guidata e le scelte fatte a mano (file tolti,
    destinazioni cambiate): le applica importa, così valgono anche da riga di comando e nelle ricette."""
    if inventario is not None and isinstance(getattr(importa, "_INVENTARI_ESPANSI", None), dict):
        # come per le cartelle aperte da importa.espandi: proponi ritrova l'inventario dai file proposti
        for f in files:
            importa._INVENTARI_ESPANSI[_chiave(f)] = inventario
    abb = importa.proponi(files, scelte=scelte or None)
    if inventario is not None and not getattr(abb, "inventario", None):
        abb.inventario = inventario
        if scelte:
            importa.applica_scelte_inventario(abb, scelte)
    return abb


def _esamina(files, dati=None, scelte=None, inventario=None):
    """``files``: come li ha scelti l'utente (anche cartelle); ``dati``: i file da leggere davvero
    (le cartelle sostituite dai file spuntati nell'inventario). Senza ``dati`` si usano ``files``.
    ``scelte``: le spunte e le destinazioni cambiate a mano nell'inventario."""
    dati = list(files if dati is None else dati)
    dati, note_file = importa.espandi(dati)
    layers, tabelle = importa.esamina(dati)
    tab = {}
    for f, fogli in tabelle.items():
        tab[f] = {n: dict(colonne=[str(c) for c in df.columns], righe=len(df),
                          esempio=json.loads(df.head(5).to_json(orient="values", date_format="iso", default_handler=str)))
                  for n, df in fogli.items()}
    abb = _proponi(dati, scelte, inventario)
    abb.note = note_file + abb.note
    d_abb = asdict(abb)
    if inventario is not None and "inventario" not in d_abb:
        d_abb["inventario"] = inventario
    return dict(files=dati, cartelle=[f for f in files if os.path.isdir(f)], layers=[asdict(l) for l in layers],
                tabelle=tab, raster=importa.esamina_raster(dati), abbinamento=_json_sicuro(d_abb))


class Attivita:
    """Battiti della pagina e richieste in corso: servono a chiudere il server quando la pagina non c'è più.

    Nel ripiego sul browser il processo non ha una finestra propria: la pagina invia un "battito" ogni
    pochi secondi (e ogni richiesta all'API vale come battito); finché una richiesta è in corso
    (es. una ricostruzione lunga) il server non viene mai chiuso.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.ultimo_battito = None      # time.monotonic() dell'ultimo battito, None se mai ricevuto
        self.in_corso = 0               # richieste HTTP in elaborazione

    def battito(self):
        with self._lock:
            self.ultimo_battito = time.monotonic()

    def inizio(self):
        with self._lock:
            self.in_corso += 1

    def fine(self, battito=False):
        with self._lock:
            self.in_corso = max(0, self.in_corso - 1)
            if battito:
                self.ultimo_battito = time.monotonic()

    def istantanea(self):
        """(ultimo_battito, richieste_in_corso), letti insieme."""
        with self._lock:
            return self.ultimo_battito, self.in_corso


class App:
    def __init__(self, progetto=None):
        self.stato = Stato()
        self.gettone = secrets.token_urlsafe(16)
        self.attivita = Attivita()
        self._inventari = {}            # radice -> (firma, inventario): gli inventari già fatti
        self._lock_inventari = threading.Lock()
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

    def _inventario_radice(self, mod, radice, forza=False):
        try:
            firma = (os.path.getmtime(radice), os.path.getsize(radice) if os.path.isfile(radice) else 0)
        except OSError:
            firma = None
        with self._lock_inventari:
            c = self._inventari.get(radice)
        if c and c[0] == firma and not forza:
            return c[1]
        # la lettura può essere lunga: si fa fuori da ogni blocco (il server risponde intanto alle altre richieste)
        inv = mod.esamina_cartella([radice])
        inv = dict(inv or {})
        voci = []
        for v in inv.get("voci") or []:
            v = dict(v)
            v["_radice"] = radice
            voci.append(v)
        inv["voci"] = voci
        with self._lock_inventari:
            if len(self._inventari) >= 16:
                self._inventari.pop(next(iter(self._inventari)))
            self._inventari[radice] = (firma, inv)
        return inv

    def inventario(self, percorsi, forza=False):
        """Inventario delle cartelle e degli archivi .zip tra ``percorsi`` (gli altri file si ignorano).
        Le voci portano ``_radice``: la cartella o lo zip da cui vengono, così come l'ha indicato l'utente."""
        radici = []
        for p in percorsi or []:
            if _e_radice(p) and p not in radici:
                radici.append(p)
        mod = _modulo_inventario()
        out = dict(disponibile=mod is not None, radici=radici, cartelle=[p for p in radici if os.path.isdir(p)],
                   voci=[], riepilogo={}, note=[], file_proposta=[])
        if mod is None or not radici:
            return out
        for r in radici:
            inv = self._inventario_radice(mod, r, forza)
            out["voci"] += inv["voci"]
            for k, n in (inv.get("riepilogo") or {}).items():
                out["riepilogo"][k] = out["riepilogo"].get(k, 0) + (n if isinstance(n, (int, float)) else 0)
            out["note"] += list(inv.get("note") or [])
            out["file_proposta"] += [f for f in inv.get("file_proposta") or [] if f not in out["file_proposta"]]
        return out

    def dati_da_esaminare(self, files, scelti=None, usa=None, ruoli=None):
        """(file da leggere, inventario per l'abbinamento): le cartelle sostituite dai file di dati spuntati.

        ``scelti``: i file di dati spuntati nell'inventario (None = la proposta dell'inventario);
        ``usa``: {percorso: bool} le spunte cambiate a mano; ``ruoli``: {percorso: ruolo} le destinazioni
        cambiate: restano nell'inventario («scelte») e le applica ``importa.proponi``. I file spuntati rimasti
        in un archivio si estraggono adesso."""
        cartelle = [f for f in files if os.path.isdir(f)]
        if scelti is None and (not cartelle or hasattr(importa, "inventaria")):
            # nessuna scelta nell'inventario: file, cartelle e zip passano così come sono (importa li apre)
            return list(files), None
        mod = _modulo_inventario()
        if mod is None:
            out = []
            for f in files:
                for x in (_file_cartelle_semplice(f) if os.path.isdir(f) else [f]):
                    if x not in out:
                        out.append(x)
            return out, None
        inv = self.inventario(files)
        voci = inv["voci"]
        if scelti is None:
            proposta = set(inv.get("file_proposta") or [])
            dati = _categorie_dati(mod)
            scelti = [v["percorso"] for v in voci if v.get("percorso") in proposta
                      or (v.get("usa") and v.get("categoria") in dati)]
        scelti = set(scelti)
        estrai = getattr(mod, "assicura_estratto", None)

        def sul_disco(v):
            """Il file della voce: se è rimasto nell'archivio (non estratto dall'inventario) lo si estrae ora."""
            if os.path.isfile(v["percorso"]):
                return v["percorso"]
            return estrai(v, voci) if callable(estrai) else None
        out = []
        for f in files:
            membri = [v for v in voci if v.get("_radice") == f]
            if f in inv["radici"] and (os.path.isdir(f) or membri):
                nuovi = [p for p in (sul_disco(v) for v in membri if v["percorso"] in scelti) if p]
            else:
                nuovi = [f]                             # un file, o un archivio che non si è potuto aprire
            out += [x for x in nuovi if x not in out]
        voci_abb = [_snella({k: x for k, x in v.items() if k != "_radice"}) for v in voci]
        inv_abb = dict(radici=inv["radici"], voci=voci_abb, riepilogo=inv["riepilogo"], note=inv["note"])
        scelte = _scelte(usa, ruoli)
        if scelte:
            inv_abb["scelte"] = scelte
        compatto = getattr(importa, "_inventario_compatto", None)      # la stessa forma delle cartelle aperte da importa
        return out, _json_sicuro(compatto(inv_abb) if callable(compatto) else inv_abb)

    def _esamina_richiesta(self, a):
        files = [f for f in a.get("files") or [] if f]
        mancanti = [f for f in files if not os.path.exists(f)]
        if mancanti:
            raise Errore("File non trovati: " + ", ".join(mancanti))
        if not files:
            raise Errore("Aggiungi almeno un file")
        ruoli = {k: v for k, v in (a.get("ruoli") or {}).items() if v}
        dati, inv = self.dati_da_esaminare(files, a.get("scelti"), a.get("usa"), ruoli)
        if not dati:
            raise Errore("Nessun file di dati scelto: spunta almeno una pianta, una tabella o un raster nell'inventario")
        return _esamina(files, dati, _scelte(a.get("usa"), ruoli), inv)

    def azione(self, nome, a):
        st = self.stato
        self.attivita.battito()          # ogni richiesta della pagina dimostra che è ancora aperta
        if nome == "battito":
            return {}
        if nome == "stato":
            return st.descrizione()
        if nome == "lingua":
            from ..lingue import imposta_lingua, lingua_corrente, LINGUE
            if a.get("lingua"):
                try:
                    imposta_lingua(a["lingua"])
                except ValueError as e:
                    raise Errore(str(e))
            return dict(lingua=lingua_corrente(), lingue=LINGUE)
        if nome == "dialogo":
            r = dialoghi.scegli(a.get("tipo", "apri"), a.get("filtri", ["dati"]), a.get("multiplo", False), a.get("nome"))
            return dict(percorsi=r, disponibile=r is not None)
        if nome == "inventario":
            # cosa c'è nelle cartelle (e negli zip): senza blocchi sullo stato, il server intanto risponde
            percorsi = [p for p in a.get("percorsi") or [] if p]
            mancanti = [p for p in percorsi if not os.path.exists(p)]
            if mancanti:
                raise Errore("File non trovati: " + ", ".join(mancanti))
            inv = self.inventario(percorsi, forza=bool(a.get("forza")))
            inv["voci"] = [_snella(v) for v in inv["voci"]]
            inv["categorie_dati"] = sorted(_categorie_dati(_modulo_inventario()))
            return _json_sicuro(inv)
        if nome == "esamina":
            return self._esamina_richiesta(a)
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
        if nome == "insegna":
            # «questo nome di layer / di colonna vuol dire…»: nel vocabolario dell'utente, poi nuova proposta
            try:
                concetto = importa.insegna(a.get("ambito"), a.get("termine"), a.get("valore"))
            except (KeyError, ValueError) as e:
                raise Errore(str(e))
            except OSError as e:
                raise Errore(f"Impossibile salvare il vocabolario: {e}")
            files = [f for f in a.get("files") or [] if f]
            return dict(self._esamina_richiesta(a) if files else {}, concetto=concetto)
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
        from ..lingue import inserisci, lingua_corrente
        html = resources.files("stratigrafia3d.app").joinpath("statici/app.html").read_text(encoding="utf-8")
        lingua = lingua_corrente()
        html = inserisci(html, lingua).replace('<html lang="it">', f'<html lang="{lingua}">', 1)
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
            app.attivita.inizio()
            try:
                self._get()
            finally:
                app.attivita.fine()

        def do_POST(self):
            app.attivita.inizio()
            autorizzato = False
            try:
                autorizzato = self._post()
            finally:
                # anche la fine di una richiesta lunga vale come battito (solo se autorizzata)
                app.attivita.fine(battito=autorizzato)

        def _get(self):
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

        def _post(self):
            """Gestisce la richiesta; ritorna True se il gettone era valido."""
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                self._invia(404, "{}")
                return False
            if self.headers.get("X-Gettone") != app.gettone:
                self._invia(403, json.dumps(dict(ok=False, errore="Accesso non autorizzato")))
                return False
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
            return True

    return ThreadingHTTPServer(("127.0.0.1", porta), H)
