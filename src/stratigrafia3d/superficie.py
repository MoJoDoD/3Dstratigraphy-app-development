# -*- coding: utf-8 -*-
"""
Superficie di riferimento: la quota da cui partono le unità che non hanno quote proprie
(tagli di cui si conosce solo la profondità, strati di cui si conosce solo lo spessore).

Tre modi, descritti da un dizionario salvato nei parametri del progetto:
    {"tipo": "costante", "quota": 45.20, "abbassa": 0.0}
    {"tipo": "raster",   "sorgente": "dtm.tif", "abbassa": 0.30}      # modello del terreno
    {"tipo": "quote",    "abbassa": 0.0}                              # interpolata dalle quote rilevate
    {"tipo": "nessuna"}
"abbassa" sposta la superficie verso il basso (es. lo spessore dell'arativo asportato).
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
