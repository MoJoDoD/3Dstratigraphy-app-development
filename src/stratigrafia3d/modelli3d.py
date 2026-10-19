"""Modelli 3D rilevati (fotogrammetria, laser scanner) da mostrare accanto alle unità ricostruite.

Formati: OBJ (con colori dei vertici o texture dal file .mtl) e PLY (ASCII o binario, con colori).
Le coordinate devono essere nello stesso sistema del GIS; se il modello è stato esportato con uno
spostamento (frequente con Metashape e simili) lo si indica e viene sommato. I modelli troppo pesanti
si semplificano raggruppando i vertici su una griglia, fino a circa 300 000 triangoli.
"""
import io
import os

import numpy as np

EST_MODELLI = {".obj", ".ply"}
TRIANGOLI_MAX = 300_000
TRIANGOLI_TOTALI = 900_000        # tra tutti i modelli mostrati insieme
LATO_TEXTURE = 4096


class Modello3D:
    def __init__(self, V, F, colori=None, uv=None, texture=None, nome=""):
        self.V = np.asarray(V, "float64")          # coordinate reali (E, N, quota)
        self.F = np.asarray(F, "int64")
        self.colori = None if colori is None else np.asarray(colori, "uint8")
        self.uv = None if uv is None else np.asarray(uv, "float32")
        self.texture = texture                      # byte JPEG
        self.nome = nome

    # ------------------------------------------------------------------ lettura
    @classmethod
    def leggi(cls, path, spostamento=(0.0, 0.0, 0.0), triangoli_max=TRIANGOLI_MAX, lato_texture=LATO_TEXTURE):
        """Modello letto e semplificato a ``triangoli_max``; il risultato resta nella cache (cache.py), così
        i modelli da centinaia di MB si leggono una volta sola."""
        from . import cache
        cp = cache.percorso("modelli3d", path, tuple(spostamento), triangoli_max, lato_texture) \
            if triangoli_max < 10 ** 11 else None
        b = cache.leggi(cp)
        if b is not None:
            try:
                return cls.da_bytes(b)
            except Exception:
                pass
        m = cls._leggi(path, spostamento, triangoli_max, lato_texture)
        if cp:
            cache.scrivi(cp, m.a_bytes())
        return m

    @classmethod
    def _leggi(cls, path, spostamento=(0.0, 0.0, 0.0), triangoli_max=TRIANGOLI_MAX, lato_texture=LATO_TEXTURE):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".obj":
            m = _leggi_obj(path, lato_texture)
        elif ext == ".ply":
            m = _leggi_ply(path)
        else:
            raise RuntimeError(f"Formato di modello 3D non supportato: {ext}")
        m.nome = os.path.basename(path)
        if any(spostamento):
            m.V = m.V + np.asarray(spostamento, "float64")
        if len(m.F) > triangoli_max:
            m = m.semplifica(triangoli_max)
        return m

    def semplifica(self, triangoli_max):
        """Semplificazione per raggruppamento dei vertici su una griglia (rapida, senza dipendenze)."""
        lato = np.ptp(self.V, axis=0)
        area = max(lato[0] * lato[1], lato[0] * lato[2], lato[1] * lato[2], 1e-9)
        passo = np.sqrt(area / triangoli_max) * 0.75
        for _ in range(8):
            k = np.floor((self.V - self.V.min(0)) / passo).astype(np.int64)
            n1, n2 = int(k[:, 0].max()) + 1, int(k[:, 1].max()) + 1
            chiave = k[:, 0] + n1 * (k[:, 1] + n2 * k[:, 2])          # una chiave intera per cella
            _, gruppo, conta = np.unique(chiave, return_inverse=True, return_counts=True)
            gruppo = gruppo.ravel()
            F = gruppo[self.F]
            buoni = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
            if buoni.sum() <= triangoli_max:
                break
            passo *= 1.25
        n = len(conta)
        V = np.zeros((n, 3))
        np.add.at(V, gruppo, self.V)
        V /= conta[:, None]
        colori = uv = None
        if self.colori is not None:
            c = np.zeros((n, 3))
            np.add.at(c, gruppo, self.colori[:, :3].astype(float))
            colori = (c / conta[:, None]).round().astype("uint8")
        if self.uv is not None:
            u = np.zeros((n, 2))
            np.add.at(u, gruppo, self.uv)
            uv = u / conta[:, None]
        return Modello3D(V, F[buoni], colori, uv, self.texture, self.nome)

    def descrizione(self):
        return dict(nome=self.nome, vertici=int(len(self.V)), triangoli=int(len(self.F)),
                    colori=self.colori is not None, texture=self.texture is not None,
                    estensione=[round(float(v), 2) for v in (*self.V.min(0), *self.V.max(0))])

    # ------------------------------------------------------------------ progetto
    def a_bytes(self):
        buf = io.BytesIO()
        extra = {}
        if self.colori is not None:
            extra["colori"] = self.colori
        if self.uv is not None:
            extra["uv"] = self.uv
        if self.texture is not None:
            extra["texture"] = np.frombuffer(self.texture, "uint8")
        np.savez_compressed(buf, V=self.V, F=self.F.astype("<u4"), nome=np.array(self.nome), **extra)
        return buf.getvalue()

    @classmethod
    def da_bytes(cls, b):
        z = np.load(io.BytesIO(b))
        return cls(z["V"], z["F"].astype(np.int64), z["colori"] if "colori" in z else None,
                   z["uv"] if "uv" in z else None, z["texture"].tobytes() if "texture" in z else None, str(z["nome"]))


