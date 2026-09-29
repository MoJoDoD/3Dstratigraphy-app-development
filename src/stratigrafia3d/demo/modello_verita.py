# -*- coding: utf-8 -*-
"""
Modello "di verità" dello scavo immaginario, costruito su griglia raster (5 cm).
Simula in ordine cronologico: deposizioni, tagli, riempimenti, costruzione di muri,
crolli, spoliazioni. Da questo modello si estraggono poi i dati "osservati"
(poligoni, quote, profili) come li avrebbe rilevati un archeologo.
"""
import numpy as np
from scipy import ndimage
from shapely.geometry import box, Polygon, Point, LineString
from shapely.ops import unary_union
from shapely import contains_xy

RES = 0.05
W, H = 20.0, 16.0
xs = np.arange(RES / 2, W, RES)
ys = np.arange(RES / 2, H, RES)
X, Y = np.meshgrid(xs, ys)          # shape (ny, nx) ; riga = y
NY, NX = X.shape

TRENCH = box(0, 0, W, H)
SONDAGE = box(10.6, 8.6, 15.6, 12.5)             # saggio in profondità
ROOM_A = box(2.4, 3.0, 10.0, 12.5)
ROOM_B = box(10.6, 3.0, 20.0, 12.5)


def wobbly_box(x0, y0, x1, y1, amp=0.025, seed=0, step=0.25):
    """Rettangolo con bordi leggermente irregolari (paramento di un muro)."""
    rng = np.random.default_rng(seed)
    pts = []
    def edge(ax, ay, bx, by):
        n = max(2, int(np.hypot(bx - ax, by - ay) / step))
        for i in range(n):
            t = i / n
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            nx, ny = -(by - ay), (bx - ax)
            L = np.hypot(nx, ny) or 1
            d = rng.normal(0, amp) if 0 < i else 0
            pts.append((px + nx / L * d, py + ny / L * d))
    edge(x0, y0, x1, y0); edge(x1, y0, x1, y1); edge(x1, y1, x0, y1); edge(x0, y1, x0, y0)
    return Polygon(pts).buffer(0)


def blob(cx, cy, rx, ry, seed=0, irr=0.15, rot=0.0, n=90):
    rng = np.random.default_rng(seed)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = np.ones_like(th)
    for k in range(2, 6):
        r += irr / k * rng.normal() * np.cos(k * th + rng.uniform(0, 2 * np.pi))
    px, py = rx * r * np.cos(th), ry * r * np.sin(th)
    c, s = np.cos(rot), np.sin(rot)
    return Polygon(np.c_[cx + c * px - s * py, cy + s * px + c * py]).buffer(0)


def M(geom):
    return contains_xy(geom, X, Y)


def noise(sigma_m, amp, seed):
    r = np.random.default_rng(seed).standard_normal(X.shape)
    f = ndimage.gaussian_filter(r, sigma_m / RES, mode="reflect")
    return f / f.std() * amp


def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def dist_in(mask):
    """Distanza (m) dal bordo interno della maschera (i bordi della griglia non contano)."""
    return ndimage.distance_transform_edt(mask) * RES


# ----------------------------------------------------------------------------
# Muri (poligoni esatti)
# ----------------------------------------------------------------------------
W1101 = wobbly_box(1.8, 12.5, 20.0, 13.1, seed=11)
W1102 = wobbly_box(1.8, 2.4, 20.0, 3.0, seed=12)
W1103 = wobbly_box(1.8, 3.0, 2.4, 12.5, seed=13)
W1100 = unary_union([wobbly_box(10.0, 3.0, 10.6, 6.8, seed=14),
                     wobbly_box(10.0, 8.0, 10.6, 12.5, seed=15)])
W1106 = box(10.02, 6.8, 10.58, 8.0)
W1105 = unary_union([wobbly_box(2.5, 14.0, 20.0, 14.18, amp=0.01, seed=16),
                     wobbly_box(2.5, 14.52, 20.0, 14.7, amp=0.01, seed=17),
                     box(2.5, 14.0, 2.7, 14.7)])       # testata O chiusa
W1107 = box(2.7, 14.18, 20.0, 14.52)
WALLS_ALL = unary_union([W1100, W1101, W1102, W1103, W1105, W1106, W1107])

