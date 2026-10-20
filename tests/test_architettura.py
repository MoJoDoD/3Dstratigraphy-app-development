"""Fasi costruttive dei muri e cronologia dello scavo dalle date dei rilievi (architettura.py)."""
import pandas as pd

from stratigrafia3d import architettura as ar
from stratigrafia3d import stratigrafia as st


def _rap(righe):
    return st.da_tabella(pd.DataFrame(righe, columns=["US", "Rapporto", "US correlata"]))


def test_date_dal_testo():
    assert ar.date_dal_testo("2025-09-30, 2025-09-24;2025-9-24") == ["2025-09-24", "2025-09-30"]
    assert ar.date_dal_testo(None) == [] and ar.date_dal_testo(float("nan")) == []
    assert ar.date_dal_testo("2025-13-01 2025-02-40") == []
    assert ar.data_iso((2025, 9, 4)) == "2025-09-04"


def test_fasi_murarie():
    # 2001 e 2002 legati (un cantiere); 2003 si appoggia a 2001; 2004 copre uno strato che copre 2002;
    # 2005 non ha rapporti con altri muri
    rap = _rap([
        (2001, "si lega a", 2002),
        (2003, "si appoggia a", 2001),
        (2004, "copre", 1001),
        (1001, "copre", 2002),
        (1002, "si appoggia a", 2005),
    ])
    f = ar.fasi_murarie(rap, [2001, 2002, 2003, 2004, 2005])
    assert f[2001]["fase"] == f[2002]["fase"] == 0 and f[2001]["cantiere"] == f[2002]["cantiere"] == 2001
    assert f[2003]["fase"] == 1 and f[2004]["fase"] == 1       # anche attraverso lo strato 1001
    assert f[2005]["rapporti"] == 0
    assert f[2001]["rapporti"] >= 3                             # legato a 2002, sotto a 2003 e 2004
    # rapporti contraddittori tra muri: nessun errore, stessa fase
    ciclo = _rap([(2001, "si appoggia a", 2002), (2002, "si appoggia a", 2001), (2003, "copre", 2001)])
    g = ar.fasi_murarie(ciclo, [2001, 2002, 2003])
    assert g[2001]["fase"] == g[2002]["fase"] == 0 and g[2003]["fase"] == 1
    assert ar.fasi_murarie(ciclo, []) == {}


def test_cronologia_scavo():
    # 1001 copre 1002 copre 1003; 1004 (senza date) copre 1003; 1005 copre il muro 2001, rilevato il 25;
    # 1006 copre 1007, nessuna delle due datata
    rap = _rap([(1001, "copre", 1002), (1002, "copre", 1003), (1004, "copre", 1003), (1002, "si appoggia a", 2001),
                (1005, "copre", 2001), (1006, "copre", 1007)])
    date = {1001: ["2025-09-24"], 1002: ["2025-09-25", "2025-09-27"], 1003: ["2025-09-28"],
            2001: ["2025-09-25"]}
    c = ar.cronologia_scavo(rap, date, murarie=[2001])
    assert c["date"] == ["2025-09-24", "2025-09-25", "2025-09-27", "2025-09-28"]
    u = c["unita"]
    # rilevata due volte: asportata entro l'ultimo rilievo
    assert u[1002] == {"rilievi": [1, 2], "insieme": [], "rimossa": 2, "stimata": False}
    # un solo rilievo: asportata quando compare la prima unità sottostante
    assert u[1001]["rimossa"] == 1 and u[1001]["stimata"]
    assert u[1004]["rilievi"] == [] and u[1004]["rimossa"] == 3 and u[1004]["stimata"]
    # niente di datato sotto: resta in posto; i muri restano sempre
    assert u[1003]["rimossa"] is None and u[2001]["rimossa"] is None
    assert u[1005]["rimossa"] == 1 and u[1005]["stimata"]     # la sommità del muro compare il 25
    assert 1006 not in u and 1007 not in u
    assert ar.cronologia_scavo(rap, {}) is None


def test_cronologia_con_dem_di_piu_unita():
    # 1001 copre 1002; 1002 compare solo in un DEM che avvolge anche 1003 (il 27): 1001 tolta entro il 27;
    # 1002 era ancora esposta il 28 (altro DEM d'insieme): la sua asportazione stimata non viene prima
    rap = _rap([(1001, "copre", 1002), (1002, "copre", 1004)])
    c = ar.cronologia_scavo(rap, {1001: ["2025-09-24"], 1004: ["2025-09-25"]},
                            insieme={1002: ["2025-09-27", "2025-09-28"], 1003: ["2025-09-27"]})
    assert c["date"] == ["2025-09-24", "2025-09-25", "2025-09-27", "2025-09-28"]
    u = c["unita"]
    assert u[1002]["insieme"] == [2, 3] and u[1002]["rilievi"] == []
    assert u[1002]["rimossa"] == 3 and u[1002]["stimata"]
    assert u[1001]["rimossa"] == 1                      # 1004, sotto 1002, compare il 25
    assert ar.cronologia_scavo(rap, {}, insieme={1003: ["2025-09-27"]})["unita"][1003]["rimossa"] is None


def test_date_delle_schede():
    us = pd.DataFrame({"US": [1001, 1002, 1003], ar.C_DATE_RILIEVI: ["2025-09-24", None, "2025-09-25, 2025-09-24"]})
    usm = pd.DataFrame({"USM": [2001], "Altro": ["x"]})
    d = ar.date_delle_schede((us, "US"), (usm, "USM"), (None, "US"))
    assert d == {1001: ["2025-09-24"], 1003: ["2025-09-24", "2025-09-25"]}
