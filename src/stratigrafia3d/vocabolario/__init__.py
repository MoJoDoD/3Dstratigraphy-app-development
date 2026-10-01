# -*- coding: utf-8 -*-
"""
Vocabolario dei termini archeologici e tecnici: riconosce che cosa rappresenta un file, un layer,
una tabella, una colonna o un valore anche quando archivi diversi usano parole, lingue,
abbreviazioni o convenzioni diverse per lo stesso concetto.

    from stratigrafia3d import vocabolario as voc
    voc.riconosci("Context Number", "colonna")[0]   # concetto "us", canonico "US"
    voc.riconosci_valore("is cut by", "rapporto")   # "tagliato da"
    voc.spiega("Höhe OK", "colonna")                # «Höhe OK» è un termine tedesco per la quota superiore…

I termini stanno nei file JSON di questa cartella, uno per argomento, con la struttura

    {"concetto": {"descrizione": "testo breve", "descrizioni": {ambito: testo},
                  "ambiti": ["file", "layer", "tabella", "colonna", "valore"],
                  "canonico": {ambito: nome usato dal programma},
                  "campo": "tipo" | "rapporto" | "tipo_quota"      (solo per i vocabolari di valori),
                  "termini": {lingua: [...]}, "sistemi": {sistema: [...]},
                  "abbreviazioni": [...], "deboli": [...], "codici": [...],
                  "pattern": [regex sul testo normalizzato], "esclusioni": [...],
                  "contesti": [concetti che lo rendono più probabile], "geometrie": ["punto", ...]}}

«deboli» sono termini generici (contano poco e solo se il nome è esattamente quello), «codici» sono
sigle valide solo come valori («n», «=», «>»). L'utente può aggiungere termini in
~/.stratigrafia3d/vocabolario.json (stessa struttura): i suoi termini prevalgono su quelli
integrati. Una ricetta d'importazione può passare altri termini al momento ({"concetto": [...]}).
"""
import difflib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

AMBITI = ("file", "layer", "tabella", "colonna", "valore")
_AMBITI_NOMI = ("file", "layer", "tabella", "colonna")
LINGUE = {"it": "italiano", "en": "inglese", "fr": "francese", "de": "tedesco", "es": "spagnolo",
          "sv": "svedese", "nl": "olandese"}
CARTELLA = os.path.dirname(os.path.abspath(__file__))
FILE_UTENTE = os.path.join(os.path.expanduser("~"), ".stratigrafia3d", "vocabolario.json")

# estensioni tolte dai nomi dei file
ESTENSIONI = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".gpkg", ".geojson", ".json", ".dxf", ".dwg", ".sqlite", ".db",
              ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".ods", ".mdb", ".accdb", ".zip", ".kml", ".kmz",
              ".gml", ".tif", ".tiff", ".asc", ".las", ".laz", ".obj", ".ply", ".stl", ".jpg", ".jpeg", ".png",
              ".pdf", ".xml", ".qgz", ".qgs", ".tab", ".mif", ".gdb", ".e00", ".fgb", ".parquet", ".glb", ".gltf"}
# parole che non dicono niente sul contenuto (tolte dai nomi, non dai valori)
RUMORE = frozenset({
    "tbl", "table", "tables", "tab", "layer", "layers", "lyr", "shp", "shapefile", "export", "exported",
    "esport", "esportazione", "esportato", "copy", "copia", "copie", "kopie", "v", "ver", "vers", "version",
    "versione", "def", "definitivo", "new", "nuovo", "old", "vecchio", "bak", "backup", "tmp", "temp", "draft",
    "bozza", "dati", "sheet", "sheets", "foglio", "fogli", "dbo", "public", "csv", "xlsx", "xls", "dxf", "geojson"})
# parole che qualificano un numero o un codice («US n.», «Context ID»): non cambiano il concetto
QUALIFICATORI = frozenset({"n", "nr", "no", "num", "numero", "number", "nummer", "nro", "id", "cod", "codice", "code",
                           "#"})
