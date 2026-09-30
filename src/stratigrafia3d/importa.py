# -*- coding: utf-8 -*-
"""
Import flessibile: legge file di scavo "come vengono" e propone un abbinamento
(quale layer contiene le US, quale campo è il numero di US, da dove viene la quota, ...).

    info = esamina(["rilievo.dxf", "schede.xlsx"])     # cosa c'è nei file
    abb = proponi(["rilievo.dxf", "schede.xlsx"])     # abbinamento proposto, modificabile
    scavo = applica(abb)                             # Scavo pronto per verifica e ricostruzione

L'abbinamento è serializzabile in JSON: si salva nel progetto e come profilo riutilizzabile.

Formati: GeoPackage, shapefile, GeoJSON, DXF (poligoni da polilinee chiuse, testi come
etichette o come quote), CSV di punti; Excel (.xlsx/.xls/.ods) e CSV per le schede.
"""
import datetime as _dt
import json
import os
import re
from dataclasses import dataclass, field, asdict

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

from . import schema as sc

EST_GIS = {".gpkg", ".shp", ".geojson", ".json", ".dxf"}
EST_TAB = {".xlsx", ".xlsm", ".xls", ".ods"}
RUOLI = ["us", "usm", "quote", "profili", "area", "sezioni", "sezioni_disegno", "reperti", "campioni", "ignora"]
NOME_LAYER = {"us": sc.L_US, "usm": sc.L_USM, "quote": sc.L_QUOTE, "profili": sc.L_PROFILI, "area": sc.L_AREA,
              "sezioni": sc.L_SEZIONI, "sezioni_disegno": sc.L_SEZ_DISEGNO, "reperti": sc.L_RS,
              "campioni": sc.L_CAMPIONI}

SINONIMI_TIPO = {
    "sup": ["sup", "superiore", "superficie", "top", "tetto", "s", "q.sup", "quota superiore", "q sup", "upper"],
    "inf": ["inf", "inferiore", "base", "bottom", "letto", "i", "q.inf", "quota inferiore", "q inf", "lower"],
    "taglio": ["taglio", "cut", "interfaccia", "t", "fondo taglio", "fondo"],
    "orlo": ["orlo", "rim", "bordo", "ciglio", "margine"],
    "rasatura": ["rasatura", "cresta", "crest", "top muro", "sommità", "sommita"],
    "fondazione": ["fondazione", "base muro", "foundation", "risega"],
}
_SIN = {s: k for k, v in SINONIMI_TIPO.items() for s in v}
PAROLE_RUOLO = [
    ("ignora", ["griglia", "grid", "quadrett", "layer_styles"]),
    ("usm", ["usm", "mur", "wall", "muratur", "struttur"]),
    ("area", ["area_scavo", "limite", "limit", "saggio", "trincea", "trench", "perimetr", "area"]),
    ("profili", ["profil", "interfacc"]),
    ("sezioni_disegno", ["sezioni_disegno", "disegno_sez"]),
    ("sezioni", ["sezion", "sez", "section"]),
    ("reperti", ["reperti", "reperto", "find", "rs_"]),
    ("campioni", ["campion", "sample"]),
    ("quote", ["quot", "punti", "point", "spot", "height", "rilievo_punti", "elev"]),
    ("us", ["us", "strat", "context", "unita", "unità", "unit", "layer"]),
]
ALIAS_UNITA = ["us", "n_us", "num_us", "numero_us", "n. us", "n.us", "context", "su", "unita", "unità", "usm",
               "n_usm", "numero", "code", "codice", "layer"]
ALIAS_QUOTA = ["quota", "z", "q", "elev", "elevation", "h", "altezza", "quota_m", "zeta", "height"]
ALIAS_SEZIONE = ["sezione", "sez", "section", "nome", "name"]
RAPPORTI_COLONNE = ["copre", "coperto da", "taglia", "tagliato da", "riempie", "riempito da", "si appoggia a",
                    "gli si appoggia", "si lega a", "uguale a"]
_INT_RE = re.compile(r"(\d{1,7})")


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower().replace("_", " "))


def _intero(v):
    """Numero di US da un valore qualsiasi: 1005, '1005', 'US 1005', 'US_1005', 1005.0."""
    if v is None:
        return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else int(round(v))
    m = _INT_RE.search(str(v))
    return int(m.group(1)) if m else None


def _numero(v):
    try:
        x = float(str(v).replace(",", "."))
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


