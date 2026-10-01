# -*- coding: utf-8 -*-
"""
Superficie di riferimento: la quota da cui partono le unità che non hanno quote proprie
(tagli di cui si conosce solo la profondità, strati di cui si conosce solo lo spessore).

Tre modi, descritti da un dizionario salvato nei parametri del progetto:
    {"tipo": "costante", "quota": 45.20, "abbassa": 0.0}
    {"tipo": "raster",   "sorgente": "dtm.tif", "abbassa": 0.30}      # modello del terreno
    {"tipo": "raster",   "sorgente": "dtm.tif", "correzione": "troncamento.tif"}   # più un raster di differenze
    {"tipo": "quote",    "abbassa": 0.0}                              # interpolata dalle quote rilevate
    {"tipo": "nessuna"}
    {"tipo": "raster",   "sorgente": "dtm.tif", "correzione": "troncamento.tif", "quote": true}
"abbassa" sposta la superficie verso il basso (es. lo spessore dell'arativo asportato).
"correzione" è un secondo raster di differenze (metri, di solito negativi) da sommare al primo: per esempio
il modello di troncamento che dice di quanto il piano di scavo sta sotto il terreno storico. Dove il raster
di correzione non arriva, se ci sono quote rilevate del piano di scavo (sup, orlo, rasatura, anche senza US)
la correzione si ricava da quelle (quota rilevata meno modello del terreno) e si raccorda al bordo del raster;
altrimenti vale il bordo più vicino.
"quote": true adatta in più il risultato alle quote rilevate, dove sono fitte (scarti interpolati e limitati).
Il raster viene copiato nel progetto, così il file .scavo resta autosufficiente.
"""
import io
import os

import numpy as np

TIPI = ("nessuna", "costante", "raster", "quote")
EST_RASTER = {".tif", ".tiff"}