UNITA = frozenset({"m", "cm", "mm", "g", "gr", "kg", "mq", "mc", "km", "ha"})
# parole vuote: contano poco nella copertura del nome e non servono a cercare i candidati
PAROLE_VUOTE = frozenset({
    "di", "da", "del", "della", "dello", "dei", "degli", "delle", "dell", "il", "lo", "la", "le", "i", "gli", "l", "e",
    "o", "ed", "a", "al", "in", "per", "con", "the", "of", "by", "an", "and", "or", "to", "on", "is", "for", "de",
    "du", "des", "d", "et", "ou", "un", "une", "der", "die", "das", "dem", "den", "und", "oder", "von", "im", "el",
    "los", "las", "y", "en", "och", "av", "pa", "med", "het", "een", "van", "met", "s"})
PESI = {"termine": 1.0, "sistema": 1.0, "abbreviazione": 0.85, "debole": 0.5, "codice": 0.85, "pattern": 1.0}
# nomi dei vocabolari di valori (come nelle ricette: abb.vocabolari)
_CAMPI = {"tipo": "tipo", "tipo us": "tipo", "rapporto": "rapporto", "rapporti": "rapporto",
          "tipo quota": "tipo_quota", "tipo_quota": "tipo_quota", "quota": "tipo_quota", "quote": "tipo_quota"}
_CAMPO_DA_COLONNA = {"tipo": "tipo", "tipo_quota": "tipo_quota", "rapporti": "rapporto"}
_CHIAVI_LISTA = ("ambiti", "abbreviazioni", "deboli", "codici", "pattern", "esclusioni", "contesti", "geometrie")


# ============================================================================ normalizzazione
_SPECIALI = str.maketrans({"ß": "ss", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ł": "l",
                           "Ł": "L", "đ": "d", "þ": "th", "°": " ", "º": " ", "²": " ", "³": " ", "№": " n "})
_TOKEN_RE = re.compile(r"[a-z]+|\d+|[=<>#]")


def _senza_accenti(s):
    s = s.translate(_SPECIALI)
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


@lru_cache(maxsize=200000)
def _token(testo, rumore=True):
    s = _senza_accenti(str(testo).strip())
    base, est = os.path.splitext(s)
    if base and est.lower() in ESTENSIONI:
        s = base
    s = re.sub(r"(\w)['’]s\b", r"\1s", s)                    # foto's -> fotos
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)               # ContextNumber -> Context Number
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)         # SGData -> SG Data
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([A-Za-z])", r"\1 \2", s)
    grezzi = _TOKEN_RE.findall(s.lower())
    out = []
    i = 0
    while i < len(grezzi):
        t = grezzi[i]
        if t in ("2", "3") and i + 1 < len(grezzi) and grezzi[i + 1] == "d":     # 3D, 2D
            out.append(t + "d")
            i += 2
            continue
        i += 1
        if t.isdigit() or (rumore and t in RUMORE):
            continue
        out.append(t)
    return tuple(out)


def normalizza(testo, rumore=True):
    """Parole di un nome, pronte per il confronto: minuscole, senza accenti, divise su camelCase,
    trattini, punti e cifre («ContextNumber» -> ["context", "number"], «q.sup» -> ["q", "sup"],
    «US_n» -> ["us", "n"]). Toglie l'estensione dei file, i numeri (anni, versioni) e, se
    ``rumore`` è vero, le parole che non dicono nulla sul contenuto («tbl», «layer», «export», «copia»…)."""
    if testo is None:
        return []
    return list(_token(str(testo), bool(rumore)))


def _in_ordine(parti, tutto):
    it = iter(tutto)
    return all(any(p == t for t in it) for p in parti)


# ============================================================================ dati
@dataclass(frozen=True)
class Riconoscimento:
    """Un concetto riconosciuto in un nome: ``punteggio`` da 0 a 1, ``motivo`` spiega la scelta,
    ``canonico`` è il nome usato dal programma per quell'ambito (ruolo del layer, foglio, colonna,
    valore), se esiste."""
    concetto: str
    punteggio: float
    motivo: str
    termine: str = ""
    lingua: str = ""
    canonico: str = None


