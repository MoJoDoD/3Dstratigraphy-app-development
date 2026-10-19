# -*- coding: utf-8 -*-
"""
Modelli del terreno di una singola unità: «G2_A16_DEM_2409.tif», «GR6.A66_DEM.tif», «G10_A30-39_DEM_2909.tif».

In molti scavi (Ba'ja: rilievo fotogrammetrico a ogni US esposta) la forma degli strati non è disegnata in
pianta: sta nei DEM fatti quando ciascuna unità era scoperta. Da questi DEM si ricavano:

- la **pianta** dell'unità: la zona coperta dal suo DEM (senza le murature), se l'unità non ne ha già una;
- il **tetto**: punti campionati dal DEM più antico dell'unità (quote «sup»; per le murature «rasatura»);
- la **superficie raggiunta**: dal DEM più recente, se è più basso del primo (quote «inf»).

La base degli strati si aggancia poi, come sempre, al tetto delle unità sottostanti (dai loro DEM).
I DEM con più unità nel nome («G2_A16-33-B33») danno le quote delle unità già note dentro le loro piante.
I DEM senza unità nel nome («AREA_G_DEM», «G12_apertura_DEM») restano superfici di riferimento.
"""
import hashlib
import os
import re

import numpy as np

CELLA = 0.02            # m: risoluzione a cui si lavora (i DEM fotogrammetrici sono al millimetro)
PUNTI_MAX = 800         # punti per unità e superficie (il kriging risolve un sistema n × n)
AREA_MIN = 0.03         # m²: parti della pianta più piccole si tralasciano
_PAROLE_DEM = re.compile(r"(^|[^a-z])(dem|dtm|dsm|mde|mdt)([^a-z]|$)", re.I)


def e_dem_di_unita(nome):
    """Vero se il nome indica un modello del terreno («…_DEM…»)."""
    return bool(_PAROLE_DEM.search(os.path.splitext(os.path.basename(str(nome)))[0]))


def data_dal_nome(percorso):
    """(anno, mese, giorno) dal nome («…_DEM_2409.tif» = 24 settembre; «2210_AREA_G…» = 22 ottobre), con
    l'anno dalla cartella («BAJA25», «2025») o dalla data del file; None se il nome non ha una data."""
    stem = os.path.splitext(os.path.basename(str(percorso)))[0]
    gg = mm = None
    for t in reversed(re.split(r"[^0-9]+", stem)):
        if len(t) == 4:
            d, m = int(t[:2]), int(t[2:])
            if 1 <= d <= 31 and 1 <= m <= 12:
                gg, mm = d, m
                break
    if gg is None:
        return None
    anno = None
    for parte in list(reversed(os.path.normpath(str(percorso)).split(os.sep)[:-1]))[:4]:   # le cartelle vicine
        # «2025», «BAJA25», «Scavo 25» (non «G16», che è un locus)
        a = re.search(r"(?<!\d)(20\d{2})(?!\d)", parte) or re.search(r"[A-Za-z]{3,}[\s_\-]?(\d{2})$", parte)
        if a:
            v = int(a.group(1))
            anno = v if v > 1900 else 2000 + v
            break
    if anno is None:
        try:
            import datetime as dt
            anno = dt.datetime.fromtimestamp(os.path.getmtime(percorso)).year
        except OSError:
            anno = 0
    return anno, mm, gg


def _cartella_cache():
    d = os.path.join(os.path.expanduser("~"), ".stratigrafia3d", "dem_ridotti")
    os.makedirs(d, exist_ok=True)
    return d


