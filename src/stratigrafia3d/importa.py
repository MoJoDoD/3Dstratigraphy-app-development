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
from . import tabelle_grezze as tg
from . import vocabolario as V
from .superficie import L_QUOTE_SUPERFICIE

EST_GIS = {".gpkg", ".shp", ".geojson", ".json", ".dxf", ".sqlite", ".db"}
EST_CONTENITORI = {".gpkg", ".sqlite", ".db"}          # possono contenere anche tabelle senza geometria
EST_TAB = {".xlsx", ".xlsm", ".xls", ".ods"}
RUOLI = ["us", "usm", "quote", "profili", "fondi", "area", "sezioni", "sezioni_disegno", "reperti", "campioni",
         "ignora"]
PUNTI_SOLO_SUPERFICIE = 5000      # punti quotati senza US oltre i quali servono solo alla superficie
NOME_LAYER = {"us": sc.L_US, "usm": sc.L_USM, "quote": sc.L_QUOTE, "profili": sc.L_PROFILI, "area": sc.L_AREA,
              "sezioni": sc.L_SEZIONI, "sezioni_disegno": sc.L_SEZ_DISEGNO, "reperti": sc.L_RS,
              "campioni": sc.L_CAMPIONI, "fondi": sc.L_FONDI, "quote_superficie": L_QUOTE_SUPERFICIE}

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
    ("fondi", ["base of slope", "base_of_slope", "linee fondo", "linea di fondo", "linee di fondo", "fondo taglio",
               "fondo_taglio", "break of slope"]),
    ("ignora", ["griglia", "grid", "quadrett", "layer_styles", "hachure", "tratteggi"]),
    ("usm", ["usm", "mur", "wall", "muratur", "struttur"]),
    ("area", ["area_scavo", "limite", "limit", "saggio", "trincea", "trench", "perimetr", "area", "excavation",
              "scavi", "evaluation"]),
    ("profili", ["profil", "interfacc"]),
    ("sezioni_disegno", ["sezioni_disegno", "disegno_sez"]),
    ("sezioni", ["sezion", "sez", "section"]),
    ("reperti", ["reperti", "reperto", "find", "rs_"]),
    ("campioni", ["campion", "sample"]),
    ("quote", ["quot", "punti", "point", "spot", "height", "rilievo_punti", "elev", "level"]),
    ("us", ["us", "strat", "context", "unita", "unità", "unit", "layer"]),
]
ALIAS_UNITA = ["us", "n_us", "num_us", "numero_us", "n. us", "n.us", "context", "su", "unita", "unità", "usm",
               "n_usm", "numero", "code", "codice", "layer"]
ALIAS_QUOTA = ["quota", "z", "q", "elev", "elevation", "h", "altezza", "quota_m", "zeta", "height"]
ALIAS_SEZIONE = ["sezione", "sez", "section", "nome", "name"]
RAPPORTI_COLONNE = ["copre", "coperto da", "taglia", "tagliato da", "riempie", "riempito da", "si appoggia a",
                    "gli si appoggia", "si lega a", "uguale a"]
# rapporti scritti in inglese (archivi britannici, Harris matrix) -> forma italiana usata dal motore
RAPPORTI_INGLESE = {
    "covers": "copre", "overlies": "copre", "above": "copre", "seals": "copre",
    "covered by": "coperto da", "overlain by": "coperto da", "below": "coperto da", "sealed by": "coperto da",
    "cuts": "taglia", "cut by": "tagliato da", "fills": "riempie", "fill of": "riempie", "filled by": "riempito da",
    "abuts": "si appoggia a", "butts": "si appoggia a", "abutted by": "gli si appoggia", "butted by": "gli si appoggia",
    "bonded with": "si lega a", "bonds with": "si lega a", "bonded to": "si lega a", "tied to": "si lega a",
    "same as": "uguale a", "equal to": "uguale a", "equals": "uguale a",
}
# fogli con nomi inglesi -> foglio e colonne attesi dal visualizzatore
FOGLI_ALIAS = {
    sc.S_FASI: (["phases", "phase", "periods", "fasi"],
                {"phase": "Fase", "title": "Titolo", "name": "Titolo", "period": "Periodo",
                 "from (year)": "Da (anno)", "to (year)": "A (anno)", "from": "Da (anno)", "to": "A (anno)",
                 "start": "Da (anno)", "end": "A (anno)"}),
    sc.S_MATERIALI: (["finds", "materials", "artefacts", "artifacts", "materiali", "findssummaries", "finds summaries",
                      "finds summary", "reperti", "inventario materiali"],
                     {"context": "US", "us": "US", "deposit": "US", "context number": "US", "material": "Classe",
                      "class": "Classe", "classe": "Classe", "object": "Tipo / forma", "type": "Tipo / forma",
                      "count": "NR", "quantity": "NR", "objectcount": "NR", "object count": "NR", "nr": "NR",
                      "weight (g)": "Peso (g)", "weight": "Peso (g)", "peso": "Peso (g)", "mni": "NMI", "nmi": "NMI",
                      "box": "Cassetta", "cassetta": "Cassetta"}),
    sc.S_DOC: (["documentation", "archive", "documentazione"],
               {"context": "US/USM", "us": "US/USM", "subject": "Soggetto", "description": "Soggetto", "date": "Data",
                "file": "File", "filename": "File", "file name": "File", "path": "File", "percorso": "File",
                "immagine": "File", "image": "File", "type": "Tipo", "tipo": "Tipo", "soggetto": "Soggetto",
                "data": "Data"}),
    sc.S_CAMPIONI: (["samples", "campioni"],
                    {"sample": "Campione", "context": "US", "sample type": "Tipo", "type": "Tipo",
                     "analysis": "Analisi", "collected for": "Analisi"}),
}
_INT_RE = re.compile(r"(\d{1,7})")


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower().replace("_", " "))


# ============================================================================ vocabolario dei termini
# Il vocabolario (stratigrafia3d.vocabolario) riconosce nomi di layer, fogli e colonne e valori in più
# lingue; le liste di questo modulo restano come ripiego per i casi propri del programma.
_RAPP_SET = frozenset(RAPPORTI_COLONNE)
_CAMPI_VALORE = ("tipo", "rapporto", "tipo_quota")
_VOC_CACHE = {}
_CACHE_RAPPORTI = {}


def _campo_concetto(voc, c):
    return (voc._def.get(c) or {}).get("campo")


def _concetto_valore(voc, campo, valore):
    """Il concetto del vocabolario che dà ``valore`` per il campo («tipo», «rapporto», «tipo_quota»)."""
    for c in voc.concetti("valore"):
        if _campo_concetto(voc, c) == campo and voc.canonico(c, "valore") == valore:
            return c
    return None


def termini_ricetta(abb):
    """Termini che una ricetta insegna al vocabolario: i suoi vocabolari di valori (solo quelli che il
    vocabolario non conosce già con lo stesso significato) e i suoi «termini» ({concetto: [nomi]})."""
    extra = {}
    if abb is None:
        return extra
    base = V.vocabolario()
    for campo, mappa in (getattr(abb, "vocabolari", None) or {}).items():
        if campo not in _CAMPI_VALORE:
            continue
        for valore, canon in (mappa or {}).items():
            valore = str(valore).strip()
            if not canon or not valore or base.riconosci_valore(valore, campo) == canon:
                continue
            c = _concetto_valore(base, campo, canon)
            if c and valore not in extra.setdefault(c, []):
                extra[c].append(valore)
    for c, termini in (getattr(abb, "termini", None) or {}).items():
        for t in ([termini] if isinstance(termini, str) else list(termini or [])):
            if str(t).strip() and t not in extra.setdefault(c, []):
                extra[c].append(t)
    return {c: v for c, v in extra.items() if v}


def vocabolario_per(abb=None, termini=None):
    """Il vocabolario condiviso (integrato + termini dell'utente), esteso con i termini della ricetta."""
    base = V.vocabolario()
    extra = termini_ricetta(abb)
    for c, t in (termini or {}).items():
        for x in ([t] if isinstance(t, str) else list(t or [])):
            if x not in extra.setdefault(c, []):
                extra[c].append(x)
    if not extra:
        return base
    k = (id(base), json.dumps(extra, sort_keys=True, ensure_ascii=False))
    v = _VOC_CACHE.get(k)
    if v is None:
        if len(_VOC_CACHE) > 8:
            _VOC_CACHE.clear()
        v = _VOC_CACHE[k] = V.Vocabolario(file_utente=base.file_utente or False, extra=extra)
    return v


def _migliore(voc, nome, ambito, contesto=None, soglia=0.6, canonici=None, campo=None):
    """Il riconoscimento più probabile di ``nome`` (con un canonico tra ``canonici``, o un concetto del
    ``campo`` di valori indicato), se è il primo della lista e supera ``soglia``; altrimenti None."""
    try:
        ris = voc.riconosci(nome, ambito, contesto, soglia=0.3, massimo=4)
    except Exception:          # un nome strano non deve fermare l'importazione
        return None
    if not ris:
        return None
    r = ris[0]
    if r.punteggio < soglia:
        return None
    if canonici is not None and r.canonico not in canonici and r.concetto not in canonici:
        return None
    if campo is not None and _campo_concetto(voc, r.concetto) != campo:
        return None
    return r


def _insegnato(r):
    """Vero se il riconoscimento viene da un termine aggiunto dall'utente o indicato dalla ricetta."""
    return r.lingua == "xx" or "aggiunto dall'utente" in r.motivo or "indicato dalla ricetta" in r.motivo


def _rapporto(v, voc=None):
    """Nome del rapporto nella forma italiana del motore: accetta l'inglese, le altre lingue del
    vocabolario («recouvre», «schneidet», «cubre»…) e i segni «=», «>», «<»."""
    n = _norm(v)
    if n in RAPPORTI_INGLESE:
        return RAPPORTI_INGLESE[n]
    if n in _RAPP_SET or not n or n == "nan" or re.fullmatch(r"[\d\s.,;:/+\-]*", n):
        return n
    voc = voc or V.vocabolario()
    k = (n, voc)             # il vocabolario stesso nella chiave: un altro vocabolario non riusa i risultati
    r = _CACHE_RAPPORTI.get(k)
    if r is None:
        r = tg.rapporto_da_parola(v) or voc.riconosci_valore(n, "rapporto", soglia=0.8)
        r = r if r in _RAPP_SET else n
        if len(_CACHE_RAPPORTI) > 20000:
            _CACHE_RAPPORTI.clear()
        _CACHE_RAPPORTI[k] = r
    return r


def _rapporto_colonna(nome, voc=None, contesto=None):
    """(rapporto, motivo) se il nome della colonna è un rapporto stratigrafico («Copre», «Fill of»,
    «Recoupe», «schneidet»…), altrimenti (None, None)."""
    n = _norm(nome)
    if n in _RAPP_SET or n in RAPPORTI_INGLESE:
        return RAPPORTI_INGLESE.get(n, n), None
    voc = voc or V.vocabolario()
    r = _migliore(voc, nome, "colonna", contesto, soglia=0.8, campo="rapporto")
    if r is not None and (r.canonico or r.concetto) in _RAPP_SET:
        return r.canonico or r.concetto, r.motivo
    p = tg.rapporto_da_parola(nome)
    if p in _RAPP_SET and len(n) > 4:
        return p, None
    # intestazione su due righe: «Rapporti» sopra «copre», «taglia»… -> «Rapporti copre»
    parole = str(nome).split()
    for k in range(1, len(parole)):
        testa, coda = " ".join(parole[:k]), " ".join(parole[k:])
        if _migliore(voc, testa, "colonna", soglia=0.8, canonici=("rapporti",)) is not None:
            rel, motivo = _rapporto_colonna(coda, voc)
            if rel is not None:
                return rel, motivo
    return None, None


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


_CACHE_CSV = {}