class _Voce:
    __slots__ = ("concetto", "termine", "tipo", "lingua", "origine", "token", "lettere")

    def __init__(self, concetto, termine, tipo, lingua, origine, token=()):
        self.concetto, self.termine, self.tipo, self.lingua, self.origine = concetto, termine, tipo, lingua, origine
        self.token = token
        self.lettere = sum(len(t) for t in token if t not in PAROLE_VUOTE) or sum(len(t) for t in token)


def _voci(concetto, d, origine):
    for lingua, termini in (d.get("termini") or {}).items():
        for t in termini or []:
            yield _Voce(concetto, str(t), "termine", lingua, origine)
    for sistema, termini in (d.get("sistemi") or {}).items():
        for t in termini or []:
            yield _Voce(concetto, str(t), "sistema", sistema, origine)
    for chiave, tipo in (("abbreviazioni", "abbreviazione"), ("deboli", "debole"), ("codici", "codice")):
        for t in d.get(chiave) or []:
            yield _Voce(concetto, str(t), tipo, "", origine)


class _Indice:
    """Indice dei termini: per corrispondenza esatta, attaccata («contextnumber»), per parola e per
    iniziale (somiglianze)."""

    def __init__(self, voci, rumore, codici):
        tutte = []
        for v in voci:
            if v.tipo == "codice" and not codici:
                continue
            tok = _token(v.termine, rumore)
            if tok:
                tutte.append((v, tok))
        # i termini dell'utente e della ricetta prevalgono: lo stesso termine non vale per altri concetti
        propri = {}
        for v, tok in tutte:
            if v.origine != "integrato":
                propri.setdefault(tok, set()).add(v.concetto)
        self.esatti, self.compatti, self.per_token = {}, {}, {}
        for v, tok in tutte:
            if v.origine == "integrato" and tok in propri and v.concetto not in propri[tok]:
                continue
            w = _Voce(v.concetto, v.termine, v.tipo, v.lingua, v.origine, tok)
            self.esatti.setdefault(tok, []).append(w)
            comp = "".join(tok)
            if len(comp) >= 5:
                self.compatti.setdefault(comp, []).append(w)
            for t in set(tok):
                self.per_token.setdefault(t, []).append(w)
        self.token_noti = frozenset(self.per_token)
        # per le somiglianze: parole raggruppate per le prime due lettere
        self.iniziali = {}
        for t in self.token_noti:
            if len(t) >= 4 and t.isalpha():
                self.iniziali.setdefault(t[:2], []).append(t)
        self.compatti_iniziali = {}
        for c in self.compatti:
            if len(c) >= 6:
                self.compatti_iniziali.setdefault(c[:2], []).append(c)
        self._simili = {}

    def simile(self, parola, compatto=False):
        """La parola nota più simile (rapporto di difflib ≥ 0.85, stesse prime due lettere), o None."""
        chiave = (parola, compatto)
        if chiave in self._simili:
            return self._simili[chiave]
        soglia = 0.88 if compatto else 0.85
        lista = (self.compatti_iniziali if compatto else self.iniziali).get(parola[:2], ())
        n = len(parola)
        cand = [t for t in lista if 0.74 * n <= len(t) <= n / 0.74]
        best = None
        if cand:
            sm = difflib.SequenceMatcher(None, "", parola, autojunk=False)
            for t in cand:
                sm.set_seq1(t)
                if sm.real_quick_ratio() >= soglia and sm.quick_ratio() >= soglia:
                    r = sm.ratio()
                    if r >= soglia and (best is None or r > best[1]):
                        best = (t, r)
        self._simili[chiave] = best
        return best