BUILDING = box(1.8, 2.4, 20.0, 13.1)
EXT = TRENCH.difference(BUILDING).difference(unary_union([W1101, W1102, W1103]))
N_EXT = EXT.intersection(box(0, 12.8, W, H))
SW_EXT = EXT.difference(box(0, 12.8, W, H))
# interno dell'edificio diviso in due ambienti dall'asse del tramezzo
INTERIOR = BUILDING.difference(unary_union([W1100, W1101, W1102, W1103, W1106]))
ROOM_A_REAL = INTERIOR.intersection(box(0, 0, 10.3, H))
ROOM_B_REAL = INTERIOR.intersection(box(10.3, 0, W, H))


class Truth:
    def __init__(self):
        self.S = np.zeros(X.shape)           # superficie corrente
        self.owner = np.zeros(X.shape, int)  # US che forma la superficie
        self.bodies = {}                      # us -> dict(top,bot,kind)
        self.cuts = {}                        # us -> dict(surf, rim)
        self.order = []                       # sequenza di costruzione
        self.rel = {}                         # (a, tipo, b) -> n celle
        self.wall_ids = []

    # -- registro rapporti -------------------------------------------------
    def addrel(self, a, t, b, n):
        if a == b or b == 0:
            return
        self.rel[(a, t, b)] = self.rel.get((a, t, b), 0) + int(n)

    def _record_under(self, us, m):
        own = self.owner[m]
        for b, n in zip(*np.unique(own, return_counts=True)):
            if b == 0:
                continue
            t = "riempie" if b in self.cuts else "copre"
            self.addrel(us, t, b, n)

    def _record_abut(self, us, m, bot):
        dil = ndimage.binary_dilation(m, iterations=2)
        for w in self.wall_ids:
            wb = self.bodies[w]
            ring = dil & ~m & ~np.isnan(wb["top"])
            if ring.sum() > 8:
                # il muro deve emergere sopra la base dello strato
                if np.nanmean(wb["top"][ring]) > np.nanmean(bot[m]) + 0.02:
                    self.addrel(us, "si appoggia a", w, ring.sum())

    # -- operazioni ---------------------------------------------------------
    def base(self, us, top):
        self.S = top.copy()
        b = dict(top=top.copy(), bot=top - 0.6, kind="strato")
        self.bodies[us] = b
        self.owner[:] = us
        self.order.append(us)

    def deposit(self, us, mask, th, kind="strato", abut=True):
        m = mask & (th > 0.004)
        top = np.full(X.shape, np.nan); bot = np.full(X.shape, np.nan)
        bot[m] = self.S[m]; top[m] = self.S[m] + th[m]
        self._record_under(us, m)
        if abut:
            self._record_abut(us, m, bot)
        self.bodies[us] = dict(top=top, bot=bot, kind=kind)
        self.S[m] = top[m]; self.owner[m] = us
        self.order.append(us)

    def fill_to(self, us, mask, level, kind="riempimento"):
        th = np.where(mask, level - self.S, 0)
        self.deposit(us, mask, th, kind=kind)

    def _truncate(self, us, mask, surf):
        for b_id, b in self.bodies.items():
            t = b["top"]
            hit = mask & ~np.isnan(t) & (t > surf + 1e-4)
            if hit.sum() == 0:
                continue
            if us is not None:
                self.addrel(us, "taglia", b_id, hit.sum())
            t[hit] = surf[hit]
            gone = hit & (t - b["bot"] < 0.004)
            t[gone] = np.nan; b["bot"][gone] = np.nan

    def cut(self, us, mask, depth, wall_w=0.15, flat=None):
        """Taglio a pareti ripide: profondità piena a distanza wall_w dal bordo."""
        d = dist_in(mask)
        prof = smoothstep(d / wall_w)
        surf = self.S - depth * prof
        if flat is not None:                     # fondo piano a quota assoluta
            surf = np.minimum(self.S, np.maximum(surf, flat))
        rim = self.S.copy()
        self._truncate(us, mask, surf)
        sc = np.full(X.shape, np.nan); sc[mask] = surf[mask]
        self.cuts[us] = dict(surf=sc, rim=np.where(mask, rim, np.nan))
        self.S[mask] = surf[mask]; self.owner[mask] = us
        self.order.append(us)

    def erode(self, mask, depth_to):
        """Degrado senza numero di US (es. lacune del pavimento)."""
        self._truncate(None, mask, np.where(mask, depth_to, 1e9))
        self.S[mask] = np.minimum(self.S[mask], depth_to[mask])
        # l'owner torna allo strato sottostante esposto
        for b_id in reversed(self.order):
            b = self.bodies.get(b_id)
            if b is None:
                continue
            ok = mask & ~np.isnan(b["top"]) & (np.abs(b["top"] - self.S) < 1e-3)
            self.owner[ok] = b_id

    def wall(self, us, geom, base, top, in_cut=None):
        m = M(geom)
        basearr = np.full(X.shape, base) if np.isscalar(base) else base
        # la fondazione asporta ciò che sta sopra la base
        for b_id, b in self.bodies.items():
            t = b["top"]
            hit = m & ~np.isnan(t) & (t > basearr)
            if hit.sum():
                t[hit] = np.maximum(basearr[hit], b["bot"][hit])
                gone = hit & (t - b["bot"] < 0.004)
                t[gone] = np.nan; b["bot"][gone] = np.nan
        if in_cut is not None:
            self.addrel(us, "riempie", in_cut, m.sum())
        topa = np.full(X.shape, np.nan); bota = np.full(X.shape, np.nan)
        tt = np.full(X.shape, top) if np.isscalar(top) else top
        topa[m] = tt[m]; bota[m] = basearr[m]
        self.bodies[us] = dict(top=topa, bot=bota, kind="muro")
        self.S[m] = tt[m]; self.owner[m] = us
        self.wall_ids.append(us)
        self.order.append(us)

    def raze(self, us, crest):
        b = self.bodies[us]
        m = ~np.isnan(b["top"])
        b["top"][m] = np.minimum(b["top"][m], crest[m])
        self.S[m] = b["top"][m]


