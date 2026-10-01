# -*- coding: utf-8 -*-
"""
Inventario di un archivio di scavo: si indica una o più cartelle (o file, o archivi .zip) e il programma
elenca che cosa c'è e a che cosa serve, prima dell'importazione.

    inv = esamina_cartella(["/dati/scavo_2024"])
    inv["voci"]           # una voce per file (o gruppo di file: shapefile, raster con .tfw, OBJ con .mtl…)
    inv["riepilogo"]      # {"gis": 12, "tabella": 4, "immagine": 230, …}
    inv["file_proposta"]  # i file di dati da passare a importa.proponi

Ogni voce dice il ruolo riconosciuto (piante delle US, schede US, rapporti, quote, modello del terreno,
ortofoto, foto, disegni, relazione…), dove andrà nel progetto («destinazione»), quanto è sicuro il
riconoscimento («punteggio» da 0 a 1) e perché («motivo»). Gli archivi .zip (anche uno dentro l'altro)
si aprono nella stessa cartella di lavoro usata da ``importa.espandi`` (~/.stratigrafia3d/estratti), così
l'importazione ritrova i file già estratti. Dei file grandi si leggono solo l'intestazione e un campione;
il risultato di ogni file resta in memoria finché il file non cambia (percorso, data, dimensione).
"""
import copy
import csv
import hashlib
import io
import os
import re
import shutil
import time
import zipfile
from collections import Counter, defaultdict

try:
    from .documenti_auto import tipo_immagine as _tipo_immagine_auto
except Exception:            # modulo assente (o in modifica): si riconosce dal nome
    _tipo_immagine_auto = None

CATEGORIE = ("gis", "tabella", "raster", "modello3d", "immagine", "documento", "database", "archivio", "altro",
             "ignorato")
CATEGORIE_DATI = ("gis", "tabella", "raster", "modello3d")      # quelle che vanno a importa.proponi

EST_VETTORI = {".shp", ".gpkg", ".geojson", ".json", ".dxf", ".sqlite", ".db", ".gml", ".kml", ".kmz", ".fgb",
               ".tab", ".mif"}
EST_TABELLE = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls", ".ods"}
EST_RASTER = {".tif", ".tiff"}
EST_RASTER_ALTRI = {".asc", ".jp2", ".ecw", ".sid", ".img", ".vrt", ".dem", ".bil", ".adf"}
EST_MODELLI = {".obj", ".ply"}
EST_MODELLI_ALTRI = {".stl", ".glb", ".gltf", ".fbx", ".3ds", ".dae", ".las", ".laz", ".e57", ".pts", ".xyz", ".nxs",
                     ".nxz", ".3dm", ".blend", ".usdz"}
EST_IMMAGINI = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".cr2", ".nef", ".dng", ".arw",
                ".raw", ".jfif"}
EST_DOCUMENTI = {".pdf", ".doc", ".docx", ".rtf", ".odt", ".txt", ".md", ".html", ".htm", ".pptx", ".ppt", ".odp"}
EST_ACCESS = {".mdb", ".accdb"}
EST_ZIP = {".zip"}
EST_ALTRI_ARCHIVI = {".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}

# file accessori: si uniscono al file principale con lo stesso nome (prima i suffissi doppi)
SUFFISSI_ACCESSORI = sorted([
    ".shp.xml", ".aux.xml", ".tif.xml", ".tiff.xml", ".txt.xml", ".csv.xml", ".dbf.xml", ".shp.ini", ".tif.ini",
    ".tiff.ini", ".tif.aux", ".tif.ovr", ".tif.vat.dbf", ".vat.dbf", ".vat.cpg", ".shp.qix", ".shx", ".dbf", ".prj",
    ".cpg", ".qpj", ".sbn", ".sbx", ".qix", ".fix", ".atx", ".ain", ".aih", ".ixs", ".mxs", ".tfw", ".tifw",
    ".tiffw", ".wld", ".jgw", ".jpgw", ".pgw", ".pngw", ".aux", ".rrd", ".rmf", ".ovr", ".ini", ".xml", ".xsd",
    ".gfs", ".mtl", ".csvt", ".qmd", ".qml", ".sld", ".lyr", ".lyrx"], key=len, reverse=True)
_SOLO_SHP = {".dbf", ".shx", ".sbn", ".sbx", ".qix", ".fix", ".cpg", ".atx", ".ain", ".aih", ".ixs", ".mxs",
             ".shp.xml", ".shp.ini", ".shp.qix", ".qpj"}

FILE_INUTILI = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db", ".localized", "icon\r", ".directory",
                "zone.identifier"}
CARTELLE_INUTILI = {"__macosx", ".git", ".svn", ".hg", "__pycache__", ".trash", ".trashes", "$recycle.bin",
                    "system volume information", ".ipynb_checkpoints", ".spotlight-v100", ".fseventsd", ".idea",
                    ".vscode", "node_modules"}

# cartelle che contengono i layer di una figura della pubblicazione (Framework: Chapter1…Chapter12)
_FIGURA_RE = re.compile(r"^(chapter|chap|capitolo|cap|fig|figs|figure|figura|figures|figure_pubblicazione|tav|tavola|"
                        r"tavole|plate|plates|illustrazioni|illustrations|abbildung|abb|kapitel)[\s_.\-]*\d*[a-z]?$",
                        re.I)
_CURVE_RE = re.compile(r"contour|isoips|curve.?di.?livello|curve.?livello|hohenlin|höhenlin|courbes?.?de.?niveau",
                       re.I)

GRANDE_ZIP = 100 * 2 ** 20          # oltre: le immagini si elencano senza estrarle tutte
CAMPIONE_IMMAGINI = 3               # immagini estratte per cartella di un archivio grande (per riconoscerle)
MAX_DOC_ESTRATTO = 30 * 2 ** 20     # documenti più grandi restano nell'archivio
RIGHE_CAMPIONE = 200
MAX_RASTER_LETTO = 400 * 2 ** 20    # raster più grandi: valori non controllati
MAX_DXF_LETTO = 40 * 2 ** 20
MAX_TIPO_IMMAGINE = 600             # immagini analizzate una per una; le altre come le vicine
IMMAGINI_PER_CARTELLA = 25

RUOLI_LAYER = ("us", "usm", "quote", "profili", "fondi", "area", "sezioni", "sezioni_disegno", "reperti", "campioni")
DESTINAZIONE = {
    # layer
    "us": "Piante delle US", "usm": "Piante delle USM", "quote": "Quote", "profili": "Profili 3D",
    "fondi": "Linee di fondo", "area": "Limite di scavo", "sezioni": "Tracce delle sezioni",
    "sezioni_disegno": "Disegni delle sezioni", "reperti": "Reperti", "campioni": "Campioni",
    # tabelle
    "schede_us": "Schede US", "schede_usm": "Schede USM", "rapporti": "Rapporti stratigrafici",
    "materiali": "Materiali", "documentazione": "Documentazione (elenco)", "fasi": "Fasi",
    "gruppi": "Gruppi stratigrafici", "datazioni": "Datazioni",
    # raster
    "dem": "Superficie di riferimento", "differenza": "Correzione della superficie", "ortofoto": "Ortofoto",
    # immagini
    "foto": "Documentazione (foto)", "disegno": "Documentazione (disegni)", "scansione": "Documentazione (scansioni)",
    # documenti
    "relazione": "Documenti (relazione)", "elenco": "Documenti (elenco)", "metadati": "Documenti (metadati)",
    "licenza": "Licenza", "dizionario": "Dizionario dei dati",
}
NON_USATO = "Non usato"
_TAB_DA_CONCETTO = {"us": "schede_us", "usm": "schede_usm", "rapporti": "rapporti", "materiali": "materiali",
                    "reperti": "materiali", "campioni": "campioni", "documentazione": "documentazione",
                    "fase": "fasi", "periodo": "fasi", "datazione": "datazioni", "gruppo": "gruppi"}
_RELAZIONI = {"copre", "coperto da", "taglia", "tagliato da", "riempie", "riempito da", "si appoggia a",
              "gli si appoggia", "si lega a", "uguale a"}
_COL_RAPPORTO = {"rapporto", "rapporti", "relazione", "relationship", "relation", "relationship type", "rel type",
                 "tipo rapporto", "tipo di rapporto", "relazione stratigrafica", "rapporto stratigrafico",
                 "stratigraphic relationship", "beziehung", "relation type"}
_PREFISSI_SISTEMA = ("s3d_", "tab_", "layer_styles", "gpkg_", "rtree_", "sqlite_", "spatial_ref_sys",
                     "geometry_columns", "views_geometry", "virts_geometry", "spatialite_history", "sql_statements_log",
                     "idx_", "elementarygeometries", "spatialindex", "knn", "data_licenses", "vector_layers",
                     "iso_metadata", "geom_cols_ref_sys", "spatial_ref_sys_aux", "sqlitestudio_", "sql_statements")

_CACHE = {}                 # (percorso, mtime_ns, dimensione, accessori) -> risultato dell'analisi


# ============================================================================ utilità
def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower().replace("_", " "))


def _chiave_nome(nome):
    """Nome senza estensione e senza segni, per riconoscere gli stessi dati in formati diversi."""
    base = os.path.basename(str(nome))
    low = base.lower()
    for s in (".shp.xml", ".txt.xml"):
        if low.endswith(s):
            base = base[:-len(s)]
    return re.sub(r"[^0-9a-z]+", "", os.path.splitext(base)[0].lower())


def _estensione(nome):
    low = nome.lower()
    for s in SUFFISSI_ACCESSORI:
        if low.endswith(s) and len(low) > len(s) and s.count(".") > 1:
            return s
    return os.path.splitext(low)[1]