def _unisci(base, nuovo):
    """Unisce le definizioni di ``nuovo`` in ``base`` (liste e termini si sommano, il resto si sostituisce)."""
    for c, d in (nuovo or {}).items():
        if not isinstance(d, dict) or str(c).startswith("//"):
            continue
        b = base.setdefault(c, {})
        for k, v in d.items():
            if k in ("termini", "sistemi"):
                dest = b.setdefault(k, {})
                for lingua, lst in (v or {}).items():
                    cur = dest.setdefault(lingua, [])
                    cur.extend(x for x in (lst if isinstance(lst, list) else [lst]) if x not in cur)
            elif k in _CHIAVI_LISTA:
                cur = b.setdefault(k, [])
                cur.extend(x for x in (v if isinstance(v, list) else [v]) if x not in cur)
            elif k in ("canonico", "descrizioni"):
                b.setdefault(k, {}).update(v or {})
            else:
                b[k] = v
    return base


def _forma_extra(extra):
    """Termini passati al momento: {"concetto": ["t1", ...]} oppure {"concetto": {lingua: [...]}}
    oppure definizioni complete."""
    out = {}
    for c, v in (extra or {}).items():
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple)):
            out[c] = {"termini": {"xx": list(v)}}
        elif isinstance(v, dict):
            if any(k in v for k in ("termini", "sistemi", "abbreviazioni", "deboli", "codici", "descrizione")):
                out[c] = v
            else:
                out[c] = {"termini": {k: (x if isinstance(x, list) else [x]) for k, x in v.items()}}
    return out


@lru_cache(maxsize=1)
def _integrato():
    defs = {}
    for nome in sorted(os.listdir(CARTELLA)):
        if nome.endswith(".json"):
            with open(os.path.join(CARTELLA, nome), encoding="utf-8") as f:
                _unisci(defs, json.load(f))
    return defs


