import pandas as pd
from stratigrafia3d import stratigrafia as st


def _rap(righe):
    return st.da_tabella(pd.DataFrame(righe, columns=["US", "Rapporto", "US correlata"]))


def test_forme_inverse():
    r = _rap([(2, "coperto da", 1), (3, "tagliato da", 2)])
    assert r.grafo.has_edge(1, 2) and r.grafo.has_edge(2, 3)


def test_ciclo_segnalato():
    r = _rap([(1, "copre", 2), (2, "copre", 3), (3, "copre", 1)])
    assert any(p.codice == "ciclo" for p in st.controlla(r))


def test_contraddizione_contemporanei():
    r = _rap([(1, "copre", 2), (1, "si lega a", 2)])
    assert any(p.codice == "contraddizione" for p in st.controlla(r))


def test_livelli_e_profondita():
    r = _rap([(1, "copre", 2), (2, "copre", 3), (1, "taglia", 3), (4, "si lega a", 3)])
    lv = st.livelli_dal_basso(r)
    assert lv[3] == 0 and lv[2] == 1 and lv[1] == 2 and lv[4] == lv[3]
    pr = st.profondita_dall_alto(r)
    assert pr[1] == 0 and pr[3] == 2


def test_harris_riduzione_transitiva():
    r = _rap([(1, "copre", 2), (2, "copre", 3), (1, "copre", 3)])
    h = st.harris(r)
    assert sorted(map(tuple, h["edges"])) == [(1, 2), (2, 3)]


def test_harris_per_gruppi_e_dedotti():
    # due buche con i loro riempimenti, più un'unità senza rapporti
    r = _rap([(11, "riempie", 10), (12, "riempie", 10), (21, "riempie", 20)])
    r.grafo.add_node(99)
    h = st.harris(r, dedotti=[(12, 11)])
    g = {n["id"]: n["g"] for n in h["nodes"]}
    assert g[10] == g[11] == g[12] != g[20] == g[21] != g[99]
    assert h["dedotti"] == [[12, 11]] and [12, 11] in h["edges"] and [12, 10] not in h["edges"]
    # ogni gruppo sta nel suo rettangolo e i rettangoli non si sovrappongono
    for n in h["nodes"]:
        G = h["gruppi"][n["g"]]
        assert G["r"] <= n["r"] < G["r"] + G["rows"] and G["c"] <= n["c"] < G["c"] + G["cols"]
    # un dedotto che creerebbe un ciclo viene ignorato
    assert st.harris(r, dedotti=[(10, 11)])["dedotti"] == []