def build(seed=1974):
    T = Truth()
    n = lambda s, a, k: noise(s, a, seed + k)

    # --- Fase 0: substrato -------------------------------------------------
    top1031 = 243.72 - 0.030 * X + 0.012 * Y + n(2.0, 0.05, 1) + n(0.6, 0.012, 2)
    T.base(1031, top1031)

    # --- Fase 1: paleosuolo, buche di palo, livello ellenistico ------------
    T.deposit(1030, M(TRENCH), 0.18 + n(1.5, 0.03, 3), abut=False)
    for cut_id, fill_id, (cx, cy), r, dep, sd in [
            (1024, 1025, (12.6, 10.9), 0.23, 0.42, 21),
            (1026, 1027, (13.9, 11.35), 0.20, 0.36, 22),
            (1028, 1029, (13.2, 9.3), 0.25, 0.47, 23)]:
        g = blob(cx, cy, r, r * 0.95, seed=sd, irr=0.08)
        mk = M(g)
        rim = T.S.copy()
        T.cut(cut_id, mk, dep, wall_w=0.06)
        T.fill_to(fill_id, mk, rim - 0.01 + n(0.3, 0.004, sd))
    g1023 = blob(13.3, 10.4, 2.3, 1.5, seed=31, irr=0.25, rot=0.3)
    m1023 = M(g1023)
    th = 0.14 * smoothstep(dist_in(m1023) / 0.6) * (1 + n(0.5, 0.25, 4))
    T.deposit(1023, m1023, np.clip(th, 0, None), abut=False)

    # --- Fase 2: livellamento, fondazioni, muri, cantiere ------------------
    L = 244.05 + n(2.5, 0.02, 5)
    T.deposit(1021, M(TRENCH), np.maximum(L - T.S, 0.14) + n(0.8, 0.012, 6), abut=False)

    # muri perimetrali (1101 con trincea di fondazione vista nel saggio), poi il tramezzo 1100
    tr1101 = W1101.buffer(0.25, join_style=2).intersection(box(0, 12.0, W, 13.6))
    m_tr = M(tr1101)
    rim = T.S.copy()
    T.cut(1037, m_tr, 0.45, wall_w=0.05, flat=243.66)
    T.wall(1101, W1101, 243.66 + n(1, 0.01, 8), 246.5, in_cut=1037)
    T.fill_to(1038, m_tr & ~M(W1101), rim - 0.015)
    T.wall(1102, W1102, 243.70 + n(1, 0.01, 9), 246.5)
    T.wall(1103, W1103, 243.74 + n(1, 0.01, 10), 246.5)
    T.addrel(1101, "si lega a", 1103, 100); T.addrel(1102, "si lega a", 1103, 100)

    perim = unary_union([W1101, W1102, W1103])
    tr1100 = W1100.buffer(0.25, join_style=2).intersection(box(0, 3.0, W, 12.5)).difference(perim)
    m_tr = M(tr1100) & ~M(perim)
    rim = T.S.copy()
    T.cut(1019, m_tr, 0.40, wall_w=0.05, flat=243.72)
    T.wall(1100, W1100.difference(perim), 243.72 + n(1, 0.01, 7), 246.5, in_cut=1019)
    T.fill_to(1020, m_tr & ~M(W1100), rim - 0.015)
    T.addrel(1100, "si appoggia a", 1101, 50); T.addrel(1100, "si appoggia a", 1102, 50)

    T.wall(1106, W1106, 244.08, 244.31 + n(0.5, 0.004, 11))
    T.addrel(1106, "si appoggia a", 1100, 50)

    g1022 = unary_union([blob(12.4, 10.2, 1.6, 1.1, seed=41, irr=0.3),
                         blob(6.5, 8.0, 2.0, 1.4, seed=42, irr=0.3)])
    m1022 = M(g1022) & ~M(WALLS_ALL)
    th = 0.075 * smoothstep(dist_in(m1022) / 0.5) * (1 + n(0.4, 0.3, 12))
    T.deposit(1022, m1022, np.clip(th, 0, None))

    # --- Fase 3: pavimenti, canaletta, piani esterni ------------------------
    mA = M(ROOM_A_REAL) & ~M(WALLS_ALL); mB = M(ROOM_B_REAL) & ~M(WALLS_ALL)
    T.deposit(1015, mA, np.maximum(244.215 + 0.002 * X + n(1.5, 0.006, 13) - T.S, 0.06), kind="strato")
    T.deposit(1014, mA, 0.07 + n(1.0, 0.004, 14), kind="strato")
    T.deposit(1017, mB, np.maximum(244.115 + n(1.5, 0.008, 15) - T.S, 0.06))
    T.deposit(1016, mB, 0.05 + n(1.0, 0.006, 16))

    # canaletta
    T.wall(1107, W1107, 243.84 - 0.003 * X, 243.92 - 0.004 * X)
    T.wall(1105, W1105, 243.84 - 0.003 * X, 244.30 + n(1.2, 0.03, 17))
    T.addrel(1105, "si lega a", 1107, 50)
    mN = M(N_EXT) & ~M(W1105) & ~M(W1107)
    T.deposit(1033, mN, 0.085 + n(1.0, 0.012, 18))
    T.deposit(1035, M(SW_EXT), 0.07 + n(1.0, 0.01, 19))

    # --- Fase 4: lacune, focolare, abbandono, interro canaletta -------------
    lac = unary_union([blob(3.6, 11.0, 0.7, 0.5, seed=51, irr=0.3),
                       blob(8.2, 4.2, 0.6, 0.45, seed=52, irr=0.35),
                       blob(7.6, 9.9, 0.9, 0.55, seed=53, irr=0.3),
                       blob(5.6, 8.25, 0.5, 0.4, seed=54, irr=0.3)])
    mlac = M(lac) & mA
    T.erode(mlac, np.where(mlac, T.bodies[1015]["top"], np.nan))

    g1013 = blob(15.3, 7.2, 0.62, 0.45, seed=61, irr=0.1, rot=0.4)
    m1013 = M(g1013)
    th = 0.065 * smoothstep(dist_in(m1013) / 0.3)
    T.deposit(1013, m1013, th)
    T.fill_to(1018, M(W1107), 244.16 - 0.003 * X + n(1, 0.01, 20))
    T.deposit(1008, mB, 0.17 + n(1.3, 0.05, 21) + n(0.4, 0.015, 22))
    T.deposit(1007, mA, np.maximum(0.2 + n(1.3, 0.06, 23) + n(0.4, 0.015, 24), 0.08) +
              np.where(mlac, 0.03, 0))

    # --- Fase 5: tomba a cappuccina -----------------------------------------
    gT = LineString([(4.35, 5.4), (5.85, 5.4)]).buffer(0.42, cap_style=1).intersection(box(3.9, 4.95, 6.3, 5.85))
    gT = gT.buffer(0.05).buffer(-0.05)
    mT = M(gT)
    rimT = T.S.copy()
    T.cut(1009, mT, 1.0, wall_w=0.07, flat=243.62)
    T.fill_to(1012, mT, 243.93 + n(0.3, 0.004, 25))
    tent_mask = mT & (np.abs(Y - 5.4) < 0.34) & (X > 4.1) & (X < 6.1)
    tent_top = 243.93 + np.clip(0.30 - 0.85 * np.abs(Y - 5.4), 0, None)
    T.deposit(1010, tent_mask, np.where(tent_mask, tent_top - T.S, 0), kind="struttura")
    T.fill_to(1011, mT, rimT - 0.03)

    # --- Fase 6: crolli ------------------------------------------------------
    def near_wall(mask, w=1.2):
        d = ndimage.distance_transform_edt(~M(WALLS_ALL)) * RES
        return np.exp(-d / w)
    lumps = np.clip(n(0.45, 1.0, 26), -1, 3)
    T.deposit(1005, mA, np.clip(0.13 + 0.07 * lumps + 0.18 * near_wall(mA), 0.03, None))
    lumps = np.clip(n(0.5, 1.0, 27), -1, 3)
    T.deposit(1006, mB, np.clip(0.16 + 0.08 * lumps + 0.25 * near_wall(mB), 0.04, None))
    T.deposit(1032, M(N_EXT), np.clip(0.18 + n(1.0, 0.05, 28) + 0.15 * near_wall(None), 0.05, None))
    T.deposit(1034, M(SW_EXT), np.clip(0.12 + n(0.8, 0.05, 29) + 0.22 * near_wall(None), 0.04, None))

    # rasatura dei muri
    for w, c, a, sd in [(1100, 244.86, 0.10, 30), (1101, 244.95, 0.12, 31),
                        (1102, 244.80, 0.12, 32), (1103, 244.90, 0.10, 33)]:
        T.raze(w, c + n(1.0, a, sd) + n(0.25, 0.03, sd + 50))

    # --- Fase 7: spoliazione e fossa -----------------------------------------
    g1003 = Polygon([(9.72, 9.15), (10.95, 9.35), (10.9, 11.0), (10.98, 12.45),
                     (9.68, 12.45), (9.62, 11.2)]).buffer(0.08).buffer(-0.08)
    m1003 = M(g1003)
    rim = T.S.copy()
    # il fondo della spoliazione si ferma sulla risega di fondazione
    T.cut(1003, m1003, 1.2, wall_w=0.18, flat=244.06 + n(0.6, 0.02, 34))
    T.fill_to(1004, m1003, rim - 0.04)

    g1001 = blob(17.0, 5.2, 1.05, 0.95, seed=71, irr=0.18, rot=0.5)
    m1001 = M(g1001)
    rim = T.S.copy()
    T.cut(1001, m1001, 1.4, wall_w=0.45, flat=243.33 + n(0.4, 0.02, 35))
    T.fill_to(1036, m1001, 243.62 + n(0.4, 0.02, 36))
    T.fill_to(1002, m1001, rim - 0.07 + n(0.4, 0.01, 37))

    # --- Fase 8: arativo ------------------------------------------------------
    G = ndimage.gaussian_filter(T.S, 2.0 / RES) + 0.30
    G = np.maximum(G, T.S + 0.20)
    G = ndimage.gaussian_filter(G, 0.3 / RES)
    G = np.maximum(G, T.S + 0.16) + n(1.5, 0.02, 38)
    T.deposit(1000, M(TRENCH), G - T.S, abut=False)
    return T


if __name__ == "__main__":
    T = build()
    for us in T.order:
        b = T.bodies.get(us)
        if b is not None:
            m = ~np.isnan(b["top"])
            print(us, b["kind"], m.sum(), np.round(np.nanmin(b["bot"]), 2) if m.any() else "-",
                  np.round(np.nanmax(b["top"]), 2) if m.any() else "-")
        else:
            c = T.cuts[us]
            print(us, "taglio", np.round(np.nanmin(c["surf"]), 2))