class Raster:
    """Griglia di quote georiferita (una banda). Coordinate del centro della prima cella + passo."""

    def __init__(self, z, x0, y0, sx, sy, nodata=None, nome=""):
        z = np.asarray(z, dtype="float32")
        if nodata is not None:
            z = np.where(np.isclose(z, nodata), np.nan, z)
        z[z < -1e30] = np.nan
        self.z, self.x0, self.y0, self.sx, self.sy, self.nome = z, float(x0), float(y0), float(sx), float(sy), nome

    # ------------------------------------------------------------------ lettura
    @classmethod
    def leggi(cls, path):
        """GeoTIFF (tag GeoTIFF o file .tfw accanto). Con più bande si usa la prima."""
        g = georef(path)
        import tifffile
        with tifffile.TiffFile(path) as t:
            p = t.pages[0]
            try:
                z = p.asarray()
            except Exception as e:
                raise RuntimeError(f"Compressione del raster non supportata ({p.compression}); "
                                   "salvalo senza compressione o con compressione DEFLATE") from e
        if z.ndim == 3:
            z = z[..., 0] if z.shape[-1] <= 4 else z[0]
        if z.dtype == np.int16:                           # valori "vuoti" tipici dei DEM interi
            z = np.where((z == -32768) | (z == 32767), np.nan, z.astype("float32"))
        xs, ys, sx, sy = g["angolo"][0], g["angolo"][1], g["passo"][0], g["passo"][1]
        return cls(z, xs + sx / 2, ys - sy / 2, sx, sy, g["nodata"], os.path.basename(path))

    # ------------------------------------------------------------------ uso
    def __call__(self, x, y):
        """Quota bilineare (coordinate assolute). Fuori dal raster: il bordo più vicino."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        z = self.z
        c = np.clip((x - self.x0) / self.sx, 0, z.shape[1] - 1)
        r = np.clip((self.y0 - y) / self.sy, 0, z.shape[0] - 1)
        c0 = np.minimum(np.floor(c).astype(int), max(z.shape[1] - 2, 0))
        r0 = np.minimum(np.floor(r).astype(int), max(z.shape[0] - 2, 0))
        c1, r1 = np.minimum(c0 + 1, z.shape[1] - 1), np.minimum(r0 + 1, z.shape[0] - 1)
        fc, fr = c - c0, r - r0
        v = ((z[r0, c0] * (1 - fc) + z[r0, c1] * fc) * (1 - fr) + (z[r1, c0] * (1 - fc) + z[r1, c1] * fc) * fr)
        if np.isnan(v).any():                            # celle vuote: il valore valido più vicino
            vicino = self._piu_vicino(c, r)
            v = np.where(np.isnan(v), vicino, v)
        return v

    def _piu_vicino(self, c, r):
        from scipy.spatial import cKDTree
        ok = np.argwhere(~np.isnan(self.z))
        if len(ok) == 0:
            return np.full(np.shape(c), np.nan)
        _, i = cKDTree(ok).query(np.c_[np.ravel(r), np.ravel(c)])
        rr, cc = ok[i].T
        return self.z[rr, cc].reshape(np.shape(c))

    def copre(self, x, y):
        """Vero dove il raster ha un valore (dentro l'estensione e cella non vuota)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        c = np.floor((x - self.x0) / self.sx + 0.5).astype(np.int64)
        r = np.floor((self.y0 - y) / self.sy + 0.5).astype(np.int64)
        ok = (c >= 0) & (c < self.z.shape[1]) & (r >= 0) & (r < self.z.shape[0])
        out = np.zeros(np.shape(x), bool)
        out[ok] = ~np.isnan(self.z[r[ok], c[ok]])
        return out

    def ritaglia(self, xmin, ymin, xmax, ymax, margine=None):
        """Solo la parte che serve allo scavo (con un margine di qualche cella)."""
        m = margine if margine is not None else 3 * max(self.sx, self.sy)
        c0 = int(np.clip(np.floor((xmin - m - self.x0) / self.sx), 0, self.z.shape[1] - 1))
        c1 = int(np.clip(np.ceil((xmax + m - self.x0) / self.sx), 0, self.z.shape[1] - 1))
        r0 = int(np.clip(np.floor((self.y0 - ymax - m) / self.sy), 0, self.z.shape[0] - 1))
        r1 = int(np.clip(np.ceil((self.y0 - ymin + m) / self.sy), 0, self.z.shape[0] - 1))
        return Raster(self.z[r0:r1 + 1, c0:c1 + 1].copy(), self.x0 + c0 * self.sx, self.y0 - r0 * self.sy,
                      self.sx, self.sy, None, self.nome)

    def descrizione(self):
        v = self.z[~np.isnan(self.z)]
        return dict(nome=self.nome, righe=int(self.z.shape[0]), colonne=int(self.z.shape[1]), passo=round(self.sx, 3),
                    quota_min=round(float(v.min()), 2) if len(v) else None,
                    quota_max=round(float(v.max()), 2) if len(v) else None,
                    estensione=[round(self.x0 - self.sx / 2, 2), round(self.y0 - (self.z.shape[0] - 0.5) * self.sy, 2),
                                round(self.x0 + (self.z.shape[1] - 0.5) * self.sx, 2), round(self.y0 + self.sy / 2, 2)])

    def a_bytes(self):
        buf = io.BytesIO()
        np.savez_compressed(buf, z=self.z, geo=np.array([self.x0, self.y0, self.sx, self.sy]),
                            nome=np.array(self.nome))
        return buf.getvalue()

    @classmethod
    def da_bytes(cls, b):
        d = np.load(io.BytesIO(b))
        x0, y0, sx, sy = d["geo"]
        return cls(d["z"], x0, y0, sx, sy, None, str(d["nome"]))


def e_differenza(descr):
    """Un raster di differenze (troncamento, spessore asportato) e non di quote: valori tutti tra -20 e 0."""
    return descr.get("quota_max") is not None and descr["quota_max"] <= 0 and descr["quota_min"] >= -20


CELLA_PUNTI = 0.5         # m: delle quote rilevate si tiene la più alta per cella (i fondi restano sotto)
# correzione ricavata dalle quote fuori dal raster di correzione
VICINO, LONTANO = 10.0, 30.0   # m dalla quota più vicina: piena fiducia / nessuna (poi il bordo del raster)
RACCORDO = 10.0                # m: fascia in cui si passa dal bordo del raster alla correzione delle quote
# adattamento alle quote ("quote": true)
ADATTA_VICINO, ADATTA_LONTANO = 3.0, 10.0   # m dalla quota più vicina
ADATTA_MIN_PUNTI = 3                        # quote entro ADATTA_LONTANO perché i punti contino come «fitti»
ADATTA_LIMITE = 1.0                         # m: scarto massimo applicato


def combina(base, correzione, xmin, ymin, xmax, ymax, celle_max=4_000_000, punti=None, adatta=False):
    """Raster = base + correzione sull'area indicata (coordinate assolute), al passo del più fine dei due
    ma con al massimo ``celle_max`` celle. ``correzione`` può mancare (None).

    Fuori dalla copertura della correzione: se ci sono ``punti`` (N x 3, quote rilevate del piano di scavo)
    vicini, la correzione è la loro differenza dalla base (senza i fondi, interpolata e smussata) raccordata
    al bordo del raster; altrimenti vale il bordo più vicino. Con ``adatta`` il risultato si avvicina in più
    alle quote dove sono fitte."""
    punti = np.zeros((0, 3)) if punti is None else np.asarray(punti, float).reshape(-1, 3)
    passo = min(base.sx, correzione.sx) if correzione is not None else base.sx
    if adatta and len(punti):
        passo = min(passo, CELLA_PUNTI)
    passo = max(passo, float(np.sqrt((xmax - xmin) * (ymax - ymin) / celle_max)))
    m = 2 * passo
    xs = np.arange(xmin - m, xmax + m + passo / 2, passo)
    ys = np.arange(ymax + m, ymin - m - passo / 2, -passo)
    X, Y = np.meshgrid(xs, ys)
    x, y = X.ravel(), Y.ravel()
    zb = base(x, y)
    nome = base.nome
    usati = adattati = 0
    copertura = 1.0
    if correzione is not None:
        c = correzione(x, y)
        dentro = correzione.copre(x, y)
        e = correzione.descrizione()["estensione"]
        copertura = float(np.mean((x >= e[0]) & (x <= e[2]) & (y >= e[1]) & (y <= e[3])))
        # le quote servono solo vicino all'area (e fuori dalla copertura della correzione)
        vicini = _nel_riquadro(punti, xs[0] - LONTANO, ys[-1] - LONTANO, xs[-1] + LONTANO, ys[0] + LONTANO)
        if len(vicini) and not dentro.all():
            c, usati = _correzione_dalle_quote(c, dentro, X.shape, passo, base, vicini, x, y)
        zb = zb + c
        nome = f"{nome} + {correzione.nome}"
    r = Raster(zb.reshape(X.shape), xs[0], ys[0], passo, passo, None, nome)
    if adatta and len(punti):
        vicini = _nel_riquadro(punti, xs[0] - ADATTA_LONTANO, ys[-1] - ADATTA_LONTANO,
                               xs[-1] + ADATTA_LONTANO, ys[0] + ADATTA_LONTANO)
        if len(vicini) >= ADATTA_MIN_PUNTI:
            dz, adattati = _adatta_alle_quote(r, vicini, x, y)
            r.z = (r.z.ravel() + dz).reshape(X.shape).astype("float32")
    if usati or adattati:
        r.nome = f"{r.nome} + quote rilevate"
    r.copertura = copertura
    r.punti_correzione, r.punti_adattamento = int(usati), int(adattati)
    return r


def _nel_riquadro(P, x0, y0, x1, y1):
    if not len(P):
        return P
    return P[(P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1) & np.isfinite(P[:, 2])]


def _massimo_per_cella(P, cella=CELLA_PUNTI):
    """Per ogni cella la quota più alta: la superficie da cui si scava, non i fondi."""
    if not len(P):
        return P
    k = np.floor(P[:, :2] / cella).astype(np.int64)
    o = np.lexsort((P[:, 2], k[:, 1], k[:, 0]))
    ks = k[o]
    ultima = np.r_[np.any(ks[1:] != ks[:-1], axis=1), True]
    return P[o][ultima]


def _senza_fondi(P, v, vicini=12, raggio=15.0):
    """Vero per le quote da tenere: via quelle molto più basse delle vicine (fondi di buche, «sinks»),
    cioè sotto la mediana locale di più di 3 deviazioni robuste (almeno 10 cm)."""
    n = len(v)
    if n < 4:
        return np.ones(n, bool)
    from scipy.spatial import cKDTree
    k = min(vicini, n)
    _, i = cKDTree(P[:, :2]).query(P[:, :2], k=k, distance_upper_bound=raggio)
    V = np.where(i < n, v[np.minimum(i, n - 1)], np.nan)
    conta = np.sum(~np.isnan(V), axis=1)
    med = np.nanmedian(V, axis=1)
    mad = np.nanmedian(np.abs(V - med[:, None]), axis=1)
    soglia = np.maximum(0.10, 3 * 1.4826 * mad)
    return (conta < 4) | ~(v < med - soglia)


def _idw(P, v, Q, vicini=12, liscio=2.0):
    """Media pesata con l'inverso del quadrato della distanza (smussata di ``liscio`` m) e distanza
    dalla quota più vicina."""
    from scipy.spatial import cKDTree
    k = min(vicini, len(v))
    d, i = cKDTree(P[:, :2]).query(Q, k=k)
    d, i = d.reshape(len(Q), k), i.reshape(len(Q), k)
    w = 1.0 / (d ** 2 + liscio ** 2)
    return (w * v[i]).sum(1) / w.sum(1), d[:, 0]


def _correzione_dalle_quote(c, dentro, forma, passo, base, P, x, y):
    """Fuori dalla copertura del raster di correzione: correzione = quota rilevata − base, interpolata;
    raccordata al bordo del raster entro RACCORDO m e lasciata al bordo lontano dalle quote."""
    P = _massimo_per_cella(P)
    d = P[:, 2] - base(P[:, 0], P[:, 1])
    tieni = _senza_fondi(P, d)
    P, d = P[tieni], d[tieni]
    if not len(P):
        return c, 0
    fuori = ~dentro
    Q = np.c_[x[fuori], y[fuori]]
    F, dp = _idw(P, d, Q)
    wp = np.clip((LONTANO - dp) / (LONTANO - VICINO), 0, 1)
    if not (wp > 0).any():                         # quote tutte lontane dalle celle scoperte
        return c, 0
    if dentro.any():
        from scipy.ndimage import distance_transform_edt
        dist = distance_transform_edt(~dentro.reshape(forma)).ravel()[fuori] * passo
    else:
        dist = np.full(len(Q), np.inf)
    wb = np.clip(1 - dist / RACCORDO, 0, 1)
    co = c[fuori]
    c = c.copy()
    c[fuori] = wb * co + (1 - wb) * (wp * F + (1 - wp) * co)
    return c, int(len(P))


def _adatta_alle_quote(r, P, x, y):
    """Scarti quota rilevata − superficie, senza fondi, interpolati e limitati a ±ADATTA_LIMITE; applicati
    solo dove le quote sono fitte."""
    from scipy.spatial import cKDTree
    P = _massimo_per_cella(P)
    s = P[:, 2] - r(P[:, 0], P[:, 1])
    tieni = _senza_fondi(P, s) & np.isfinite(s)
    P, s = P[tieni], np.clip(s[tieni], -ADATTA_LIMITE, ADATTA_LIMITE)
    if len(P) < ADATTA_MIN_PUNTI:
        return np.zeros(len(x)), 0
    Q = np.c_[x, y]
    dz = np.zeros(len(x))
    tree = cKDTree(P[:, :2])
    dp, _ = tree.query(Q, k=1, distance_upper_bound=ADATTA_LONTANO)
    vic = np.isfinite(dp)
    vic[vic] = tree.query_ball_point(Q[vic], ADATTA_LONTANO, return_length=True) >= ADATTA_MIN_PUNTI
    if not vic.any():
        return dz, 0
    F, dpv = _idw(P, s, Q[vic], vicini=8, liscio=1.0)
    w = np.clip((ADATTA_LONTANO - dpv) / (ADATTA_LONTANO - ADATTA_VICINO), 0, 1)
    dz[vic] = np.clip(w * F, -ADATTA_LIMITE, ADATTA_LIMITE)
    return dz, int(len(P))


# punti quotati usati solo per la superficie di riferimento, senza US (es. i «datum points» di Heathrow)
L_QUOTE_SUPERFICIE = "quote_superficie"


def punti_rilevati(scavo):
    """Quote rilevate del piano di scavo in coordinate assolute, N x 3: dal layer delle quote quelle di tipo
    sup, orlo, rasatura (anche senza US); dal layer ``quote_superficie`` tutte (o quelle di quei tipi)."""
    from . import schema as sc
    import shapely
    out = []
    for nome in (sc.L_QUOTE, L_QUOTE_SUPERFICIE):
        g = scavo.layers.get(nome)
        if g is None or not len(g):
            continue
        g = g[g.geometry.notna()]
        g = g[~g.geometry.is_empty & (g.geometry.geom_type == "Point")]
        if sc.F_TIPO_QUOTA in g.columns:
            ok = g[sc.F_TIPO_QUOTA].astype(str).isin([sc.Q_SUP, sc.Q_ORLO, sc.Q_RASATURA])
            if nome == L_QUOTE_SUPERFICIE:
                ok |= g[sc.F_TIPO_QUOTA].isna()
            g = g[ok]
        if len(g):
            out.append(shapely.get_coordinates(np.asarray(g.geometry.values), include_z=True))
    if not out:
        return np.zeros((0, 3))
    P = np.vstack(out)
    return P[np.isfinite(P).all(axis=1)]


def georef(path):
    """Georiferimento di un GeoTIFF senza decodificare i pixel: angolo in alto a sinistra (bordo della
    cella), passo, dimensioni, bande, tipo, valore vuoto. Legge i tag GeoTIFF o il file .tfw accanto."""
    try:
        import tifffile
    except ImportError as e:      # pragma: no cover - dipende dall'installazione
        raise RuntimeError("Per leggere i raster serve il pacchetto 'tifffile': esegui di nuovo "
                           "l'installazione (Installa (Windows).bat)") from e
    import logging
    logging.getLogger("tifffile").setLevel(logging.ERROR)
    with tifffile.TiffFile(path) as t:
        p = t.pages[0]
        tags = p.tags
        forma = p.shape
        bande = p.samplesperpixel
        dtype = str(p.dtype)
        nodata = None
        if "GDAL_NODATA" in tags:
            try:
                nodata = float(str(tags["GDAL_NODATA"].value).strip().strip("\x00"))
            except ValueError:
                nodata = None
        geo = None
        if "ModelTransformationTag" in tags:
            m = tags["ModelTransformationTag"].value
            if abs(m[1]) > 1e-9 or abs(m[4]) > 1e-9:
                raise RuntimeError("Raster ruotato: non supportato")
            geo = (m[3], m[7], m[0], -m[5])            # angolo in alto a sinistra, passo x, passo y
        elif "ModelPixelScaleTag" in tags and "ModelTiepointTag" in tags:
            sx, sy = tags["ModelPixelScaleTag"].value[:2]
            i, j, _, X, Y, _ = tags["ModelTiepointTag"].value[:6]
            geo = (X - i * sx, Y + j * sy, sx, sy)
        punto = False
        if "GeoKeyDirectoryTag" in tags:
            gk = list(tags["GeoKeyDirectoryTag"].value)
            for k in range(4, len(gk) - 3, 4):
                if gk[k] == 1025 and gk[k + 3] == 2:      # GTRasterTypeGeoKey = RasterPixelIsPoint
                    punto = True
    tfw = _cerca_tfw(path)
    if tfw is not None:
        a, d, b, e, c, f = tfw
        if abs(d) > 1e-6 * abs(a) or abs(b) > 1e-6 * abs(e):
            raise RuntimeError("Raster ruotato nel file .tfw: non supportato")
        geo = (c - a / 2, f - e / 2, a, -e)            # il .tfw indica il centro della prima cella
        punto = False
    if geo is None:
        raise RuntimeError("Il raster non è georiferito (mancano tag GeoTIFF e file .tfw)")
    xs, ys, sx, sy = geo
    if punto:                                          # la coordinata indica il centro della cella
        xs, ys = xs - sx / 2, ys + sy / 2
    righe, colonne = forma[0], forma[1]
    if len(forma) == 3 and forma[0] <= 4 and forma[-1] > 4:       # bande per prime
        righe, colonne = forma[1], forma[2]
    return dict(angolo=(float(xs), float(ys)), passo=(float(sx), float(sy)), righe=int(righe),
                colonne=int(colonne), bande=int(bande), dtype=dtype, nodata=nodata,
                estensione=[float(xs), float(ys - righe * sy), float(xs + colonne * sx), float(ys)])


def e_ortofoto(g):
    """Un raster a colori (3 o 4 bande a 8 bit) è un'immagine da drappeggiare, non un modello del terreno."""
    return g["bande"] >= 3 and g["dtype"] == "uint8"


def _cerca_tfw(path):
    base = os.path.splitext(path)[0]
    for est in (".tfw", ".tifw", ".TFW", ".wld"):
        p = base + est
        if os.path.exists(p):
            try:
                v = [float(x) for x in open(p).read().split()[:6]]
                return v if len(v) == 6 else None
            except ValueError:
                return None
    return None


def normalizza(spec):
    """Specifica della superficie con i valori mancanti riempiti."""
    s = dict(spec or {})
    s.setdefault("tipo", "nessuna")
    if s["tipo"] not in TIPI:
        s["tipo"] = "nessuna"
    s["abbassa"] = float(s.get("abbassa") or 0.0)
    if s["tipo"] == "costante":
        s["quota"] = float(s.get("quota") or 0.0)
    if "quote" in s:
        s["quote"] = bool(s["quote"])
    return s


def campionatore(scavo):
    """Funzione (x, y locali) -> quota della superficie di riferimento, oppure None se non definita."""
    s = normalizza(scavo.parametri.superficie)
    o = scavo.origine
    if s["tipo"] == "costante":
        q = s["quota"] - s["abbassa"]
        return lambda xy: np.full(len(xy), q)
    if s["tipo"] == "raster":
        r = scavo.raster_superficie
        if r is None:
            return None
        return lambda xy: r(np.asarray(xy)[:, 0] + o["E0"], np.asarray(xy)[:, 1] + o["N0"]) - s["abbassa"]
    if s["tipo"] == "quote":
        from . import schema as sc
        q = scavo.quote_locali()
        q = q[q.tipo.isin([sc.Q_SUP, sc.Q_ORLO, sc.Q_RASATURA])]
        if len(q) < 3:
            return None
        from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
        P = q[["x", "y"]].to_numpy()
        # per ogni cella di 0,5 m la quota più alta: la superficie da cui si scava, non i fondi
        k = np.floor(P / 0.5).astype(int)
        d = q.assign(kx=k[:, 0], ky=k[:, 1]).sort_values("z").groupby(["kx", "ky"]).tail(1)
        P, Z = d[["x", "y"]].to_numpy(), d.z.to_numpy()
        lin, near = LinearNDInterpolator(P, Z), NearestNDInterpolator(P, Z)

        def f(xy):
            v = lin(xy)
            m = np.isnan(v)
            if m.any():
                v[m] = near(np.asarray(xy)[m])
            return v - s["abbassa"]
        return f
    return None