# ============================================================================ vocabolario
class Vocabolario:
    """Vocabolario integrato + termini dell'utente (``file_utente``, predefinito
    ~/.stratigrafia3d/vocabolario.json; False per nessuno) + termini passati al momento (``extra``,
    per esempio da una ricetta). I termini dell'utente e della ricetta prevalgono su quelli integrati."""

    def __init__(self, file_utente=None, extra=None, integrato=True):
        self.file_utente = FILE_UTENTE if file_utente is None else (file_utente or None)
        self.errori = []
        self._base = _integrato() if integrato else {}
        self._utente = self._leggi_utente()
        self._extra = _unisci({}, _forma_extra(extra))
        self._costruisci()

    # ------------------------------------------------------------------ costruzione
    def _leggi_utente(self):
        p = self.file_utente
        if not p or not os.path.exists(p):
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return _unisci({}, d) if isinstance(d, dict) else {}
        except (OSError, ValueError) as e:
            self.errori.append(f"Vocabolario dell'utente illeggibile ({p}): {e}")
            return {}

    def _costruisci(self):
        defs = {}
        for fonte in (self._base, self._utente, self._extra):
            _unisci(defs, json.loads(json.dumps(fonte)))
        self._ordine = {c: i for i, c in enumerate(defs)}
        for c, d in defs.items():
            d.setdefault("descrizione", f"«{c}»")
            amb = set(d.get("ambiti") or (["valore"] if d.get("campo") else _AMBITI_NOMI))
            if amb & {"layer", "tabella"}:
                amb.add("file")
            if d.get("campo"):
                amb.add("valore")
            d["_ambiti"] = amb
        self._def = defs
        voci = []
        for origine, fonte in (("integrato", self._base), ("utente", self._utente), ("ricetta", self._extra)):
            for c, d in fonte.items():
                voci.extend(_voci(c, d, origine))
        self._nomi = _Indice(voci, rumore=True, codici=False)
        self._valori = _Indice([v for v in voci if defs[v.concetto].get("campo")], rumore=False, codici=True)
        self._pattern = []
        for c, d in defs.items():
            for p in d.get("pattern") or []:
                try:
                    self._pattern.append((re.compile(p), _Voce(c, p, "pattern", "", "integrato")))
                except re.error as e:
                    self.errori.append(f"Espressione non valida per «{c}»: {p} ({e})")
        self._esclusioni = {c: [t for t in (_token(e, True) for e in d.get("esclusioni") or []) if t]
                            for c, d in defs.items()}
        self._cache = {}

    def estendi(self, extra):
        """Aggiunge termini per questa sessione (non salvati): {"concetto": ["termine", ...]}."""
        _unisci(self._extra, _forma_extra(extra))
        self._costruisci()

    def aggiungi(self, concetto, termine, lingua="xx", descrizione=None, ambiti=None):
        """Aggiunge un termine al vocabolario dell'utente e lo salva nel suo file. Per un concetto nuovo
        servono ``descrizione`` (e facoltativamente ``ambiti``)."""
        if concetto not in self._def and not descrizione:
            raise KeyError(f"Concetto sconosciuto: «{concetto}»")
        dati = {}
        p = self.file_utente
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    dati = json.load(f)
            except (OSError, ValueError):
                dati = {}
        if not isinstance(dati, dict):
            dati = {}
        d = dati.setdefault(concetto, {})
        if descrizione:
            d["descrizione"] = descrizione
        if ambiti:
            d["ambiti"] = list(ambiti)
        lst = d.setdefault("termini", {}).setdefault(lingua, [])
        if termine not in lst:
            lst.append(termine)
        if p:
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dati, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        self._utente = _unisci({}, dati)
        self._costruisci()

    # ------------------------------------------------------------------ informazioni
    def concetti(self, ambito=None):
        """I concetti noti (per un ambito, se indicato)."""
        return [c for c, d in self._def.items() if ambito is None or ambito in d["_ambiti"]]

    def descrizione(self, concetto, ambito=None):
        d = self._def.get(concetto) or {}
        return (d.get("descrizioni") or {}).get(ambito) or d.get("descrizione") or f"«{concetto}»"

    def canonico(self, concetto, ambito):
        """Nome usato dal programma per il concetto in quell'ambito (ruolo, foglio, colonna, valore)."""
        d = self._def.get(concetto) or {}
        c = (d.get("canonico") or {}).get(ambito)
        if c is None and ambito == "valore" and d.get("campo"):
            c = concetto
        return c

    def termini(self, concetto):
        """Tutti i termini di un concetto, per lingua o sistema."""
        d = self._def.get(concetto) or {}
        out = {k: list(v) for k, v in (d.get("termini") or {}).items()}
        out.update({k: list(v) for k, v in (d.get("sistemi") or {}).items()})
        for k in ("abbreviazioni", "deboli", "codici"):
            if d.get(k):
                out[k] = list(d[k])
        return out

    # ------------------------------------------------------------------ riconoscimento
    def _confronta(self, idx, N, metti, fattore=1.0, simile=False):
        sig = tuple(t for t in N if t not in QUALIFICATORI and t not in UNITA) or N
        nucleo = tuple(t for t in sig if t not in PAROLE_VUOTE) or sig
        lettere = sum(len(t) for t in nucleo) or 1
        modo = "simile" if simile else None
        for v in idx.esatti.get(N, ()):
            metti(v, 0.97 * PESI[v.tipo] * fattore, modo or "esatto")
        for v in idx.compatti.get("".join(N), ()):
            metti(v, 0.95 * PESI[v.tipo] * fattore, modo or "esatto")
        if sig != N:
            for v in idx.esatti.get(sig, ()):
                metti(v, 0.93 * PESI[v.tipo] * fattore, modo or "esatto")
            for v in idx.compatti.get("".join(sig), ()):
                metti(v, 0.91 * PESI[v.tipo] * fattore, modo or "esatto")
        if not simile:
            testo = " ".join(N)
            for rx, v in self._pattern:
                if rx.search(testo):
                    metti(v, 0.85 * fattore, "pattern")
        insN, insS = set(N), set(sig)
        chiavi = [t for t in insN if t not in PAROLE_VUOTE and t not in QUALIFICATORI and t not in UNITA] or insN
        viste = set()
        for t in chiavi:
            for v in idx.per_token.get(t, ()):
                if id(v) in viste:
                    continue
                viste.add(id(v))
                T = v.token
                if T == N or T == sig or v.tipo in ("debole", "codice"):
                    continue
                corto = len(T) == 1 and len(T[0]) <= 2
                if insN.issuperset(T):
                    if corto and v.tipo in ("abbreviazione", "codice"):
                        continue
                    if len(T) > 1:
                        spec = min(1.0 + 0.03 * (len(T) - 1), 1.1)
                    else:
                        spec = 0.7 if corto else (0.85 if len(T[0]) == 3 else 1.0)
                    cop = min(1.0, v.lettere / lettere)
                    s = 0.9 * PESI[v.tipo] * spec * (0.5 + 0.5 * cop) * (1.0 if _in_ordine(T, N) else 0.9)
                    metti(v, min(s, 0.92) * fattore, modo or "contiene")
                elif insS.issubset(T) and not (len(sig) == 1 and len(sig[0]) <= 2):
                    s = 0.55 * PESI[v.tipo] * min(1.0, lettere / max(len("".join(T)), 1)) ** 2
                    metti(v, s * fattore, modo or "parte")

    def _abbina(self, N, ambito, lingue=None, campo=None):
        chiave = (N, ambito, lingue, campo)
        if chiave in self._cache:
            return self._cache[chiave]
        idx = self._valori if ambito == "valore" else self._nomi
        defs = self._def
        ris = {}

        def metti(v, s, modo):
            d = defs.get(v.concetto)
            if d is None or ambito not in d["_ambiti"] or (campo is not None and d.get("campo") != campo):
                return
            if lingue and v.tipo == "termine" and v.origine == "integrato" and v.lingua not in lingue:
                return
            if s > ris.get(v.concetto, (0.0,))[0]:
                ris[v.concetto] = (s, v, modo)

        if N:
            self._confronta(idx, N, metti)
            if max((x[0] for x in ris.values()), default=0.0) < 0.8:
                # parole scritte in modo un po' diverso («Hoehe», «Contex Number»)
                N2, rmin = list(N), 1.0
                for i, t in enumerate(N):
                    if len(t) >= 4 and t.isalpha() and t not in idx.token_noti:
                        m = idx.simile(t)
                        if m:
                            N2[i], rmin = m[0], min(rmin, m[1])
                if tuple(N2) != N:
                    self._confronta(idx, tuple(N2), metti, 0.85 * rmin, simile=True)
                comp = "".join(t for t in N if t not in QUALIFICATORI)
                if len(comp) >= 6 and comp not in idx.compatti:
                    m = idx.simile(comp, compatto=True)
                    if m:
                        for v in idx.compatti[m[0]]:
                            metti(v, 0.85 * m[1] * PESI[v.tipo], "simile")
            for c in list(ris):
                if ris[c][2] != "esatto" and any(set(e) <= set(N) and _in_ordine(e, N)
                                                  for e in self._esclusioni.get(c, ())):
                    del ris[c]
        self._cache[chiave] = ris
        return ris

    def _leggi_contesto(self, contesto, ambito, lingue):
        contenitori, fratelli, geom = [], [], None
        if isinstance(contesto, str):
            contenitori = [("colonna" if ambito == "valore" else "file", contesto)]
        elif isinstance(contesto, dict):
            mappa = {"file": "file", "layer": "layer", "tabella": "tabella", "foglio": "tabella",
                     "contenitore": "file", "colonna": "colonna"}
            contenitori = [(mappa[k], v) for k, v in contesto.items() if k in mappa and v]
            fratelli = list(contesto.get("colonne") or [])
            geom = contesto.get("geometria")
        elif isinstance(contesto, (list, tuple, set)):
            fratelli = list(contesto)
        cont, fr, campo, campo_nome = {}, {}, None, None
        for amb, nome in contenitori:
            testo = os.path.basename(str(nome).replace("\\", "/")) if amb == "file" else str(nome)
            r = self._abbina(_token(testo, True), amb, lingue)
            for c, (s, _, _) in sorted(r.items(), key=lambda kv: -kv[1][0]):
                if s >= 0.6:
                    cont.setdefault(c, str(nome))
                    if amb == "colonna" and campo is None:
                        campo = _CAMPO_DA_COLONNA.get(c) or self._def[c].get("campo")
                        campo_nome = str(nome)
        for f in fratelli[:300]:
            r = self._abbina(_token(str(f), True), "colonna", lingue)
            if r:
                c, (s, _, _) = max(r.items(), key=lambda kv: kv[1][0])
                if s >= 0.8:
                    fr.setdefault(c, str(f))
        return cont, fr, geom, campo, campo_nome

    def riconosci(self, nome, ambito, contesto=None, lingue=None, soglia=0.3, massimo=5):
        """Concetti che ``nome`` può rappresentare nell'``ambito`` indicato («file», «layer», «tabella»,
        «colonna», «valore»), dal più probabile. ``contesto`` aiuta a scegliere: il nome del layer,
        della tabella o del file che contiene la colonna (stringa, o dict con «tabella», «layer»,
        «file», «colonna»), i nomi delle colonne vicine (lista, o «colonne» nel dict) e la
        «geometria» del layer («punto», «linea», «poligono»). ``lingue`` limita i termini alle lingue
        indicate (sigle, abbreviazioni e nomi dei sistemi valgono sempre)."""
        if ambito not in AMBITI:
            raise ValueError(f"Ambito sconosciuto: «{ambito}» (ammessi: {', '.join(AMBITI)})")
        if nome is None or (isinstance(nome, float) and nome != nome):
            return []
        testo = str(nome).strip()
        if ambito == "file":
            testo = os.path.basename(testo.replace("\\", "/")) or testo
        lingue = tuple(sorted(lingue)) if lingue else None
        ris = self._abbina(_token(testo, ambito != "valore"), ambito, lingue)
        righe = [[s, c, v, modo, None, False] for c, (s, v, modo) in ris.items()]
        if contesto and righe:
            cont, fr, geom, campo, campo_nome = self._leggi_contesto(contesto, ambito, lingue)
            for r in righe:
                d = self._def[r[1]]
                vicini = d.get("contesti") or ()
                x = next((cont[k] for k in vicini if k in cont), None)
                if x:
                    r[0] += 0.12
                    r[4] = x
                else:
                    x = next((fr[k] for k in vicini if k in fr), None)
                    if x:
                        r[0] += 0.06
                        r[4] = x
                if geom and d.get("geometrie") and ambito != "valore":
                    if geom in d["geometrie"]:
                        r[0] += 0.08
                        r[5] = True
                    else:
                        r[0] -= 0.1
                if ambito == "valore" and campo and d.get("campo") == campo:
                    r[0] += 0.15
                    r[4] = campo_nome
        righe.sort(key=lambda r: (-r[0], self._ordine.get(r[1], 0)))
        out = []
        for s, c, v, modo, nota, geo in righe:
            if s < soglia:
                break
            out.append(Riconoscimento(c, round(min(s, 1.0), 3), self._motivo(testo, v, modo, ambito, nota, geo),
                                      v.termine, v.lingua, self.canonico(c, ambito)))
            if massimo and len(out) >= massimo:
                break
        return out

    def migliore(self, nome, ambito, contesto=None, lingue=None, soglia=0.6):
        """Il riconoscimento più probabile, se supera ``soglia``; altrimenti None."""
        r = self.riconosci(nome, ambito, contesto, lingue, soglia=soglia, massimo=1)
        return r[0] if r else None

    def riconosci_valore(self, valore, concetto_campo=None, contesto=None, soglia=0.6):
        """Valore del programma per un valore dell'archivio: tipo di unità («Cut» -> «negativa»),
        rapporto («is cut by» -> «tagliato da», «=» -> «uguale a»), tipo di quota («top» -> «sup»).
        ``concetto_campo``: «tipo», «rapporto» o «tipo_quota». None se non riconosciuto."""
        if valore is None or (isinstance(valore, float) and valore != valore):
            return None
        testo = str(valore).strip()
        if not testo:
            return None
        campo = None
        if concetto_campo:
            k = " ".join(_token(str(concetto_campo), False))
            campo = _CAMPI.get(k, _CAMPI.get(str(concetto_campo), str(concetto_campo)))
        elif contesto:          # il nome della colonna dice di che vocabolario si tratta
            campo = self._leggi_contesto(contesto, "valore", None)[3]
        ris = self._abbina(_token(testo, False), "valore", None, campo)
        if not ris:
            return None
        c, (s, _, _) = min(ris.items(), key=lambda kv: (-kv[1][0], self._ordine.get(kv[0], 0)))
        return (self.canonico(c, "valore") or c) if s >= soglia else None

    def spiega(self, nome, ambito, contesto=None, lingue=None):
        """Spiegazione in italiano del riconoscimento migliore (con le alternative)."""
        ris = self.riconosci(nome, ambito, contesto, lingue, soglia=0.3, massimo=3)
        if not ris:
            return f"«{nome}»: nessun termine noto"
        p = ris[0]
        testo = f"{p.motivo} (attendibilità {round(p.punteggio * 100)}%)"
        if p.canonico:
            testo += f"; nel programma: «{p.canonico}»"
        if len(ris) > 1:
            testo += ". Altre possibilità: " + ", ".join(
                f"{self.descrizione(r.concetto, ambito)} ({round(r.punteggio * 100)}%)" for r in ris[1:])
        return testo

    def _motivo(self, nome, v, modo, ambito, nota=None, geo=False):
        desc = self.descrizione(v.concetto, ambito)
        if modo == "pattern":
            testo = f"«{nome}» ha la forma di una sigla per {desc}"
        else:
            if v.origine == "utente":
                origine = "un termine aggiunto dall'utente"
            elif v.origine == "ricetta":
                origine = "un termine indicato dalla ricetta"
            elif v.tipo == "sistema":
                origine = f"il nome usato da {v.lingua}"
            elif v.tipo in ("abbreviazione", "codice"):
                origine = "un'abbreviazione comune"
            elif v.tipo == "debole":
                origine = "un termine generico"
            elif v.lingua in LINGUE:
                origine = f"un termine {LINGUE[v.lingua]}"
            else:
                origine = "un termine noto"
            if modo == "esatto":
                testo = f"«{nome}» è {origine} per {desc}"
            elif modo == "contiene":
                testo = f"«{nome}» contiene «{v.termine}», {origine} per {desc}"
            elif modo == "parte":
                testo = f"«{nome}» è parte di «{v.termine}», {origine} per {desc}"
            else:
                testo = f"«{nome}» somiglia a «{v.termine}», {origine} per {desc}"
            if v.tipo == "debole":
                testo += " (indizio debole)"
        if nota:
            testo += f"; il contesto («{nota}») lo conferma"
        if geo:
            testo += "; la geometria lo conferma"
        return testo


