# -*- coding: utf-8 -*-
"""Interpolazione di superfici da punti sparsi: trend planare + kriging semplice dei residui."""
import numpy as np
from scipy.spatial import cKDTree


class Krig:
    """Superficie z = trend(x, y) + residuo krigato (covarianza gaussiana).

    - ``mean`` impone la media (kriging semplice): lontano dai dati il valore torna a ``mean``.
      Usato per lo spessore, che deve tornare allo spessore medio dove non ci sono misure.
    - senza ``mean`` e con almeno 8 punti ben distribuiti si stima un piano di tendenza.
    - ``rng`` è la portata (m); se assente è stimata dalla distanza media tra i punti.
    """

    def __init__(self, P, mean=None, trend=True, rng=None, nug=0.003, min_sill=1e-4):
        P = np.asarray(P, float).reshape(-1, 3)
        if len(P):  # elimina punti entro 2 cm (duplicati di rilievo)
            keep = np.ones(len(P), bool)
            for i, j in sorted(cKDTree(P[:, :2]).query_pairs(0.02)):
                if keep[i] and keep[j]:
                    keep[j] = False
            P = P[keep]
        self.P = P
        n = len(P)
        self.const = float(mean) if mean is not None else (float(np.median(P[:, 2])) if n else 0.0)
        self.coef = None
        if trend and mean is None and n >= 8 and np.ptp(P[:, 0]) > 1.0 and np.ptp(P[:, 1]) > 1.0:
            A = np.c_[np.ones(n), P[:, 0], P[:, 1]]
            self.coef, *_ = np.linalg.lstsq(A, P[:, 2], rcond=None)
        r = P[:, 2] - self._trend(P[:, :2]) if n else np.zeros(0)
        if rng is None:
            if n >= 3:
                d, _ = cKDTree(P[:, :2]).query(P[:, :2], k=2)
                rng = float(np.clip(2.0 * np.median(d[:, 1]), 0.45, 3.0))
            else:
                rng = 1.5
        self.a = float(rng)
        # con media nota la varianza si misura attorno alla media, non attorno alla media campionaria
        var = float(np.mean(r ** 2)) if (mean is not None and n) else (float(np.var(r)) if n > 1 else 0.0)
        self.s2 = max(var, min_sill)
        self.w = np.zeros(0)
        if n:
            K = self._cov(P[:, :2], P[:, :2]) + np.eye(n) * (nug ** 2 + 1e-3 * self.s2)
            self.w = np.linalg.solve(K, r)

    @property
    def n(self):
        return len(self.P)

    def _trend(self, xy):
        if self.coef is None:
            return np.full(len(xy), self.const)
        return self.coef[0] + self.coef[1] * xy[:, 0] + self.coef[2] * xy[:, 1]

    def _cov(self, A, B):
        d2 = ((A[:, None, :] - B[None, :, :]) ** 2).sum(-1)
        return self.s2 * np.exp(-d2 / self.a ** 2)

    def __call__(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        out = self._trend(xy)
        if len(self.P):
            for i in range(0, len(xy), 4000):
                out[i:i + 4000] += self._cov(xy[i:i + 4000], self.P[:, :2]) @ self.w
        return out


def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)
