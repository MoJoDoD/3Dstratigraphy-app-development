"""Ortofoto: un'immagine georiferita (GeoTIFF a colori, anche compresso JPEG) da drappeggiare sul modello.

L'immagine viene ritagliata sull'area dello scavo, ridotta a una misura che il visualizzatore regge
(4096 pixel di lato al massimo) e conservata nel progetto come JPEG, così il file .scavo resta
autosufficiente. Nel visualizzatore diventa la texture delle unità, proiettata dall'alto.
"""
import io
import json
import os

import numpy as np

from .superficie import georef

LATO_MAX = 4096
PIXEL_MAX = 400_000_000          # oltre, meglio ridurre l'immagine prima (GIS)


class Ortofoto:
    def __init__(self, jpeg, estensione, larghezza, altezza, nome="", passo=None):
        self.jpeg = jpeg                       # byte JPEG
        self.estensione = [float(v) for v in estensione]    # x0, y0, x1, y1 (bordi, coordinate reali)
        self.larghezza, self.altezza = int(larghezza), int(altezza)
        self.nome = nome
        self.passo = passo if passo is not None else (self.estensione[2] - self.estensione[0]) / max(self.larghezza, 1)

    @classmethod
    def leggi(cls, path, limiti=None, margine=5.0, lato_max=LATO_MAX):
        """Legge un GeoTIFF a colori. ``limiti`` (x0, y0, x1, y1): ritaglia sull'area, con un margine."""
        g = georef(path)
        if g["righe"] * g["colonne"] > PIXEL_MAX:
            raise RuntimeError(f"Ortofoto troppo grande ({g['colonne']} × {g['righe']} pixel): riducila nel GIS "
                               "a una risoluzione adatta alla vista d'insieme (per esempio 5 cm)")
        img = _pixel(path)
        x0, y0, x1, y1 = g["estensione"]
        sx, sy = g["passo"]
        # ritaglio sull'area dello scavo
        c0, c1, r0, r1 = 0, img.shape[1], 0, img.shape[0]
        if limiti is not None:
            a, b, c, d = limiti
            a, b, c, d = a - margine, b - margine, c + margine, d + margine
            c0 = int(np.clip(np.floor((a - x0) / sx), 0, img.shape[1]))
            c1 = int(np.clip(np.ceil((c - x0) / sx), 0, img.shape[1]))
            r0 = int(np.clip(np.floor((y1 - d) / sy), 0, img.shape[0]))
            r1 = int(np.clip(np.ceil((y1 - b) / sy), 0, img.shape[0]))
            if c1 - c0 < 2 or r1 - r0 < 2:
                raise RuntimeError("L'ortofoto non copre l'area dello scavo")
        img = img[r0:r1, c0:c1]
        est = [x0 + c0 * sx, y1 - r1 * sy, x0 + c1 * sx, y1 - r0 * sy]
        from PIL import Image
        im = Image.fromarray(img)
        passo = sx
        if max(im.size) > lato_max:
            k = lato_max / max(im.size)
            im = im.resize((max(1, round(im.size[0] * k)), max(1, round(im.size[1] * k))), Image.LANCZOS)
            passo = (est[2] - est[0]) / im.size[0]
        # cornice neutra di 2 pixel: fuori dall'immagine la texture ripete il bordo, cioè questo grigio
        w, h = im.size
        sx_, sy_ = (est[2] - est[0]) / w, (est[3] - est[1]) / h
        cornice = Image.new("RGB", (w + 4, h + 4), (200, 196, 188))
        cornice.paste(im.convert("RGB"), (2, 2))
        est = [est[0] - 2 * sx_, est[1] - 2 * sy_, est[2] + 2 * sx_, est[3] + 2 * sy_]
        buf = io.BytesIO()
        cornice.save(buf, "JPEG", quality=85)
        return cls(buf.getvalue(), est, w + 4, h + 4, os.path.basename(path), passo)

    def descrizione(self):
        return dict(nome=self.nome, larghezza=self.larghezza, altezza=self.altezza,
                    passo_cm=round(self.passo * 100, 1), estensione=[round(v, 2) for v in self.estensione],
                    kb=round(len(self.jpeg) / 1024))

    def a_bytes(self):
        meta = dict(estensione=self.estensione, larghezza=self.larghezza, altezza=self.altezza, nome=self.nome,
                    passo=self.passo)
        m = json.dumps(meta).encode("utf-8")
        return len(m).to_bytes(4, "little") + m + self.jpeg

    @classmethod
    def da_bytes(cls, b):
        n = int.from_bytes(b[:4], "little")
        meta = json.loads(b[4:4 + n].decode("utf-8"))
        return cls(b[4 + n:], meta["estensione"], meta["larghezza"], meta["altezza"], meta.get("nome", ""),
                   meta.get("passo"))


def _pixel(path):
    """Pixel RGB (righe, colonne, 3) a 8 bit. Pillow legge anche i GeoTIFF compressi JPEG."""
    try:
        from PIL import Image
    except ImportError as e:           # pragma: no cover
        raise RuntimeError("Per le ortofoto serve il pacchetto 'Pillow': esegui di nuovo l'installazione") from e
    Image.MAX_IMAGE_PIXELS = PIXEL_MAX
    try:
        with Image.open(path) as im:
            im.load()
            a = np.asarray(im.convert("RGBA") if im.mode in ("P", "LA", "PA") else im)
    except Exception:
        import tifffile
        try:
            a = tifffile.imread(path)
        except Exception as e:
            raise RuntimeError(f"Impossibile leggere l'ortofoto: {e}") from e
        if a.ndim == 3 and a.shape[0] <= 4 and a.shape[-1] > 4:
            a = np.moveaxis(a, 0, -1)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    if a.shape[-1] == 4:              # trasparenza: sfondo bianco
        alfa = a[..., 3:4].astype("float32") / 255
        a = (a[..., :3] * alfa + 255 * (1 - alfa)).astype("uint8")
    return np.ascontiguousarray(a[..., :3].astype("uint8"))
