# -*- coding: utf-8 -*-
"""
Lo Scavo in memoria e il formato di progetto ``.scavo``.

Un file ``.scavo`` è un GeoPackage valido (lo apre anche QGIS) che contiene:
  - i layer vettoriali dello scavo, con gli stili QGIS
  - i fogli dell'Excel come tabelle ``tab_<foglio>``
  - ``s3d_progetto``  impostazioni, origine, parametri (chiave -> JSON)
  - ``s3d_sorgenti``  file di origine con impronta SHA-256 (per la sincronizzazione futura)
  - ``s3d_modelli``   geometrie ricostruite di ogni unità (array compressi)
  - ``s3d_storico``   registro delle operazioni
  - ``s3d_raster``    modello del terreno usato come superficie di riferimento e ortofoto (se ci sono)
"""
import datetime as _dt
import hashlib
import io
import json
import math
import os
import sqlite3
from dataclasses import dataclass, field, asdict

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import affinity
from shapely.ops import unary_union

from . import schema as sc
from . import stratigrafia as st
from .stratigrafia import Problema

VERSIONE_FORMATO = 1


@dataclass
class Parametri:
    """Parametri della ricostruzione 3D (salvati nel progetto)."""
    passo_bordo_piccole: float = 0.06     # m, US sotto 3 m²
    passo_bordo_medie: float = 0.10       # m, US sotto 20 m²
    passo_bordo_grandi: float = 0.16      # m
    area_triangolo_fattore: float = 1000  # area max triangolo = area US / fattore
    area_triangolo_min: float = 0.006
    area_triangolo_max: float = 0.08
    spessore_minimo: float = 0.004        # m
    spessore_predefinito: float = 0.10    # m, se la scheda non ha spessore
    substrato_spessore_max: float = 0.30  # m, blocco convenzionale per la fase 0
    passo_profili: float = 0.20           # m, densificazione dei profili di sezione
    lenti_rastremate: bool = True
    aggancio_stratigrafico: bool = True
    profondita_predefinita: float = 0.20  # m, tagli senza quote né profondità in scheda
    # profondità e spessori mancanti presi dalla mediana delle unità dello stesso tipo (Definizione)
    tipici_dal_sito: bool = False
    escluse: list = field(default_factory=list)   # unità lasciate fuori dalla ricostruzione
    # superficie da cui partono le unità senza quote proprie (vedi superficie.py)
    superficie: dict = field(default_factory=lambda: {"tipo": "nessuna"})


@dataclass
class UnitaModello:
    unita: int
    tipo: str                 # "us" | "usm" | "taglio"
    V2: np.ndarray            # vertici in pianta (locali)
    F: np.ndarray             # triangoli
    top: np.ndarray           # quote del tetto (assolute)
    bot: np.ndarray           # quote della base (assolute)
    qualita: dict = field(default_factory=dict)

    def volume(self):
        from .mesh import volume_prismi
        return 0.0 if self.tipo == "taglio" else volume_prismi(self.V2, self.F, self.top, self.bot)


@dataclass
class Modello:
    unita: dict = field(default_factory=dict)      # numero -> UnitaModello
    rapporto: list = field(default_factory=list)   # righe di resoconto della ricostruzione
    dedotti: list = field(default_factory=list)    # rapporti «copre» dedotti tra riempimenti (a sopra b)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pulisci(df):
    """Rende scrivibile in GeoPackage un DataFrame proveniente da Excel."""
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            vals = df[c].dropna()
            tipi = {type(v) for v in vals}
            if len(tipi) > 1 or (tipi and not tipi <= {str}):
                if tipi <= {int, float, np.integer, np.floating}:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                elif tipi <= {_dt.datetime, pd.Timestamp}:
                    df[c] = pd.to_datetime(df[c], errors="coerce")
                else:
                    df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v))
    return df


