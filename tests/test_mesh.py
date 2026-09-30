import numpy as np
from shapely.geometry import box
from stratigrafia3d.mesh import triangola, mesh_chiusa, volume_prismi


def _poligono():
    return box(0, 0, 4, 3).difference(box(1, 1, 2, 2))


def test_triangoli_antiorari():
    V, F = triangola(_poligono(), passo=0.2, area_max=0.05)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    assert (cr > 0).all()


def test_mesh_chiusa_e_stagna():
    V, F = triangola(_poligono(), passo=0.2, area_max=0.05)
    P, Fa = mesh_chiusa(V, F, np.full(len(V), 1.0), np.full(len(V), 0.5))
    # ogni spigolo orientato compare una sola volta e il suo opposto esiste: superficie chiusa e coerente
    # (i vertici delle pareti sono duplicati, quindi si confrontano le coordinate)
    key = lambda i: tuple(np.round(P[i], 6))
    diretti = {}
    for f in Fa:
        for i, j in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            e = (key(i), key(j))
            diretti[e] = diretti.get(e, 0) + 1
    assert all(n == 1 for n in diretti.values())
    assert all((b, a) in diretti for a, b in diretti)


def test_volume_prismi():
    g = _poligono()
    V, F = triangola(g, passo=0.2, area_max=0.05)
    vol = volume_prismi(V, F, np.full(len(V), 1.0), np.full(len(V), 0.5))
    assert abs(vol - g.area * 0.5) < 1e-6


def test_triangolazione_scipy_equivalente():
    """La triangolazione di riserva (senza la libreria triangle) copre il poligono e rispetta i buchi."""
    g = _poligono()
    V, F = triangola(g, passo=0.1, area_max=0.02, metodo="scipy")
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    assert (cr > 0).all()
    assert abs(cr.sum() / 2 - g.area) / g.area < 0.002
    P, Fa = mesh_chiusa(V, F, np.full(len(V), 1.0), np.full(len(V), 0.5))
    key = lambda i: tuple(np.round(P[i], 6))
    d = {}
    for f in Fa:
        for i, j in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            d[(key(i), key(j))] = d.get((key(i), key(j)), 0) + 1
    assert all(n == 1 for n in d.values()) and all((b_, a_) in d for a_, b_ in d)