def esamina(path):
    """Descrizione rapida (senza semplificare) per il wizard: vertici, triangoli, estensione."""
    try:
        return Modello3D.leggi(path, triangoli_max=10**12).descrizione()
    except Exception as e:
        return dict(errore=str(e))


# ---------------------------------------------------------------------------------------------- OBJ
BLOCCO_OBJ = 64 * 2 ** 20


def _numeri(righe, salta, tipo=float):
    """Numeri di più righe di testo (bytes) come array: «v 1 2 3» -> [1, 2, 3]."""
    if not righe:
        return np.zeros(0, tipo)
    return np.array(b" ".join(r[salta:] for r in righe).split(), dtype=tipo)


def _leggi_obj(path, lato_texture=LATO_TEXTURE):
    """OBJ letto a blocchi, con i numeri convertiti in un colpo solo (i modelli fotogrammetrici pesano
    centinaia di MB: la lettura riga per riga richiedeva minuti e diversi GB di memoria). Facce con un
    numero di vertici diverso, o scritte in modi diversi nello stesso file, passano alla lettura riga per riga."""
    pezzi_v, pezzi_vt, pezzi_f = [], [], []
    ncol_v = None
    formato_f = None              # (angoli, indici per angolo, con texture)
    mtl = None
    resto = b""
    with open(path, "rb") as f:
        while True:
            blocco = f.read(BLOCCO_OBJ)
            fine = not blocco
            dati = resto + blocco
            if not fine:
                i = dati.rfind(b"\n")
                if i < 0:
                    resto = dati
                    continue
                dati, resto = dati[:i], dati[i + 1:]
            righe = dati.split(b"\n")
            v = [r for r in righe if r[:2] == b"v "]
            vt = [r for r in righe if r[:3] == b"vt "]
            fc = [r for r in righe if r[:2] == b"f "]
            if mtl is None:
                m = next((r for r in righe if r[:7] == b"mtllib "), None)
                if m is not None:
                    mtl = m[7:].decode("utf-8", "replace").strip()
            if v:
                a = _numeri(v, 2)
                n = len(v[0].split()) - 1
                if ncol_v is None:
                    ncol_v = n
                if n != ncol_v or a.size != len(v) * n:
                    return _leggi_obj_righe(path, lato_texture)
                pezzi_v.append(a.reshape(-1, n))
            if vt:
                a = _numeri(vt, 3)
                n = len(vt[0].split()) - 1
                if a.size != len(vt) * n:
                    return _leggi_obj_righe(path, lato_texture)
                pezzi_vt.append(a.reshape(-1, n)[:, :2])
            if fc:
                t = fc[0].split()[1:]
                k = t[0].split(b"/")
                fmt = (len(t), len([x for x in k if x]), len(k) > 1 and k[1] != b"")
                if formato_f is None:
                    formato_f = fmt
                if fmt != formato_f:
                    return _leggi_obj_righe(path, lato_texture)
                a = _numeri([r.replace(b"/", b" ") for r in fc], 2, np.int64)
                if a.size != len(fc) * fmt[0] * fmt[1]:
                    return _leggi_obj_righe(path, lato_texture)
                pezzi_f.append(a.reshape(-1, fmt[0], fmt[1]))
            if fine:
                break
    if not pezzi_v or not pezzi_f:
        raise RuntimeError("Il file OBJ non contiene triangoli")
    V = np.concatenate(pezzi_v)
    C = None
    if V.shape[1] >= 6:
        C, V = V[:, 3:6], V[:, :3]
    V = V[:, :3]
    VT = np.concatenate(pezzi_vt) if pezzi_vt else np.zeros((0, 2))
    A = np.concatenate(pezzi_f)
    del pezzi_f
    angoli, _, con_vt = formato_f
    if angoli > 3:                                   # poligoni -> triangoli a ventaglio
        A = np.concatenate([A[:, [0, i, i + 1]] for i in range(1, angoli - 1)])
    nv, nt = len(V), len(VT)
    vi = A[..., 0]
    vi = np.where(vi < 0, nv + vi, vi - 1)
    texture = _texture_obj(path, mtl, lato_texture) if (nt and con_vt) else None
    if texture is not None:
        ti = A[..., 1]
        ti = np.where(ti < 0, nt + ti, ti - 1)
        del A
        # una coppia (vertice, coordinata texture) per angolo; chiave intera: molto più rapida di unique(axis=0)
        chiave, inv = np.unique(vi.ravel() * np.int64(nt + 1) + ti.ravel(), return_inverse=True)
        cv, ct = chiave // (nt + 1), chiave % (nt + 1)
        return Modello3D(V[cv], inv.reshape(-1, 3), None, VT[np.clip(ct, 0, nt - 1)], texture)
    colori = None
    if C is not None and len(C) == nv:
        colori = (C if C.max() > 1.0 else C * 255).clip(0, 255).round().astype("uint8")
    return Modello3D(V, vi, colori)