def leggi_csv(path):
    """CSV con separatore e codifica riconosciuti (UTF-8, altrimenti Windows/Latin-1)."""
    import csv
    chiave = (os.path.abspath(path), os.path.getmtime(path))
    if chiave in _CACHE_CSV:
        return _CACHE_CSV[chiave].copy()
    campione = open(path, "rb").read(65536).decode("latin-1")
    try:
        sep = csv.Sniffer().sniff("\n".join(campione.splitlines()[:20]), delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    df = None
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, sep=sep, encoding=cod, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError:
            df = pd.read_csv(path, sep=None, engine="python", encoding=cod)
            break
    if len(_CACHE_CSV) > 40:
        _CACHE_CSV.clear()
    _CACHE_CSV[chiave] = df
    return df.copy()


_WKT_RE = re.compile(r"^\s*(MULTI)?(POINT|LINESTRING|POLYGON)\s*(Z|M|ZM)?\s*\(", re.I)


def _colonna_wkt(df):
    for c in df.columns:
        if _norm(c) in ("geometry", "wkt", "geom", "the geom", "geometria", "shape", "wkt geom") or \
                str(c).lower() in ("geometry", "wkt", "the_geom"):
            v = df[c].dropna().astype(str).head(20)
            if len(v) and v.map(lambda x: bool(_WKT_RE.match(x))).mean() > 0.8:
                return c
    return None


def _leggi_csv_punti(path):
    df = leggi_csv(path)
    cw = _colonna_wkt(df)
    if cw is not None:           # geometrie scritte come testo (WKT)
        from shapely import wkt as _wkt
        geom = [(_wkt.loads(v) if isinstance(v, str) and _WKT_RE.match(v) else None) for v in df[cw]]
        return gpd.GeoDataFrame(df.drop(columns=[cw]), geometry=geom)
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


def esamina_raster(files):
    """Descrizione dei raster tra i file: percorso -> dict (con «tipo»: «dem» o «ortofoto») o errore."""
    from .superficie import Raster, EST_RASTER, georef, e_ortofoto, e_differenza
    out = {}
    for f in files:
        if os.path.splitext(f)[1].lower() in EST_RASTER:
            try:
                g = georef(f)
                if e_ortofoto(g):
                    out[f] = dict(tipo="ortofoto", nome=os.path.basename(f), righe=g["righe"], colonne=g["colonne"],
                                  passo=round(g["passo"][0], 3), estensione=[round(v, 2) for v in g["estensione"]])
                else:
                    d = Raster.leggi(f).descrizione()
                    out[f] = dict(d, tipo="dem", differenza=e_differenza(d))
            except Exception as e:
                out[f] = dict(errore=str(e))
    return out


def esamina(files):
    """Elenco dei layer (InfoLayer) e dei fogli trovati nei file."""
    from .superficie import EST_RASTER
    layers, tabelle = [], {}
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext in EST_RASTER:
            continue
        if ext == ".dxf":
            df = _dxf_gruppi(f)
            for k in sorted(df["_chiave"].unique()):
                layers.append(_info(f, k, leggi_layer(f, k)))
        elif ext in EST_GIS:
            for nome, tipo in pyogrio.list_layers(f):
                if nome.startswith(("s3d_", "tab_", "layer_styles", "gpkg_", "rtree_", "sqlite_", "spatial_ref_sys",
                                    "geometry_columns", "views_geometry", "virts_geometry", "spatialite_history",
                                    "sql_statements_log", "idx_")):
                    continue
                if ext in EST_CONTENITORI and tipo is None:
                    if ext == ".gpkg":
                        tabelle.setdefault(f, {})[nome] = pyogrio.read_dataframe(f, layer=nome, read_geometry=False)
                    continue
                layers.append(_info(f, nome, gpd.read_file(f, layer=nome)))
            if ext in (".sqlite", ".db"):
                t = _tabelle_sqlite(f)
                if t:
                    tabelle[f] = t
        elif ext == ".csv" and _csv_e_punti(f):
            g = _leggi_csv_punti(f)
            layers.append(_info(f, os.path.basename(f), g))
            if _colonna_wkt(leggi_csv(f)) is not None:     # le colonne di un CSV con geometrie sono anche schede
                tabelle[f] = leggi_tabelle(f)
        elif ext in EST_TAB or ext == ".csv":
            tabelle[f] = leggi_tabelle(f)
    return layers, tabelle


_SISTEMA_SQLITE = ("sqlite_", "spatial_ref_sys", "spatialite_history", "sql_statements_log", "geometry_columns",
                   "views_geometry_columns", "virts_geometry_columns", "geom_cols_ref_sys", "spatial_ref_sys_aux",
                   "idx_", "elementarygeometries", "spatialindex", "knn", "data_licenses", "rl2map_configurations",
                   "vector_coverages", "raster_coverages", "wms_", "se_", "topologies", "networks", "iso_metadata",
                   "gpkg_", "rtree_", "layer_styles", "s3d_", "tab_", "vector_layers", "stored_procedures", "stored_variables", "sqlitestudio_", "sql_statements")


def _senza_bytes(df):
    """Colonne con valori binari (BLOB): testo se si decodifica, altrimenti la colonna si toglie."""
    for c in list(df.columns):
        if df[c].dtype != object:
            continue
        v = df[c].dropna()
        if not len(v) or not v.map(lambda x: isinstance(x, (bytes, bytearray, memoryview))).any():
            continue
        def testo(x):
            if not isinstance(x, (bytes, bytearray, memoryview)):
                return x
            b = bytes(x)
            try:
                return b.decode("utf-8")
            except UnicodeDecodeError:
                return None
        t = df[c].map(testo)
        if t.notna().sum() < len(v) * 0.9:        # dati binari (geometrie, immagini): inutili qui
            df = df.drop(columns=c)
        else:
            df[c] = t
    return df


def _tabelle_sqlite(path):
    """Tabelle senza geometria di un database SQLite/SpatiaLite (GDAL elenca solo quelle spaziali)."""
    import sqlite3
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        nomi = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")]
        try:
            spaziali = {r[0].lower() for r in con.execute("SELECT f_table_name FROM geometry_columns")}
        except sqlite3.Error:
            spaziali = set()
        out = {}
        for n in nomi:
            if n.lower() in spaziali or n.lower().startswith(_SISTEMA_SQLITE):
                continue
            try:
                con.text_factory = lambda b: b.decode("utf-8", errors="replace")
                out[n] = _senza_bytes(pd.read_sql_query(f'SELECT * FROM "{n}"', con))
            except Exception:
                pass
        return out
    finally:
        con.close()


_CACHE_TABELLE = {}          # (percorso, data di modifica) -> (fogli ordinati, note per foglio)


def _ordina_foglio(df, nome):
    """Un foglio letto così com'è -> {nome: (tabella ordinata, note)} con ``tabelle_grezze``.

    I nomi delle colonne restano quelli del file: le misure con l'unità nei valori («45 cm», «0,45 m») e
    la virgola decimale si convertono sul posto, ma una colonna con l'unità nell'intestazione («Spessore
    (cm)») non cambia nome né valori. Così la riscrittura nei file d'origine (modifiche.py) ritrova le
    colonne della ricetta, e la conversione resta quella dell'importazione (``_misura``, «unità di misura»)."""
    out = {}
    for chiave, (d1, note) in tg.normalizza_foglio(df, nome, misure=False).items():
        d2, note2 = tg.converti_misure(d1, [])
        if d2 is not d1 and list(d2.columns) != list(d1.columns):
            rinominate = {b: a for a, b in zip(d1.columns, d2.columns) if a != b}
            d2 = d2.rename(columns=rinominate)
            for orig in rinominate.values():
                d2[orig] = d1[orig]
            note2 = [n for n in note2 if n["codice"] != "misura_intestazione"]
        out[chiave] = (d2, list(note) + note2)
    return out


def _leggi_tabelle_grezze(path, ext):
    if ext in (".sqlite", ".db"):
        return _tabelle_sqlite(path), False
    if ext in EST_CONTENITORI:          # tabelle senza geometria di un GeoPackage
        return {n: pyogrio.read_dataframe(path, layer=n, read_geometry=False)
                for n, t in pyogrio.list_layers(path) if t is None and not n.startswith(("s3d_", "gpkg_", "rtree_"))
                and n not in ("layer_styles", "spatial_ref_sys", "geometry_columns")}, False
    if ext == ".csv":
        df = leggi_csv(path)
        cw = _colonna_wkt(df)
        return {os.path.splitext(os.path.basename(path))[0]: df.drop(columns=[cw]) if cw else df}, True
    return pd.read_excel(path, sheet_name=None), True


def leggi_tabelle(path, note=None):
    """Fogli (o tabelle) di un file: {nome: DataFrame}. I fogli di Excel e i CSV passano per
    ``tabelle_grezze``: intestazione non in prima riga, intestazione su più righe, schede trasposte,
    tabelle campo/valore, matrici dei rapporti, più tabelle in un foglio («foglio · titolo»), numeri con
    la virgola. Se ``note`` è una lista, vi si aggiungono le trasformazioni fatte ({foglio: [messaggi]}
    per foglio, come dict). Il risultato resta in memoria finché il file non cambia."""
    ext = os.path.splitext(path)[1].lower()
    try:
        st = os.stat(path)
        chiave = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    except OSError:
        chiave = None
    if chiave is None or chiave not in _CACHE_TABELLE:
        fogli, ordina = _leggi_tabelle_grezze(path, ext)
        tab, rap = {}, {}
        for nome, df in fogli.items():
            if not ordina:
                tab[nome] = df
                continue
            try:
                parti = _ordina_foglio(df, nome)
            except Exception:           # una forma imprevista: il foglio resta com'è
                parti = {nome: (df, [])}
            for k, (d, n) in parti.items():
                tab[k] = d
                if n:
                    rap[k] = [x["messaggio"] for x in n]
        if chiave is None:
            return tab
        if len(_CACHE_TABELLE) > 30:
            _CACHE_TABELLE.clear()
        _CACHE_TABELLE[chiave] = (tab, rap)
    tab, rap = _CACHE_TABELLE[chiave]
    if note is not None:
        note.append(dict(rap))
    return {k: d.copy() for k, d in tab.items()}


def note_tabelle(path):
    """Le trasformazioni fatte sui fogli del file da ``leggi_tabelle``: {foglio: [messaggi]}."""
    n = []
    try:
        leggi_tabelle(path, n)
    except Exception:
        return {}
    return n[0] if n else {}


EST_ZIP = {".zip"}
EST_ACCESS = {".mdb", ".accdb"}
_ACCOMPAGNANO = {".dbf", ".shx", ".prj", ".cpg", ".qpj", ".tfw", ".tifw", ".wld", ".aux", ".xml", ".sbn", ".sbx"}


def espandi(files, cartella=None):
    """Apre gli archivi .zip tra i file (in una cartella di lavoro) e ritorna l'elenco dei file utili.
    Ritorna (file, note)."""
    import hashlib
    import zipfile
    from .superficie import EST_RASTER
    from .modelli3d import EST_MODELLI
    utili = EST_GIS | EST_TAB | EST_RASTER | EST_MODELLI | {".csv"}
    out, note = [], []
    base = cartella or os.path.join(os.path.expanduser("~"), ".stratigrafia3d", "estratti")
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext in EST_ACCESS:
            note.append(f"«{os.path.basename(f)}» è un database Access: esporta le tabelle in CSV "
                        "(in Access: Dati esterni → Esporta → File di testo) e aggiungi i CSV")
            continue
        if ext not in EST_ZIP:
            out.append(f)
            continue
        try:
            z = zipfile.ZipFile(f)
        except zipfile.BadZipFile:
            note.append(f"«{os.path.basename(f)}» non è un archivio zip valido (download incompleto?)")
            continue
        chiave = hashlib.sha1(f"{os.path.abspath(f)}|{os.path.getmtime(f)}".encode()).hexdigest()[:12]
        dest = os.path.join(base, os.path.splitext(os.path.basename(f))[0] + "_" + chiave)
        nomi = [n for n in z.namelist() if not n.endswith("/") and "__MACOSX" not in n]
        # con un modello 3D servono anche il .mtl e le immagini della texture
        extra = {".mtl", ".jpg", ".jpeg", ".png"} if any(os.path.splitext(n)[1].lower() in EST_MODELLI for n in nomi) else set()
        scelti = [n for n in nomi if os.path.splitext(n)[1].lower() in utili | _ACCOMPAGNANO | extra]
        principali = [n for n in scelti if os.path.splitext(n)[1].lower() in utili]
        if not principali:
            note.append(f"«{os.path.basename(f)}»: nessun file di dati riconosciuto nell'archivio")
            continue
        for n in scelti:
            p = os.path.join(dest, *n.split("/"))
            if not os.path.exists(p):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with z.open(n) as src, open(p, "wb") as dst:
                    dst.write(src.read())
        for n in principali:
            out.append(os.path.join(dest, *n.split("/")))
        note.append(f"«{os.path.basename(f)}»: {len(principali)} file estratti")
    return out, note


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
    campi_scheda: dict = field(default_factory=dict)   # {colonna del programma: campo del layer}
    quote_vertici: bool = False    # poligoni 3D: i vertici diventano quote (del tetto, o dell'orlo per i tagli)
    motivo: str = ""
    # quote: punti usati solo per la superficie di riferimento, senza US (layer «quote_superficie»)
    solo_superficie: bool = False


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
    # superficie di riferimento per le unità senza quote (vedi superficie.py)
    superficie: dict = field(default_factory=lambda: {"tipo": "nessuna"})
    # ---- ricetta: trasformazioni dei dati
    nome: str = ""                                      # nome della ricetta (es. "Framework Archaeology")
    tabelle_extra: list = field(default_factory=list)   # altri file di tabelle (CSV collegati, Excel)
    vocabolari: dict = field(default_factory=dict)      # {"tipo"|"rapporto"|"tipo_quota": {valore: valore}}
    rapporti_extra: list = field(default_factory=list)  # [{"foglio", "colonna", "rapporto", "colonna_unita"}]
    unita_misura: dict = field(default_factory=dict)    # {colonna del programma: "m"|"cm"|"mm"|"auto"}
    valori_nulli: list = field(default_factory=lambda: [-9999.0, -999.0, -99.99])
    filtri: list = field(default_factory=list)          # [{"dove": "scheda"|"layer", "colonna", "valori", ...}]
    poligoni_ereditati: bool = False                    # riempimenti senza pianta: poligono del taglio
    solo_con_poligono: bool = False                     # tralascia le schede senza pianta
    fogli_collegati: dict = None                        # {"Materiali": {"foglio", "colonne"}, ...}
    # fase scritta in due colonne (periodo + fase, come in pyArchInit): {"scheda": [periodo, fase],
    # "fasi": [periodo, fase], "da": colonna anno iniziale, "a": anno finale, "titolo": colonna}
    fase_composta: dict = None
    # colonne prese da altre tabelle con una chiave, anche a catena (Heathrow: scheda -> SGData):
    # [{"foglio", "chiave": colonna del foglio, "colonna": colonna della scheda, "porta": [colonne]}]
    colonne_collegate: list = field(default_factory=list)
    ortofoto: str = None                                # GeoTIFF a colori da drappeggiare sul modello
    modelli3d: list = field(default_factory=list)       # [{"percorso", "spostamento": [dx, dy, dz]}]
    # perché il programma ha scelto un ruolo o una colonna (dal vocabolario dei termini):
    # {"layer:<layer>": motivo, "colonna:<foglio o layer>:<colonna>": motivo, "tabella:<foglio>": motivo}
    spiegazioni: dict = field(default_factory=dict)
    # termini che la ricetta insegna al vocabolario per i nomi: {concetto: [nomi]} (es. {"us": ["Kontekst"]})
    termini: dict = field(default_factory=dict)

    def a_json(self):
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def da_json(cls, s):
        d = json.loads(s) if isinstance(s, str) else dict(s)
        campi_layer = RuoloLayer.__dataclass_fields__
        d["layers"] = [RuoloLayer(**{k: v for k, v in x.items() if k in campi_layer}) for x in d.get("layers", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def salva_profilo(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.a_json())

    @classmethod
    def carica_profilo(cls, path):
        return cls.da_json(open(path, encoding="utf-8").read())


_ALIAS_ID_US = ("us", "n us", "n. us", "numero us", "num us", "n.us", "context", "context number", "context no",
                "su", "unità stratigrafica", "unita stratigrafica", "stratigraphic unit")
_ALIAS_ID_USM = ("usm", "n usm", "n. usm", "numero usm")
_NOMI_SCHEDE = ("us", "schede us", "schede", "unità stratigrafiche", "contexts", "context register", "context sheets",
                "us table")
_NON_SCHEDE = ("materiali", "inventario", "reperti", "finds", "campion", "sample", "foto", "photo", "media", "quote",
               "toimp")
_FOGLI_NON_SCHEDE = {sc.S_MATERIALI, sc.S_RS, sc.S_CAMPIONI, sc.S_DOC, sc.S_QUOTE, sc.S_RAPPORTI, sc.S_FASI}
_CONCETTI_QUOTA = ("quote", "sup", "inf", "taglio", "orlo", "rasatura", "fondazione")


def _punteggio_unita(serie, noti, nome, voc=None):
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
    if not bonus and voc is not None and _migliore(voc, nome, "colonna", soglia=0.8, canonici=(sc.C_US, sc.C_USM)):
        bonus = 0.3                # «Context No.», «UE», «Befund-Nr.»…
    # un campo con pochissimi valori diversi (area, saggio, settore) non è il numero dell'unità
    overlap *= min(1.0, len(set(ok)) / 5)
    if pd.api.types.is_float_dtype(serie) and not np.allclose(vals, np.round(vals)):
        return 0.0            # quote, non numeri di US
    return frac * 0.3 + overlap + bonus


def _campo_unita(g, noti, voc=None):
    """(campo con il numero dell'unità, punteggio, spiegazione del vocabolario o None)."""
    best, sb = None, 0.0
    for c in g.columns:
        if c in ("geometry", "Text", "SubClasses", "Linetype", "EntityHandle", "PaperSpace", "fid"):
            continue
        s = _punteggio_unita(g[c], noti, c, voc)
        if s > sb:
            best, sb = c, s
    if sb < 0.45:
        return None, sb, None
    r = _migliore(voc, best, "colonna", soglia=0.6, canonici=(sc.C_US, sc.C_USM)) if voc is not None else None
    return best, sb, (r.motivo if r else None)


def _campo_tipo(g, voc=None):
    """Campo con il tipo di quota (sup, inf, taglio… anche in altre lingue: «top», «Oberkante»)."""
    voc = voc or V.vocabolario()
    for c in g.columns:
        if c == "geometry":
            continue
        vals = g[c].dropna().astype(str).map(_norm)
        if not len(vals):
            continue
        if vals.map(lambda v: v in _SIN).mean() > 0.8:
            return c
        u = vals.unique()
        if len(u) <= 30 and not pd.api.types.is_numeric_dtype(g[c]):
            noti = {x: x in _SIN or voc.riconosci_valore(x, "tipo_quota") is not None for x in u}
            if vals.map(noti).mean() > 0.8:
                return c
    return None


def _campo_quota(g, voc=None):
    def varia(c):
        v = g[c].map(_numero).dropna()
        return len(v) and v.std() > 0.01
    for c in g.columns:
        if c == "geometry" or _norm(c) not in ALIAS_QUOTA:
            continue
        if varia(c):
            return c
    if voc is not None:
        for c in g.columns:
            if c != "geometry" and _migliore(voc, c, "colonna", soglia=0.8, canonici=_CONCETTI_QUOTA) and varia(c):
                return c
    for c in g.columns:     # campo numerico decimale con valori da quota
        if c != "geometry" and pd.api.types.is_float_dtype(g[c]):
            v = g[c].dropna()
            if len(v) > 3 and v.std() > 0.01 and not np.allclose(v, np.round(v)):
                return c
    return None


def _ruolo_da_nome(nome, geometria=None):
    """Ruolo suggerito dal nome del layer/file (parole del programma). Se più parole corrispondono, per i
    poligoni vince l'ordine ignora > usm > us > area (es. "US_limiti" sono limiti di US, non dell'area)."""
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


def _ruolo_proposto(nome, geometria=None, voc=None):
    """(ruolo, parola, motivo): prima il vocabolario (in più lingue, con la geometria come indizio), poi le
    parole del programma. ``motivo`` è la spiegazione del vocabolario, None se decide il ripiego."""
    voc = voc or V.vocabolario()
    testo = re.sub(r"\s*·\s*(poligono|linea|punto|testo|misto|nessuna)$", "", str(nome)).replace("#", " ")
    contesto = {"geometria": geometria} if geometria in ("poligono", "linea", "punto") else None
    r = _migliore(voc, testo, "layer", contesto, soglia=0.6)
    if r is not None:
        ruolo = r.canonico if r.canonico in RUOLI else (r.concetto if r.concetto in RUOLI else None)
        if ruolo:
            return ruolo, r.termine or testo, r.motivo
    ruolo, parola = _ruolo_da_nome(nome, geometria)
    return ruolo, parola, None


def _schede(tabelle, voc=None, spieg=None):
    """Trova il foglio delle US, quello delle USM, i numeri noti e il modo dei rapporti."""
    voc = voc or V.vocabolario()
    best = (None, None, 0, None)
    usm = (None, None, 0, None)
    for nome, df in tabelle.items():
        cols = [str(c) for c in df.columns]
        rt = _migliore(voc, nome, "tabella", soglia=0.6)
        for c in df.columns:
            nc = _norm(c)
            vals = df[c].dropna()
            if not len(vals):
                continue
            frac = np.mean([_intero(v) is not None for v in vals])
            if frac < 0.8:
                continue
            rv = None
            if nc not in _ALIAS_ID_US and nc not in _ALIAS_ID_USM:
                rv = _migliore(voc, c, "colonna", {"tabella": nome, "colonne": cols}, soglia=0.75,
                               canonici=(sc.C_US, sc.C_USM))
            if nc in _ALIAS_ID_US or (rv is not None and rv.canonico == sc.C_US):
                s = frac + (0.5 if _norm(nome) in _NOMI_SCHEDE or (rt and rt.canonico == sc.S_US) else 0)
                # nel foglio delle schede ogni unità compare una volta sola, e le colonne sono molte;
                # materiali, campioni e foto ripetono il numero di US
                s += 0.3 * vals.map(_intero).nunique() / len(vals) + min(len(df.columns), 40) / 200
                if any(k in _norm(nome) for k in _NON_SCHEDE) or (rt and rt.canonico in _FOGLI_NON_SCHEDE):
                    s -= 0.4
                if s > best[2]:
                    best = (nome, c, s, rv)
            if nc in _ALIAS_ID_USM or (rv is not None and rv.canonico == sc.C_USM):
                s = frac + (0.5 if _norm(nome) in ("usm", "schede usm") or (rt and rt.canonico == sc.S_USM) else 0)
                if s > usm[2]:
                    usm = (nome, c, s, rv)
    if spieg is not None:
        for nome, c, _, rv in (best, usm):
            if nome and rv is not None:
                spieg[f"colonna:{nome}:{c}"] = rv.motivo
    return best[:2], usm[:2]


_CANDIDATI_SCHEDA = {
    sc.C_TIPO: ["tipo", "tipo us", "positiva/negativa", "natura", "type", "context type", "positive/negative"],
    sc.C_CATEGORIA: ["categoria", "definizione generale", "tipo di unità", "category", "class"],
    sc.C_SPESSORE: ["spessore medio stimato (m)", "spessore", "spessore medio", "spessore (m)", "spessore medio (m)",
                    "potenza", "spessore (cm)", "thickness (m)", "thickness", "average thickness (m)",
                    "thickness (cm)", "context depth (m)", "context depth"],
    sc.C_MARGINI: ["margini", "limiti", "limite", "limiti/margini", "boundary", "edges", "boundaries"],
    sc.C_FASE: ["fase", "phase", "period/phase"],
    sc.C_COLORE: ["colore hex", "colore rgb", "hex", "colour hex", "color hex", "colour", "color"],
    "Definizione": ["definizione", "descrizione breve", "interpretazione sintetica", "definition",
                    "interpretation keyword", "short description"],
    "Descrizione": ["descrizione", "description", "brief description", "descriz", "desc"],
    "Interpretazione": ["interpretazione", "interpretation", "comments", "context comments"],
    "Spessore/profondità max (m)": ["profondità (m)", "profondità", "depth (m)", "depth", "max depth (m)",
                                    "context depth (m)", "context depth", "profondità max (m)"],
    "Data scavo": ["data scavo", "date recorded", "date excavated", "excavation date"],
    "Datazione da": ["datazione da", "da (anno)", "from (year)", "start year", "start_year", "anno inizio",
                     "cronologia iniziale", "date from"],
    "Datazione a": ["datazione a", "a (anno)", "to (year)", "end year", "end_year", "anno fine", "cronologia finale",
                    "date to"],
    "Responsabile": ["responsabile", "recorded by", "excavator", "supervisor"],
    sc.C_BASE_USM: ["quota base usata (rilevata o stimata)", "quota fondazione", "quota base", "base"],
}
_NUMERICI_ALIAS = {sc.C_SPESSORE, sc.C_BASE_USM, "Spessore/profondità max (m)"}
_NUMERICI_SCHEDA = _NUMERICI_ALIAS | {"Datazione da", "Datazione a"}


def _numerica(serie):
    v = serie.dropna()
    return not len(v) or v.map(lambda x: _numero(x) is not None).mean() >= 0.8


def _colonna_tipo_dai_valori(df, escluse, voc):
    """Colonna i cui valori sono tipi di unità (Cut/Fill, Creusement/Remblai, Schicht/Eingriff…), con
    unità positive e negative. Ritorna (colonna, motivo) o (None, None)."""
    best = (None, 0.0, None)
    for c in df.columns:
        if c in escluse or pd.api.types.is_numeric_dtype(df[c]):
            continue
        v = df[c].dropna().astype(str).str.strip()
        u = [x for x in v.unique() if x]
        if not 1 < len(u) <= 40:
            continue
        ric = {x: voc.riconosci_valore(x, "tipo") for x in u}
        frac = float(np.mean([r is not None for r in ric.values()]))
        if frac >= 0.8 and {"positiva", "negativa"} <= set(ric.values()) and frac > best[1]:
            neg = next(x for x in u if ric[x] == "negativa")
            pos = next(x for x in u if ric[x] == "positiva")
            best = (c, frac, f"i valori della colonna «{c}» («{neg}», «{pos}») indicano unità positive e negative")
    return best[0], best[2]


def _colonne_scheda(df, col_id, canon_id, voc=None, foglio="", spieg=None):
    """Abbina le colonne note della scheda (tipo, spessore, margini, fase, ...): prima i nomi del
    programma, poi il vocabolario (in più lingue), poi i valori (per il tipo positiva/negativa)."""
    voc = voc or V.vocabolario()
    spieg = {} if spieg is None else spieg
    out = {canon_id: col_id}
    cols = [str(c) for c in df.columns]
    contesto = {"tabella": foglio, "colonne": cols} if foglio else cols
    # i termini insegnati dall'utente (o dalla ricetta) prevalgono sui nomi del programma
    for c in df.columns:
        if c == col_id:
            continue
        r = _migliore(voc, c, "colonna", contesto, soglia=0.9, canonici=set(_CANDIDATI_SCHEDA))
        if r is not None and _insegnato(r) and r.canonico in _CANDIDATI_SCHEDA and r.canonico not in out:
            out[r.canonico] = c
            spieg[f"colonna:{foglio}:{c}"] = r.motivo
    low = {_norm(c): c for c in df.columns if c not in out.values()}
    for canon, alias in _CANDIDATI_SCHEDA.items():
        if canon in out:
            continue
        if canon in df.columns:
            out[canon] = canon
            continue
        for a in alias:
            if _norm(a) in low:
                col = low[_norm(a)]
                if canon in _NUMERICI_ALIAS and not _numerica(df[col]):
                    continue           # "Base" può essere la forma del fondo, non una quota
                out[canon] = col
                break
    for canon, col in out.items():
        if col == canon or col == col_id or f"colonna:{foglio}:{col}" in spieg:
            continue
        r = _migliore(voc, col, "colonna", contesto, soglia=0.5, canonici=(canon,))
        spieg[f"colonna:{foglio}:{col}"] = r.motivo if r else f"«{col}» è un nome noto al programma per «{canon}»"
    # il vocabolario per le colonne che restano: la proposta più sicura per prima
    usate = set(out.values())
    proposte = []
    for c in df.columns:
        if c in usate:
            continue
        r = _migliore(voc, c, "colonna", contesto, soglia=0.75, canonici=set(_CANDIDATI_SCHEDA))
        if r is not None and r.canonico in _CANDIDATI_SCHEDA:
            proposte.append((r.punteggio, c, r))
    for _, c, r in sorted(proposte, key=lambda x: -x[0]):
        if r.canonico in out or c in usate:
            continue
        if r.canonico in _NUMERICI_SCHEDA and not _numerica(df[c]):
            continue
        out[r.canonico] = c
        usate.add(c)
        spieg[f"colonna:{foglio}:{c}"] = r.motivo
    if sc.C_TIPO not in out:
        c, motivo = _colonna_tipo_dai_valori(df, usate, voc)
        if c is not None:
            out[sc.C_TIPO] = c
            spieg[f"colonna:{foglio}:{c}"] = motivo
    return out


def _cifre(serie):
    """Vero se i valori sono quasi tutti numeri di unità (anche elenchi «12, 15»), o se non ce ne sono."""
    v = serie.dropna()
    v = v[v.astype(str).str.strip() != ""]
    return not len(v) or v.astype(str).str.contains(r"\d").mean() >= 0.6


def _rapporti(tabelle, foglio_us, voc=None, spieg=None, idcol=None):
    voc = voc or V.vocabolario()
    spieg = {} if spieg is None else spieg

    def interi(s):
        v = s.dropna()
        return bool(len(v)) and np.mean([_intero(x) is not None for x in v]) > 0.8
    for nome, df in tabelle.items():
        cols = list(df.columns)
        for i, c in enumerate(cols):
            if not 0 < i < len(cols) - 1 or pd.api.types.is_numeric_dtype(df[c]):
                continue
            v = df[c].dropna().astype(str).map(_norm)
            u = v.unique()
            if len(v) < 2 or len(u) > 100:
                continue
            noti = {x: _rapporto(x, voc) in _RAPP_SET for x in u}
            if v.map(noti).mean() > 0.6 and interi(df[cols[i - 1]]) and interi(df[cols[i + 1]]):
                return {"modo": "foglio", "foglio": nome, "colonne": [cols[i - 1], c, cols[i + 1]]}
    if foglio_us and foglio_us in tabelle:
        df = tabelle[foglio_us]
        cols = [str(c) for c in df.columns]
        mappa = {}
        for c in df.columns:
            if c == idcol:
                continue
            rel, motivo = _rapporto_colonna(c, voc, {"tabella": foglio_us, "colonne": cols})
            if rel is None:
                continue
            esatto = _norm(c) in _RAPP_SET or _norm(c) in RAPPORTI_INGLESE
            if not esatto and not _cifre(df[c]):
                continue          # «Sopra», «Above» con testi: non sono elenchi di unità (vuote vanno bene)
            mappa[c] = rel
            if motivo:
                spieg[f"colonna:{foglio_us}:{c}"] = motivo
        if mappa:
            return {"modo": "colonne", "foglio": foglio_us, "colonne": mappa}
        # una colonna di testo con i rapporti scritti per esteso (o nel formato di pyArchInit)
        for c in df.columns:
            r = None
            if _norm(c) not in ("rapporti", "rapporti stratigrafici", "relations", "relationships",
                                "stratigraphic relations", "matrix", "harris"):
                r = _migliore(voc, c, "colonna", soglia=0.8, canonici=("rapporti",))
                if r is None:
                    continue
            v = df[c].dropna().astype(str).head(50)
            if len(v) and v.map(lambda x: len(tg.rapporti_da_testo(x)) > 0).mean() > 0.5:
                if r is not None:
                    spieg[f"colonna:{foglio_us}:{c}"] = r.motivo
                return {"modo": "testo", "foglio": foglio_us, "colonna": c}
    return {"modo": "nessuno"}


def _note_identificativi(df, col):
    """Note sui numeri di unità scritti in forma composta («US 1005», «1005a», «SU-12») e sui numeri che
    si ripetono tra siti o saggi diversi (sito + numero in due colonne)."""
    out = []
    if col not in df.columns:
        return out
    v = df[col].dropna()
    v = v[v.astype(str).str.strip() != ""]
    if not len(v):
        return out
    parti = tg.separa_identificativo(v)
    composti = parti[(parti["prefisso"].notna() | parti["suffisso"].notna()) & parti["numero"].notna()]
    if len(composti):
        i = composti.index[0]
        out.append(f"Numeri di US scritti con sigle o lettere in «{col}» (es. «{v.loc[i]}»): "
                   f"si usa il numero ({int(composti.loc[i, 'numero'])})")
        num = parti["numero"].dropna()
        testi = v.loc[num.index].astype(str).str.strip()
        diversi = testi.groupby(num.values).nunique()
        doppi = diversi[diversi > 1]
        if len(doppi):
            n0 = int(doppi.index[0])
            es = sorted(set(testi[num.values == n0]))[:2]
            out.append(f"{len(doppi)} numeri di US scritti in modi diversi diventano una sola unità "
                       f"(es. «{es[0]}» e «{es[1]}»)")
    numeri = v.map(_intero)
    if numeri.notna().all() and numeri.duplicated().any():
        voc = V.vocabolario()
        sn = tg.trova_sito_numero(df)
        prima = [sn[0]] if sn and sn[1] == col else []
        for c in prima + [c for c in df.columns if c not in prima]:
            if c == col:
                continue
            r = None if _norm(c) in tg._NOMI_SITO else _migliore(voc, c, "colonna", soglia=0.8,
                                                                    canonici=("sito", "area", "intervento"))
            if _norm(c) not in tg._NOMI_SITO and r is None:
                continue
            coppie = pd.DataFrame({"s": df.loc[v.index, c].astype(str), "n": numeri})
            if not coppie.duplicated().any():
                out.append(f"Il numero di US si ripete in «{c}» diversi: per importare un sito alla volta "
                           f"aggiungi un filtro su «{c}»")
                break
    return out


def proponi(files, termini=None):
    """Abbinamento proposto per i file indicati, con il motivo di ogni scelta. ``termini`` aggiunge
    termini al vocabolario per questa proposta ({concetto: [nomi]})."""
    layers_info, tabelle_per_file = esamina(files)
    abb = Abbinamento()
    if termini:
        abb.termini = {k: list(v) if not isinstance(v, str) else [v] for k, v in termini.items()}
    voc = vocabolario_per(abb)
    spieg = abb.spiegazioni
    noti = set()
    tabs = {}
    origine = {}            # foglio nel progetto -> (file, foglio nel file)
    if tabelle_per_file:
        # il file con il foglio US più convincente; gli altri file di tabelle restano collegati
        for f, t in tabelle_per_file.items():
            sp = {}
            (fus, cus), (fusm, cusm) = _schede(t, voc, sp)
            if fus and abb.tabella is None:
                spieg.update(sp)
                abb.tabella, abb.foglio_us = f, fus
                abb.colonne_us = _colonne_scheda(t[fus], cus, sc.C_US, voc, fus, spieg)
                noti |= {_intero(v) for v in t[fus][cus].dropna()}
                if fusm:
                    abb.foglio_usm = fusm
                    abb.colonne_usm = _colonne_scheda(t[fusm], cusm, sc.C_USM, voc, fusm, spieg)
                    noti |= {_intero(v) for v in t[fusm][cusm].dropna()}
                abb.note.append(f"Schede US nel foglio «{fus}» (colonna «{cus}»)" +
                                (f", USM nel foglio «{fusm}»" if fusm else ""))
                abb.note.extend(_note_identificativi(t[fus], cus))
        if abb.tabella is None:
            abb.note.append("Nessun foglio con i numeri di US: le schede verranno create dai poligoni")
        else:
            abb.tabelle_extra = [f for f in tabelle_per_file if f != abb.tabella]
            for f in [abb.tabella] + abb.tabelle_extra:
                for nome, df in tabelle_per_file[f].items():
                    k = nome if nome not in tabs else f"{os.path.splitext(os.path.basename(f))[0]} · {nome}"
                    tabs[k] = df
                    origine[k] = (f, nome)
            if abb.tabelle_extra:
                abb.note.append(f"{len(abb.tabelle_extra)} altri file di tabelle collegati")
            idc = abb.colonne_us.get(sc.C_US)
            abb.rapporti = _rapporti(tabs, abb.foglio_us, voc, spieg, idc)
            r = abb.rapporti
            # colonne «padre»: l'unità che questa riempie (Fill of, Riempie…)
            dus = tabs[abb.foglio_us]
            for c in dus.columns:
                rel = COLONNE_PADRE.get(_norm(c))
                if rel and c != idc and (r.get("modo") != "colonne" or c not in r.get("colonne", {})):
                    v = dus[c].dropna()
                    if len(v) and np.mean([_intero(x) is not None for x in v]) > 0.8:
                        abb.rapporti_extra.append({"foglio": abb.foglio_us, "colonna": c, "rapporto": rel,
                                                   "colonna_unita": idc})
                        abb.note.append(f"Rapporti «{rel}» dalla colonna «{c}»")
            if r["modo"] != "nessuno" or not abb.rapporti_extra:
                abb.note.append({"foglio": f"Rapporti dal foglio «{r.get('foglio')}»",
                                 "colonne": f"Rapporti dalle colonne della scheda US ({', '.join(r.get('colonne', {}))})",
                                 "testo": f"Rapporti dal testo della colonna «{r.get('colonna')}»",
                                 "nessuno": "Nessun rapporto stratigrafico trovato: le basi non saranno agganciate"}[r["modo"]])
            abb.vocabolari = _proponi_vocabolari(abb, tabs, voc)
            usati = {abb.foglio_us, abb.foglio_usm, r.get("foglio") if r.get("modo") == "foglio" else None}
            abb.fogli_collegati = _proponi_collegati(tabs, usati, voc, spieg)
    noti.discard(None)
    testi = [li for li in layers_info if li.geometria == "testo"]
    for li in layers_info:
        r = RuoloLayer(li.sorgente, li.layer)
        nome = f"{os.path.splitext(os.path.basename(li.sorgente))[0]} {li.layer}"
        ruolo, parola, motivo_voc = _ruolo_proposto(
            li.layer if li.sorgente.lower().endswith((".gpkg", ".dxf", ".sqlite", ".db")) else
            (li.layer if _norm(li.layer) == _norm(os.path.splitext(os.path.basename(li.sorgente))[0]) else nome),
            li.geometria, voc)
        g = leggi_layer(li.sorgente, li.layer)
        motivo = []
        dal_nome = motivo_voc or f"nome «{parola}»"
        if li.geometria == "poligono":
            if ruolo not in ("us", "usm", "area", "sezioni_disegno", "ignora"):
                ruolo = "us"
                motivo.append("poligoni")
            else:
                motivo.append(dal_nome)
            if li.crs is None and li.layer == sc.L_SEZ_DISEGNO:
                ruolo = "sezioni_disegno"
        elif li.geometria == "punto":
            if ruolo not in ("quote", "reperti", "campioni", "ignora"):
                ruolo = "quote" if (li.ha_z or _campo_quota(g, voc)) else "ignora"
                motivo.append("punti con quota" if ruolo == "quote" else "punti senza quota")
            else:
                motivo.append(dal_nome)
        elif li.geometria == "linea":
            if ruolo not in ("profili", "sezioni", "fondi", "ignora"):
                ruolo = "profili" if li.ha_z else "sezioni"
                motivo.append("linee 3D" if li.ha_z else "linee 2D")
            else:
                motivo.append(dal_nome)
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
        if motivo_voc and motivo and motivo[0] == motivo_voc:
            spieg[f"layer:{li.layer}"] = motivo_voc
        r.ruolo = ruolo
        if ruolo in ("us", "usm") and li.ha_z:
            r.quote_vertici = True
            motivo.append("quote dai vertici 3D")
        if ruolo in ("us", "usm", "quote", "profili", "reperti", "campioni", "sezioni_disegno"):
            campo, punti, motivo_campo = _campo_unita(g, noti, voc)
            if campo:
                r.campo_unita = campo
                motivo.append(f"numero di US dal campo «{campo}»")
                if motivo_campo:
                    spieg[f"colonna:{li.layer}:{campo}"] = motivo_campo
                if ruolo in ("us", "usm"):
                    abb.note.extend(_note_identificativi(g, campo))
            elif ruolo in ("us", "usm") and testi:
                r.testi_unita = testi[0].layer
                motivo.append(f"numero di US dalle etichette «{testi[0].layer}»")
            elif ruolo == "quote":
                motivo.append("US assegnata dalla posizione (solo dove un solo poligono contiene il punto)")
        if ruolo == "quote":
            if r.quota_da != "testo":
                if not li.ha_z:
                    cq = _campo_quota(g, voc)
                    r.quota_da = f"campo:{cq}" if cq else "z"
                    if cq:
                        motivo.append(f"quota dal campo «{cq}»")
            ct = _campo_tipo(g, voc)
            if ct:
                r.campo_tipo = ct
                motivo.append(f"tipo di quota dal campo «{ct}»")
            else:
                n = _norm(li.layer + " " + os.path.basename(li.sorgente))
                r.tipo_predefinito = "inf" if re.search(r"inf|base|bottom|letto", n) else \
                    ("rasatura" if "rasatura" in n else "sup")
                motivo.append(f"tipo di quota «{r.tipo_predefinito}» per tutti i punti")
        if ruolo == "profili":
            ct = _campo_tipo(g, voc)
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
    # CSV con geometrie senza un foglio di schede riconosciuto: le sue colonne sono le schede
    if abb.tabella is None:
        for r in abb.layers:
            if r.ruolo == "us" and r.campo_unita and r.sorgente in tabelle_per_file:
                t = tabelle_per_file[r.sorgente]
                nome = next(iter(t))
                if r.campo_unita in t[nome].columns:
                    abb.tabella, abb.foglio_us = r.sorgente, nome
                    abb.colonne_us = _colonne_scheda(t[nome], r.campo_unita, sc.C_US, voc, nome, spieg)
                    tabs = dict(t)
                    origine = {k: (r.sorgente, k) for k in t}
                    abb.vocabolari = _proponi_vocabolari(abb, tabs, voc)
                    abb.note = [n for n in abb.note if not n.startswith("Nessun foglio con i numeri")]
                    abb.note.append(f"Schede dalle colonne di «{os.path.basename(r.sorgente)}» (numero: «{r.campo_unita}»)")
                    break
    # come sono stati riordinati i fogli usati (intestazione spostata, tabella trasposta, matrice…)
    if abb.foglio_us:
        usati = [abb.foglio_us, abb.foglio_usm, abb.rapporti.get("foglio") if abb.rapporti.get("modo") == "foglio"
                 else None] + [v.get("foglio") for v in (abb.fogli_collegati or {}).values()]
        for k in dict.fromkeys(x for x in usati if x and x in origine):
            f, nome_f = origine[k]
            for m in note_tabelle(f).get(nome_f, []):
                abb.note.append(f"Foglio «{k}»: {m}")
    # archivi più ampi della pianta, riempimenti senza pianta propria
    if abb.foglio_us and abb.foglio_us in tabs:
        poli = set()
        for r in abb.layers:
            if r.ruolo == "us" and r.campo_unita:
                poli |= {_intero(v) for v in leggi_layer(r.sorgente, r.layer)[r.campo_unita]}
        poli.discard(None)
        schede = {_intero(v) for v in tabs[abb.foglio_us][abb.colonne_us[sc.C_US]]}
        schede.discard(None)
        senza = schede - poli
        riempie = bool(abb.rapporti_extra) or sc.R_RIEMPIE in (abb.rapporti.get("colonne") or {}).values() \
            if isinstance(abb.rapporti.get("colonne"), dict) else bool(abb.rapporti_extra)
        if poli and riempie and len(senza) > 0.2 * len(schede):
            abb.poligoni_ereditati = True
            abb.note.append("Molte schede senza pianta: i riempimenti useranno il poligono del taglio che riempiono")
        if poli and len(schede) > 3 * len(poli):
            abb.solo_con_poligono = True
            abb.note.append(f"Le schede ({len(schede)}) sono molte più dei poligoni ({len(poli)}): "
                            "si tengono solo le unità con una pianta")
    # superficie di riferimento: serve quando mancano le quote o quando ci sono profondità da usare
    er = esamina_raster(files)
    raster = [f for f, d in er.items() if "errore" not in d and d.get("tipo") == "dem" and not d.get("differenza")]
    differenze = [f for f, d in er.items() if "errore" not in d and d.get("differenza")]
    orto = [f for f, d in er.items() if "errore" not in d and d.get("tipo") == "ortofoto"]
    from .modelli3d import EST_MODELLI
    for f in files:
        if os.path.splitext(f)[1].lower() in EST_MODELLI:
            abb.modelli3d.append({"percorso": f, "spostamento": [0.0, 0.0, 0.0]})
            abb.note.append(f"Modello 3D «{os.path.basename(f)}»: sarà mostrato accanto alle unità")
    if orto:
        abb.ortofoto = orto[0]
        abb.note.append(f"Ortofoto «{os.path.basename(orto[0])}»: sarà drappeggiata sul modello")
    # molti punti quotati senza numero di US, con un modello del terreno: servono solo alla superficie
    if raster:
        n_punti = {li.layer: li.n for li in layers_info}
        for r in abb.layers:
            if r.ruolo == "quote" and not r.campo_unita and r.quota_da != "testo" and \
                    n_punti.get(r.layer, 0) >= PUNTI_SOLO_SUPERFICIE:
                r.solo_superficie = True
                r.motivo += "; punti senza numero di US: solo per la superficie di riferimento"
    ha_quote = any((r.ruolo == "quote" and not r.solo_superficie) or r.quote_vertici for r in abb.layers)
    if raster:
        abb.superficie = {"tipo": "raster", "sorgente": raster[0], "abbassa": 0.0}
        abb.note.append(f"Modello del terreno «{os.path.basename(raster[0])}» usato come superficie di riferimento "
                        "per le unità senza quote")
        if differenze:
            abb.superficie["correzione"] = differenze[0]
            abb.note.append(f"«{os.path.basename(differenze[0])}» contiene differenze di quota (valori negativi): "
                            "sommato al modello del terreno come troncamento")
        elif any(r.solo_superficie for r in abb.layers):
            abb.superficie["quote"] = True
    elif not ha_quote:
        abb.superficie = {"tipo": "costante", "quota": 0.0, "abbassa": 0.0}
        abb.note.append("Nessuna quota: le unità partono da una superficie piana a quota 0. "
                        "Puoi indicare una quota o un modello del terreno")
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


def _foglio_canonico(nome, df, voc=None):
    """Fogli dal nome inglese o in altre lingue (Phases, Finds, Mobilier, Funde…) -> foglio e colonne
    attesi dal programma."""
    canon = next((c for c, (nomi, _) in FOGLI_ALIAS.items() if _norm(nome) in nomi and c != nome), None)
    if canon is None:
        r = _migliore(voc or V.vocabolario(), nome, "tabella", soglia=0.7, canonici=tuple(FOGLI_ALIAS))
        canon = r.canonico if r is not None and r.canonico in FOGLI_ALIAS and r.canonico != nome else None
    if canon is None:
        return nome, df
    mappa = _mappa_alias(df, canon, voc, nome)
    return canon, df.rename(columns={v: k for k, v in mappa.items()})


def _tipo_canonico(v, predefinito, voc=None):
    """Tipo di quota del programma per un valore dell'archivio («top», «Oberkante», «q.sup»…)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return predefinito
    n = _norm(v)
    if n in _SIN:
        return _SIN[n]
    r = (voc or V.vocabolario()).riconosci_valore(v, "tipo_quota")
    return r if r in sc.TIPI_QUOTA else predefinito


# ============================================================================ ricetta: trasformazioni
PAROLE_NEGATIVA = ("neg", "tagl", "interfacc")
VALORI_NEGATIVA = {"cut", "interface", "intervention", "cut feature", "negative feature", "n"}
FATTORI = {"m": 1.0, "cm": 0.01, "mm": 0.001}
COLONNE_PADRE = {"fill of": sc.R_RIEMPIE, "filled in": sc.R_RIEMPIE, "fills": sc.R_RIEMPIE, "riempie": sc.R_RIEMPIE,
                 "riempimento di": sc.R_RIEMPIE, "parent": sc.R_RIEMPIE, "contained by": sc.R_RIEMPIE,
                 "within": sc.R_RIEMPIE}
TUTTI_RAPPORTI = sorted(set(RAPPORTI_COLONNE) | set(RAPPORTI_INGLESE), key=len, reverse=True)


def _tipo_da_valore(v, voc=None):
    """«positiva» o «negativa» per un valore del tipo di unità: il vocabolario (Cut, Creusement, Eingriff,
    Taglio…), poi le parole del programma; quello che non si riconosce è positivo."""
    t = _norm(v)
    if t in ("positiva", "negativa"):
        return t
    r = (voc or V.vocabolario()).riconosci_valore(v, "tipo") if t and t != "nan" else None
    if r in ("positiva", "negativa"):
        return r
    return "negativa" if any(p in t for p in PAROLE_NEGATIVA) or t in VALORI_NEGATIVA else "positiva"


def _vocabolario(abb, chiave):
    """Tabella di corrispondenza della ricetta (valore dell'archivio -> valore del programma)."""
    return {_norm(k): v for k, v in ((abb.vocabolari or {}).get(chiave) or {}).items()}


def _tutte_le_tabelle(abb):
    """I fogli del file delle schede e dei file collegati, in un solo dizionario."""
    tabs = {}
    for f in [abb.tabella] + list(abb.tabelle_extra or []):
        if not f or not os.path.exists(f):
            continue
        for nome, df in leggi_tabelle(f).items():
            k = nome if nome not in tabs else f"{os.path.splitext(os.path.basename(f))[0]} · {nome}"
            df.attrs["s3d_file"] = os.path.abspath(f)       # da dove viene: serve per i percorsi relativi
            tabs[k] = df
    return tabs


EST_IMMAGINI = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"}


def risolvi_file(valori, basi, profondita=4, massimo=50000):
    """Percorsi assoluti dei file citati in una tabella (foto, disegni): assoluti, relativi a una delle
    cartelle ``basi``, oppure cercati per nome nelle loro sottocartelle. None dove non si trovano."""
    indice = None

    def cerca(nome):
        nonlocal indice
        if indice is None:
            indice = {}
            for b in basi:
                n0 = b.rstrip(os.sep).count(os.sep)
                for rad, cartelle, files in os.walk(b):
                    if rad.count(os.sep) - n0 >= profondita:
                        cartelle[:] = []
                    cartelle[:] = [c for c in cartelle if not c.startswith((".", "_"))]
                    for f in files:
                        indice.setdefault(f.lower(), os.path.join(rad, f))
                    if len(indice) > massimo:
                        break
        return indice.get(nome.lower())

    out = []
    for v in valori:
        if v is None or (isinstance(v, float) and np.isnan(v)) or not str(v).strip():
            out.append(None)
            continue
        s = str(v).strip().replace("\\", os.sep).replace("/", os.sep)
        trovato = s if os.path.isabs(s) and os.path.isfile(s) else None
        for b in basi:
            if trovato:
                break
            p = os.path.join(b, s)
            if os.path.isfile(p):
                trovato = p
        if not trovato:
            trovato = cerca(os.path.basename(s))
        out.append(os.path.abspath(trovato) if trovato else None)
    return out


def _rinomina(df, colonne):
    """Colonne dell'archivio -> nomi del programma. Se due nomi usano la stessa colonna la si copia."""
    df = df.copy()
    usate = {}
    for canon, col in (colonne or {}).items():
        if col and col in df.columns and canon != col:
            usate.setdefault(col, []).append(canon)
    # una colonna dell'archivio che ha già il nome (anche con altre maiuscole) di un campo del programma
    # riempito da un'altra colonna: la si tiene con un nome diverso (i GeoPackage non distinguono le maiuscole)
    nuovi = {c.lower() for cs in usate.values() for c in cs}
    for c in list(df.columns):
        if c.lower() in nuovi and c not in usate:
            df = df.rename(columns={c: f"{c} (archivio)"})
    for col, canoni in usate.items():
        for canon in canoni:
            df[canon] = df[col]
        if len(canoni) == 1:
            df = df.drop(columns=[col])
    return df


def _filtra(df, filtri, dove, layer=None):
    """Applica i filtri della ricetta. Un filtro senza layer vale per ogni layer (o tabella) che ha la
    colonna; il nome della colonna si cerca anche senza badare alle maiuscole (SITECODE / SiteCode),
    e così il nome del layer."""
    tolte = 0
    for f in filtri or []:
        fl = f.get("layer")
        if f.get("dove", "scheda") != dove or \
                (layer and fl not in (None, "", layer) and str(fl).strip().lower() != str(layer).strip().lower()):
            continue
        col = f.get("colonna")
        if col not in df.columns:
            simili = [c for c in df.columns if str(c).strip().lower() == str(col or "").strip().lower()]
            if len(simili) != 1:
                continue
            col = simili[0]
        valori = {str(v).strip() for v in f.get("valori") or []}
        dentro = df[col].map(lambda v: str(_intero(v) if isinstance(v, float) and v == int(v) else v).strip()
                             if v is not None and not (isinstance(v, float) and np.isnan(v)) else "").isin(valori)
        tieni = ~dentro if f.get("escludi") else dentro
        tolte += int((~tieni).sum())
        df = df[tieni]
    return df, tolte


def _misura(serie, unita, nome_col, nulli):
    v = serie.map(_numero)
    if nulli:
        v = v.map(lambda x: None if x is not None and any(abs(x - n) < 1e-9 for n in nulli) else x)
    v = pd.to_numeric(v, errors="coerce")
    if unita in FATTORI:
        return v * FATTORI[unita]
    if "cm" in _norm(nome_col).split() or "(cm)" in _norm(nome_col) or (v.dropna() > 5).mean() > 0.5:
        return v / 100.0
    if "mm" in _norm(nome_col).split() or "(mm)" in _norm(nome_col):
        return v / 1000.0
    return v


def _rapporti_da_testo(testo):
    """Rapporti scritti in un campo di testo: «copre 1002, 1003; taglia 1005», oppure il formato
    di pyArchInit [['Copre', '1002', '1', 'Sito'], …]. Ritorna [(rapporto, unità)]."""
    if testo is None or (isinstance(testo, float) and np.isnan(testo)):
        return []
    s = str(testo).strip()
    out = []
    if s.startswith("[["):
        import ast
        try:
            for el in ast.literal_eval(s):
                if len(el) >= 2 and _intero(el[1]) is not None:
                    out.append((_rapporto(el[0]), _intero(el[1])))
            return out
        except (ValueError, SyntaxError):
            pass
    t = _norm(s)
    trovati = []
    for r in TUTTI_RAPPORTI:
        for m in re.finditer(r"(^|[^a-z])" + re.escape(r) + r"($|[^a-z])", t):
            a, b = m.start() + len(m.group(1)), m.end() - len(m.group(2))
            if not any(x[0] <= a < x[1] or x[0] < b <= x[1] for x in trovati):
                trovati.append((a, b, r))
    trovati.sort()
    for i, (a, b, r) in enumerate(trovati):
        fine = trovati[i + 1][0] if i + 1 < len(trovati) else len(t)
        for n in re.findall(r"\d+", t[b:fine]):
            out.append((_rapporto(r), int(n)))
    return out


def _leggi_rapporti(abb, tabs, note):
    """Tutti i rapporti della ricetta: foglio, colonne, testo, colonne «padre»."""
    voc = _vocabolario(abb, "rapporto")
    termini = vocabolario_per(abb)

    def canonico(t):
        k = _norm(t)
        if k in voc:
            return voc[k] or None          # "" = da ignorare
        r = _rapporto(t, termini)
        return r if r in RAPPORTI_COLONNE else None

    righe, ignoti = [], set()
    r = abb.rapporti or {"modo": "nessuno"}
    idcol = abb.colonne_us.get(sc.C_US)
    if r.get("modo") == "foglio" and r.get("foglio") in tabs:
        rdf = tabs[r["foglio"]]
        a, t, b = r["colonne"]
        for ua, tt, ub in zip(rdf[a], rdf[t], rdf[b]):
            ua, ub = _intero(ua), _intero(ub)
            if ua is None or ub is None or tt is None or (isinstance(tt, float) and np.isnan(tt)):
                continue
            c = canonico(tt)
            if c:
                righe.append((ua, c, ub))
            else:
                ignoti.add(str(tt))
    elif r.get("modo") == "colonne" and r.get("foglio") in tabs:
        src = tabs[r["foglio"]]
        for _, x in src.iterrows():
            ua = _intero(x[idcol])
            if ua is None:
                continue
            for col, rel in r["colonne"].items():
                rel = canonico(rel)
                v = x[col]
                if rel is None or v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                numeri = [_intero(v)] if isinstance(v, (int, float, np.integer, np.floating)) else \
                    [int(b) for b in re.findall(r"\d+", str(v))]
                righe.extend((ua, rel, b) for b in numeri if b is not None)
    elif r.get("modo") == "testo" and r.get("foglio") in tabs:
        src = tabs[r["foglio"]]
        cu = r.get("colonna_unita") or idcol
        for ua, testo in zip(src[cu], src[r["colonna"]]):
            ua = _intero(ua)
            if ua is None:
                continue
            for rel, ub in tg.rapporti_da_testo(testo):       # in più lingue, con «=», «>», «1001-1004»
                c = canonico(rel)
                if c:
                    righe.append((ua, c, ub))
    for e in abb.rapporti_extra or []:
        if e.get("foglio") not in tabs:
            continue
        src = tabs[e["foglio"]]
        cu = e.get("colonna_unita") or idcol
        if cu not in src.columns or e.get("colonna") not in src.columns:
            continue
        rel = canonico(e.get("rapporto", sc.R_RIEMPIE)) or sc.R_RIEMPIE
        n = 0
        for ua, ub in zip(src[cu], src[e["colonna"]]):
            ua, ub = _intero(ua), _intero(ub)
            if ua is not None and ub is not None and ua != ub:
                righe.append((ua, rel, ub))
                n += 1
        note.append(f"{n} rapporti «{rel}» dalla colonna «{e['colonna']}»")
    if ignoti:
        note.append("Rapporti non riconosciuti e ignorati: " + ", ".join(sorted(ignoti)[:12]) +
                    " (si possono tradurre nel vocabolario dei rapporti)")
    return righe


# colonne attese nei fogli collegati, e i nomi canonici del vocabolario da tradurre per quel foglio
_COLONNE_COLLEGATI = {
    sc.S_MATERIALI: {"US", "Classe", "Tipo / forma", "NR", "Peso (g)", "NMI", "Cassetta"},
    sc.S_DOC: {"US/USM", "Soggetto", "Data", "File", "Tipo"},
    sc.S_CAMPIONI: {"Campione", "US", "Tipo", "Analisi", "Peso (g)", "Cassetta"},
    sc.S_FASI: {"Fase", "Titolo", "Periodo", "Da (anno)", "A (anno)"},
}
_CANONICI_COLLEGATI = {
    sc.S_DOC: {"US": "US/USM", "Tipo / forma": "Tipo"},
    sc.S_CAMPIONI: {"Tipo / forma": "Tipo"},
    sc.S_FASI: {"Datazione da": "Da (anno)", "Datazione a": "A (anno)"},
}
_CHIAVE_COLLEGATI = {sc.S_MATERIALI: "US", sc.S_DOC: "US/USM", sc.S_CAMPIONI: "US", sc.S_FASI: "Fase"}


def _mappa_alias(df, canon, voc=None, nome="", spieg=None):
    """Colonne di un foglio -> colonne attese per quel tipo di foglio (materiali, fasi…): i nomi del
    programma, poi il vocabolario (in più lingue)."""
    colonne = FOGLI_ALIAS.get(canon, ([], {}))[1]
    mappa, presi = {}, set()
    for c in df.columns:
        k = colonne.get(_norm(c))
        if k and k not in presi and k not in df.columns:
            mappa[k] = c
            presi.add(k)
    attese = _COLONNE_COLLEGATI.get(canon)
    if not attese:
        return mappa
    voc = voc or V.vocabolario()
    trad = _CANONICI_COLLEGATI.get(canon, {})
    cols = [str(c) for c in df.columns]
    proposte = []
    for c in df.columns:
        if c in mappa.values() or str(c) in attese:
            continue
        r = _migliore(voc, c, "colonna", {"tabella": nome or canon, "colonne": cols}, soglia=0.6)
        k = trad.get(r.canonico, r.canonico) if r is not None else None
        if k in attese and k not in df.columns:
            proposte.append((r.punteggio, c, k, r.motivo))
    for _, c, k, motivo in sorted(proposte, key=lambda x: -x[0]):
        if k in presi or c in mappa.values():
            continue
        mappa[k] = c
        presi.add(k)
        if spieg is not None:
            spieg[f"colonna:{nome}:{c}"] = motivo
    return mappa


def _proponi_collegati(tabs, usati, voc=None, spieg=None):
    """Fogli da leggere come materiali, fasi, documentazione, campioni: dal nome del foglio (parole del
    programma o vocabolario in più lingue: «Finds», «Mobilier», «Funde», «Photos», «Prélèvements»…)."""
    voc = voc or V.vocabolario()
    out = {}
    for nome, df in tabs.items():
        if nome in usati:
            continue
        canon, motivo = None, None
        for c, (nomi, _) in FOGLI_ALIAS.items():
            if c not in out and (_norm(nome) in nomi or _norm(nome) == _norm(c)):
                canon = c
                break
        if canon is None:
            r = _migliore(voc, nome, "tabella", soglia=0.7, canonici=tuple(FOGLI_ALIAS))
            if r is None or r.canonico not in FOGLI_ALIAS or r.canonico in out:
                continue
            canon, motivo = r.canonico, r.motivo
        sp = {}
        mappa = _mappa_alias(df, canon, voc, nome, sp)
        chiave = _CHIAVE_COLLEGATI.get(canon)
        if motivo is not None and chiave and chiave not in mappa and chiave not in df.columns:
            continue           # riconosciuto solo dal nome, ma senza la colonna che lo collega alle unità
        out[canon] = {"foglio": nome, "colonne": mappa}
        if spieg is not None:
            spieg.update(sp)
            if motivo:
                spieg[f"tabella:{nome}"] = motivo
    return out


def _proponi_vocabolari(abb, tabs, voc=None):
    """Tabelle di corrispondenza proposte, da correggere nel wizard: tipo di unità, rapporti."""
    termini = voc or vocabolario_per(abb)
    voc = {}
    col = abb.colonne_us.get(sc.C_TIPO)
    if col and abb.foglio_us in tabs and col in tabs[abb.foglio_us].columns:
        vals = tabs[abb.foglio_us][col].dropna().astype(str).str.strip().unique()
        if 0 < len(vals) <= 40:
            voc["tipo"] = {v: _tipo_da_valore(v, termini) for v in sorted(vals)}
    r = abb.rapporti or {}
    if r.get("modo") == "foglio" and r.get("foglio") in tabs:
        vals = tabs[r["foglio"]][r["colonne"][1]].dropna().astype(str).str.strip().unique()
        if 0 < len(vals) <= 60:
            voc["rapporto"] = {v: (lambda x: x if x in RAPPORTI_COLONNE else "")(_rapporto(v, termini))
                               for v in sorted(vals)}
    return voc


def applica_ricetta(abb, ricetta):
    """Adatta una ricetta salvata (o pronta) ai file di adesso: layer riconosciuti per nome (anche con *),
    fogli e colonne se esistono, trasformazioni copiate. Ritorna (abbinamento, note)."""
    import copy
    import fnmatch
    r = ricetta if isinstance(ricetta, Abbinamento) else Abbinamento.da_json(ricetta)
    out = copy.deepcopy(abb)
    note = []
    n = 0
    for l in out.layers:
        cand = [x for x in r.layers if fnmatch.fnmatch(l.layer.lower(), x.layer.lower()) and
                (not x.sorgente or x.sorgente in ("*", "") or
                 fnmatch.fnmatch(os.path.basename(l.sorgente).lower(), os.path.basename(x.sorgente).lower()))]
        if cand:
            x = cand[0]
            for k in ("ruolo", "campo_unita", "testi_unita", "campo_tipo", "tipo_predefinito", "quota_da", "campo_sezione", "quote_vertici",
                      "campi_scheda", "solo_superficie"):
                setattr(l, k, getattr(x, k))
            l.motivo = f"ricetta «{r.nome or 'salvata'}»"
            out.spiegazioni.pop(f"layer:{l.layer}", None)
            n += 1
        elif any(x.layer == "*" for x in r.layers):
            l.ruolo = "ignora"
    note.append(f"Ricetta applicata a {n} layer")
    tabelle = {}
    for f in [out.tabella] + list(out.tabelle_extra or []):
        if f:
            try:
                for nome in leggi_tabelle(f):
                    tabelle.setdefault(nome, f)
            except Exception:
                pass
    if r.foglio_us and r.foglio_us in tabelle:
        principale = tabelle[r.foglio_us]
        out.tabelle_extra = [f for f in dict.fromkeys([out.tabella] + list(out.tabelle_extra or [])) if f and f != principale]
        out.tabella, out.foglio_us = principale, r.foglio_us
        cols = set(leggi_tabelle(principale)[r.foglio_us].columns)
        out.colonne_us = {k: v for k, v in r.colonne_us.items() if v in cols}
        mancano = sorted(set(r.colonne_us) - set(out.colonne_us))
        if mancano:
            note.append("Colonne della ricetta non trovate: " + ", ".join(mancano))
    elif r.foglio_us:
        note.append(f"Il foglio «{r.foglio_us}» della ricetta non c'è tra i file")
    if r.foglio_usm and r.foglio_usm in tabelle:
        out.foglio_usm, out.colonne_usm = r.foglio_usm, dict(r.colonne_usm)
    if (r.rapporti or {}).get("modo", "nessuno") != "nessuno" and \
            (r.rapporti.get("foglio") in tabelle or r.rapporti.get("foglio") is None):
        out.rapporti = copy.deepcopy(r.rapporti)
    out.rapporti_extra = [e for e in r.rapporti_extra if e.get("foglio") in tabelle]
    if r.foglio_us and out.foglio_us == r.foglio_us:
        # le note della proposta automatica sulle schede non valgono più
        out.note = [n for n in out.note if not isinstance(n, str) or not n.startswith(
            ("Schede US nel foglio", "Nessun rapporto", "Rapporti «", "Nessun foglio con i numeri"))]
    for k in ("vocabolari", "unita_misura", "valori_nulli", "filtri", "poligoni_ereditati", "solo_con_poligono", "nome",
              "fase_composta", "colonne_collegate", "termini"):
        setattr(out, k, copy.deepcopy(getattr(r, k)))
    if r.fogli_collegati is not None:
        out.fogli_collegati = {k: v for k, v in r.fogli_collegati.items() if v.get("foglio") in tabelle}
    if r.crs:
        out.crs = r.crs
    sup = dict(r.superficie or {})
    if sup.get("tipo") == "raster":
        if (out.superficie or {}).get("tipo") == "raster":
            # con un raster di troncamento l'abbassamento fisso della ricetta non serve più
            out.superficie = dict(out.superficie, abbassa=0.0 if out.superficie.get("correzione")
                                  else sup.get("abbassa", 0.0))
        else:
            note.append("La ricetta usa un modello del terreno: aggiungilo ai file")
    elif sup.get("tipo") not in (None, "nessuna"):
        out.superficie = sup
    return out, note


def insegna(ambito, termine, valore, lingua="xx"):
    """L'utente insegna al vocabolario che un nome di layer (``ambito`` «layer», ``valore`` = ruolo) o di
    colonna delle schede («colonna», ``valore`` = colonna del programma, es. «Tipo») ha quel significato.
    Il termine si salva nel vocabolario dell'utente (~/.stratigrafia3d/vocabolario.json) e vale anche per
    i prossimi archivi. Ritorna il concetto del vocabolario."""
    voc = V.vocabolario()
    termine = str(termine or "").strip()
    if not termine:
        raise ValueError("Manca il termine da insegnare")
    if ambito == "layer":
        if valore not in RUOLI:
            raise ValueError(f"Uso del layer sconosciuto: «{valore}»")
        if valore == "ignora":
            concetto = "ignora"
            voc.aggiungi(concetto, termine, lingua, descrizione="un layer da non usare", ambiti=["layer"])
        else:
            cand = [c for c in voc.concetti("layer") if voc.canonico(c, "layer") == valore]
            if not cand:
                raise ValueError(f"Uso del layer sconosciuto: «{valore}»")
            concetto = valore if valore in cand else cand[0]
            voc.aggiungi(concetto, termine, lingua)
    elif ambito == "colonna":
        cand = [c for c in voc.concetti("colonna") if voc.canonico(c, "colonna") == valore]
        if not cand:
            raise ValueError(f"Colonna del programma sconosciuta: «{valore}»")
        concetto = str(valore).lower() if str(valore).lower() in cand else cand[0]
        voc.aggiungi(concetto, termine, lingua)
    else:
        raise ValueError(f"Ambito sconosciuto: «{ambito}»")
    _VOC_CACHE.clear()
    _CACHE_RAPPORTI.clear()
    return concetto


def ricette_pronte():
    """Ricette fornite con il programma: nome -> descrizione."""
    from importlib import resources
    out = {}
    for f in sorted(resources.files("stratigrafia3d.ricette").iterdir(), key=lambda x: x.name):
        if f.name.endswith(".json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            out[f.name[:-5]] = dict(nome=d.get("nome") or f.name[:-5], descrizione=d.get("descrizione", ""))
    return out


def carica_ricetta_pronta(chiave):
    from importlib import resources
    d = json.loads(resources.files("stratigrafia3d.ricette").joinpath(chiave + ".json").read_text(encoding="utf-8"))
    d.pop("descrizione", None)
    return Abbinamento.da_json(d)


def valori_distinti(path, foglio=None, colonna=None, layer=None, massimo=60):
    """Valori distinti (con il conteggio) di una colonna di un foglio o di un campo di un layer."""
    if layer is not None:
        g = leggi_layer(path, layer)
        s = g[colonna]
    else:
        s = leggi_tabelle(path)[foglio][colonna]
    s = s.dropna().map(lambda v: str(_intero(v)) if isinstance(v, float) and v == int(v) else str(v).strip())
    c = s.value_counts()
    return [[k, int(v)] for k, v in c.head(massimo).items()], int(len(c))


def _chiave_fase(p, f):
    """Chiave di una fase composta: «2.1» e 2.10 restano distinti, 2.0 e «2» no."""
    def t(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ("", "nan", "None"):
            return None
        n = _numero(v)
        return str(int(n)) if n is not None and float(n).is_integer() else str(v).strip()
    a, b = t(p), t(f)
    return None if a is None and b is None else (a or "", b or "")


def _collega_colonne(grezzo, tabs, collegamenti):
    """Aggiunge alle schede colonne di altre tabelle, cercate con una chiave (anche a catena)."""
    note = []
    def k(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        n = _numero(v)
        return str(int(n)) if n is not None and float(n).is_integer() else str(v).strip()
    for c in collegamenti or []:
        t, chiave, col = tabs.get(c.get("foglio")), c.get("chiave"), c.get("colonna")
        if t is None or chiave not in t.columns or col not in grezzo.columns:
            note.append(f"Collegamento a «{c.get('foglio')}» non applicato: tabella o colonne mancanti")
            continue
        t = t.drop_duplicates(subset=[chiave])
        chiavi = t[chiave].map(k)
        for porta in c.get("porta") or []:
            if porta in t.columns:
                grezzo[porta] = grezzo[col].map(k).map(dict(zip(chiavi, t[porta])))
        trovate = grezzo[col].map(k).isin(set(chiavi)).sum()
        note.append(f"«{c['foglio']}» collegato alle schede con «{col}»: {int(trovate)} schede su {len(grezzo)}")
    return grezzo, note


def _fasi_composte(spec, tabs, df_schede, grezzo):
    """Numera le fasi composte (periodo + fase) dalla più antica alla più recente.

    Ritorna (numero per ogni riga delle schede, tabella Fasi nel formato del programma, note)."""
    note = []
    cp, cf = (list(spec.get("scheda") or []) + [None, None])[:2]          # una sola colonna: la fase è un testo
    if cp not in grezzo.columns or (cf is not None and cf not in grezzo.columns):
        return None, None, [f"Fase composta: colonne «{cp}» e «{cf}» non trovate nelle schede"]
    esclusi = {str(v).strip().lower() for v in spec.get("esclusi") or []}
    vf = grezzo.loc[df_schede.index, cf] if cf else [None] * len(df_schede)
    chiavi_schede = [None if str(a).strip().lower() in esclusi else _chiave_fase(a, b)
                     for a, b in zip(grezzo.loc[df_schede.index, cp], vf)]
    righe = {}
    tf = tabs.get(spec.get("foglio")) if spec.get("foglio") else None
    if tf is not None:
        fp, ff = (list(spec.get("fasi") or []) + [None, None])[:2]
        if fp in tf.columns and (ff is None or ff in tf.columns):
            for _, r in tf.iterrows():
                k = _chiave_fase(r[fp], r[ff] if ff else None)
                if k is None or k in righe:
                    continue
                righe[k] = dict(da=_numero(r.get(spec.get("da"))), a=_numero(r.get(spec.get("a"))),
                                titolo=r.get(spec.get("titolo")) if spec.get("titolo") else None)
    usate = {k for k in chiavi_schede if k is not None}
    senza = sorted(usate - set(righe))
    if senza:
        note.append(f"{len(senza)} fasi delle schede non compaiono nella periodizzazione: messe dopo le altre")

    def ordine(k):
        r = righe.get(k)
        anno = r["da"] if r and r["da"] is not None else (r["a"] if r and r["a"] is not None else None)
        return (0 if anno is not None else 1, anno if anno is not None else 0, k)
    # «solo_usate»: tralascia le fasi della periodizzazione che nessuna scheda del progetto usa
    tutte = sorted(usate if spec.get("solo_usate") else set(righe) | usate, key=ordine)
    numero = {k: i + 1 for i, k in enumerate(tutte)}
    def nome(k):
        return k[0] if not k[1] else f"Periodo {k[0]}, fase {k[1]}"
    fasi = pd.DataFrame([dict(Fase=numero[k], Titolo=(righe.get(k) or {}).get("titolo") or nome(k),
                              Periodo=k[0] if not k[1] else f"Periodo {k[0]} · fase {k[1]}", **{"Da (anno)": (righe.get(k) or {}).get("da"),
                                                                          "A (anno)": (righe.get(k) or {}).get("a")})
                         for k in tutte])
    note.append(f"Fasi composte da «{cp}» e «{cf}»: {len(tutte)} fasi numerate dalla più antica" if cf else
                f"Fasi dalla colonna «{cp}»: {len(tutte)} fasi numerate dalla più antica")
    return [numero.get(k) if k is not None else None for k in chiavi_schede], fasi, note


def _punti_superficie(g, r, abb, note, voc=None):
    """Punti quotati usati solo per la superficie di riferimento (layer «quote_superficie»): quota dal
    campo, dal testo o dalla Z; nessuna US (assegnarla a decine di migliaia di punti è lento e inutile)."""
    if r.quota_da == "testo" and "Text" in g.columns:
        z = g["Text"].map(_numero)
    elif (r.quota_da or "").startswith("campo:") and r.quota_da[6:] in g.columns:
        z = g[r.quota_da[6:]].map(_numero)
    else:
        z = pd.Series([p.z if p is not None and p.has_z else None for p in g.geometry], index=g.index)
    nulli = [float(v) for v in (abb.valori_nulli or [])]
    z = pd.to_numeric(z.map(lambda v: None if v is None or any(abs(float(v) - n) < 1e-6 for n in nulli) else v),
                      errors="coerce")
    tipi = [_tipo_canonico(v, r.tipo_predefinito or "sup", voc) for v in
            (g[r.campo_tipo] if r.campo_tipo and r.campo_tipo in g.columns else [None] * len(g))]
    ok = [p is not None and not p.is_empty and p.geom_type == "Point" and zz == zz for p, zz in zip(g.geometry, z)]
    out = gpd.GeoDataFrame({sc.F_TIPO_QUOTA: [t for t, k in zip(tipi, ok) if k]},
                           geometry=[Point(p.x, p.y, zz) for p, zz, k in zip(g.geometry, z, ok) if k], crs=g.crs)
    note.append(f"{len(out)} punti quotati di «{r.layer}» usati solo per la superficie di riferimento"
                + (f" ({len(g) - len(out)} senza quota)" if len(out) < len(g) else ""))
    return out


def applica(abb, log=None):
    """Costruisce uno Scavo canonico applicando l'abbinamento."""
    from .progetto import Scavo, _sha256
    log = log or (lambda *a: None)
    s = Scavo()
    note = []
    crs = abb.crs
    voc = vocabolario_per(abb)          # vocabolario + termini e vocabolari della ricetta
    raccolti = {}          # ruolo -> list di GeoDataFrame canonici
    dal_layer = {}         # colonna del programma -> {unità: valore} presi dagli attributi dei poligoni

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
        g, tolti = _filtra(g, abb.filtri, "layer", r.layer)
        if tolti:
            note.append(f"Filtri: {tolti} elementi di «{r.layer}» esclusi")
        if g.empty:
            continue
        if r.ruolo == "quote" and r.solo_superficie:
            # punti che danno solo la forma della superficie di riferimento: nessuna US da assegnare
            raccolti.setdefault("quote_superficie", []).append(_punti_superficie(g, r, abb, note, voc))
            continue
        if r.campo_unita:
            unita = [_intero(v) for v in g[r.campo_unita]]
        elif r.testi_unita:
            unita = _unita_da_testi(g, r.sorgente, r.testi_unita)
        else:
            unita = [None] * len(g)
        g = g.assign(_u=unita)
        for canon, campo in (r.campi_scheda or {}).items():
            if campo in g.columns:
                m = dal_layer.setdefault(canon, {})
                for u, v in zip(g._u, g[campo]):
                    if u is not None and v is not None and not (isinstance(v, float) and np.isnan(v)) and u not in m:
                        m[u] = v
        if r.ruolo in ("us", "usm") and r.quote_vertici:
            nulli_v = [float(v) for v in (abb.valori_nulli or [])]
            pts, uu = [], []
            for u, geom in zip(g._u, g.geometry):
                if u is None or geom is None or not geom.has_z:
                    continue
                for x, y, zv in _coords(geom):
                    if zv is None or not np.isfinite(zv) or abs(zv) < 1e-9 or any(abs(zv - n) < 1e-6 for n in nulli_v):
                        continue
                    pts.append(Point(x, y, zv))
                    uu.append(int(u))
            if pts:
                tipo_v = "rasatura" if r.ruolo == "usm" else "vertice"
                raccolti.setdefault("quote", []).append(gpd.GeoDataFrame(
                    {sc.F_US: uu, sc.F_TIPO_QUOTA: tipo_v}, geometry=pts, crs=g.crs))
                note.append(f"{len(pts)} quote dai vertici 3D di «{r.layer}»")
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
            if not parts:
                note.append(f"«{r.layer}»: nessun poligono con un numero di unità, layer ignorato")
                continue
            out = gpd.GeoDataFrame(parts, geometry="geometry", crs=g.crs)
        elif r.ruolo == "quote":
            if r.quota_da == "testo":
                z = g["Text"].map(_numero)
            elif r.quota_da.startswith("campo:"):
                z = g[r.quota_da[6:]].map(_numero)
            else:
                z = pd.Series([c.z if c.has_z else None for c in g.geometry], index=g.index)
            nulli = [float(v) for v in (abb.valori_nulli or [])]
            vuote = z.map(lambda v: v is None or (isinstance(v, float) and np.isnan(v)) or
                          any(abs(float(v) - n) < 1e-6 for n in nulli))
            if vuote.any():
                note.append(f"{int(vuote.sum())} punti di «{r.layer}» senza quota o con quota nulla: ignorati")
            z = z.where(~vuote, None)
            voc_q = _vocabolario(abb, "tipo_quota")
            tipi = [voc_q.get(_norm(v)) or _tipo_canonico(v, r.tipo_predefinito or "sup", voc) for v in
                    (g[r.campo_tipo] if r.campo_tipo else [None] * len(g))]
            out = gpd.GeoDataFrame({sc.F_US: g._u.values, sc.F_TIPO_QUOTA: tipi},
                                   geometry=[Point(p.x, p.y, zz) if zz is not None and not pd.isna(zz) else None
                                             for p, zz in zip(g.geometry, z)], crs=g.crs)
            out = out[out.geometry.notna()]
        elif r.ruolo == "profili":
            tipi = [_tipo_canonico(v, r.tipo_predefinito or "sup", voc) for v in
                    (g[r.campo_tipo] if r.campo_tipo else [None] * len(g))]
            out = gpd.GeoDataFrame({sc.F_SEZIONE: g[r.campo_sezione].astype(str).values if r.campo_sezione else "—",
                                    sc.F_US: g._u.values, sc.F_INTERFACCIA: tipi}, geometry=g.geometry.values, crs=g.crs)
            out = out[out[sc.F_US].notna()]
        elif r.ruolo == "fondi":
            out = gpd.GeoDataFrame({"tipo": ["linea di fondo"] * len(g)}, geometry=g.geometry.values, crs=g.crs)
            out = out[out.geometry.notna()]
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
    # limiti di scavo molto più ampi delle US (un intero cantiere): si tiene la parte che serve
    if sc.L_AREA in s.layers and sc.L_US in s.layers and len(s.layers[sc.L_US]):
        from shapely.geometry import box as _box
        b = s.layers[sc.L_US].total_bounds
        a = s.layers[sc.L_AREA]
        if (a.total_bounds[2] - a.total_bounds[0]) > 3 * (b[2] - b[0]) + 50 or \
                (a.total_bounds[3] - a.total_bounds[1]) > 3 * (b[3] - b[1]) + 50:
            riquadro = _box(*b).buffer(20)
            a = a[a.intersects(riquadro)].copy()
            a["geometry"] = [x.intersection(riquadro) for x in a.geometry]
            a = a[~a.geometry.is_empty]
            a["geometry"] = [max(getattr(x, "geoms", [x]), key=lambda p: p.area) if x.geom_type != "Polygon" else x
                             for x in a.geometry]
            s.layers[sc.L_AREA] = a[[x.geom_type == "Polygon" for x in a.geometry]]
            note.append("Limite di scavo ritagliato attorno alle unità importate")
    if sc.L_US in s.layers and len(s.layers[sc.L_US]):
        from shapely.geometry import box as _box
        riquadro = _box(*s.layers[sc.L_US].total_bounds).buffer(20)
        for nome in (sc.L_FONDI, sc.L_SEZIONI):
            if nome in s.layers:
                g = s.layers[nome]
                dentro = g[g.intersects(riquadro)]
                if len(dentro) < len(g):
                    s.layers[nome] = dentro
                    note.append(f"«{nome}»: tenuti i {len(dentro)} elementi attorno alle unità (su {len(g)})")

    # ------------------------------------------------ tabelle (file principale + file collegati)
    tabs = _tutte_le_tabelle(abb)
    usati = {abb.foglio_us, abb.foglio_usm}
    if (abb.rapporti or {}).get("modo") == "foglio":
        usati.add(abb.rapporti.get("foglio"))
    collegati = abb.fogli_collegati if abb.fogli_collegati is not None else _proponi_collegati(tabs, usati, voc)
    if sc.L_US in s.layers and sc.L_USM in s.layers:
        # stesso numero disegnato sia come US sia come USM: vale la pianta delle US
        doppi = set(s.layers[sc.L_US][sc.F_US]) & set(s.layers[sc.L_USM][sc.F_USM])
        if doppi:
            s.layers[sc.L_USM] = s.layers[sc.L_USM][~s.layers[sc.L_USM][sc.F_USM].isin(doppi)]
            note.append(f"{len(doppi)} numeri disegnati sia tra le US sia tra le USM: tenuta la pianta delle US "
                        f"({', '.join(map(str, sorted(doppi)[:12]))}{'…' if len(doppi) > 12 else ''})")
    poli_us = set(s.layers[sc.L_US][sc.F_US]) if sc.L_US in s.layers else set()
    poli_usm = set(s.layers[sc.L_USM][sc.F_USM]) if sc.L_USM in s.layers else set()
    nulli = {float(v) for v in (abb.valori_nulli or [])}
    if abb.foglio_us:
        grezzo, tolte = _filtra(tabs[abb.foglio_us], abb.filtri, "scheda")     # i filtri usano i nomi dell'archivio
        if tolte:
            note.append(f"Filtri: {tolte} schede escluse")
        if abb.colonne_collegate:
            grezzo, nc = _collega_colonne(grezzo.copy(), tabs, abb.colonne_collegate)
            note.extend(nc)
        df = _rinomina(grezzo, abb.colonne_us)
        df[sc.C_US] = df[sc.C_US].map(_intero)
        df = df[df[sc.C_US].notna()].copy()
        df[sc.C_US] = df[sc.C_US].astype(int)
        fasi_composte = None
        if abb.fase_composta:
            num, fasi_composte, nf = _fasi_composte(abb.fase_composta, tabs, df, grezzo)
            note.extend(nf)
            if num is not None:
                df[sc.C_FASE] = num
        # in alcuni archivi USM e US stanno nello stesso foglio: si separano con i poligoni
        if not abb.foglio_usm and poli_usm:
            usm_df = df[df[sc.C_US].isin(poli_usm) & ~df[sc.C_US].isin(poli_us)].rename(columns={sc.C_US: sc.C_USM})
            df = df[~df[sc.C_US].isin(usm_df[sc.C_USM])]
            if len(usm_df):
                s.tabelle[sc.S_USM] = usm_df
    else:
        df = pd.DataFrame({sc.C_US: sorted(poli_us)})
        fasi_composte = None
    for canon, m in dal_layer.items():         # valori dagli attributi dei poligoni, dove la scheda non li ha
        val = df[sc.C_US].map(m)
        if canon in df.columns:
            vuoti = df[canon].isna() | (df[canon].astype(str).str.strip() == "")
            df.loc[vuoti, canon] = val[vuoti]
        else:
            df[canon] = val
        note.append(f"«{canon}» completato dagli attributi dei poligoni per {int(val.notna().sum())} unità")
    voc_tipo = _vocabolario(abb, "tipo")
    if sc.C_TIPO not in df.columns:
        testo = df.get(sc.C_CATEGORIA, pd.Series([""] * len(df))).astype(str) + " " + \
            df.get("Definizione", pd.Series([""] * len(df))).astype(str)
        df[sc.C_TIPO] = np.where(testo.str.lower().str.contains("taglio|cut|negativ"), "negativa", "positiva")
        note.append("Colonna Tipo assente: US negative riconosciute dalla parola «taglio»")
    else:
        df[sc.C_TIPO] = df[sc.C_TIPO].map(lambda v: voc_tipo.get(_norm(v)) or _tipo_da_valore(v, voc))
    for canon in (sc.C_SPESSORE, sc.C_PROFONDITA):
        if canon in df.columns:
            df[canon] = _misura(df[canon], (abb.unita_misura or {}).get(canon, "auto"),
                                (abb.colonne_us or {}).get(canon, canon), nulli)
    righe = _leggi_rapporti(abb, tabs, note)
    # unità che non hanno una pianta propria (riempimenti): il poligono dell'unità che riempiono
    schede_ids = set(df[sc.C_US])
    if abb.poligoni_ereditati and sc.L_US in s.layers:
        g_us = s.layers[sc.L_US]
        geo = dict(zip(g_us[sc.F_US], g_us.geometry))
        nuovi = []
        for a, t, b in righe:
            if t == sc.R_RIEMPIE and a in schede_ids and a not in geo and b in geo and a not in {x[0] for x in nuovi}:
                nuovi.append((a, geo[b]))
        if nuovi:
            agg = gpd.GeoDataFrame({sc.F_US: [a for a, _ in nuovi], "poligono_di": "unità riempita"},
                                   geometry=[g for _, g in nuovi], crs=g_us.crs)
            s.layers[sc.L_US] = gpd.GeoDataFrame(pd.concat([g_us, agg], ignore_index=True), geometry="geometry",
                                                 crs=g_us.crs)
            poli_us = set(s.layers[sc.L_US][sc.F_US])
            note.append(f"{len(nuovi)} unità senza pianta propria: usato il poligono dell'unità che riempiono")
    if abb.solo_con_poligono:
        prima = len(df)
        df = df[df[sc.C_US].isin(poli_us | poli_usm)]
        if prima - len(df):
            note.append(f"{prima - len(df)} schede senza poligono escluse")
    for u in sorted(poli_us - set(df[sc.C_US])):
        note.append(f"US {u} ha un poligono ma nessuna scheda: aggiunta una scheda vuota")
    extra = sorted(poli_us - set(df[sc.C_US]))
    if extra:
        if abb.filtri:
            # i filtri sulle schede tolgono anche i poligoni corrispondenti
            s.layers[sc.L_US] = s.layers[sc.L_US][~s.layers[sc.L_US][sc.F_US].isin(extra)]
            note[-len(extra):] = [f"{len(extra)} poligoni senza scheda (o con la scheda fuori dai filtri) esclusi"]
            poli_us -= set(extra)
        else:
            df = pd.concat([df, pd.DataFrame({sc.C_US: extra, sc.C_TIPO: "positiva"})], ignore_index=True)
    s.tabelle[sc.S_US] = df
    if abb.foglio_usm:
        du = _rinomina(tabs[abb.foglio_usm], abb.colonne_usm)
        du[sc.C_USM] = du[sc.C_USM].map(_intero)
        s.tabelle[sc.S_USM] = du[du[sc.C_USM].notna()].astype({sc.C_USM: int})
    elif poli_usm and sc.S_USM not in s.tabelle:
        s.tabelle[sc.S_USM] = pd.DataFrame({sc.C_USM: sorted(poli_usm)})

    # ------------------------------------------------ rapporti: senza doppioni, senza autoriferimenti
    tutte = set(df[sc.C_US]) | (set(s.tabelle[sc.S_USM][sc.C_USM]) if sc.S_USM in s.tabelle else set())
    auto = [x for x in righe if x[0] == x[2]]
    righe = [x for x in righe if x[0] != x[2]]
    if auto:
        note.append(f"{len(auto)} rapporti di un'unità con se stessa ignorati")
    if abb.filtri or abb.solo_con_poligono:
        fuori = [x for x in righe if x[0] not in tutte or x[2] not in tutte]
        righe = [x for x in righe if x[0] in tutte and x[2] in tutte]
        if fuori:
            note.append(f"{len(fuori)} rapporti con unità escluse dai filtri tralasciati")
    s.tabelle[sc.S_RAPPORTI] = pd.DataFrame(righe, columns=[sc.C_US, "Rapporto", "US correlata"]).drop_duplicates()

    # ------------------------------------------------ tabelle collegate (materiali, fasi, documentazione…)
    for nome, tab in tabs.items():
        if nome in usati or not len(tab):        # le tabelle vuote non servono al progetto
            continue
        s.tabelle.setdefault(nome, tab)
    for canon, spec in (collegati or {}).items():
        nome = spec.get("foglio")
        if nome not in tabs:
            continue
        mappa = spec.get("colonne") or _proponi_collegati({nome: tabs[nome]}, set(), voc).get(canon, {}).get("colonne", {})
        if not mappa:
            mappa = {k: v for k, v in _mappa_alias(tabs[nome], canon, voc, nome).items()}
        t = tabs[nome].rename(columns={v: k for k, v in mappa.items() if v and v != k})
        chiave = "US/USM" if canon == sc.S_DOC else ("Fase" if canon == sc.S_FASI else "US")
        if chiave in t.columns and canon != sc.S_FASI:
            t[chiave] = t[chiave].map(_intero)
            prima = len(t)
            t = t[t[chiave].isin(tutte)]
            if prima - len(t) and prima > 5 * max(len(t), 1):
                note.append(f"«{nome}»: tenute le {len(t)} righe delle unità del progetto su {prima}")
        for c in ("NR", "NMI", "Peso (g)", "Quota (m)"):
            if c in t.columns:
                t[c] = _misura(t[c], "m", c, nulli)
        if canon == sc.S_DOC and "File" in t.columns:
            # foto e disegni: percorsi relativi al file della tabella, o cercati per nome nelle sue cartelle
            origine = tabs[nome].attrs.get("s3d_file")
            basi = [os.path.dirname(origine)] if origine else []
            if abb.tabella:
                basi.append(os.path.dirname(os.path.abspath(abb.tabella)))
            basi = list(dict.fromkeys(basi))
            t = t.copy()
            t["Percorso file"] = risolvi_file(list(t["File"]), basi)
            citati, trovati = int(t["File"].notna().sum()), int(t["Percorso file"].notna().sum())
            if citati:
                note.append(f"Documentazione: {trovati} file trovati su {citati} citati"
                            + ("" if trovati == citati else " (gli altri non sono nelle cartelle del progetto)"))
        if canon == sc.S_FASI and fasi_composte is not None:
            t = fasi_composte
        s.tabelle.pop(nome, None)
        s.tabelle[canon] = t
        note.append(f"Foglio «{nome}» letto come «{canon}»")
    if fasi_composte is not None and sc.S_FASI not in s.tabelle:
        s.tabelle[sc.S_FASI] = fasi_composte

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
        t[q[sc.F_US].isin(neg) & (t == "vertice")] = "orlo"          # il contorno di un taglio è il suo orlo
        t[t == "vertice"] = "sup"
        t[q[sc.F_US].isin(neg) & t.isin(["sup", "inf"])] = "taglio"
        t[q[sc.F_US].isin(muri) & (t == "sup")] = "rasatura"
        t[q[sc.F_US].isin(muri) & (t == "inf")] = "fondazione"
        q[sc.F_TIPO_QUOTA] = t
        s.layers[sc.L_QUOTE] = q

    # ------------------------------------------------ superficie di riferimento
    sup = dict(abb.superficie or {"tipo": "nessuna"})
    raster_fonte = None
    if sup.get("tipo") == "raster":
        raster_fonte = sup.get("sorgente")
        if not raster_fonte or not os.path.exists(raster_fonte):
            note.append("Modello del terreno non trovato: superficie di riferimento non impostata")
            sup = {"tipo": "nessuna"}
            raster_fonte = None
        elif sup.get("correzione") and not os.path.exists(sup["correzione"]):
            note.append(f"Raster di correzione «{os.path.basename(sup['correzione'])}» non trovato: non usato")
            sup.pop("correzione")
    corr_fonte = sup.get("correzione") if sup.get("tipo") == "raster" else None
    try:
        s.imposta_superficie(sup)
        cop = s.parametri.superficie.get("copertura_correzione")
        n_corr = s.parametri.superficie.get("punti_correzione") or 0
        if cop is not None and cop < 0.9:
            if n_corr:
                note.append(f"Il raster di correzione copre solo il {cop:.0%} dell'area dello scavo: fuori si "
                            f"usano {n_corr} quote rilevate, raccordate al suo bordo")
            else:
                note.append(f"Il raster di correzione copre solo il {cop:.0%} dell'area dello scavo: "
                            "fuori si usa il valore del suo bordo più vicino")
    except Exception as e:
        note.append(f"Superficie di riferimento non impostata: {e}")
        s.imposta_superficie({"tipo": "nessuna"})
        raster_fonte = corr_fonte = None

    # ------------------------------------------------ ortofoto
    orto_fonte = None
    if abb.ortofoto:
        if not os.path.exists(abb.ortofoto):
            note.append("Ortofoto non trovata: il modello resterà senza immagine")
        else:
            try:
                from .ortofoto import Ortofoto
                g = s.layers.get(sc.L_AREA)
                g = g if g is not None and not g.empty else s.layers.get(sc.L_US)
                s.ortofoto = Ortofoto.leggi(abb.ortofoto, limiti=tuple(g.total_bounds) if g is not None and len(g) else None)
                orto_fonte = abb.ortofoto
                d = s.ortofoto.descrizione()
                note.append(f"Ortofoto «{d['nome']}»: {d['larghezza']} × {d['altezza']} pixel, {d['passo_cm']} cm")
            except Exception as e:
                note.append(f"Ortofoto non letta: {e}")

    # ------------------------------------------------ modelli 3D rilevati
    modelli_fonti = set()
    for spec in abb.modelli3d or []:
        p = spec.get("percorso")
        if spec.get("escluso"):
            continue
        if not p or not os.path.exists(p):
            note.append(f"Modello 3D non trovato: {p}")
            continue
        try:
            from .modelli3d import Modello3D
            m = Modello3D.leggi(p, spostamento=tuple(spec.get("spostamento") or (0, 0, 0)))
        except Exception as e:
            note.append(f"Modello 3D «{os.path.basename(p)}» non letto: {e}")
            continue
        d = m.descrizione()
        g = s.layers.get(sc.L_US)
        if g is not None and len(g):
            x0, y0, x1, y1 = g.total_bounds
            cx, cy = m.V[:, 0].mean(), m.V[:, 1].mean()
            if max(x0 - cx, cx - x1, y0 - cy, cy - y1) > 1000:
                note.append(f"Il modello 3D «{d['nome']}» è a più di un chilometro dallo scavo: forse è stato "
                            "esportato con uno spostamento delle coordinate, da indicare nel riquadro dei modelli 3D")
        s.modelli3d.append(m)
        modelli_fonti.add(p)
        note.append(f"Modello 3D «{d['nome']}»: {d['triangoli']:,} triangoli".replace(",", ".")
                    + (", con texture" if d["texture"] else (", con colori" if d["colori"] else "")))

    now = _dt.datetime.now().isoformat(timespec="seconds")
    fonti = sorted({x.sorgente for x in abb.layers if x.ruolo != "ignora"} | ({abb.tabella} if abb.tabella else set())
                   | ({raster_fonte} if raster_fonte else set()) | ({orto_fonte} if orto_fonte else set())
                   | ({corr_fonte} if corr_fonte else set()) | modelli_fonti)
    fonti = sorted(set(fonti) | {f for f in (abb.tabelle_extra or []) if f and os.path.exists(f)})
    for p in fonti:
        s.sorgenti.append(dict(percorso=os.path.abspath(p),
                               tipo="excel" if p == abb.tabella else ("raster" if p in (raster_fonte, orto_fonte, corr_fonte) else "modello 3d" if p in modelli_fonti else
                                                                     ("tabella" if p in (abb.tabelle_extra or []) else "gis")),
                               sha256=_sha256(p), dimensione=os.path.getsize(p), importato=now))
    base = next((x.sorgente for x in abb.layers if x.ruolo == "us"), fonti[0] if fonti else "scavo")
    s.meta = dict(creato=now, modificato=now, nome=os.path.splitext(os.path.basename(base))[0])
    s.abbinamento = abb
    s.note_importazione = abb.note + note
    s.registra("importazione", dict(file=[os.path.basename(p) for p in fonti], note=note))
    for n in note:
        log(n)
    return s