# ============================================================================ lettura
@dataclass
class InfoLayer:
    sorgente: str
    layer: str
    geometria: str          # poligono | linea | punto | testo | misto | nessuna
    n: int
    ha_z: bool
    campi: list
    esempi: dict
    crs: str = None


def _tipo_geom(g):
    if g is None or g.is_empty:
        return "nessuna"
    t = g.geom_type
    if "Polygon" in t:
        return "poligono"
    if "Line" in t:
        return "linea"
    if "Point" in t:
        return "punto"
    return "misto"


def _chiuso(g):
    if g is None or g.geom_type != "LineString":
        return False
    c = list(g.coords)
    return len(c) >= 4 and np.allclose(c[0][:2], c[-1][:2], atol=1e-6)


def _dxf_gruppi(path):
    """Il DXF ha un solo layer GDAL ('entities'): lo si divide per layer CAD (con i numeri
    sostituiti da #, così US_1005, US_1006… diventano un gruppo) e per tipo di entità."""
    df = pyogrio.read_dataframe(path)
    kinds = []
    for g, t in zip(df.geometry, df.get("Text", pd.Series([None] * len(df)))):
        if isinstance(t, str) and t.strip():
            kinds.append("testo")
        elif _chiuso(g) or (g is not None and "Polygon" in g.geom_type):
            kinds.append("poligono")
        else:
            kinds.append(_tipo_geom(g))
    df["_tipo"] = kinds
    df["_gruppo"] = [re.sub(r"\d+", "#", str(l)) for l in df["Layer"]]
    df["_chiave"] = df["_gruppo"] + " · " + df["_tipo"]
    return df


def _leggi_csv_punti(path):
    df = pd.read_csv(path, sep=None, engine="python")
    low = {_norm(c): c for c in df.columns}
    cx = next((low[k] for k in ("x", "e", "est", "east", "easting") if k in low), None)
    cy = next((low[k] for k in ("y", "n", "nord", "north", "northing") if k in low), None)
    if cx is None or cy is None:
        return None
    cz = next((low[k] for k in ("z", "quota", "q", "h", "elev") if k in low), None)
    zs = df[cz].map(_numero) if cz else None
    geom = [Point(x, y, z) if zs is not None and z is not None else Point(x, y)
            for x, y, z in zip(df[cx], df[cy], zs if zs is not None else [None] * len(df))]
    return gpd.GeoDataFrame(df, geometry=geom)


def _csv_e_punti(path):
    try:
        return _leggi_csv_punti(path) is not None
    except Exception:
        return False


def leggi_layer(sorgente, layer):
    """GeoDataFrame del layer indicato (per il DXF, del gruppo 'CAD · tipo')."""
    ext = os.path.splitext(sorgente)[1].lower()
    if ext == ".dxf":
        df = _dxf_gruppi(sorgente)
        sub = df[df["_chiave"] == layer].copy()
        if sub.empty:
            return gpd.GeoDataFrame(sub)
        if layer.endswith("poligono"):
            sub["geometry"] = [Polygon(g.coords) if g.geom_type == "LineString" else g for g in sub.geometry]
        return gpd.GeoDataFrame(sub.drop(columns=["_tipo", "_gruppo", "_chiave"]), geometry="geometry")
    if ext == ".csv":
        return _leggi_csv_punti(sorgente)
    return gpd.read_file(sorgente, layer=layer)


def _info(sorgente, layer, g):
    tipi = {_tipo_geom(x) for x in g.geometry if x is not None}
    if "Text" in g.columns and g["Text"].notna().all() and len(g):
        geom = "testo"
    else:
        geom = tipi.pop() if len(tipi) == 1 else ("misto" if tipi else "nessuna")
    ha_z = bool(len(g) and g.geometry.has_z.any() and
                np.ptp([c[2] for x in g.geometry if x is not None and x.has_z for c in _coords(x)][:5000] or [0]) > 0)
    campi = [c for c in g.columns if c != "geometry"]
    esempi = {c: [str(v) for v in g[c].dropna().unique()[:6]] for c in campi}
    crs = g.crs.to_string() if getattr(g, "crs", None) is not None else None
    return InfoLayer(sorgente, layer, geom, int(len(g)), ha_z, campi, esempi, crs)


def _coords(g):
    if g.geom_type == "Point":
        return [g.coords[0]]
    if g.geom_type in ("LineString", "LinearRing"):
        return list(g.coords)
    if g.geom_type == "Polygon":
        return list(g.exterior.coords)
    out = []
    for p in getattr(g, "geoms", []):
        out += _coords(p)
    return out