def _leggi_obj_righe(path, lato_texture=LATO_TEXTURE):
    V, C, VT, facce, mtl = [], [], [], [], None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for riga in f:
            if riga.startswith("v "):
                p = riga.split()
                V.append([float(p[1]), float(p[2]), float(p[3])])
                if len(p) >= 7:
                    C.append([float(p[4]), float(p[5]), float(p[6])])
            elif riga.startswith("vt "):
                p = riga.split()
                VT.append([float(p[1]), float(p[2])])
            elif riga.startswith("f "):
                angoli = []
                for t in riga.split()[1:]:
                    k = t.split("/")
                    vi = int(k[0])
                    ti = int(k[1]) if len(k) > 1 and k[1] else 0
                    angoli.append((vi, ti))
                for i in range(1, len(angoli) - 1):          # poligoni -> triangoli a ventaglio
                    facce.append((angoli[0], angoli[i], angoli[i + 1]))
            elif riga.startswith("mtllib ") and mtl is None:
                mtl = riga.split(None, 1)[1].strip()
    if not V or not facce:
        raise RuntimeError("Il file OBJ non contiene triangoli")
    V = np.array(V)
    nv, nt = len(V), len(VT)
    A = np.array(facce)                                          # (n, 3, 2)
    vi = A[..., 0]
    vi = np.where(vi < 0, nv + vi, vi - 1)
    texture = _texture_obj(path, mtl, lato_texture) if VT else None
    if texture is not None:
        # una coppia (vertice, coordinata texture) per ogni angolo: vertici duplicati dove serve
        ti = A[..., 1]
        ti = np.where(ti < 0, nt + ti, ti - 1)
        chiave, inv = np.unique(vi.ravel() * np.int64(nt + 1) + ti.ravel(), return_inverse=True)
        cv, ct = chiave // (nt + 1), chiave % (nt + 1)
        return Modello3D(V[cv], inv.reshape(-1, 3), None, np.array(VT)[np.clip(ct, 0, nt - 1)], texture)
    colori = None
    if len(C) == nv:
        C = np.array(C)
        colori = (C if C.max() > 1.0 else C * 255).clip(0, 255).round().astype("uint8")
    return Modello3D(V, vi, colori)


def _texture_obj(path, mtl, lato_texture=LATO_TEXTURE):
    if not mtl:
        return None
    p = os.path.join(os.path.dirname(path), mtl)
    if not os.path.exists(p):
        return None
    img = None
    for riga in open(p, encoding="utf-8", errors="replace"):
        if riga.strip().lower().startswith("map_kd"):
            img = riga.strip().split(None, 1)[1].strip().split()[-1]
            break
    if not img:
        return None
    q = os.path.join(os.path.dirname(p), img)
    if not os.path.exists(q):
        return None
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 400_000_000
        with Image.open(q) as im:
            im = im.convert("RGB")
            if max(im.size) > lato_texture:
                k = lato_texture / max(im.size)
                im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------- PLY