def _inutile(nome):
    low = nome.lower()
    return (low in FILE_INUTILI or low.startswith(("~$", "._", ".~lock")) or low.endswith(("~", ".tmp", ".bak", ".lck"))
            or (low.startswith(".") and low not in (".", "..")))


def cartella_estratti():
    """Cartella di lavoro dove si aprono gli archivi (la stessa di ``importa.espandi``)."""
    return os.path.join(os.path.expanduser("~"), ".stratigrafia3d", "estratti")


def _destinazione_zip(path, base=None):
    """Cartella in cui ``importa.espandi`` estrae l'archivio: stesso nome, così l'importazione riusa i file."""
    chiave = hashlib.sha1(f"{os.path.abspath(path)}|{os.path.getmtime(path)}".encode()).hexdigest()[:12]
    return os.path.join(base or cartella_estratti(), os.path.splitext(os.path.basename(path))[0] + "_" + chiave)


def _firma(path):
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None, None


def _importa():
    from . import importa
    return importa


def _voc():
    from . import vocabolario as V
    return V.vocabolario()


def _riconosci(nome, ambito, contesto=None, soglia=0.3):
    try:
        r = _voc().riconosci(nome, ambito, contesto, soglia=soglia, massimo=3)
    except Exception:
        return None
    return r[0] if r else None


# ============================================================================ raccolta dei file
class _Elemento:
    """Un file trovato (su disco o dentro un archivio)."""
    __slots__ = ("percorso", "origine", "relativo", "nome", "dimensione", "livello", "estratto", "cartella", "radice",
                 "contenitore", "archivio", "membro")

    def __init__(self, percorso, origine, relativo, dimensione, livello, estratto, cartella, radice, contenitore,
                 archivio=None, membro=None):
        self.percorso, self.origine, self.relativo = percorso, origine, relativo
        self.nome = os.path.basename(relativo)
        self.dimensione, self.livello, self.estratto = dimensione, livello, estratto
        self.cartella, self.radice, self.contenitore = cartella, radice, contenitore
        self.archivio, self.membro = archivio, membro      # file dentro uno zip: l'archivio e il nome nell'archivio