def leggi_ridotto(percorso, cella=CELLA):
    """Il DEM a ``cella`` metri (un valore ogni k celle): Raster. Il risultato resta in una cache accanto alle
    impostazioni, così una nuova importazione non decodifica di nuovo i file grandi."""
    from .superficie import Raster, georef
    try:
        st = os.stat(percorso)
        chiave = hashlib.sha1(f"{os.path.abspath(percorso)}|{st.st_mtime_ns}|{st.st_size}|{cella}".encode()).hexdigest()
        cache = os.path.join(_cartella_cache(), chiave + ".npz")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return Raster.da_bytes(f.read())
    except OSError:
        cache = None
    passo = georef(percorso)["passo"][0]
    r = Raster.leggi(percorso)
    k = max(1, int(round(cella / max(passo, 1e-6))))
    if k > 1:
        # la prima cella ridotta è centrata dove era il centro della cella (k//2, k//2) dell'originale
        z = r.z[k // 2::k, k // 2::k]
        r = Raster(z, r.x0 + (k // 2) * r.sx, r.y0 - (k // 2) * r.sy, r.sx * k, r.sy * k, None, r.nome)
    if cache:
        try:
            with open(cache, "wb") as f:
                f.write(r.a_bytes())
        except OSError:
            pass
    return r


def impronta(r, area_min=AREA_MIN):
    """Poligono delle celle con un valore (la parte rilevata del DEM), semplificato alla cella."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    ok = ~np.isnan(r.z)
    if not ok.any():
        return None
    pezzi = []
    for i in range(ok.shape[0]):
        riga = ok[i]
        if not riga.any():
            continue
        d = np.diff(np.r_[0, riga.astype(np.int8), 0])
        inizi, fini = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        y1 = r.y0 - (i - 0.5) * r.sy
        y0 = y1 - r.sy
        for a, b in zip(inizi, fini):
            pezzi.append(box(r.x0 + (a - 0.5) * r.sx, y0, r.x0 + (b - 0.5) * r.sx, y1))
    g = unary_union(pezzi).buffer(r.sx * 0.6).buffer(-r.sx * 0.6).simplify(r.sx * 0.75)
    return pulisci(g, area_min)


def pulisci(g, area_min=AREA_MIN):
    """Solo le parti abbastanza grandi, senza i buchi piccoli."""
    from shapely.geometry import Polygon, MultiPolygon
    if g is None or g.is_empty:
        return None
    parti = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type != "Polygon" or p.area < area_min:
            continue
        buchi = [h for h in p.interiors if Polygon(h).area >= area_min]
        parti.append(Polygon(p.exterior, buchi))
    if not parti:
        return None
    return MultiPolygon(parti).buffer(0)


def campiona(r, geom, punti_max=PUNTI_MAX, passo_min=0.05):
    """Punti (x, y, z) del DEM dentro ``geom``, su una griglia regolare (al massimo ``punti_max``)."""
    from shapely import contains_xy
    if geom is None or geom.is_empty:
        return np.zeros((0, 3))
    passo = max(passo_min, float(np.sqrt(geom.area / max(punti_max, 1))))
    x0, y0, x1, y1 = geom.bounds
    xs = np.arange(x0 + passo / 2, x1, passo)
    ys = np.arange(y0 + passo / 2, y1, passo)
    if not len(xs) or not len(ys):
        return np.zeros((0, 3))
    X, Y = np.meshgrid(xs, ys)
    x, y = X.ravel(), Y.ravel()
    dentro = contains_xy(geom, x, y) & r.copre(x, y)
    x, y = x[dentro], y[dentro]
    if not len(x):
        return np.zeros((0, 3))
    z = r(x, y)
    ok = np.isfinite(z)
    return np.c_[x[ok], y[ok], z[ok]]


def abbassamento(r_alto, r_basso, geom):
    """Quanto il DEM ``r_basso`` è più basso di ``r_alto`` dentro ``geom`` (mediana, m); None se non si
    sovrappongono."""
    P = campiona(r_basso, geom, 300)
    if not len(P):
        return None
    dentro = r_alto.copre(P[:, 0], P[:, 1])
    if dentro.sum() < 10:
        return None
    return float(np.median(r_alto(P[dentro, 0], P[dentro, 1]) - P[dentro, 2]))