def nome_crs(crs):
    """Nome leggibile di un sistema di riferimento (codice EPSG o WKT)."""
    if not crs:
        return "—"
    try:
        from pyproj import CRS
        c = CRS.from_user_input(crs)
        ep = c.to_epsg()
        return f"{c.name} (EPSG:{ep})" if ep else c.name
    except Exception:
        return str(crs)[:60]


class Scavo:
    """Tutti i dati di uno scavo: layer GIS, tabelle, modello 3D, parametri."""

    def __init__(self):
        self.layers = {}
        self.tabelle = {}
        self.crs = None
        self.parametri = Parametri()
        self.modello = None
        self.sorgenti = []
        self.meta = {}
        self.storico = []
        self._origine = None
        self.abbinamento = None           # importa.Abbinamento usato per l'import
        self.note_importazione = []
        self.raster_superficie = None     # superficie.Raster (modello del terreno), se usato
        self.modifiche = []               # registro delle modifiche fatte nell'app (vedi modifiche.py)
        self.ortofoto = None              # ortofoto.Ortofoto drappeggiata sul modello, se c'è
        self.modelli3d = []               # modelli3d.Modello3D rilevati (fotogrammetria, laser scanner)

    # ------------------------------------------------------------------ lettura
    @classmethod
    def da_sorgenti(cls, gpkg, xlsx):
        s = cls()
        disponibili = [l[0] for l in pyogrio.list_layers(gpkg)]
        for nome in sc.LAYER_OBBLIGATORI + sc.LAYER_FACOLTATIVI:
            if nome in disponibili:
                s.layers[nome] = gpd.read_file(gpkg, layer=nome)
        for nome in disponibili:          # layer in più: conservati così come sono
            if nome not in s.layers and not nome.startswith(("s3d_", "tab_", "layer_styles")):
                try:
                    s.layers[nome] = gpd.read_file(gpkg, layer=nome)
                except Exception:
                    pass
        for n in (sc.L_US, sc.L_USM, sc.L_AREA, sc.L_QUOTE):
            if n in s.layers and s.layers[n].crs is not None:
                s.crs = s.layers[n].crs.to_string()
                break
        fogli = pd.read_excel(xlsx, sheet_name=None)
        for nome, df in fogli.items():
            s.tabelle[nome] = df
        if sc.S_US in s.tabelle:
            s.tabelle[sc.S_US] = sc.normalizza_colonne(s.tabelle[sc.S_US],
                                                      [sc.C_US, sc.C_TIPO, sc.C_SPESSORE, sc.C_MARGINI, sc.C_FASE, sc.C_CATEGORIA])
        if sc.S_USM in s.tabelle:
            s.tabelle[sc.S_USM] = sc.normalizza_colonne(s.tabelle[sc.S_USM], [sc.C_USM, sc.C_FASE])
        now = _dt.datetime.now().isoformat(timespec="seconds")
        for p, t in ((gpkg, "gis"), (xlsx, "excel")):
            s.sorgenti.append(dict(percorso=os.path.abspath(p), tipo=t, sha256=_sha256(p),
                                   dimensione=os.path.getsize(p), importato=now))
        s.meta = dict(creato=now, modificato=now, nome=os.path.splitext(os.path.basename(gpkg))[0])
        s.registra("importazione", dict(gis=os.path.basename(gpkg), excel=os.path.basename(xlsx)))
        return s

    def registra(self, azione, dettagli=None):
        self.storico.append(dict(quando=_dt.datetime.now().isoformat(timespec="seconds"),
                                 azione=azione, dettagli=dettagli or {}))

    # ------------------------------------------------------------------ accesso
    @property
    def origine(self):
        """Origine locale (E0, N0, Z0): angolo SO dell'area e quota sotto il punto più basso."""
        if self._origine is None:
            # l'angolo delle US (il limite di scavo può essere molto più ampio dell'area documentata)
            src = self.layers.get(sc.L_US)
            if src is None or src.empty:
                src = self.layers.get(sc.L_AREA)
            b = src.total_bounds
            if sc.L_QUOTE in self.layers and len(self.layers[sc.L_QUOTE]):
                z0 = float(self.layers[sc.L_QUOTE].geometry.z.min())
            else:
                z0 = self._quota_minima_superficie(b)
            self._origine = dict(E0=float(math.floor(b[0])), N0=float(math.floor(b[1])),
                                 Z0=float(math.floor(z0 - 0.5)))
        return self._origine

    def _quota_minima_superficie(self, b):
        """Senza quote rilevate: la superficie di riferimento meno la profondità massima prevista."""
        from .superficie import normalizza
        s = normalizza(self.parametri.superficie)
        prof = [self.parametri.profondita_predefinita, 1.0]
        df = self.tabelle.get(sc.S_US)
        if df is not None and sc.C_PROFONDITA in df.columns:
            prof.append(float(pd.to_numeric(df[sc.C_PROFONDITA], errors="coerce").max() or 0))
        if s["tipo"] == "costante":
            return s["quota"] - s["abbassa"] - max(prof)
        if s["tipo"] == "raster" and self.raster_superficie is not None:
            xs, ys = np.linspace(b[0], b[2], 12), np.linspace(b[1], b[3], 12)
            X, Y = np.meshgrid(xs, ys)
            return float(np.nanmin(self.raster_superficie(X.ravel(), Y.ravel()))) - s["abbassa"] - max(prof)
        return 0.0

    def locale(self, g):
        o = self.origine
        return affinity.translate(g, -o["E0"], -o["N0"])

    def schede_us(self):
        df = self.tabelle.get(sc.S_US)
        return {} if df is None else {int(r[sc.C_US]): r for _, r in df.iterrows() if pd.notna(r[sc.C_US])}

    def schede_usm(self):
        df = self.tabelle.get(sc.S_USM)
        return {} if df is None else {int(r[sc.C_USM]): r for _, r in df.iterrows() if pd.notna(r[sc.C_USM])}

    def poligoni_us(self):
        """Poligoni delle US in coordinate locali, senza le unità escluse dalla ricostruzione."""
        g = self.layers.get(sc.L_US)
        fuori = set(self.parametri.escluse)
        return {} if g is None else {int(r[sc.F_US]): self.locale(r.geometry) for _, r in g.iterrows()
                                     if int(r[sc.F_US]) not in fuori}

    def poligoni_usm(self):
        g = self.layers.get(sc.L_USM)
        fuori = set(self.parametri.escluse)
        return {} if g is None else {int(r[sc.F_USM]): self.locale(r.geometry) for _, r in g.iterrows()
                                     if int(r[sc.F_USM]) not in fuori}

    def imposta_superficie(self, spec, raster=None):
        """Imposta la superficie di riferimento. ``raster``: percorso di un GeoTIFF o un Raster."""
        from .superficie import Raster, normalizza
        spec = normalizza(spec)
        if spec["tipo"] == "raster":
            r = raster if raster is not None else spec.get("sorgente")
            if isinstance(r, str):
                r = Raster.leggi(r)
            if r is None:
                raise ValueError("manca il file del modello del terreno")
            g = self.layers.get(sc.L_AREA)
            g = g if g is not None and not g.empty else self.layers.get(sc.L_US)
            if g is not None and len(g):
                r = r.ritaglia(*g.total_bounds)
            self.raster_superficie = r
            spec["nome"] = r.nome
        else:
            self.raster_superficie = None
        self.parametri.superficie = spec
        if sc.L_QUOTE not in self.layers:
            self._origine = None          # senza quote la quota di base dipende dalla superficie

    def linee_fondo(self):
        """Linee di base dei tagli (coordinate locali), unite; None se il layer manca."""
        g = self.layers.get(sc.L_FONDI)
        if g is None or g.empty:
            return None
        return unary_union([self.locale(x) for x in g.geometry if x is not None])

    def quote_locali(self):
        if sc.L_QUOTE not in self.layers or not len(self.layers[sc.L_QUOTE]):
            return pd.DataFrame(dict(us=pd.Series(dtype=int), tipo=pd.Series(dtype=str),
                                     x=pd.Series(dtype=float), y=pd.Series(dtype=float), z=pd.Series(dtype=float)))
        q = self.layers[sc.L_QUOTE]
        o = self.origine
        return pd.DataFrame(dict(us=q[sc.F_US].astype(int).values, tipo=q[sc.F_TIPO_QUOTA].astype(str).values,
                                 x=q.geometry.x.values - o["E0"], y=q.geometry.y.values - o["N0"],
                                 z=q.geometry.z.values))

    def punti_profilo(self, u, interfaccia, passo=0.2):
        prof = self.layers.get(sc.L_PROFILI)
        if prof is None:
            return np.zeros((0, 3))
        o = self.origine
        pts = []
        sel = prof[(prof[sc.F_US] == u) & (prof[sc.F_INTERFACCIA] == interfaccia)]
        for g in sel.geometry:
            c = np.asarray(g.coords, float)
            if c.shape[1] < 3:
                continue
            c[:, 0] -= o["E0"]; c[:, 1] -= o["N0"]
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(c[:, :2], axis=0), axis=1))]
            if d[-1] < 1e-6:
                continue
            s = np.arange(0, d[-1] + 1e-9, passo)
            pts.append(np.c_[np.interp(s, d, c[:, 0]), np.interp(s, d, c[:, 1]), np.interp(s, d, c[:, 2])])
        return np.vstack(pts) if pts else np.zeros((0, 3))

    def limiti(self):
        a = self.layers.get(sc.L_AREA)
        if a is None or a.empty:
            return unary_union([p.boundary for p in self.poligoni_us().values()]).convex_hull.boundary
        return unary_union([self.locale(g).boundary for g in a.geometry])

    def rapporti(self):
        df = self.tabelle.get(sc.S_RAPPORTI)
        unita = list(self.schede_us()) + list(self.schede_usm())
        if df is None:
            return st.Rapporti(st.nx.DiGraph(), [])
        return st.da_tabella(df, unita)

    # ------------------------------------------------------------------ controlli
    def verifica(self):
        """Controlla dati e rapporti prima della ricostruzione. Ritorna una lista di Problema."""
        out = []
        for n in sc.LAYER_OBBLIGATORI:
            if n not in self.layers:
                out.append(Problema("errore", "layer-mancante", f"manca il layer '{n}'"))
        for n in sc.FOGLI_OBBLIGATORI:
            if n not in self.tabelle:
                out.append(Problema("errore", "foglio-mancante", f"manca il foglio Excel '{n}'"))
        if any(p.livello == "errore" for p in out):
            return out
        if self.crs is None:
            out.append(Problema("avviso", "crs-mancante", "i layer non dichiarano un sistema di riferimento"))
        schede = set(self.schede_us()) | set(self.schede_usm())
        poli = set(self.poligoni_us()) | set(self.poligoni_usm())
        senza_scheda = sorted(poli - schede)
        if senza_scheda:
            out.append(Problema("errore", "poligono-senza-scheda",
                                "poligoni con un numero di US che non compare nell'Excel", tuple(senza_scheda)))
        escluse = sorted(set(self.parametri.escluse))
        if escluse:
            out.append(Problema("info", "escluse", f"{len(escluse)} unità escluse dalla ricostruzione 3D "
                                "(restano nelle schede e nel diagramma di Harris)", tuple(escluse)))
        senza_poligono = sorted(schede - poli - set(escluse))
        if senza_poligono:
            out.append(Problema("avviso", "scheda-senza-poligono",
                                "schede senza poligono in pianta: non avranno un volume", tuple(senza_poligono)))
        q = self.quote_locali()
        tipi_ignoti = sorted(set(q.tipo) - sc.TIPI_QUOTA)
        if tipi_ignoti:
            out.append(Problema("avviso", "tipo-quota-ignoto", f"tipi di quota non riconosciuti: {tipi_ignoti}"))
        # prontezza: come verrà ricostruita ogni unità
        from .stima import stima_quote, DESCRIZIONE
        stima = stima_quote(self)
        strategia, note = stima.strategia, list(stima.note)
        if stima.copre_dedotto:
            note.append(dict(messaggio=f"{len(stima.copre_dedotto)} rapporti «copre» tra riempimenti dello stesso "
                                       "taglio dedotti dal tipo di riempimento (primario in basso) e dal numero",
                             unita=sorted({u for c in stima.copre_dedotto for u in c})))
        self.strategie = strategia
        gruppi = {}
        for u, st_ in strategia.items():
            gruppi.setdefault(st_, []).append(u)
        if gruppi.get("nessuna"):
            out.append(Problema("errore", "senza-quote",
                                "unità senza quote e senza superficie di riferimento: impossibile ricostruirle "
                                "(indica una superficie di riferimento o aggiungi le quote)", tuple(sorted(gruppi["nessuna"]))))
        for st_ in ("profondita", "impilata"):
            if gruppi.get(st_):
                out.append(Problema("info", "stima-" + st_, f"{len(gruppi[st_])} unità ricostruite da {DESCRIZIONE[st_]}",
                                    tuple(sorted(gruppi[st_]))))
        if gruppi.get("schematica"):
            sch = self.schede_us()
            neg = lambda u: str(sch.get(u, {}).get(sc.C_TIPO, "")).strip().lower() == "negativa"
            tagli = sorted(u for u in gruppi["schematica"] if neg(u))
            altre = sorted(u for u in gruppi["schematica"] if not neg(u))
            P = self.parametri
            fonte = "la mediana delle unità dello stesso tipo o " if P.tipici_dal_sito else ""
            if tagli:
                out.append(Problema("avviso", "schematica-tagli",
                                    f"{len(tagli)} tagli senza profondità registrata: si usa {fonte}"
                                    f"{P.profondita_predefinita:.2f} m".replace(".", ","), tuple(tagli)))
            if altre:
                out.append(Problema("avviso", "schematica-spessori",
                                    f"{len(altre)} unità senza spessore registrato: si usa {fonte}"
                                    f"{P.spessore_predefinito:.2f} m (nei tagli, lo spazio rimasto)".replace(".", ","),
                                    tuple(altre)))
        for n in note:
            out.append(Problema("info", "stima-nota", n["messaggio"], tuple(n.get("unita", ()))))
        schede_us = self.schede_us()
        senza_base = []
        for u in sorted(set(self.poligoni_us())):
            if strategia.get(u) != "misurata":
                continue
            neg = str(schede_us.get(u, {}).get(sc.C_TIPO, "")).lower() == "negativa" if u in schede_us else False
            if not neg and not (q[q.us == u].tipo == sc.Q_INF).any() and not len(self.punti_profilo(u, "inf")):
                senza_base.append(u)
        if senza_base:
            out.append(Problema("info", "base-stimata",
                                f"{len(senza_base)} unità senza quote inferiori: la base viene dall'unità sottostante "
                                "o dallo spessore della scheda", tuple(senza_base)))
        # quote lontane dal poligono della propria unità
        polys = {**self.poligoni_us(), **self.poligoni_usm()}
        from shapely import points, distance
        lontane = []
        for u, g in polys.items():
            sq = q[q.us == u]
            if len(sq):
                d = distance(points(sq.x.values, sq.y.values), g)
                if (d > 0.3).any():
                    lontane.append(u)
        if lontane:
            out.append(Problema("avviso", "quote-fuori-poligono",
                                "quote a oltre 30 cm dal poligono della propria unità", tuple(lontane)))
        out += st.controlla(self.rapporti(), schede)
        return out

    # ------------------------------------------------------------------ salvataggio
    def salva(self, path):
        """Scrive il progetto in un file .scavo (GeoPackage)."""
        from . import stili_qgis
        tmp = path + ".tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")        # layer di sezione senza SR: voluto
            for nome, g in self.layers.items():
                g.to_file(tmp, layer=nome, driver="GPKG")
        for nome, df in self.tabelle.items():
            pyogrio.write_dataframe(_pulisci(df), tmp, layer="tab_" + nome, driver="GPKG")
        con = sqlite3.connect(tmp)
        cur = con.cursor()
        now = _dt.datetime.now().isoformat(timespec="seconds")
        self.meta["modificato"] = now
        tabelle_s3d = {
            "s3d_progetto": "chiave TEXT PRIMARY KEY, valore TEXT",
            "s3d_sorgenti": "id INTEGER PRIMARY KEY AUTOINCREMENT, percorso TEXT, tipo TEXT, sha256 TEXT, dimensione INTEGER, importato TEXT",
            "s3d_modelli": "id INTEGER PRIMARY KEY AUTOINCREMENT, unita INTEGER, tipo TEXT, qualita TEXT, dati BLOB",
            "s3d_storico": "id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, azione TEXT, dettagli TEXT",
            "s3d_raster": "nome TEXT PRIMARY KEY, dati BLOB",
            "s3d_modelli3d": "id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, dati BLOB",
        }
        for t, cols in tabelle_s3d.items():
            cur.execute(f"CREATE TABLE {t} ({cols})")
            cur.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change) "
                        "VALUES (?, 'attributes', ?, 'stratigrafia3d', ?)", (t, t, now))
        kv = dict(formato="stratigrafia3d", versione_formato=VERSIONE_FORMATO, crs=self.crs,
                  origine=self.origine, parametri=asdict(self.parametri), meta=self.meta,
                  modello_rapporto=self.modello.rapporto if self.modello else [],
                  modello_dedotti=self.modello.dedotti if self.modello else [],
                  abbinamento=asdict(self.abbinamento) if self.abbinamento is not None else None,
                  note_importazione=self.note_importazione, modifiche=self.modifiche)
        cur.executemany("INSERT INTO s3d_progetto VALUES (?, ?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in kv.items()])
        cur.executemany("INSERT INTO s3d_sorgenti (percorso, tipo, sha256, dimensione, importato) VALUES (?,?,?,?,?)",
                        [(s["percorso"], s["tipo"], s["sha256"], s["dimensione"], s["importato"]) for s in self.sorgenti])
        if self.modello:
            for u, m in self.modello.unita.items():
                buf = io.BytesIO()
                np.savez_compressed(buf, V2=m.V2.astype("<f8"), F=m.F.astype("<u4"),
                                    top=m.top.astype("<f8"), bot=m.bot.astype("<f8"))
                cur.execute("INSERT INTO s3d_modelli (unita, tipo, qualita, dati) VALUES (?,?,?,?)",
                            (int(u), m.tipo, json.dumps(m.qualita, ensure_ascii=False), buf.getvalue()))
        if self.raster_superficie is not None:
            cur.execute("INSERT INTO s3d_raster VALUES (?, ?)", ("superficie", self.raster_superficie.a_bytes()))
        if self.ortofoto is not None:
            cur.execute("INSERT INTO s3d_raster VALUES (?, ?)", ("ortofoto", self.ortofoto.a_bytes()))
        for m in self.modelli3d:
            cur.execute("INSERT INTO s3d_modelli3d (nome, dati) VALUES (?, ?)", (m.nome, m.a_bytes()))
        self.registra("salvataggio", dict(file=os.path.basename(path)))
        cur.executemany("INSERT INTO s3d_storico (quando, azione, dettagli) VALUES (?,?,?)",
                        [(h["quando"], h["azione"], json.dumps(h["dettagli"], ensure_ascii=False)) for h in self.storico])
        con.commit()
        con.close()
        stili_qgis.scrivi_stili(tmp)
        os.replace(tmp, path)
        return path

    @classmethod
    def apri(cls, path):
        s = cls()
        con = sqlite3.connect(path)
        cur = con.cursor()
        kv = {k: json.loads(v) for k, v in cur.execute("SELECT chiave, valore FROM s3d_progetto")}
        if kv.get("formato") != "stratigrafia3d":
            raise ValueError(f"{path} non è un progetto stratigrafia3d")
        if kv.get("versione_formato", 0) > VERSIONE_FORMATO:
            raise ValueError("progetto creato con una versione più recente del programma")
        s.crs = kv.get("crs")
        s._origine = kv.get("origine")
        s.parametri = Parametri(**{k: v for k, v in kv.get("parametri", {}).items() if k in Parametri.__dataclass_fields__})
        s.meta = kv.get("meta", {})
        if kv.get("abbinamento"):
            from .importa import Abbinamento
            s.abbinamento = Abbinamento.da_json(kv["abbinamento"])
        s.note_importazione = kv.get("note_importazione", [])
        s.modifiche = kv.get("modifiche", [])
        s.sorgenti = [dict(percorso=a, tipo=b, sha256=c, dimensione=d, importato=e) for a, b, c, d, e in
                      cur.execute("SELECT percorso, tipo, sha256, dimensione, importato FROM s3d_sorgenti")]
        s.storico = [dict(quando=a, azione=b, dettagli=json.loads(c)) for a, b, c in
                     cur.execute("SELECT quando, azione, dettagli FROM s3d_storico ORDER BY id")]
        righe = list(cur.execute("SELECT unita, tipo, qualita, dati FROM s3d_modelli ORDER BY id"))
        try:
            r = cur.execute("SELECT dati FROM s3d_raster WHERE nome = 'superficie'").fetchone()
            o = cur.execute("SELECT dati FROM s3d_raster WHERE nome = 'ortofoto'").fetchone()
            try:
                from .modelli3d import Modello3D
                s.modelli3d = [Modello3D.da_bytes(b) for (b,) in cur.execute("SELECT dati FROM s3d_modelli3d ORDER BY id")]
            except sqlite3.OperationalError:       # progetti precedenti alla versione 0.7
                pass
            if o:
                from .ortofoto import Ortofoto
                s.ortofoto = Ortofoto.da_bytes(o[0])
        except sqlite3.OperationalError:       # progetti salvati prima della versione 0.3
            r = None
        if r:
            from .superficie import Raster
            s.raster_superficie = Raster.da_bytes(r[0])
        con.close()
        if righe:
            s.modello = Modello(rapporto=kv.get("modello_rapporto", []),
                                dedotti=[tuple(x) for x in kv.get("modello_dedotti", [])])
            for u, t, qual, dati in righe:
                z = np.load(io.BytesIO(dati))
                s.modello.unita[int(u)] = UnitaModello(int(u), t, z["V2"], z["F"].astype(np.int64),
                                                        z["top"], z["bot"], json.loads(qual))
        for nome, gtype in pyogrio.list_layers(path):
            if nome.startswith("s3d_") or nome == "layer_styles":
                continue
            if nome.startswith("tab_"):
                s.tabelle[nome[4:]] = pyogrio.read_dataframe(path, layer=nome)
            else:
                s.layers[nome] = gpd.read_file(path, layer=nome)
        s.registra("apertura", dict(file=os.path.basename(path)))
        return s

    def riepilogo(self):
        us = self.schede_us(); usm = self.schede_usm()
        righe = [f"Progetto: {self.meta.get('nome', '—')}",
                 f"Sistema di riferimento: {nome_crs(self.crs)}",
                 f"US: {len(us)}  USM: {len(usm)}  quote: {len(self.layers.get(sc.L_QUOTE, []))}",
                 f"Layer: {', '.join(sorted(self.layers))}",
                 f"Tabelle: {', '.join(sorted(self.tabelle))}"]
        if self.modello:
            n = len(self.modello.unita)
            vol = sum(m.volume() for m in self.modello.unita.values())
            stimate = sum(1 for m in self.modello.unita.values() if m.qualita.get("base") == "stimata")
            righe.append(f"Modello 3D: {n} unità, volume totale {vol:.1f} m³, basi stimate: {stimate}")
        else:
            righe.append("Modello 3D: non ancora calcolato")
        return "\n".join(righe)