# ============================================================================ funzioni comode
_PREDEFINITO = None


def vocabolario():
    """Il vocabolario condiviso (integrato + file dell'utente), creato alla prima richiesta."""
    global _PREDEFINITO
    if _PREDEFINITO is None:
        _PREDEFINITO = Vocabolario()
    return _PREDEFINITO


def ricarica():
    """Dimentica il vocabolario condiviso (per rileggere il file dell'utente)."""
    global _PREDEFINITO
    _PREDEFINITO = None


def riconosci(nome, ambito, contesto=None, lingue=None, **kw):
    """Vedi :meth:`Vocabolario.riconosci`."""
    return vocabolario().riconosci(nome, ambito, contesto, lingue, **kw)


def riconosci_valore(valore, concetto_campo=None, contesto=None):
    """Vedi :meth:`Vocabolario.riconosci_valore`."""
    return vocabolario().riconosci_valore(valore, concetto_campo, contesto)


def spiega(nome, ambito, contesto=None, lingue=None):
    """Vedi :meth:`Vocabolario.spiega`."""
    return vocabolario().spiega(nome, ambito, contesto, lingue)


def aggiungi(concetto, termine, lingua="xx", **kw):
    """Vedi :meth:`Vocabolario.aggiungi`."""
    return vocabolario().aggiungi(concetto, termine, lingua, **kw)
