import numpy as np
from stratigrafia3d.interpolazione import Krig


def test_riproduce_un_piano():
    rng = np.random.default_rng(0)
    xy = rng.uniform(0, 10, (20, 2))
    z = 100 + 0.1 * xy[:, 0] - 0.05 * xy[:, 1]
    k = Krig(np.c_[xy, z])
    nuovi = rng.uniform(1, 9, (50, 2))
    atteso = 100 + 0.1 * nuovi[:, 0] - 0.05 * nuovi[:, 1]
    assert np.max(np.abs(k(nuovi) - atteso)) < 2e-3


def test_torna_alla_media_lontano_dai_dati():
    k = Krig(np.array([[0.0, 0.0, 0.5]]), mean=0.2, rng=1.0)
    assert abs(k(np.array([[0.0, 0.0]]))[0] - 0.5) < 0.01
    assert abs(k(np.array([[10.0, 10.0]]))[0] - 0.2) < 1e-6


def test_duplicati_non_rompono_il_sistema():
    P = np.array([[0, 0, 1.0], [0.005, 0, 1.0], [1, 0, 2.0], [0, 1, 3.0]])
    assert Krig(P).n == 3