_PLY_TIPI = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "i2", "int16": "i2",
             "ushort": "u2", "uint16": "u2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
             "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def _leggi_ply(path):
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise RuntimeError("Non è un file PLY")
        formato, elementi = None, []
        while True:
            riga = f.readline()
            if not riga:
                raise RuntimeError("Intestazione PLY incompleta")
            p = riga.decode("ascii", "replace").split()
            if not p:
                continue
            if p[0] == "format":
                formato = p[1]
            elif p[0] == "element":
                elementi.append(dict(nome=p[1], n=int(p[2]), prop=[]))
            elif p[0] == "property":
                if p[1] == "list":
                    elementi[-1]["prop"].append((p[4], "list", _PLY_TIPI[p[2]], _PLY_TIPI[p[3]]))
                else:
                    elementi[-1]["prop"].append((p[2], _PLY_TIPI[p[1]]))
            elif p[0] == "end_header":
                break
        dati = f.read()
    V = C = F = None
    if formato == "ascii":
        righe = dati.decode("ascii", "replace").split("\n")
        pos = 0
        for el in elementi:
            blocco = righe[pos:pos + el["n"]]
            pos += el["n"]
            if el["nome"] == "vertex":
                nomi = [q[0] for q in el["prop"]]
                a = np.array([r.split()[:len(nomi)] for r in blocco], float)
                V = a[:, [nomi.index("x"), nomi.index("y"), nomi.index("z")]]
                if "red" in nomi:
                    C = a[:, [nomi.index("red"), nomi.index("green"), nomi.index("blue")]].astype("uint8")
            elif el["nome"] == "face":
                tri = []
                for r in blocco:
                    v = [int(x) for x in r.split()]
                    n = v[0]
                    tri.extend((v[1], v[1 + i], v[2 + i]) for i in range(1, n - 1))
                F = np.array(tri)
    else:
        end = "<" if formato == "binary_little_endian" else ">"
        off = 0
        for el in elementi:
            if all(len(q) == 2 for q in el["prop"]):
                dt = np.dtype([(q[0], end + q[1]) for q in el["prop"]])
                a = np.frombuffer(dati, dt, count=el["n"], offset=off)
                off += dt.itemsize * el["n"]
                if el["nome"] == "vertex":
                    V = np.stack([a["x"], a["y"], a["z"]], 1).astype("float64")
                    if "red" in a.dtype.names:
                        C = np.stack([a["red"], a["green"], a["blue"]], 1).astype("uint8")
            else:
                # elemento con liste (le facce): veloce se tutte triangolari
                (nome_l, _, tc, ti), = [q for q in el["prop"] if len(q) == 4] or [(None, None, None, None)]
                altri = [q for q in el["prop"] if len(q) == 2]
                if el["nome"] == "face" and not altri:
                    dc, di = np.dtype(end + tc), np.dtype(end + ti)
                    passo = dc.itemsize + 3 * di.itemsize
                    prova = np.frombuffer(dati, np.dtype([("n", dc), ("i", di, 3)]), count=el["n"], offset=off) \
                        if off + passo * el["n"] <= len(dati) else None
                    if prova is not None and (prova["n"] == 3).all():
                        F = prova["i"].astype(np.int64)
                        off += passo * el["n"]
                        continue
                tri = []
                for _ in range(el["n"]):
                    for q in el["prop"]:
                        if len(q) == 2:
                            off += np.dtype(q[1]).itemsize
                        else:
                            dc, di = np.dtype(end + q[2]), np.dtype(end + q[3])
                            n = int(np.frombuffer(dati, dc, 1, off)[0])
                            off += dc.itemsize
                            idx = np.frombuffer(dati, di, n, off)
                            off += di.itemsize * n
                            if el["nome"] == "face":
                                tri.extend((idx[0], idx[i], idx[i + 1]) for i in range(1, n - 1))
                if el["nome"] == "face":
                    F = np.array(tri, np.int64)
    if V is None or F is None or not len(F):
        raise RuntimeError("Il file PLY non contiene una superficie a triangoli (forse è solo una nuvola di punti)")
    return Modello3D(V, F, C)