class _Raccolta:
    def __init__(self, profondita_max, limite_file):
        self.profondita_max, self.limite = profondita_max, limite_file
        self.elementi, self.voci_extra, self.note = [], [], []
        self.pieno = False
        self.n_cartelle = self.n_zip = 0

    def aggiungi(self, el):
        if len(self.elementi) >= self.limite:
            self.pieno = True
            return False
        self.elementi.append(el)
        return True

    # ------------------------------------------------------------------ cartelle
    def cartella(self, radice):
        self.n_cartelle += 1
        base_liv = radice.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(radice):
            liv = dirpath.rstrip(os.sep).count(os.sep) - base_liv
            tieni = []
            for d in sorted(dirnames):
                if d.lower() in CARTELLE_INUTILI:
                    p = os.path.join(dirpath, d)
                    self.voci_extra.append(_voce_inutile(p, None, _rel(p, radice), "cartella di sistema"))
                elif os.path.abspath(os.path.join(dirpath, d)) == os.path.abspath(cartella_estratti()):
                    continue
                elif liv + 1 > self.profondita_max:
                    self.note.append(f"Cartella «{_rel(os.path.join(dirpath, d), radice)}» oltre la profondità "
                                     f"massima ({self.profondita_max}): non esaminata")
                else:
                    tieni.append(d)
            dirnames[:] = tieni
            self.n_cartelle += len(tieni)
            for f in sorted(filenames):
                p = os.path.join(dirpath, f)
                if not os.path.isfile(p):
                    continue
                rel = _rel(p, radice)
                if os.path.splitext(f)[1].lower() in EST_ZIP:
                    self.zip(p, None, rel, liv, radice)
                    continue
                if not self.aggiungi(_Elemento(p, None, rel, os.path.getsize(p), liv, True, dirpath, radice, None)):
                    return

    # ------------------------------------------------------------------ archivi
    def zip(self, path, origine, relativo, livello, radice, profondita_zip=0, archivio=None, membro=None):
        """Apre un archivio: elenca il contenuto, estrae ciò che serve (dati, accessori, documenti, archivi
        interni; delle immagini di un archivio molto grande solo un campione) e scende negli archivi interni.
        ``archivio``/``membro``: per uno zip dentro un altro zip, quello che lo contiene e il nome lì dentro."""
        nome = os.path.basename(relativo)
        voce = dict(percorso=path, origine=origine, relativo=relativo, nome=nome, estensione=".zip",
                    dimensione=_dim(path), categoria="archivio", ruolo=None, destinazione="Aperto: contenuto elencato",
                    punteggio=1.0, motivo="archivio zip: il contenuto è elencato qui sotto", usa=False, dettagli={})
        if archivio:
            voce.update(archivio=archivio, membro=membro)
        if not self.aggiungi_voce(voce):
            return
        self.n_zip += 1
        try:
            z = zipfile.ZipFile(path)
            infos = z.infolist()
        except (zipfile.BadZipFile, OSError, NotImplementedError) as e:
            voce.update(categoria="altro", destinazione=NON_USATO, punteggio=0.9,
                        motivo="archivio zip illeggibile (download incompleto?)")
            self.note.append(f"«{nome}» non è un archivio zip valido (download incompleto?): {e}")
            return
        dest = _destinazione_zip(path)
        pref = origine or nome
        membri, macosx = [], 0
        for i in infos:
            n = i.filename.replace("\\", "/")
            if n.endswith("/"):
                continue
            parti = n.split("/")
            if any(p in ("..", "") for p in parti[:-1]) or n.startswith("/") or ":" in parti[0]:
                continue
            if any(p.lower() in CARTELLE_INUTILI for p in parti[:-1]):
                macosx += 1
                continue
            membri.append((n, i))
        if macosx:
            self.voci_extra.append(_voce_inutile(os.path.join(dest, "__MACOSX"), f"{pref}:__MACOSX", relativo +
                                                 "/__MACOSX", f"cartella di sistema ({macosx} file)"))
        immagini = [(n, i) for n, i in membri if os.path.splitext(n)[1].lower() in EST_IMMAGINI]
        con_modelli = {os.path.dirname(n) for n, _ in membri if os.path.splitext(n)[1].lower() in EST_MODELLI}
        tot_img = sum(i.file_size for _, i in immagini)
        grande = tot_img > GRANDE_ZIP or (_dim(path) > GRANDE_ZIP and len(immagini) > 50)
        campione = set()
        if grande:
            per_cartella = defaultdict(list)
            for n, i in sorted(immagini):
                per_cartella[os.path.dirname(n)].append(n)
            for d, nn in per_cartella.items():
                passo = max(1, len(nn) // CAMPIONE_IMMAGINI)
                campione |= set(nn[::passo][:CAMPIONE_IMMAGINI])
            self.note.append(f"«{nome}»: {len(immagini)} immagini ({tot_img / 2 ** 20:.0f} MB) elencate senza "
                             f"estrarle tutte (estratte {len(campione)} per riconoscerle)")
        estratti = 0
        voce["dettagli"] = dict(file=len(membri), cartella_estrazione=dest, immagini=len(immagini))
        for n, i in membri:
            ext = _estensione(os.path.basename(n))
            e1 = os.path.splitext(n)[1].lower()
            serve = (e1 in EST_VETTORI | EST_TABELLE | EST_RASTER | EST_MODELLI | EST_ZIP | EST_ACCESS
                     | EST_RASTER_ALTRI or ext in SUFFISSI_ACCESSORI or e1 in SUFFISSI_ACCESSORI)
            if e1 in EST_DOCUMENTI or "readme" in n.lower():
                serve = i.file_size <= MAX_DOC_ESTRATTO
            if e1 in EST_IMMAGINI:
                serve = not grande or n in campione or os.path.dirname(n) in con_modelli
            if _inutile(os.path.basename(n)):
                serve = False
            p = os.path.join(dest, *n.split("/"))
            if serve:
                try:
                    _estrai(z, i, p)
                    estratti += 1
                except Exception as e:          # membro danneggiato o cifrato
                    self.note.append(f"«{nome}»: impossibile estrarre «{n}» ({e})")
                    serve = False
            rel = relativo + "/" + n
            orig = f"{pref}:{n}"
            liv = livello + 1 + n.count("/")
            if e1 in EST_ZIP and serve:
                if profondita_zip >= 4:
                    self.note.append(f"«{n}»: troppi archivi uno dentro l'altro, non aperto")
                    continue
                self.zip(p, orig, rel, liv, radice, profondita_zip + 1, archivio=path, membro=i.filename)
                continue
            el = _Elemento(p, orig, rel, i.file_size, liv, serve, os.path.dirname(p), radice, pref, path, i.filename)
            if not self.aggiungi(el):
                break
        voce["dettagli"]["estratti"] = estratti

    def aggiungi_voce(self, voce):
        if len(self.elementi) + len(self.voci_extra) >= self.limite + 1000:
            self.pieno = True
            return False
        self.voci_extra.append(voce)
        return True


def _estrai(z, info, p):
    if os.path.exists(p) and os.path.getsize(p) == info.file_size:
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".parziale"
    with z.open(info) as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    os.replace(tmp, p)


def _rel(p, radice):
    r = os.path.relpath(p, radice)
    return r.replace(os.sep, "/")


def _dim(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return None


def _voce_inutile(percorso, origine, relativo, motivo):
    return dict(percorso=percorso, origine=origine, relativo=relativo, nome=os.path.basename(relativo),
                estensione=os.path.splitext(relativo)[1].lower(), dimensione=None, categoria="ignorato", ruolo=None,
                destinazione=NON_USATO, punteggio=1.0, motivo=motivo, usa=False, dettagli={})


# ============================================================================ raggruppamento
def _raggruppa(elementi):
    """Per cartella: file principali con i loro accessori (shapefile, raster con .tfw/.aux, OBJ con .mtl e
    texture, CSV con il .txt.xml di ArcGIS…). Ritorna [(principale, [accessori])] e i file inutili."""
    per_cartella = defaultdict(list)
    for el in elementi:
        per_cartella[el.cartella].append(el)
    gruppi, inutili = [], []
    for cart, els in per_cartella.items():
        principali, accessori = [], []
        for el in els:
            if _inutile(el.nome):
                inutili.append(el)
                continue
            low = el.nome.lower()
            suf = next((s for s in SUFFISSI_ACCESSORI if low.endswith(s) and len(low) > len(s)), None)
            (accessori if suf else principali).append((el, suf))
        per_stem = defaultdict(list)
        for el, _ in principali:
            low = el.nome.lower()
            per_stem[os.path.splitext(low)[0]].append(el)
            per_stem[low].append(el)
        acc = defaultdict(list)
        orfani = []
        for el, suf in accessori:
            low = el.nome.lower()
            chiavi = [low[:-len(s)] for s in SUFFISSI_ACCESSORI if low.endswith(s) and len(low) > len(s)]
            princ = None
            for k in chiavi:
                cand = per_stem.get(k, [])
                if suf in _SOLO_SHP or os.path.splitext(low)[1] == ".dbf":
                    cand = [c for c in cand if c.nome.lower().endswith(".shp")]
                if suf == ".mtl":
                    cand = [c for c in cand if os.path.splitext(c.nome)[1].lower() in EST_MODELLI]
                if cand:
                    princ = sorted(cand, key=lambda c: _priorita_principale(c.nome))[0]
                    break
            if princ is None:
                orfani.append(el)
            else:
                acc[id(princ)].append(el)
        # texture dei modelli 3D: le immagini nominate nel .mtl (o con lo stesso nome del modello)
        modelli = [el for el, _ in principali if os.path.splitext(el.nome)[1].lower() in EST_MODELLI]
        texture = set()
        for m in modelli:
            nomi = _texture_nominate(m, acc[id(m)])
            stem = os.path.splitext(m.nome)[0].lower()
            for el, _ in principali:
                ext = os.path.splitext(el.nome)[1].lower()
                if ext in EST_IMMAGINI | {".tif", ".tiff"} and (el.nome.lower() in nomi or
                                                                 os.path.splitext(el.nome)[0].lower() == stem):
                    acc[id(m)].append(el)
                    texture.add(id(el))
        for el, _ in principali:
            if id(el) not in texture:
                gruppi.append((el, acc[id(el)]))
        for el in orfani:
            gruppi.append((el, []))
    return gruppi, inutili


def _priorita_principale(nome):
    ext = os.path.splitext(nome)[1].lower()
    return {".shp": 0, ".tif": 1, ".tiff": 1, ".obj": 2, ".ply": 2}.get(ext, 5)


def _texture_nominate(modello, accessori):
    nomi = set()
    for a in accessori:
        if a.nome.lower().endswith(".mtl") and a.estratto:
            try:
                with open(a.percorso, encoding="utf-8", errors="replace") as f:
                    for riga in f:
                        r = riga.strip()
                        if r.lower().startswith("map_"):
                            nomi.add(os.path.basename(r.split()[-1].replace("\\", "/")).lower())
            except OSError:
                pass
    return nomi


# ============================================================================ analisi dei file
def _risultato(categoria, ruolo=None, punteggio=0.0, motivo="", usa=None, destinazione=None, dettagli=None, parti=None):
    if usa is None:
        usa = categoria not in ("altro", "ignorato", "database", "archivio") and (
            ruolo is not None or categoria in ("documento",))
    if destinazione is None:
        destinazione = DESTINAZIONE.get(ruolo, NON_USATO) if (usa or ruolo) else NON_USATO
        if categoria == "modello3d":
            destinazione = "Modelli 3D"
        if categoria == "documento" and ruolo is None:
            destinazione = "Documenti"
    r = dict(categoria=categoria, ruolo=ruolo, punteggio=round(float(punteggio), 2), motivo=motivo, usa=bool(usa),
             destinazione=destinazione, dettagli=dettagli or {})
    if parti is not None:
        r["parti"] = parti
    return r


def _analizza(el, accessori):
    """Classifica un file principale (con i suoi accessori). Il risultato si ricorda finché il file non cambia."""
    mt, dim = _firma(el.percorso) if el.estratto else (None, el.dimensione)
    chiave = (el.percorso, mt, dim, tuple(sorted(a.nome.lower() for a in accessori)))
    if el.estratto and chiave in _CACHE:
        return _CACHE[chiave]
    try:
        r = _analizza_file(el, accessori)
    except Exception as e:           # un file strano non deve fermare l'inventario
        r = _risultato("altro", None, 0.2, f"file non leggibile ({type(e).__name__}: {e})", usa=False)
    if el.estratto:
        if len(_CACHE) > 50000:
            _CACHE.clear()
        _CACHE[chiave] = r
    return r


def _analizza_file(el, accessori):
    low = el.nome.lower()
    ext = os.path.splitext(low)[1]
    est_acc = {_estensione(a.nome) for a in accessori} | {os.path.splitext(a.nome.lower())[1] for a in accessori}
    if not el.estratto and ext not in EST_IMMAGINI | EST_DOCUMENTI:
        return _risultato("altro", None, 0.3, "nell'archivio, non estratto", usa=False)
    if ext == ".shp":
        if ".dbf" not in est_acc and ".shx" not in est_acc:
            return _risultato("gis", None, 0.3, "shapefile incompleto: mancano .dbf e .shx", usa=False)
        return _analizza_vettore(el, accessori)
    if ext in (".gpkg", ".sqlite", ".db"):
        return _analizza_contenitore(el)
    if ext in (".geojson", ".gml", ".kml", ".fgb", ".tab", ".mif"):
        return _analizza_vettore(el, accessori)
    if ext == ".json":
        testa = _testa(el.percorso, 4096)
        if re.search(r'"type"\s*:\s*"(Feature|FeatureCollection)"', testa):
            return _analizza_vettore(el, accessori)
        return _risultato("altro", None, 0.4, "file JSON senza geometrie", usa=False)
    if ext == ".kmz":
        return _risultato("gis", None, 0.4, "KMZ: aprilo in QGIS ed esporta in GeoPackage", usa=False)
    if ext == ".dxf":
        return _analizza_dxf(el)
    if ext == ".dwg":
        return _risultato("gis", None, 0.5, "disegno DWG: esportalo in DXF per importarlo", usa=False)
    if ext == ".dbf":
        return _analizza_dbf(el)
    if ext in (".csv", ".tsv"):
        return _analizza_csv(el)
    if ext in (".xlsx", ".xlsm", ".xls", ".ods"):
        return _analizza_excel(el)
    if ext in EST_RASTER:
        return _analizza_tif(el, accessori)
    if ext in EST_RASTER_ALTRI:
        return _risultato("raster", "dem", 0.4, f"raster in formato {ext}: esportalo in GeoTIFF per usarlo",
                          usa=False)
    if ext in EST_MODELLI:
        n_tex = sum(1 for a in accessori if os.path.splitext(a.nome)[1].lower() in EST_IMMAGINI | EST_RASTER)
        mtl = any(a.nome.lower().endswith(".mtl") for a in accessori)
        motivo = "modello 3D" + (" con materiale (.mtl)" if mtl else "") + (f" e {n_tex} texture" if n_tex else "")
        return _risultato("modello3d", "modello3d", 0.95, motivo, usa=True,
                          dettagli=dict(texture=n_tex, mtl=mtl))
    if ext in EST_MODELLI_ALTRI:
        return _risultato("modello3d", None, 0.6, f"modello 3D in formato {ext}: esportalo in OBJ o PLY per "
                          "mostrarlo nel progetto", usa=False, destinazione=NON_USATO)
    if ext in EST_IMMAGINI:
        return _analizza_immagine(el, accessori)
    if ext in EST_ACCESS:
        return _risultato("database", None, 0.9, "database Access: esporta le tabelle in CSV (in Access: Dati "
                          "esterni → Esporta → File di testo) e aggiungi i CSV", usa=False,
                          destinazione="Da esportare in CSV")
    if ext in EST_ALTRI_ARCHIVI:
        return _risultato("archivio", None, 0.8, f"archivio {ext}: estrailo per esaminarne il contenuto", usa=False)
    if ext == ".txt" and not re.search(r"read.?me|leggimi|licen|copyright", low):
        t = _analizza_txt_tabella(el)
        if t is not None:
            return t
    if ext in EST_DOCUMENTI or re.match(r"^(read.?me|leggimi|licen[cs]e|copying|authors|citation)", low):
        return _analizza_documento(el)
    if ext == ".xml":
        testa = _testa(el.percorso, 2048)
        if re.search(r"<(gml:|ogr:FeatureCollection|wfs:FeatureCollection)", testa):
            return _analizza_vettore(el, accessori)
        return _risultato("documento", "metadati", 0.6, "file XML (metadati)", usa=True)
    if ext == ".ini" and low == "schema.ini":
        return _risultato("documento", "metadati", 0.7, "schema.ini: descrive le colonne dei file di testo", usa=True)
    if ext in (".qgz", ".qgs", ".mxd", ".aprx"):
        return _risultato("altro", None, 0.7, "progetto GIS: si importano i layer, non il progetto", usa=False)
    if ext in SUFFISSI_ACCESSORI or _estensione(low) in SUFFISSI_ACCESSORI:
        return _risultato("altro", None, 0.6, "file accessorio senza il file principale", usa=False)
    return _risultato("altro", None, 0.3, f"formato non riconosciuto ({ext or 'senza estensione'})", usa=False)


def _testa(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n).decode("utf-8", errors="replace")
    except OSError:
        return ""


# ------------------------------------------------------------------ vettori
def _geometria(tipo):
    if tipo is None:
        return "nessuna"
    t = str(tipo)
    if "Polygon" in t:
        return "poligono"
    if "Line" in t or "Curve" in t:
        return "linea"
    if "Point" in t:
        return "punto"
    return "misto"


def _campo_unita(campi):
    I = _importa()
    for c in campi:
        n = _norm(c)
        if n in I._ALIAS_ID_US or n in I._ALIAS_ID_USM:
            return c
    for c in campi:
        r = _riconosci(c, "colonna", None, 0.75)
        if r is not None and r.concetto in ("us", "usm"):
            return c
    return None


def _campo_quota(campi):
    I = _importa()
    for c in campi:
        if _norm(c) in I.ALIAS_QUOTA:
            return c
    for c in campi:
        r = _riconosci(c, "colonna", None, 0.75)
        if r is not None and r.concetto == "quote":
            return c
    return None


def ruolo_layer(nome, geometria, ha_z=False, campi=()):
    """(ruolo, punteggio, motivo) di un layer dal nome (vocabolario e parole del programma), dalla
    geometria e dai campi, con le stesse regole di ``importa.proponi``. ``ruolo`` None: non serve."""
    I = _importa()
    campi = list(campi or ())
    if _CURVE_RE.search(str(nome)):
        return None, 0.75, "curve di livello: la superficie si ricava dal modello del terreno"
    try:
        ruolo, parola, motivo_voc = I._ruolo_proposto(nome, geometria)
    except Exception:
        ruolo, parola, motivo_voc = None, None, None
    p = 0.9 if motivo_voc else (0.7 if parola else 0.0)
    motivo = motivo_voc or (f"il nome contiene «{parola}»" if parola else "")
    if ruolo == "ignora":
        return None, max(p, 0.6), (motivo + ": " if motivo else "") + "layer di servizio (griglia, tratteggi…)"
    cu = _campo_unita(campi) if geometria in ("poligono", "punto", "linea") else None
    if geometria == "poligono":
        if ruolo not in ("us", "usm", "area", "sezioni_disegno"):
            ruolo, p = "us", 0.45 if cu else 0.35
            motivo = "poligoni senza un nome riconoscibile: forse piante di US"
    elif geometria == "punto":
        if ruolo not in ("quote", "reperti", "campioni"):
            cq = _campo_quota(campi)
            if ha_z or cq:
                ruolo, p = "quote", 0.55
                motivo = "punti con quota" + (f" (campo «{cq}»)" if cq and not ha_z else " (3D)")
            else:
                return None, 0.5, "punti senza quota"
    elif geometria == "linea":
        if ruolo not in ("profili", "sezioni", "fondi"):
            ruolo, p = ("profili", 0.5) if ha_z else ("sezioni", 0.35)
            motivo = "linee 3D" if ha_z else "linee 2D: forse tracce di sezione"
    elif geometria == "testo":
        return None, 0.5, "testi (usabili come etichette)"
    else:
        return None, 0.3, "geometrie miste"
    if cu and ruolo in ("us", "usm", "quote", "profili", "reperti", "campioni", "sezioni_disegno"):
        motivo += f"; numero di US dal campo «{cu}»"
        p = min(1.0, p + 0.1)
    return ruolo, p, motivo


def _info_layer(path, layer=None):
    import pyogrio
    info = pyogrio.read_info(path, layer=layer)
    tipo = info.get("geometry_type")
    campi = [str(c) for c in info.get("fields", [])]
    return dict(geometria=_geometria(tipo), tipo_geometria=tipo, n=int(info.get("features") or 0),
                ha_z=bool(tipo and (" Z" in str(tipo) or "25D" in str(tipo))), campi=campi, crs=info.get("crs"))


def _analizza_vettore(el, accessori):
    import pyogrio
    nome_l = os.path.splitext(el.nome)[0]
    layers = pyogrio.list_layers(el.percorso)
    if len(layers) > 1:
        return _analizza_contenitore(el, layers)
    d = _info_layer(el.percorso, layers[0][0] if len(layers) else None)
    ruolo, p, motivo = ruolo_layer(nome_l, d["geometria"], d["ha_z"], d["campi"])
    det = dict(d, campi=d["campi"][:40], accessori=[a.nome for a in accessori], campo_unita=_campo_unita(d["campi"]))
    descr = f"{d['n']} elementi, {d['geometria']}" + (" 3D" if d["ha_z"] else "")
    if ".prj" not in {os.path.splitext(a.nome.lower())[1] for a in accessori} and el.nome.lower().endswith(".shp"):
        descr += ", senza .prj (sistema di riferimento ignoto)"
    if d["n"] == 0:
        return _risultato("gis", None, 0.6, f"layer vuoto ({descr})", usa=False, dettagli=det)
    return _risultato("gis", ruolo, p, f"{motivo} ({descr})" if motivo else descr, dettagli=det)


def _parte(el, nome, risultato):
    return dict(percorso=el.percorso, origine=el.origine, relativo=f"{el.relativo} › {nome}", nome=nome,
                estensione=os.path.splitext(el.nome)[1].lower(), dimensione=None, **risultato)


def _analizza_contenitore(el, layers=None):
    """GeoPackage / SpatiaLite / SQLite: una parte per layer (geometria, numero, ruolo) e per tabella."""
    import pyogrio
    ext = os.path.splitext(el.nome)[1].lower()
    if ext in (".sqlite", ".db", ".gpkg"):
        if not _testa(el.percorso, 16).startswith("SQLite format 3"):
            return _risultato("altro", None, 0.4, "non è un database SQLite", usa=False)
    if layers is None:
        try:
            layers = pyogrio.list_layers(el.percorso)
        except Exception:
            layers = []
    parti, nomi_spaziali = [], set()
    for nome, tipo in layers:
        nome = str(nome)
        if nome.lower().startswith(_PREFISSI_SISTEMA):
            continue
        if tipo is None:
            continue
        nomi_spaziali.add(nome.lower())
        try:
            d = _info_layer(el.percorso, nome)
        except Exception as e:
            parti.append(_parte(el, nome, _risultato("gis", None, 0.2, f"layer illeggibile ({e})", usa=False)))
            continue
        ruolo, p, motivo = ruolo_layer(nome, d["geometria"], d["ha_z"], d["campi"])
        descr = f"{d['n']} elementi, {d['geometria']}" + (" 3D" if d["ha_z"] else "")
        det = dict(d, campi=d["campi"][:40], layer=nome, campo_unita=_campo_unita(d["campi"]))
        if d["n"] == 0:
            parti.append(_parte(el, nome, _risultato("gis", None, 0.6, f"layer vuoto ({descr})", usa=False,
                                                     dettagli=det)))
        else:
            parti.append(_parte(el, nome, _risultato("gis", ruolo, p, f"{motivo} ({descr})" if motivo else descr,
                                                     dettagli=det)))
    for nome, df, n in (_tabelle_senza_geometria(el.percorso, ext, nomi_spaziali)
                        if ext in (".gpkg", ".sqlite", ".db") else []):
        r = _analizza_df(nome, df, n)
        r["dettagli"]["tabella"] = nome
        parti.append(_parte(el, nome, r))
    return _riassumi_parti(el, parti, "database")


def _tabelle_senza_geometria(path, ext, spaziali):
    """(nome, campione, righe) delle tabelle senza geometria (senza leggerle tutte)."""
    import sqlite3
    import pandas as pd
    out = []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    try:
        con.text_factory = lambda b: b.decode("utf-8", errors="replace")
        nomi = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")]
        try:
            spaziali = spaziali | {str(r[0]).lower() for r in con.execute("SELECT f_table_name FROM geometry_columns")}
        except sqlite3.Error:
            pass
        try:
            spaziali = spaziali | {str(r[0]).lower() for r in con.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type != 'attributes'")}
        except sqlite3.Error:
            pass
        for n in nomi:
            if n.lower() in spaziali or n.lower().startswith(_PREFISSI_SISTEMA):
                continue
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{n}" LIMIT {RIGHE_CAMPIONE}', con)
                tot = con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
            except Exception:
                continue
            df = _importa()._senza_bytes(df)
            out.append((n, df, int(tot)))
    finally:
        con.close()
    return out


def _riassumi_parti(el, parti, cosa):
    """Voce di un file con più layer o fogli: categoria e ruolo della parte più importante."""
    usate = [p for p in parti if p["usa"]]
    if not parti:
        return _risultato("altro", None, 0.4, "nessun layer né tabella", usa=False, parti=[])
    ordine = ["us", "schede_us", "usm", "schede_usm", "rapporti", "quote", "profili", "area", "sezioni",
              "sezioni_disegno", "fondi", "reperti", "campioni", "materiali", "fasi", "documentazione", "gruppi",
              "datazioni"]
    princ = min(usate, key=lambda p: ordine.index(p["ruolo"]) if p["ruolo"] in ordine else 99) if usate else None
    gis = any(p["categoria"] == "gis" for p in parti)
    categoria = "gis" if gis else "tabella"
    n_l = sum(1 for p in parti if p["categoria"] == "gis")
    n_t = len(parti) - n_l
    pezzi = []
    if n_l:
        pezzi.append(f"{n_l} layer")
    if n_t:
        pezzi.append(f"{n_t} {'tabelle' if n_t > 1 else 'tabella'}" if cosa == "database" else
                     f"{n_t} {'fogli' if n_t > 1 else 'foglio'}")
    dest = list(dict.fromkeys(p["destinazione"] for p in usate))
    ruoli = ", ".join(dict.fromkeys(DESTINAZIONE.get(p["ruolo"], p["ruolo"]) for p in usate if p["ruolo"]))
    motivo = " e ".join(pezzi) + (f": {ruoli}" if ruoli else ": nessuno riconosciuto")
    return _risultato(categoria, princ["ruolo"] if princ else None, max((p["punteggio"] for p in usate), default=0.3),
                      motivo, usa=bool(usate), destinazione=", ".join(dest) if dest else NON_USATO,
                      dettagli=dict(layer=n_l, tabelle=n_t), parti=parti)


def _analizza_dxf(el):
    I = _importa()
    if (el.dimensione or 0) > MAX_DXF_LETTO:
        return _risultato("gis", None, 0.5, "disegno CAD molto grande: i layer si esaminano all'importazione",
                          usa=True, destinazione="Piante e quote (da verificare)")
    df = I._dxf_gruppi(el.percorso)
    parti = []
    for k, sub in df.groupby("_chiave"):
        tipo = sub["_tipo"].iloc[0]
        ha_z = False
        try:
            ha_z = bool(sub.geometry.has_z.any())
        except Exception:
            pass
        ruolo, p, motivo = ruolo_layer(k, tipo, ha_z, [])
        if tipo == "testo":
            vals = sub["Text"].map(I._numero).dropna()
            if len(vals) >= 0.8 * len(sub) and len(vals) and (vals % 1 != 0).mean() > 0.5:
                ruolo, p, motivo = "quote", 0.6, "testi con valori di quota"
        parti.append(_parte(el, k, _risultato("gis", ruolo, p, f"{motivo} ({len(sub)} entità)",
                                              dettagli=dict(geometria=tipo, n=int(len(sub)), layer=k))))
    return _riassumi_parti(el, parti, "database")


# ------------------------------------------------------------------ tabelle
def _ruolo_tabella(nome, df):
    """(ruolo, punteggio, motivo, dettagli) di una tabella dal nome e dalle colonne."""
    I = _importa()
    cols = [str(c) for c in df.columns]
    punti, perche = defaultdict(float), {}
    r = _riconosci(nome, "tabella", None, 0.5)
    if r is not None and r.concetto in _TAB_DA_CONCETTO:
        k = _TAB_DA_CONCETTO[r.concetto]
        punti[k] += 0.6 * r.punteggio
        perche[k] = r.motivo
    concetti = {}
    for c in cols[:80]:
        n = _norm(c)
        if n in I._ALIAS_ID_US:
            concetti[c] = "us"
        elif n in I._ALIAS_ID_USM:
            concetti[c] = "usm"
        elif n in _COL_RAPPORTO:
            concetti[c] = "rapporti"
        else:
            rc = _riconosci(c, "colonna", {"tabella": nome, "colonne": cols}, 0.75)
            if rc is not None:
                concetti[c] = rc.concetto
            elif re.match(r"^(us|usm|context|su|unit[aà])\b", n):
                concetti[c] = "us_rif"
    conta = Counter(concetti.values())
    us_cols = [c for c, k in concetti.items() if k == "us"]
    usm_cols = [c for c, k in concetti.items() if k == "usm"]
    rel = sum(conta[k] for k in _RELAZIONI)

    def unicita(c):
        v = df[c].dropna().tolist()
        return len(set(map(str, v))) / len(v) if v else 0.0

    def motivo_col(k, testo):
        perche.setdefault(k, testo)

    col_rap = next((c for c, k in concetti.items() if k == "rapporti"), None)
    if col_rap is not None and (us_cols or conta["us_rif"]):
        v = df[col_rap].dropna().astype(str).head(60)
        noti = [I._rapporto(x) for x in v]
        frac = sum(1 for x in noti if x in I._RAPP_SET) / len(v) if len(v) else 0.0
        if frac >= 0.5:
            punti["rapporti"] += 0.5 + (0.1 if len(us_cols) + conta["us_rif"] >= 2 else 0)
            motivo_col("rapporti", f"colonne con le unità e il tipo di rapporto («{col_rap}»)")
        elif frac == 0 and len(v):
            perche.setdefault("_nota", f"la colonna «{col_rap}» non contiene nomi di rapporti")
    if us_cols:
        u = unicita(us_cols[0])
        if u >= 0.9 and len(cols) >= 4:
            punti["schede_us"] += 0.35 + (0.1 if rel >= 2 else 0) + min(len(cols), 30) / 300
            motivo_col("schede_us", f"una riga per unità (colonna «{us_cols[0]}»)" +
                       (f" e {rel} colonne di rapporti" if rel >= 2 else ""))
        elif u < 0.9:
            punti["schede_us"] -= 0.3          # il numero di US si ripete: materiali, foto, campioni…
    if usm_cols and unicita(usm_cols[0]) >= 0.9 and len(cols) >= 3:
        punti["schede_usm"] += 0.4
        motivo_col("schede_usm", f"una riga per USM (colonna «{usm_cols[0]}»)")
    mat = sum(conta[k] for k in ("classe", "conteggio", "peso", "nmi", "cassetta", "forma"))
    if mat >= 2:
        punti["materiali"] += 0.25 + 0.1 * min(mat, 4)
        motivo_col("materiali", "colonne di classe, quantità o peso dei reperti")
    if conta["campioni"] or conta["analisi"]:
        punti["campioni"] += 0.3 + (0.15 if conta["analisi"] else 0)
        motivo_col("campioni", "colonne dei campioni")
    if conta["file"] or conta["soggetto"]:
        punti["documentazione"] += 0.4
        motivo_col("documentazione", "colonne di file o soggetto (foto, disegni)")
    if (conta["fase"] or conta["periodo"]) and (conta["datazione_da"] or conta["datazione_a"] or conta["titolo"]):
        punti["fasi"] += 0.35 if not us_cols else 0.1
        motivo_col("fasi", "colonne di fase o periodo con le date")
    if conta["gruppo"] and not us_cols:
        punti["gruppi"] += 0.25
        motivo_col("gruppi", "colonna dei gruppi stratigrafici")
    if punti.get("schede_us", 0) > 0 and not us_cols:
        punti["schede_us"] -= 0.25                 # «ContextSections», «ContextPlans»: il nome non basta
    det = dict(colonne=cols[:60], colonne_riconosciute={c: k for c, k in concetti.items() if k != "us_rif"})
    if not punti or max(punti.values()) < 0.3:
        return None, 0.3, "tabella non riconosciuta (nome e colonne)", det
    k = max(punti, key=punti.get)
    return k, min(1.0, punti[k] + 0.2), perche.get(k, ""), det


def _dizionario(nome, df):
    """Vero se la tabella descrive altre tabelle, campi o file (dizionario dei dati)."""
    cols = [_norm(c) for c in df.columns]
    descr = [c for c, n in zip(df.columns, cols) if re.search(r"descr|purpose|significato|definition|definizione|"
                                                              r"beschreibung|meaning|comment", n)]
    nomi = [n for n in cols if re.search(r"\b(table|tabella|tabelle|field|fields|campo|campi|column|colonna|file|"
                                         r"layer|attribut|attribute|variable|variabile|feld)", n)]
    if not descr or not nomi:
        return False
    v = df[descr[0]].dropna().astype(str)
    lunghi = len(v) and v.str.len().mean() > 25
    nome_ok = re.search(r"descr|dictionar|dizionar|field|campi|metadat|schema|legend|codebook|format", _norm(nome))
    return bool(lunghi and (nome_ok or len(nomi) >= 2))


def _analizza_df(nome, df, righe=None):
    if df is None or not len(df.columns):
        return _risultato("tabella", None, 0.3, "tabella vuota", usa=False)
    if _dizionario(nome, df):
        return _risultato("documento", "dizionario", 0.85, "descrive tabelle, campi o file (dizionario dei dati)",
                          usa=True, dettagli=dict(colonne=[str(c) for c in df.columns], righe=righe))
    ruolo, p, motivo, det = _ruolo_tabella(nome, df)
    det["righe"] = righe if righe is not None else int(len(df))
    return _risultato("tabella", ruolo, p, motivo, dettagli=det)


def _campione_csv(path, sep=None):
    """Prime righe di un CSV (separatore e codifica riconosciuti) e numero di righe (stimato se grande)."""
    import pandas as pd
    with open(path, "rb") as f:
        grezzo = f.read(256 * 1024)
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            testo = grezzo.decode(cod)
            break
        except UnicodeDecodeError as e:
            if cod == "utf-8-sig" and e.start > len(grezzo) - 4:      # carattere tagliato a fine blocco
                testo = grezzo[:e.start].decode(cod)
                break
    righe = testo.splitlines()
    if len(grezzo) == 256 * 1024 and len(righe) > 1:
        righe = righe[:-1]
    if sep is None:
        sep = _separatore(righe[:20])
    try:
        df = pd.read_csv(io.StringIO("\n".join(righe[:RIGHE_CAMPIONE + 1])), sep=sep, low_memory=False,
                         on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(io.StringIO("\n".join(righe[:RIGHE_CAMPIONE + 1])), sep=None, engine="python",
                         on_bad_lines="skip")
    dim = os.path.getsize(path)
    if dim <= len(grezzo):
        n = max(len(righe) - 1, 0)
    elif dim <= 64 * 2 ** 20:
        with open(path, "rb") as f:
            n = sum(b.count(b"\n") for b in iter(lambda: f.read(1 << 22), b"")) - 1
    else:
        media = max(len(grezzo) / max(len(righe), 1), 1)
        n = int(dim / media)
    return df, max(n, 0), sep


def _separatore(righe):
    """Separatore delle colonne: quello che compare lo stesso numero di volte in tutte le prime righe
    (senza contare le parti tra virgolette); se nessuno è netto, ``csv.Sniffer``."""
    righe = [re.sub(r'"[^"]*"', "", r) for r in righe if r.strip()]
    if righe:
        migliori = []
        for sep in (",", ";", "\t", "|"):
            n = [r.count(sep) for r in righe[:10]]
            if n[0] >= 1 and all(x == n[0] for x in n):
                migliori.append((n[0], sep))
        if len(migliori) == 1:
            return migliori[0][1]
    try:
        return csv.Sniffer().sniff("\n".join(righe[:20]), delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _analizza_csv(el, sep=None):
    I = _importa()
    df, n, sep = _campione_csv(el.percorso, sep)
    nome = os.path.splitext(el.nome)[0]
    cw = I._colonna_wkt(df)
    low = {_norm(c): c for c in df.columns}
    cx = next((low[k] for k in ("x", "e", "est", "east", "easting") if k in low), None)
    cy = next((low[k] for k in ("y", "n", "nord", "north", "northing") if k in low), None)
    if cw is not None or (cx is not None and cy is not None and _numerica(df[cx]) and _numerica(df[cy])):
        if cw is not None:
            tipi = {I._WKT_RE.match(str(v)).group(2).upper() for v in df[cw].dropna().head(50)
                    if I._WKT_RE.match(str(v))}
            geom = _geometria({"POINT": "Point", "LINESTRING": "LineString", "POLYGON": "Polygon"}.get(
                tipi.pop(), None)) if len(tipi) == 1 else "misto"
            ha_z = bool(df[cw].dropna().head(20).astype(str).str.contains(r"^\s*\w+\s+Z", regex=True).any())
            come = f"geometrie in testo (WKT, colonna «{cw}»)"
        else:
            geom = "punto"
            cz = next((low[k] for k in ("z", "quota", "q", "h", "elev") if k in low), None)
            ha_z = cz is not None
            come = f"coordinate nelle colonne «{cx}», «{cy}»" + (f", «{cz}»" if cz else "")
        campi = [str(c) for c in df.columns if c != cw]
        ruolo, p, motivo = ruolo_layer(nome, geom, ha_z, campi)
        det = dict(geometria=geom, n=n, ha_z=ha_z, campi=campi[:40], separatore=sep)
        return _risultato("gis", ruolo, p, f"{come}; {motivo} ({n} righe)" if motivo else f"{come} ({n} righe)",
                          dettagli=det)
    parti = _tabelle_ordinate(nome, df)
    if len(parti) == 1:
        (k, d), = parti.items()
        r = _analizza_df(nome, d, n)
        r["dettagli"]["separatore"] = sep
        return r
    return _riassumi_parti(el, [_parte(el, k, _analizza_df(k, d)) for k, d in parti.items()], "foglio")


def _numerica(serie):
    import pandas as pd
    v = pd.to_numeric(serie.dropna().astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return len(v) > 0 and v.notna().mean() > 0.9


def _in_ordine(df):
    """Una tabella già in ordine: intestazione di testi diversi, nessuna riga o colonna vuota."""
    cols = [str(c) for c in df.columns]
    if not len(df) or len(set(cols)) != len(cols):
        return False
    if any(re.match(r"^unnamed:\s*\d+", c, re.I) or re.fullmatch(r"[-+\d.,\s]*", c) for c in cols):
        return False
    vuote = df.isna().to_numpy()
    return not vuote.all(axis=0).any() and not vuote.all(axis=1).any()


def _tabelle_ordinate(nome, df):
    """Tabelle del foglio ordinate con ``tabelle_grezze`` (intestazione spostata, più tabelle…)."""
    from . import tabelle_grezze as tg
    if _in_ordine(df):
        return {nome: df}
    try:
        return {k: d for k, (d, _) in tg.normalizza_foglio(df, nome, misure=False).items()}
    except Exception:
        return {nome: df}


def _analizza_txt_tabella(el):
    """Un .txt con colonne separate (tabulazione, punto e virgola…) è una tabella."""
    righe = [r for r in _testa(el.percorso, 16384).splitlines()[:30] if r.strip()]
    if len(righe) < 3:
        return None
    for sep in ("\t", ";", "|", ","):
        n = [r.count(sep) for r in righe[:-1] or righe]
        if n[0] >= 1 and sum(1 for x in n if x == n[0]) >= 0.9 * len(n):
            try:
                return _analizza_csv(el, sep)
            except Exception:
                return None
    return None


def _analizza_dbf(el):
    import pyogrio
    df = pyogrio.read_dataframe(el.percorso, read_geometry=False, max_features=RIGHE_CAMPIONE)
    n = int(pyogrio.read_info(el.percorso).get("features") or len(df))
    r = _analizza_df(os.path.splitext(el.nome)[0], df, n)
    if r["categoria"] == "tabella":
        r["usa"] = False
        r["destinazione"] = NON_USATO
        r["motivo"] = (r["motivo"] + "; " if r["motivo"] else "") + \
            "tabella dBase senza shapefile: per usarla salvala in CSV o Excel"
    return r


def _analizza_excel(el):
    import pandas as pd
    fogli = pd.read_excel(el.percorso, sheet_name=None, nrows=RIGHE_CAMPIONE)
    parti = []
    for nome_f, df in fogli.items():
        for k, d in _tabelle_ordinate(str(nome_f), df).items():
            r = _analizza_df(k, d)
            r["dettagli"]["foglio"] = str(nome_f)
            parti.append(_parte(el, k, r))
    if not parti:
        return _risultato("tabella", None, 0.4, "cartella di lavoro vuota", usa=False)
    return _riassumi_parti(el, parti, "foglio")


# ------------------------------------------------------------------ raster e immagini
def _analizza_tif(el, accessori):
    from .superficie import georef, e_ortofoto, e_differenza
    try:
        g = georef(el.percorso)
    except RuntimeError as e:
        if "ruotato" in str(e):
            return _risultato("raster", None, 0.6, f"{e}", usa=False)
        r = _analizza_immagine(el, accessori)
        r["motivo"] = "TIFF senza georiferimento: " + r["motivo"]
        return r
    det = dict(righe=g["righe"], colonne=g["colonne"], bande=g["bande"], tipo_dati=g["dtype"],
               passo=round(g["passo"][0], 3), estensione=[round(v, 2) for v in g["estensione"]],
               accessori=[a.nome for a in accessori])
    if e_ortofoto(g):
        return _risultato("raster", "ortofoto", 0.9, f"immagine georiferita a colori ({g['bande']} bande, passo "
                          f"{det['passo']} m): da drappeggiare sul modello", dettagli=det)
    if (el.dimensione or 0) > MAX_RASTER_LETTO:
        return _risultato("raster", "dem", 0.6, f"raster a una banda ({g['dtype']}) molto grande: considerato un "
                          "modello del terreno (valori non controllati)", dettagli=det)
    d = _statistiche_raster(el.percorso, g)
    det.update(d)
    if d.get("quota_max") is None:
        return _risultato("raster", None, 0.4, "raster senza valori", usa=False, dettagli=det)
    if e_differenza(d):
        return _risultato("raster", "differenza", 0.85, f"valori tutti tra {d['quota_min']} e {d['quota_max']}: "
                          "differenze di quota (troncamento) da sommare al modello del terreno", dettagli=det)
    if g["bande"] == 1 and g["dtype"] == "uint8":
        return _risultato("raster", "dem", 0.4, "una banda a 8 bit: forse un'immagine in scala di grigi più che un "
                          "modello del terreno", dettagli=det)
    return _risultato("raster", "dem", 0.85, f"modello del terreno: quote da {d['quota_min']} a {d['quota_max']}",
                      dettagli=det)


def _statistiche_raster(path, g):
    import numpy as np
    import tifffile
    try:
        z = tifffile.memmap(path, mode="r")        # non compresso: si leggono solo le celle campionate
    except Exception:
        with tifffile.TiffFile(path) as t:
            z = t.pages[0].asarray()
    if z.ndim == 3:
        z = z[..., 0] if z.shape[-1] <= 4 else z[0]
    passo = max(1, int((z.size / 1_000_000) ** 0.5))
    z = np.asarray(z[::passo, ::passo], dtype="float64")
    if g.get("nodata") is not None:
        z[np.isclose(z, g["nodata"])] = np.nan
    if str(g["dtype"]) == "int16":
        z[(z == -32768) | (z == 32767)] = np.nan
    z[z < -1e30] = np.nan
    v = z[np.isfinite(z)]
    if not len(v):
        return dict(quota_min=None, quota_max=None)
    return dict(quota_min=round(float(v.min()), 2), quota_max=round(float(v.max()), 2))


_PAROLE_DISEGNO = re.compile(r"(^|[^a-z])(sez|sezione|sezioni|section|sect|pianta|piante|plan|plans|planimetri|"
                             r"prospett|elevation|disegn|drawing|draw|ril|rilievo|tav|tavola|fig|figure|figura|"
                             r"diagram|diagramma|schema|matrix|matrice|harris|profil|ritning|zeichnung|dessin|"
                             r"lucido|dwg)", re.I)
_PAROLE_SCANSIONE = re.compile(r"(^|[^a-z])(scan|scans|scansion|scheda|schede|sheet|form|modulo|giornale|diario|"
                               r"diary|notebook|taccuino|pag|page|doc|documento)", re.I)


def tipo_immagine_dal_nome(path):
    """Ripiego quando ``documenti_auto`` non c'è: foto, disegno o scansione dal nome del file e della cartella."""
    nome = os.path.splitext(os.path.basename(path))[0]
    cart = os.path.basename(os.path.dirname(path))
    for testo, peso in ((nome, 0.6), (cart, 0.5)):
        if _PAROLE_DISEGNO.search(testo.replace("_", " ")):
            return "disegno", peso, f"il nome «{testo}» indica un disegno"
        if _PAROLE_SCANSIONE.search(testo.replace("_", " ")):
            return "scansione", peso - 0.1, f"il nome «{testo}» indica una scansione"
    if re.search(r"(^|[^a-z])(foto|photo|img|image|dsc|dscn|dsc_|p\d{6,}|imgp|bild|fotografi)", nome + " " + cart,
                 re.I) or os.path.splitext(path)[1].lower() in (".jpg", ".jpeg", ".heic", ".cr2", ".nef", ".dng"):
        return "foto", 0.5, "fotografia (dal formato e dal nome)"
    return "disegno" if os.path.splitext(path)[1].lower() in (".png", ".gif", ".bmp") else "foto", 0.35, \
        "riconosciuta solo dal formato"


_ANALIZZATE = Counter()     # immagini passate a documenti_auto in questo inventario (per cartella e in tutto)


def _analizza_immagine(el, accessori):
    tipo = None
    analizzata = False
    if el.estratto and _tipo_immagine_auto is not None and _ANALIZZATE[None] < MAX_TIPO_IMMAGINE and \
            _ANALIZZATE[el.cartella] < IMMAGINI_PER_CARTELLA:
        _ANALIZZATE[None] += 1
        _ANALIZZATE[el.cartella] += 1
        try:
            tipo, p, motivo = _tipo_immagine_auto(el.percorso)
            analizzata = True
        except Exception:
            tipo = None
    if tipo not in ("foto", "disegno", "scansione"):
        tipo, p, motivo = tipo_immagine_dal_nome(el.percorso)
    geo = any(os.path.splitext(a.nome.lower())[1] in (".jgw", ".pgw", ".wld", ".tfw", ".jpgw", ".pngw")
              for a in accessori)
    det = dict(estratto=bool(el.estratto), analizzata=analizzata, georiferita=geo,
               accessori=[a.nome for a in accessori])
    if not el.estratto:
        motivo += " (nell'archivio, non estratta)"
    return _risultato("immagine", tipo, p, motivo, usa=True, dettagli=det)


# ------------------------------------------------------------------ documenti
_RUOLI_DOC = [
    ("licenza", re.compile(r"licen[cs]|copyright|copying|terms|termini|condizioni|rights|diritti|cc.?by", re.I), 0.9),
    ("dizionario", re.compile(r"dictionar|dizionar|field.?desc|table.?desc|file.?desc|fileformat|file.?format|"
                              r"codebook|glossar|legend|schema|descrizione.?(dei.?)?campi", re.I), 0.85),
    ("metadati", re.compile(r"read.?me|leggimi|metadat|about|manifest|citation|citazione|info|version|changelog",
                            re.I), 0.8),
    ("elenco", re.compile(r"elenco|lista|list|index|indice|catalog|inventar|register|registro|giornale", re.I), 0.6),
    ("relazione", re.compile(r"relazion|report|rapport|bericht|informe|rapporto|monograph|volume|pubblicazion|"
                             r"publication|articol|article|paper|mitt|tesi|thesis|notiziario|preliminar", re.I), 0.75),
]


def _analizza_documento(el):
    nome = os.path.splitext(el.nome)[0]
    ext = os.path.splitext(el.nome)[1].lower()
    for ruolo, rx, p in _RUOLI_DOC:
        if rx.search(nome.replace("_", " ")):
            return _risultato("documento", ruolo, p, f"il nome «{nome}» indica: {DESTINAZIONE[ruolo].lower()}",
                              usa=True)
    if ext in (".pdf", ".doc", ".docx", ".odt", ".rtf"):
        return _risultato("documento", "relazione", 0.45, "documento di testo: forse la relazione o una pubblicazione",
                          usa=True)
    return _risultato("documento", "metadati", 0.4, "file di testo: note sull'archivio", usa=True)


# ============================================================================ dopo l'analisi
_PREF_FORMATO = {".gpkg": 0, ".shp": 0, ".sqlite": 1, ".db": 1, ".geojson": 1, ".json": 1, ".fgb": 1, ".dxf": 2,
                 ".csv": 2, ".xlsx": 0, ".xlsm": 0, ".xls": 1, ".ods": 1, ".tsv": 2, ".txt": 3, ".gml": 3,
                 ".kml": 4, ".xml": 5, ".dbf": 4, ".tif": 0, ".tiff": 0, ".obj": 0, ".ply": 1}


def _togli_doppioni(voci, note):
    """Gli stessi dati in più formati o in più copie: si tiene il formato migliore e la copia meno profonda."""
    gruppi = defaultdict(list)
    for v in voci:
        if v["usa"] and v["categoria"] in CATEGORIE_DATI:
            gruppi[(v["categoria"], _chiave_nome(v["nome"]))].append(v)
    diversi = []
    for (_, k), vv in gruppi.items():
        if len(vv) < 2 or not k:
            continue
        vv.sort(key=lambda v: (_PREF_FORMATO.get(v["estensione"], 3), v["relativo"].count("/"), v["relativo"]))
        tenute = [vv[0]]
        for v in vv[1:]:
            stesso = next((t for t in tenute if t["estensione"] != v["estensione"] or
                           (t["dimensione"] and t["dimensione"] == v["dimensione"])), None)
            if stesso is not None:
                v["usa"] = False
                v["destinazione"] = NON_USATO
                come = "copia" if stesso["estensione"] == v["estensione"] else "stessi dati in un altro formato"
                v["motivo"] = f"{come} di «{stesso['relativo']}» (si usa quella); " + v["motivo"]
                v["dettagli"]["doppione_di"] = stesso["percorso"]
            else:
                tenute.append(v)
        if len(tenute) > 1:
            diversi.append((tenute[0]["nome"], len(tenute)))
    if diversi:
        esempi = ", ".join(f"«{n}» ({k} versioni)" for n, k in diversi[:4])
        note.append(f"Alcuni file hanno lo stesso nome ma contenuto diverso: {esempi}. Forse la cartella contiene "
                    "più scavi: controlla quali usare")


_FIGURA_FILE_RE = re.compile(r"^(fig|figure|figura|tav|tavola|plate|abb)[\s_.\-]*\d+", re.I)


def _figure_pubblicazione(voci):
    """Layer nelle cartelle delle figure (Chapter1…, Fig. 3…): esclusi solo se lo stesso insieme di dati ha
    anche layer fuori da quelle cartelle (allora le figure sono ritagli o rielaborazioni per la stampa)."""
    def cartelle(v):
        return v["relativo"].split("/")[:-1]

    def radice(v):
        return v.get("_contenitore") or v["relativo"].split("/")[0]

    per_insieme = defaultdict(list)
    for v in voci:
        if v["categoria"] == "gis":
            per_insieme[radice(v)].append(v)
    for _, vv in per_insieme.items():
        fig = [v for v in vv if any(_FIGURA_RE.match(c) for c in cartelle(v)) or _FIGURA_FILE_RE.match(v["nome"])]
        altri = [v for v in vv if v not in fig and v["usa"]]
        if not fig or not altri:
            continue
        for v in fig:
            if v["usa"]:
                c = next((c for c in cartelle(v) if _FIGURA_RE.match(c)), None)
                if c is None:
                    v["usa"] = False
                    v["destinazione"] = NON_USATO
                    v["motivo"] = f"layer di una figura della pubblicazione (nome «{v['nome']}»): non proposto; " + \
                        v["motivo"]
                    v["dettagli"]["figura"] = v["nome"]
                    continue
                v["usa"] = False
                v["destinazione"] = NON_USATO
                v["motivo"] = f"layer di una figura della pubblicazione (cartella «{c}»): non proposto; " + v["motivo"]
                v["dettagli"]["figura"] = c


def _ipotesi_deboli(voci):
    """Layer con un ruolo solo ipotizzato dalla geometria (poligoni -> US, linee -> sezioni): se lo stesso
    insieme di dati ha un layer riconosciuto con sicurezza per quel ruolo, le ipotesi non si propongono."""
    per_insieme = defaultdict(list)
    for v in voci:
        if v["categoria"] == "gis" and "parti" not in v:
            per_insieme[v.get("_contenitore") or v["relativo"].split("/")[0]].append(v)
    for _, vv in per_insieme.items():
        sicuri = defaultdict(list)
        for v in vv:
            if v["usa"] and (v["punteggio"] >= 0.8 or (v["ruolo"] in ("us", "usm") and v["dettagli"].get("campo_unita"))):
                sicuri[v["ruolo"]].append(v)
        for v in vv:
            if v["usa"] and v["punteggio"] < 0.45 and sicuri.get(v["ruolo"]) and not v["dettagli"].get("campo_unita"):
                rif = sicuri[v["ruolo"]][0]
                v["usa"] = False
                v["destinazione"] = NON_USATO
                v["motivo"] = (f"ruolo solo ipotizzato e nello stesso insieme c'è «{rif['nome']}» "
                               f"({DESTINAZIONE[v['ruolo']]}): non proposto; " + v["motivo"])


def _immagini_come_vicine(voci):
    """Immagini non analizzate (non estratte o oltre il limite): il tipo più frequente nella stessa cartella."""
    per_cartella = defaultdict(list)
    for v in voci:
        if v["categoria"] == "immagine":
            per_cartella[os.path.dirname(v["percorso"])].append(v)
    for _, vv in per_cartella.items():
        sicure = [v for v in vv if v["dettagli"].get("analizzata") and v["punteggio"] >= 0.5]
        if not sicure:
            continue
        tipo, n = Counter(v["ruolo"] for v in sicure).most_common(1)[0]
        if n < 0.7 * len(sicure):
            continue
        for v in vv:
            if not v["dettagli"].get("analizzata") and v["punteggio"] < 0.6:
                v["ruolo"], v["destinazione"] = tipo, DESTINAZIONE[tipo]
                v["punteggio"] = 0.5
                v["motivo"] = f"come le altre immagini della cartella ({DESTINAZIONE[tipo]})" + \
                    ("" if v["dettagli"].get("estratto") else "; nell'archivio, non estratta")


# ============================================================================ funzione principale
def esamina_cartella(percorsi, profondita_max=8, limite_file=20000):
    """Inventario di cartelle, file e archivi zip. ``percorsi``: uno o più percorsi (stringa o lista).

    Ritorna {"radici", "voci", "riepilogo", "note", "file_proposta"}: ogni voce ha «percorso» (assoluto; per
    i file di un archivio, quello estratto nella cartella di lavoro), «origine» («archivio.zip:cartella/file»
    o None), «relativo», «nome», «estensione», «dimensione», «categoria», «ruolo», «destinazione»,
    «punteggio», «motivo», «usa», «dettagli» e, per i file con più layer o fogli, «parti»; i file dentro uno
    zip hanno anche «archivio» e «membro», per estrarli quando servono (``assicura_estratto``).
    «file_proposta» sono i file di dati da passare a ``importa.proponi`` (senza doppioni)."""
    t0 = time.time()
    _ANALIZZATE.clear()
    if isinstance(percorsi, (str, os.PathLike)):
        percorsi = [percorsi]
    racc = _Raccolta(profondita_max, limite_file)
    radici = []
    for p in percorsi:
        p = os.path.abspath(os.path.expanduser(str(p)))
        if os.path.isdir(p):
            radici.append(p)
            racc.cartella(p)
        elif os.path.isfile(p):
            radice = os.path.dirname(p)
            radici.append(p)
            if os.path.splitext(p)[1].lower() in EST_ZIP:
                racc.zip(p, None, os.path.basename(p), 0, radice)
            else:
                racc.aggiungi(_Elemento(p, None, os.path.basename(p), os.path.getsize(p), 0, True, radice, radice,
                                        None))
        else:
            racc.note.append(f"«{p}» non esiste")
    if racc.pieno:
        racc.note.append(f"Trovati più di {limite_file} file: esaminati solo i primi {limite_file}")
    gruppi, inutili = _raggruppa(racc.elementi)
    voci = list(racc.voci_extra)
    for el in inutili:
        voci.append(_voce_inutile(el.percorso, el.origine, el.relativo, "file di sistema o temporaneo"))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2) + 2)) as ex:
        risultati = list(ex.map(lambda g: _analizza(*g), gruppi))
    for (el, acc), r in zip(gruppi, risultati):
        v = dict(percorso=el.percorso, origine=el.origine, relativo=el.relativo, nome=el.nome,
                 estensione=os.path.splitext(el.nome)[1].lower(), dimensione=el.dimensione)
        v.update(copy.deepcopy(r))          # la copia in memoria resta com'era (doppioni, figure…)
        if acc:
            v["dettagli"].setdefault("accessori", [a.nome for a in acc])
            v["dimensione"] = (el.dimensione or 0) + sum(a.dimensione or 0 for a in acc)
        v["_contenitore"] = el.contenitore
        if el.archivio:
            v["archivio"], v["membro"] = el.archivio, el.membro
        voci.append(v)
    _immagini_come_vicine(voci)
    _figure_pubblicazione(voci)
    _ipotesi_deboli(voci)
    note = list(racc.note)
    _togli_doppioni(voci, note)
    for v in voci:
        v.pop("_contenitore", None)
    voci.sort(key=lambda v: (v["relativo"].lower()))
    ordine = {"gis": 0, "tabella": 1, "raster": 2, "modello3d": 3}
    proposta = []
    for v in sorted(voci, key=lambda v: (ordine.get(v["categoria"], 9), v["relativo"].lower())):
        if v["usa"] and v["categoria"] in CATEGORIE_DATI and os.path.exists(v["percorso"]) and \
                v["percorso"] not in proposta:
            proposta.append(v["percorso"])
    riepilogo = dict(Counter(v["categoria"] for v in voci))
    n_acc = sum(len(v["dettagli"].get("accessori") or []) for v in voci)
    for v in voci:
        if v["categoria"] == "database":
            note.append(f"«{v['nome']}» è un database Access: esporta le tabelle in CSV (in Access: Dati esterni → "
                        "Esporta → File di testo) e aggiungi i CSV")
    note.insert(0, f"Esaminati {len(racc.elementi)} file ({len(voci)} voci, {n_acc} file accessori uniti al file "
                   f"principale) in {racc.n_cartelle} cartelle e {racc.n_zip} archivi zip in {time.time() - t0:.1f} s")
    if not proposta:
        note.append("Nessun file di dati da importare (piante, schede, raster o modelli 3D)")
    return dict(radici=radici, voci=voci, riepilogo=riepilogo, note=note, file_proposta=proposta)


# ============================================================================ dopo l'inventario
def _dentro(p, cartella):
    try:
        return os.path.commonpath([os.path.realpath(p), os.path.realpath(cartella)]) == os.path.realpath(cartella)
    except ValueError:
        return False


def assicura_estratto(voce, voci=None):
    """Percorso sul disco del file di una voce, estraendolo dall'archivio se non c'è ancora (le foto di un
    archivio grande si elencano senza estrarle). ``voce``: una voce dell'inventario (o un percorso);
    ``voci``: tutte le voci, per ritrovare gli archivi annidati da estrarre a loro volta. None se il file
    non c'è e non si può estrarre."""
    p = voce.get("percorso") if isinstance(voce, dict) else voce
    if p and os.path.isfile(str(p)):
        return str(p)
    if not isinstance(voce, dict) or not p:
        return None
    archivio, membro = voce.get("archivio"), voce.get("membro")
    if not archivio or not membro or not _dentro(p, cartella_estratti()):
        return None              # si scrive solo nella cartella di lavoro degli archivi
    if not os.path.isfile(archivio):
        madre = next((v for v in voci or [] if isinstance(v, dict) and v.get("percorso") == archivio
                      and v is not voce), None)
        archivio = assicura_estratto(madre, [v for v in voci if v is not voce]) if madre is not None else None
        if not archivio:
            return None
    try:
        with zipfile.ZipFile(archivio) as z:
            _estrai(z, z.getinfo(membro), p)
    except (KeyError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError, ValueError):
        return None
    return p if os.path.isfile(p) else None


NOMI_CATEGORIE = {"gis": "GIS", "tabella": "tabelle", "raster": "raster", "modello3d": "modelli 3D",
                  "immagine": "immagini", "documento": "documenti", "database": "database", "archivio": "archivi",
                  "altro": "altri file", "ignorato": "ignorati"}


def riassunto_testo(inv, massimo=15):
    """Riassunto dell'inventario da leggere (riga di comando): file per categoria e per destinazione, file
    proposti per l'importazione, note."""
    from . import importa
    voci = [v for v in (inv or {}).get("voci") or [] if isinstance(v, dict)]
    righe = []
    radici = ", ".join(f"«{os.path.basename(os.path.normpath(str(r)))}»" for r in (inv or {}).get("radici") or [])
    righe.append(f"Inventario di {radici or 'file'}: {len(voci)} file")
    conta = Counter(v.get("categoria") or "altro" for v in voci)
    ordine = {c: i for i, c in enumerate(CATEGORIE)}
    if conta:
        righe.append("Categorie: " + ", ".join(f"{NOMI_CATEGORIE.get(c, c)} {n}" for c, n in
                                                sorted(conta.items(), key=lambda x: (ordine.get(x[0], 99), x[0]))))
    usate = Counter(str(v.get("destinazione") or NON_USATO) for v in voci
                    if v.get("usa") and v.get("categoria") not in ("ignorato", "archivio"))
    if usate:
        righe.append("Destinazioni:")
        for d, n in sorted(usate.items(), key=lambda x: (-x[1], x[0])):
            righe.append(f"  {d}: {n}")
    non_usati = sum(1 for v in voci if not v.get("usa") and v.get("categoria") not in ("archivio",))
    if non_usati:
        righe.append(f"Non usati: {non_usati}")
    rel = {v.get("percorso"): v.get("relativo") or v.get("nome") for v in voci}
    proposta = list((inv or {}).get("file_proposta") or [])
    righe.append(f"File proposti per l'importazione: {len(proposta)}")
    for p in proposta[:massimo]:
        righe.append(f"  {rel.get(p) or p}")
    if len(proposta) > massimo:
        righe.append(f"  … e altri {len(proposta) - massimo}")
    note = [importa._testo_nota(n) for n in (inv or {}).get("note") or []]
    if note:
        righe.append("Note:")
        righe += [f"  - {n}" for n in note]
    return "\n".join(righe)