def esamina(files):
    """Elenco dei layer (InfoLayer) e dei fogli trovati nei file."""
    layers, tabelle = [], {}
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext == ".dxf":
            df = _dxf_gruppi(f)
            for k in sorted(df["_chiave"].unique()):
                layers.append(_info(f, k, leggi_layer(f, k)))
        elif ext in EST_GIS:
            for nome, _ in pyogrio.list_layers(f):
                if nome.startswith(("s3d_", "tab_", "layer_styles")):
                    continue
                layers.append(_info(f, nome, gpd.read_file(f, layer=nome)))
        elif ext == ".csv" and _csv_e_punti(f):
            layers.append(_info(f, os.path.basename(f), _leggi_csv_punti(f)))
        elif ext in EST_TAB or ext == ".csv":
            tabelle[f] = leggi_tabelle(f)
    return layers, tabelle


def leggi_tabelle(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return {os.path.splitext(os.path.basename(path))[0]: pd.read_csv(path, sep=None, engine="python")}
    return pd.read_excel(path, sheet_name=None)


# ============================================================================ abbinamento
@dataclass
class RuoloLayer:
    sorgente: str
    layer: str
    ruolo: str = "ignora"
    campo_unita: str = None        # campo con il numero di US (anche testo tipo "US 1005")
    testi_unita: str = None        # DXF: gruppo di testi da usare come etichette delle US
    campo_tipo: str = None         # quote: tipo di quota; profili: interfaccia
    tipo_predefinito: str = None   # se manca campo_tipo
    quota_da: str = "z"            # "z" | "campo:<nome>" | "testo"
    campo_sezione: str = None
    motivo: str = ""


@dataclass
class Abbinamento:
    layers: list = field(default_factory=list)
    tabella: str = None                     # file Excel/CSV delle schede
    foglio_us: str = None
    colonne_us: dict = field(default_factory=dict)      # nome canonico -> colonna del file
    foglio_usm: str = None
    colonne_usm: dict = field(default_factory=dict)
    rapporti: dict = field(default_factory=lambda: {"modo": "nessuno"})
    crs: str = None
    note: list = field(default_factory=list)

    def a_json(self):
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def da_json(cls, s):
        d = json.loads(s) if isinstance(s, str) else dict(s)
        d["layers"] = [RuoloLayer(**x) for x in d.get("layers", [])]
        return cls(**d)

    def salva_profilo(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.a_json())

    @classmethod
    def carica_profilo(cls, path):
        return cls.da_json(open(path, encoding="utf-8").read())


def _punteggio_unita(serie, noti, nome):
    vals = serie.dropna()
    if len(vals) == 0:
        return 0.0
    ints = [_intero(v) for v in vals]
    ok = [i for i in ints if i is not None]
    frac = len(ok) / len(vals)
    if frac < 0.6:
        return 0.0
    if noti:
        overlap = len(set(ok) & noti) / max(len(set(ok)), 1)
    else:
        overlap = 0.4 if len(set(ok)) > 1 else 0.1
    bonus = 0.3 if _norm(nome) in ALIAS_UNITA or _norm(nome).startswith(("us", "n us", "num")) else 0.0
    if pd.api.types.is_float_dtype(serie) and not np.allclose(vals, np.round(vals)):
        return 0.0            # quote, non numeri di US
    return frac * 0.3 + overlap + bonus


def _campo_unita(g, noti):
    best, sb = None, 0.0
    for c in g.columns:
        if c in ("geometry", "Text", "SubClasses", "Linetype", "EntityHandle", "PaperSpace", "fid"):
            continue
        s = _punteggio_unita(g[c], noti, c)
        if s > sb:
            best, sb = c, s
    return (best, sb) if sb >= 0.45 else (None, sb)


def _campo_tipo(g):
    for c in g.columns:
        if c == "geometry":
            continue
        vals = g[c].dropna().astype(str).map(_norm)
        if len(vals) and vals.map(lambda v: v in _SIN).mean() > 0.8:
            return c
    return None


def _campo_quota(g):
    for c in g.columns:
        if c == "geometry" or _norm(c) not in ALIAS_QUOTA:
            continue
        v = g[c].map(_numero).dropna()
        if len(v) and v.std() > 0.01:
            return c
    for c in g.columns:     # campo numerico decimale con valori da quota
        if c != "geometry" and pd.api.types.is_float_dtype(g[c]):
            v = g[c].dropna()
            if len(v) > 3 and v.std() > 0.01 and not np.allclose(v, np.round(v)):
                return c
    return None


def _ruolo_da_nome(nome, geometria=None):
    """Ruolo suggerito dal nome del layer/file. Se più parole corrispondono, per i poligoni
    vince l'ordine ignora > usm > us > area (es. "US_limiti" sono limiti di US, non dell'area)."""
    n = _norm(nome)
    trovati = {}
    for ruolo, parole in PAROLE_RUOLO:
        for p in parole:
            if re.search(r"(^|[^a-z])" + re.escape(p), n):
                trovati.setdefault(ruolo, p)
                break
    if not trovati:
        return None, None
    ordine = ["ignora", "usm", "us", "area", "sezioni_disegno"] if geometria == "poligono" else \
        [r for r, _ in PAROLE_RUOLO]
    for r in ordine:
        if r in trovati:
            return r, trovati[r]
    r = next(iter(trovati))
    return r, trovati[r]


def _schede(tabelle):
    """Trova il foglio delle US, quello delle USM, i numeri noti e il modo dei rapporti."""
    best = (None, None, 0)
    usm = (None, None, 0)
    for nome, df in tabelle.items():
        for c in df.columns:
            nc = _norm(c)
            vals = df[c].dropna()
            if not len(vals):
                continue
            frac = np.mean([_intero(v) is not None for v in vals])
            if frac < 0.8:
                continue
            if nc in ("us", "n us", "n. us", "numero us", "num us", "n.us", "context", "su", "unità stratigrafica",
                      "unita stratigrafica"):
                s = frac + (0.5 if _norm(nome) in ("us", "schede us", "schede", "unità stratigrafiche") else 0)
                if s > best[2]:
                    best = (nome, c, s)
            if nc in ("usm", "n usm", "n. usm", "numero usm"):
                s = frac + (0.5 if _norm(nome) in ("usm", "schede usm") else 0)
                if s > usm[2]:
                    usm = (nome, c, s)
    return best[:2], usm[:2]


def _colonne_scheda(df, col_id, canon_id):
    """Abbina le colonne note della scheda (tipo, spessore, margini, fase, ...)."""
    out = {canon_id: col_id}
    candidati = {
        sc.C_TIPO: ["tipo", "tipo us", "positiva/negativa", "natura"],
        sc.C_CATEGORIA: ["categoria", "definizione generale", "tipo di unità"],
        sc.C_SPESSORE: ["spessore medio stimato (m)", "spessore", "spessore medio", "spessore (m)", "spessore medio (m)",
                        "potenza", "spessore (cm)"],
        sc.C_MARGINI: ["margini", "limiti", "limite", "limiti/margini"],
        sc.C_FASE: ["fase", "phase"],
        sc.C_COLORE: ["colore hex", "colore rgb", "hex"],
        "Definizione": ["definizione", "descrizione breve", "interpretazione sintetica"],
        sc.C_BASE_USM: ["quota base usata (rilevata o stimata)", "quota fondazione", "quota base", "base"],
    }
    low = {_norm(c): c for c in df.columns}
    for canon, alias in candidati.items():
        if canon in df.columns:
            out[canon] = canon
            continue
        for a in alias:
            if _norm(a) in low:
                out[canon] = low[_norm(a)]
                break
    return out


def _rapporti(tabelle, foglio_us):
    for nome, df in tabelle.items():
        cols = list(df.columns)
        for i, c in enumerate(cols):
            v = df[c].dropna().astype(str).map(_norm)
            if len(v) >= 2 and v.isin(set(RAPPORTI_COLONNE)).mean() > 0.6 and 0 < i < len(cols) - 1:
                return {"modo": "foglio", "foglio": nome, "colonne": [cols[i - 1], c, cols[i + 1]]}
    if foglio_us and foglio_us in tabelle:
        df = tabelle[foglio_us]
        mappa = {c: _norm(c) for c in df.columns if _norm(c) in RAPPORTI_COLONNE}
        if mappa:
            return {"modo": "colonne", "foglio": foglio_us, "colonne": mappa}
    return {"modo": "nessuno"}


def proponi(files):
    """Abbinamento proposto per i file indicati, con il motivo di ogni scelta."""
    layers_info, tabelle_per_file = esamina(files)
    abb = Abbinamento()
    noti = set()
    if tabelle_per_file:
        # il file con il foglio US più convincente
        for f, tabs in tabelle_per_file.items():
            (fus, cus), (fusm, cusm) = _schede(tabs)
            if fus and abb.tabella is None:
                abb.tabella, abb.foglio_us = f, fus
                abb.colonne_us = _colonne_scheda(tabs[fus], cus, sc.C_US)
                noti |= {_intero(v) for v in tabs[fus][cus].dropna()}
                if fusm:
                    abb.foglio_usm = fusm
                    abb.colonne_usm = _colonne_scheda(tabs[fusm], cusm, sc.C_USM)
                    noti |= {_intero(v) for v in tabs[fusm][cusm].dropna()}
                abb.rapporti = _rapporti(tabs, fus)
                abb.note.append(f"Schede US nel foglio «{fus}» (colonna «{cus}»)" +
                                (f", USM nel foglio «{fusm}»" if fusm else ""))
                r = abb.rapporti
                abb.note.append({"foglio": f"Rapporti dal foglio «{r.get('foglio')}»",
                                 "colonne": f"Rapporti dalle colonne della scheda US ({', '.join(r.get('colonne', {}))})",
                                 "nessuno": "Nessun rapporto stratigrafico trovato: le basi non saranno agganciate"}[r["modo"]])
        if abb.tabella is None:
            abb.note.append("Nessun foglio con i numeri di US: le schede verranno create dai poligoni")
    noti.discard(None)
    testi = [li for li in layers_info if li.geometria == "testo"]
    for li in layers_info:
        r = RuoloLayer(li.sorgente, li.layer)
        nome = f"{os.path.splitext(os.path.basename(li.sorgente))[0]} {li.layer}"
        ruolo, parola = _ruolo_da_nome(li.layer if li.sorgente.lower().endswith((".gpkg", ".dxf")) else nome,
                                       li.geometria)
        g = leggi_layer(li.sorgente, li.layer)
        motivo = []
        if li.geometria == "poligono":
            if ruolo not in ("us", "usm", "area", "sezioni_disegno", "ignora"):
                ruolo = "us"
                motivo.append("poligoni")
            else:
                motivo.append(f"nome «{parola}»")
            if li.crs is None and li.layer == sc.L_SEZ_DISEGNO:
                ruolo = "sezioni_disegno"
        elif li.geometria == "punto":
            if ruolo not in ("quote", "reperti", "campioni", "ignora"):
                ruolo = "quote" if (li.ha_z or _campo_quota(g)) else "ignora"
                motivo.append("punti con quota" if ruolo == "quote" else "punti senza quota")
            else:
                motivo.append(f"nome «{parola}»")
        elif li.geometria == "linea":
            if ruolo not in ("profili", "sezioni", "ignora"):
                ruolo = "profili" if li.ha_z else "sezioni"
                motivo.append("linee 3D" if li.ha_z else "linee 2D")
            else:
                motivo.append(f"nome «{parola}»")
        elif li.geometria == "testo":
            vals = g["Text"].map(_numero).dropna()
            if len(vals) >= 0.8 * len(g) and len(vals) and (vals % 1 != 0).mean() > 0.5:
                ruolo, r.quota_da = "quote", "testo"
                motivo.append("testi con valori di quota")
            else:
                ruolo = "ignora"
                motivo.append("testi (usabili come etichette)")
        else:
            ruolo = "ignora"
        r.ruolo = ruolo
        if ruolo in ("us", "usm", "quote", "profili", "reperti", "campioni", "sezioni_disegno"):
            campo, punti = _campo_unita(g, noti)
            if campo:
                r.campo_unita = campo
                motivo.append(f"numero di US dal campo «{campo}»")
            elif ruolo in ("us", "usm") and testi:
                r.testi_unita = testi[0].layer
                motivo.append(f"numero di US dalle etichette «{testi[0].layer}»")
            elif ruolo == "quote":
                motivo.append("US assegnata dalla posizione (solo dove un solo poligono contiene il punto)")
        if ruolo == "quote":
            if r.quota_da != "testo":
                if not li.ha_z:
                    cq = _campo_quota(g)
                    r.quota_da = f"campo:{cq}" if cq else "z"
                    if cq:
                        motivo.append(f"quota dal campo «{cq}»")
            ct = _campo_tipo(g)
            if ct:
                r.campo_tipo = ct
                motivo.append(f"tipo di quota dal campo «{ct}»")
            else:
                n = _norm(li.layer + " " + os.path.basename(li.sorgente))
                r.tipo_predefinito = "inf" if re.search(r"inf|base|bottom|letto", n) else \
                    ("rasatura" if "rasatura" in n else "sup")
                motivo.append(f"tipo di quota «{r.tipo_predefinito}» per tutti i punti")
        if ruolo == "profili":
            ct = _campo_tipo(g)
            if ct:
                r.campo_tipo = ct
            else:
                r.tipo_predefinito = "sup"
        if ruolo in ("sezioni", "profili", "sezioni_disegno"):
            low = {_norm(c): c for c in g.columns}
            r.campo_sezione = next((low[a] for a in ALIAS_SEZIONE if a in low), None)
        r.motivo = "; ".join(motivo)
        abb.layers.append(r)
    crs = [li.crs for li in layers_info if li.crs]
    abb.crs = crs[0] if crs else None
    return abb


# ============================================================================ applicazione
def _unita_da_testi(g, sorgente, gruppo_testi):
    t = leggi_layer(sorgente, gruppo_testi)
    pts = [(geom, _intero(txt)) for geom, txt in zip(t.geometry, t["Text"]) if _intero(txt) is not None]
    out = []
    for poly in g.geometry:
        dentro = [n for p, n in pts if poly.contains(Point(p.x, p.y))]
        out.append(dentro[0] if dentro else None)
    return out


def _tipo_canonico(v, predefinito):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return predefinito
    return _SIN.get(_norm(v), predefinito)


def applica(abb, log=None):
    """Costruisce uno Scavo canonico applicando l'abbinamento."""
    from .progetto import Scavo, _sha256
    log = log or (lambda *a: None)
    s = Scavo()
    note = []
    crs = abb.crs
    raccolti = {}          # ruolo -> list di GeoDataFrame canonici

    def a_crs(g):
        if crs and g.crs is not None and g.crs.to_string() != crs:
            return g.to_crs(crs)
        if crs and g.crs is None:
            return g.set_crs(crs, allow_override=True)
        return g

    for r in abb.layers:
        if r.ruolo == "ignora":
            continue
        g = leggi_layer(r.sorgente, r.layer)
        if g is None or g.empty:
            continue
        g = a_crs(gpd.GeoDataFrame(g, geometry="geometry")) if r.ruolo != "sezioni_disegno" else gpd.GeoDataFrame(g)
        if r.campo_unita:
            unita = [_intero(v) for v in g[r.campo_unita]]
        elif r.testi_unita:
            unita = _unita_da_testi(g, r.sorgente, r.testi_unita)
        else:
            unita = [None] * len(g)
        g = g.assign(_u=unita)
        if r.ruolo in ("us", "usm"):
            g = g[g._u.notna() & g.geometry.notna()]
            mancanti = len(unita) - len(g)
            if mancanti:
                note.append(f"{mancanti} poligoni di «{r.layer}» senza numero di US: ignorati")
            campo = sc.F_US if r.ruolo == "us" else sc.F_USM
            parts = []
            dxf = r.sorgente.lower().endswith(".dxf")
            for u, sub in g.groupby("_u"):
                pezzi = [x.buffer(0) for x in sub.geometry]
                if dxf:     # nel CAD un anello dentro un altro è un buco (regola pari-dispari)
                    geom = pezzi[0]
                    for x in pezzi[1:]:
                        geom = geom.symmetric_difference(x)
                    geom = geom.buffer(0)
                else:
                    geom = unary_union(pezzi)
                if geom.geom_type == "Polygon":
                    geom = MultiPolygon([geom])
                parts.append({campo: int(u), "geometry": geom})
            out = gpd.GeoDataFrame(parts, geometry="geometry", crs=g.crs)
        elif r.ruolo == "quote":
            if r.quota_da == "testo":
                z = g["Text"].map(_numero)
            elif r.quota_da.startswith("campo:"):
                z = g[r.quota_da[6:]].map(_numero)
            else:
                z = pd.Series([c.z if c.has_z else None for c in g.geometry], index=g.index)
            tipi = [_tipo_canonico(v, r.tipo_predefinito or "sup") for v in
                    (g[r.campo_tipo] if r.campo_tipo else [None] * len(g))]
            out = gpd.GeoDataFrame({sc.F_US: g._u.values, sc.F_TIPO_QUOTA: tipi},
                                   geometry=[Point(p.x, p.y, zz) if zz is not None else None
                                             for p, zz in zip(g.geometry, z)], crs=g.crs)
            out = out[out.geometry.notna()]
        elif r.ruolo == "profili":
            tipi = [_tipo_canonico(v, r.tipo_predefinito or "sup") for v in
                    (g[r.campo_tipo] if r.campo_tipo else [None] * len(g))]
            out = gpd.GeoDataFrame({sc.F_SEZIONE: g[r.campo_sezione].astype(str).values if r.campo_sezione else "—",
                                    sc.F_US: g._u.values, sc.F_INTERFACCIA: tipi}, geometry=g.geometry.values, crs=g.crs)
            out = out[out[sc.F_US].notna()]
        elif r.ruolo in ("sezioni", "sezioni_disegno"):
            out = g.drop(columns=["_u"])
            if r.campo_sezione and r.campo_sezione != sc.F_SEZIONE:
                out = out.rename(columns={r.campo_sezione: sc.F_SEZIONE})
            if sc.F_SEZIONE not in out.columns:
                out[sc.F_SEZIONE] = [f"S{i + 1}" for i in range(len(out))]
            if r.ruolo == "sezioni_disegno" and r.campo_unita:
                out[sc.F_US] = g._u.values
        else:   # area, reperti, campioni
            out = g.drop(columns=["_u"])
            if r.campo_unita and r.ruolo in ("reperti", "campioni"):
                out[sc.F_US] = g._u.values
            if r.ruolo == "area":
                out = out[out.geometry.notna()]
                out["geometry"] = [Polygon(x.exterior) if x.geom_type == "Polygon" else x for x in out.geometry]
                if "tipo" not in out.columns:
                    out["tipo"] = "area"
                if "nome" not in out.columns:
                    out["nome"] = r.layer
        raccolti.setdefault(r.ruolo, []).append(out)

    for ruolo, gl in raccolti.items():
        g = pd.concat(gl, ignore_index=True)
        s.layers[NOME_LAYER[ruolo]] = gpd.GeoDataFrame(g, geometry="geometry", crs=gl[0].crs)
    s.crs = crs

    # ------------------------------------------------ tabelle
    tabs = leggi_tabelle(abb.tabella) if abb.tabella else {}
    for nome, df in tabs.items():
        if nome not in (abb.foglio_us, abb.foglio_usm):
            s.tabelle[nome] = df
    poli_us = set(s.layers[sc.L_US][sc.F_US]) if sc.L_US in s.layers else set()
    poli_usm = set(s.layers[sc.L_USM][sc.F_USM]) if sc.L_USM in s.layers else set()
    if abb.foglio_us:
        df = tabs[abb.foglio_us].rename(columns={v: k for k, v in abb.colonne_us.items() if v != k})
        df[sc.C_US] = df[sc.C_US].map(_intero)
        df = df[df[sc.C_US].notna()].copy()
        df[sc.C_US] = df[sc.C_US].astype(int)
        # in alcuni archivi USM e US stanno nello stesso foglio: si separano con i poligoni
        if not abb.foglio_usm and poli_usm:
            usm_df = df[df[sc.C_US].isin(poli_usm) & ~df[sc.C_US].isin(poli_us)].rename(columns={sc.C_US: sc.C_USM})
            df = df[~df[sc.C_US].isin(usm_df[sc.C_USM])]
            if len(usm_df):
                s.tabelle[sc.S_USM] = usm_df
    else:
        df = pd.DataFrame({sc.C_US: sorted(poli_us)})
    if sc.C_TIPO not in df.columns:
        testo = df.get(sc.C_CATEGORIA, pd.Series([""] * len(df))).astype(str) + " " + \
                df.get("Definizione", pd.Series([""] * len(df))).astype(str)
        df[sc.C_TIPO] = np.where(testo.str.lower().str.contains("taglio|cut|negativ"), "negativa", "positiva")
        note.append("Colonna Tipo assente: US negative riconosciute dalla parola «taglio»")
    else:
        df[sc.C_TIPO] = df[sc.C_TIPO].astype(str).str.lower().map(
            lambda v: "negativa" if ("neg" in v or "tagl" in v) else "positiva")
    if sc.C_SPESSORE in df.columns:
        sp = df[sc.C_SPESSORE].map(_numero)
        col = abb.colonne_us.get(sc.C_SPESSORE, "")
        if "cm" in _norm(col) or (sp.dropna() > 5).mean() > 0.5:
            sp = sp / 100.0          # spessori in centimetri
        df[sc.C_SPESSORE] = sp
    for u in sorted(poli_us - set(df[sc.C_US])):
        note.append(f"US {u} ha un poligono ma nessuna scheda: aggiunta una scheda vuota")
    extra = sorted(poli_us - set(df[sc.C_US]))
    if extra:
        df = pd.concat([df, pd.DataFrame({sc.C_US: extra, sc.C_TIPO: "positiva"})], ignore_index=True)
    s.tabelle[sc.S_US] = df
    if abb.foglio_usm:
        du = tabs[abb.foglio_usm].rename(columns={v: k for k, v in abb.colonne_usm.items() if v != k})
        du[sc.C_USM] = du[sc.C_USM].map(_intero)
        s.tabelle[sc.S_USM] = du[du[sc.C_USM].notna()].astype({sc.C_USM: int})
    elif poli_usm and sc.S_USM not in s.tabelle:
        s.tabelle[sc.S_USM] = pd.DataFrame({sc.C_USM: sorted(poli_usm)})

    # ------------------------------------------------ rapporti
    r = abb.rapporti or {"modo": "nessuno"}
    righe = []
    if r["modo"] == "foglio":
        rdf = tabs[r["foglio"]]
        a, t, b = r["colonne"]
        for _, x in rdf.iterrows():
            ua, ub = _intero(x[a]), _intero(x[b])
            if ua is not None and ub is not None and pd.notna(x[t]):
                righe.append((ua, _norm(x[t]), ub))
        s.tabelle.pop(r["foglio"], None)
    elif r["modo"] == "colonne":
        src = tabs[r["foglio"]]
        idcol = abb.colonne_us.get(sc.C_US)
        for _, x in src.iterrows():
            ua = _intero(x[idcol])
            if ua is None:
                continue
            for col, rel in r["colonne"].items():
                v = x[col]
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                numeri = [_intero(v)] if isinstance(v, (int, float, np.integer, np.floating)) else \
                    [int(b) for b in re.findall(r"\d+", str(v))]
                for b in numeri:
                    righe.append((ua, rel, b))
    s.tabelle[sc.S_RAPPORTI] = pd.DataFrame(righe, columns=[sc.C_US, "Rapporto", "US correlata"]).drop_duplicates()

    # ------------------------------------------------ quote: US mancanti e tipi coerenti con la scheda
    if sc.L_QUOTE in s.layers:
        q = s.layers[sc.L_QUOTE]
        manca = q[sc.F_US].isna()
        if manca.any():
            poligoni = {**{u: g for u, g in zip(s.layers[sc.L_US][sc.F_US], s.layers[sc.L_US].geometry)}} \
                if sc.L_US in s.layers else {}
            if sc.L_USM in s.layers:
                poligoni.update({u: g for u, g in zip(s.layers[sc.L_USM][sc.F_USM], s.layers[sc.L_USM].geometry)})
            assegnate = 0
            nuovi = []
            for i, p in zip(q.index[manca], q.geometry[manca]):
                dentro = [u for u, g in poligoni.items() if g.contains(Point(p.x, p.y))]
                nuovi.append(dentro[0] if len(dentro) == 1 else None)
                assegnate += len(dentro) == 1
            q.loc[manca, sc.F_US] = nuovi
            note.append(f"{int(manca.sum())} quote senza US: {assegnate} assegnate dalla posizione, "
                        f"{int(manca.sum()) - assegnate} scartate (più poligoni sovrapposti o nessuno)")
            q = q[q[sc.F_US].notna()]
        q = q.astype({sc.F_US: int})
        neg = set(df.loc[df[sc.C_TIPO] == "negativa", sc.C_US])
        muri = poli_usm | (set(s.tabelle[sc.S_USM][sc.C_USM]) if sc.S_USM in s.tabelle else set())
        t = q[sc.F_TIPO_QUOTA].copy()
        t[q[sc.F_US].isin(neg) & t.isin(["sup", "inf"])] = "taglio"
        t[q[sc.F_US].isin(muri) & (t == "sup")] = "rasatura"
        t[q[sc.F_US].isin(muri) & (t == "inf")] = "fondazione"
        q[sc.F_TIPO_QUOTA] = t
        s.layers[sc.L_QUOTE] = q

    now = _dt.datetime.now().isoformat(timespec="seconds")
    fonti = sorted({x.sorgente for x in abb.layers if x.ruolo != "ignora"} | ({abb.tabella} if abb.tabella else set()))
    for p in fonti:
        s.sorgenti.append(dict(percorso=os.path.abspath(p), tipo="excel" if p == abb.tabella else "gis",
                               sha256=_sha256(p), dimensione=os.path.getsize(p), importato=now))
    base = next((x.sorgente for x in abb.layers if x.ruolo == "us"), fonti[0] if fonti else "scavo")
    s.meta = dict(creato=now, modificato=now, nome=os.path.splitext(os.path.basename(base))[0])
    s.abbinamento = abb
    s.note_importazione = abb.note + note
    s.registra("importazione", dict(file=[os.path.basename(p) for p in fonti], note=note))
    for n in note:
        log(n)
    return s
