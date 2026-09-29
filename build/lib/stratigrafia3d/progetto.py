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
            src = self.layers.get(sc.L_AREA)
            if src is None or src.empty:
                src = self.layers[sc.L_US]
            b = src.total_bounds
            zs = self.layers[sc.L_QUOTE].geometry.z
            self._origine = dict(E0=float(math.floor(b[0])), N0=float(math.floor(b[1])),
                                 Z0=float(math.floor(zs.min() - 0.5)))
        return self._origine

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
        g = self.layers.get(sc.L_US)
        return {} if g is None else {int(r[sc.F_US]): self.locale(r.geometry) for _, r in g.iterrows()}

    def poligoni_usm(self):
        g = self.layers.get(sc.L_USM)
        return {} if g is None else {int(r[sc.F_USM]): self.locale(r.geometry) for _, r in g.iterrows()}

    def quote_locali(self):
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
        senza_poligono = sorted(schede - poli)
        if senza_poligono:
            out.append(Problema("avviso", "scheda-senza-poligono",
                                "schede senza poligono in pianta: non avranno un volume", tuple(senza_poligono)))
        q = self.quote_locali()
        tipi_ignoti = sorted(set(q.tipo) - sc.TIPI_QUOTA)
        if tipi_ignoti:
            out.append(Problema("avviso", "tipo-quota-ignoto", f"tipi di quota non riconosciuti: {tipi_ignoti}"))
        schede_us = self.schede_us()
        for u in sorted(set(self.poligoni_us())):
            sq = q[q.us == u]
            neg = str(schede_us.get(u, {}).get(sc.C_TIPO, "")).lower() == "negativa" if u in schede_us else False
            kinds = {sc.Q_TAGLIO, sc.Q_ORLO} if neg else {sc.Q_SUP}
            has_prof = len(self.punti_profilo(u, "taglio" if neg else "sup")) > 0
            if not sq.tipo.isin(kinds).any() and not has_prof:
                out.append(Problema("errore", "senza-quote",
                                    "unità senza quote della superficie: impossibile ricostruirla", (u,)))
            elif not neg and not sq.tipo.eq(sc.Q_INF).any() and not len(self.punti_profilo(u, "inf")):
                out.append(Problema("avviso", "base-stimata",
                                    "nessuna quota inferiore: base ricavata dallo spessore della scheda", (u,)))
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
        }
        for t, cols in tabelle_s3d.items():
            cur.execute(f"CREATE TABLE {t} ({cols})")
            cur.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change) "
                        "VALUES (?, 'attributes', ?, 'stratigrafia3d', ?)", (t, t, now))
        kv = dict(formato="stratigrafia3d", versione_formato=VERSIONE_FORMATO, crs=self.crs,
                  origine=self.origine, parametri=asdict(self.parametri), meta=self.meta,
                  modello_rapporto=self.modello.rapporto if self.modello else [])
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
        s.sorgenti = [dict(percorso=a, tipo=b, sha256=c, dimensione=d, importato=e) for a, b, c, d, e in
                      cur.execute("SELECT percorso, tipo, sha256, dimensione, importato FROM s3d_sorgenti")]
        s.storico = [dict(quando=a, azione=b, dettagli=json.loads(c)) for a, b, c in
                     cur.execute("SELECT quando, azione, dettagli FROM s3d_storico ORDER BY id")]
        righe = list(cur.execute("SELECT unita, tipo, qualita, dati FROM s3d_modelli ORDER BY id"))
        con.close()
        if righe:
            s.modello = Modello(rapporto=kv.get("modello_rapporto", []))
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
                 f"Sistema di riferimento: {self.crs or '—'}",
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
