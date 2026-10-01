"""Tabelle grezze -> tabelle ordinate: un esempio realistico per ogni forma «strana» degli archivi."""
import time

import numpy as np
import pandas as pd
import pytest

from stratigrafia3d import tabelle_grezze as tg

N = np.nan


def _grezzo(righe):
    """Come pd.read_excel(..., header=None): colonne 0, 1, 2…, celle vuote NaN."""
    larghezza = max(len(r) for r in righe)
    return pd.DataFrame([list(r) + [N] * (larghezza - len(r)) for r in righe], dtype=object)


def _codici(rapporto):
    return [n["codice"] for n in rapporto]


def _pulita():
    return pd.DataFrame({
        "US": [1001, 1002, 1003, 1004],
        "Tipo": ["strato", "taglio", "riempimento", "strato"],
        "Quota sup": [101.25, 101.10, 100.95, 100.80],
        "Spessore (m)": [0.2, 0.0, 0.35, 0.15],
        "Descrizione": ["terreno argilloso", "fossa circolare", "riempimento sciolto", "livello di crollo"],
        "Note": [N, N, N, N],
    })


# ---------------------------------------------------------------------------------------------- 0. pulita
@pytest.mark.parametrize("df", [
    _pulita(),
    pd.DataFrame({"Context": [1, 2, 3], "Type": ["Cut", "Fill", "Layer"], "Fill of": [N, 1, N],
                  "Description": ["Pit cut", "Pit fill", "Topsoil"]}),
    pd.DataFrame({"Fase": ["I", "II", "III"], "Titolo": ["Età del Ferro", "Romana", "Medievale"],
                  "Da (anno)": [-800, -100, 600], "A (anno)": [-100, 400, 1400]}),
    pd.DataFrame({"US": [1, 2, 3], "Classe": ["ceramica", "ceramica", "vetro"], "NR": [12, 3, 1]}),
    pd.DataFrame({"US": [1001, 1002], "Rapporto": ["copre", "taglia"], "US correlata": [1002, 1003]}),
    pd.DataFrame({"US": ["1001", "1002", "1003"], "Quota": ["10.5", "10.4", "10.3"]}),
    pd.DataFrame({"Sito": ["A", "A", "B", "B"], "US": [1, 2, 1, 2], "Descrizione": ["x", "y", "z", "w"]}),
    # materiali con «n.d.»: tre colonne, US ripetute, ma non è una tabella campo/valore
    pd.DataFrame({"US": [1, 1, 2, 2, 3, 3], "Classe": ["ceramica", "vetro"] * 3, "Peso": [12.5, "n.d.", 3, 4, "n.d.", 7]}),
    # l'ultima fase ha solo il titolo: non è una nota in fondo
    pd.DataFrame({"Fase": ["I", "II", N], "Titolo": ["Età del Ferro", "Romana", "Medievale"], "Da": [-800, -100, N]}),
    pd.DataFrame({"US": [1001, 1002, "1003a"], "Quota (m)": [10.2, 10.1, N], "Descrizione": ["a", "b", N]}),
])
def test_tabella_pulita_resta_identica(df):
    copia = df.copy()
    out, rapporto = tg.normalizza_tabella(df, "US")
    assert rapporto == []
    assert out is df
    pd.testing.assert_frame_equal(out, copia)


def test_pulita_letta_senza_intestazione():
    """La stessa tabella letta con header=None: si prende la prima riga come intestazione."""
    df = _pulita().drop(columns="Note")
    righe = [list(df.columns)] + df.values.tolist()
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert rapporto == []
    pd.testing.assert_frame_equal(out, df, check_dtype=False)


# ---------------------------------------------------------------------------------------------- 1. intestazione
def test_intestazione_sotto_titoli_e_logo():
    righe = [
        ["SOPRINTENDENZA ARCHEOLOGIA - Scavo di Roveto 2024"],
        [N],
        ["Elenco delle unità stratigrafiche", N, N, N, "Compilato da: M.R."],
        [N],
        ["US", "Tipo", "Quota sup", "Descrizione", "Fase"],
        [1001, "strato", 101.2, "humus", "IV"],
        [1002, "taglio", 101.0, "fossa", "III"],
        [1003, "riempimento", 100.8, "riempimento della fossa", "III"],
    ]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe), "Schede")
    assert list(out.columns) == ["US", "Tipo", "Quota sup", "Descrizione", "Fase"]
    assert out["US"].tolist() == [1001, 1002, 1003]
    assert pd.api.types.is_numeric_dtype(out["Quota sup"])
    assert "intestazione" in _codici(rapporto)
    assert any("riga 5" in n["messaggio"] for n in rapporto)


def test_intestazione_sotto_titolo_letta_con_header0():
    """pd.read_excel normale: il titolo diventa il nome della prima colonna, le altre «Unnamed: n»."""
    df = pd.DataFrame({"Context register - Site ABC": ["Context", 1, 2, 3],
                       "Unnamed: 1": ["Type", "Cut", "Fill", "Layer"],
                       "Unnamed: 2": ["Description", "Pit", "Pit fill", "Topsoil"]})
    out, rapporto = tg.normalizza_tabella(df)
    assert list(out.columns) == ["Context", "Type", "Description"]
    assert out["Context"].tolist() == [1, 2, 3]
    assert "intestazione" in _codici(rapporto)


# ---------------------------------------------------------------------------------------------- 2. più righe
def test_intestazione_su_due_righe_con_celle_unite():
    righe = [
        ["US", "Quote", N, "Spessore", "Descrizione"],
        [N, "sup", "inf", "(m)", N],
        [1001, 101.2, 100.9, 0.3, "humus"],
        [1002, 100.9, 100.5, 0.4, "crollo"],
        [1003, 100.5, 100.1, 0.4, "pavimento"],
    ]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["US", "Quote sup", "Quote inf", "Spessore (m)", "Descrizione"]
    assert out["Quote inf"].tolist() == [100.9, 100.5, 100.1]
    assert "intestazione_multipla" in _codici(rapporto)


def test_intestazione_inglese_su_due_righe():
    righe = [
        ["Context", "Levels", N, N, "Interpretation"],
        [N, "top", "base", "max", N],
        [1, 10.5, 10.1, 10.6, "topsoil"],
        [2, 10.1, 9.8, 10.2, "subsoil"],
    ]
    out, _ = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["Context", "Levels top", "Levels base", "Levels max", "Interpretation"]


# ---------------------------------------------------------------------------------------------- 3. righe da togliere
def test_righe_vuote_intestazioni_ripetute_totali():
    intest = ["US", "Classe", "NR", "Peso (g)"]
    righe = [intest,
             [1001, "ceramica", 12, 340.5], [1001, "vetro", 2, 12.0], [N, N, N, N],
             [1002, "ceramica", 5, 80.0],
             [N],
             intest,                                # salto pagina dell'esportazione
             [1003, "ossa", 7, 55.0],
             ["Totale", N, 26, 487.5],
             ["Compilato da M. Rossi il 12/06/2024"]]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe), "Materiali")
    assert out["US"].tolist() == [1001, 1001, 1002, 1003]
    assert out["NR"].tolist() == [12, 2, 5, 7]
    assert pd.api.types.is_numeric_dtype(out["NR"])
    c = _codici(rapporto)
    assert {"righe_vuote", "intestazioni_ripetute", "totali", "piede"} <= set(c)


def test_colonne_vuote_e_nomi_sporchi():
    df = pd.DataFrame({" US ": [1, 2, 3], "Unnamed: 1": [N, N, N], "Quota\nsup": [10.1, 10.2, 10.3],
                       "Unnamed: 3": ["a", "b", "c"]})
    out, rapporto = tg.normalizza_tabella(df)
    assert list(out.columns) == ["US", "Quota sup", "Colonna 4"]
    assert {"colonne_vuote", "nomi_colonne"} <= set(_codici(rapporto))
    assert out["Quota sup"].dtype == float


def test_totale_in_inglese_e_tedesco():
    for parola in ("Total", "Gesamt", "TOT."):
        righe = [["Context", "Count"], [1, 3], [2, 4], [parola, 7]]
        out, rapporto = tg.normalizza_tabella(_grezzo(righe))
        assert out["Context"].tolist() == [1, 2], parola
        assert "totali" in _codici(rapporto)


# ---------------------------------------------------------------------------------------------- 4. trasposte, campo/valore
def test_scheda_trasposta():
    righe = [
        ["Scheda US - Saggio 2"],
        ["US", 1001, 1002, 1003],
        ["Tipo", "strato", "taglio", "riempimento"],
        ["Quota sup", "101,20", "101,00", "100,80"],
        ["Descrizione", "humus", "fossa", "riempimento della fossa"],
        ["Copre", "1002", N, N],
    ]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["US", "Tipo", "Quota sup", "Descrizione", "Copre"]
    assert out["US"].tolist() == [1001, 1002, 1003]
    assert out["Quota sup"].tolist() == pytest.approx([101.2, 101.0, 100.8])
    assert "trasposta" in _codici(rapporto) and "virgola" in _codici(rapporto)


def test_scheda_trasposta_inglese_con_nomi_di_colonna():
    df = pd.DataFrame({"Context": ["Type", "Description", "Fill of"], 1: ["Cut", "Pit", N], 2: ["Fill", "Fill", 1]})
    out, rapporto = tg.normalizza_tabella(df)
    assert list(out.columns) == ["Context", "Type", "Description", "Fill of"]
    assert out["Context"].tolist() == [1, 2]
    assert out["Fill of"].tolist()[1] == 1


def test_campo_valore_in_tre_colonne():
    righe = [["US", "Campo", "Valore"]]
    for us, tipo, q, d in [(1001, "strato", 101.2, "humus"), (1002, "taglio", 101.0, "fossa"),
                           (1003, "riempimento", 100.8, "terra scura")]:
        righe += [[us, "Tipo", tipo], [us, "Quota sup", q], [us, "Descrizione", d]]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["US", "Tipo", "Quota sup", "Descrizione"]
    assert out["US"].tolist() == [1001, 1002, 1003]
    assert out["Tipo"].tolist() == ["strato", "taglio", "riempimento"]
    assert "campo_valore" in _codici(rapporto)


def test_campo_valore_inglese_con_sito_costante():
    df = pd.DataFrame({"Site": ["ABC"] * 6, "Context": [1, 1, 2, 2, 3, 3],
                       "Field": ["Type", "Depth", "Type", "Depth", "Type", "Depth"],
                       "Value": ["Cut", 0.4, "Fill", 0.3, "Layer", 0.1]})
    out, rapporto = tg.normalizza_tabella(df)
    assert list(out.columns) == ["Context", "Site", "Type", "Depth"]
    assert out["Depth"].tolist() == pytest.approx([0.4, 0.3, 0.1])


def test_schede_in_blocchi_etichetta_valore():
    righe = [["Esportazione schede US"], [N]]
    for us, tipo, d in [(1001, "strato", "humus"), (1002, "taglio", "fossa"), (1003, "riempimento", "terra")]:
        righe += [["US:", us], ["Tipo:", tipo], ["Descrizione:", d], ["Fase:", "II"], [N, N]]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["US", "Tipo", "Descrizione", "Fase"]
    assert out["US"].tolist() == [1001, 1002, 1003]
    assert "scheda_blocchi" in _codici(rapporto)


def test_schede_in_blocchi_su_due_coppie_di_colonne():
    righe = []
    for us, tipo, q, d in [(1, "Cut", 10.2, "Pit"), (2, "Fill", 10.1, "Dark fill"), (3, "Layer", 10.4, "Topsoil")]:
        righe += [["Context", us, "Type", tipo], ["Level", q, "Description", d]]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["Context", "Type", "Level", "Description"]
    assert out["Level"].tolist() == [10.2, 10.1, 10.4]


# ---------------------------------------------------------------------------------------------- 5. matrice
def test_matrice_dei_rapporti():
    righe = [
        ["Matrice US", N, N, N, N],
        [N, 1001, 1002, 1003, 1004],
        [1001, N, ">", ">", N],
        [1002, "<", N, "x", N],
        [1003, "<", N, N, "="],
        [1004, N, N, "=", N],
    ]
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert list(out.columns) == ["US", "Rapporto", "US correlata"]
    terne = set(map(tuple, out.values.tolist()))
    assert terne == {(1001, "copre", 1002), (1001, "copre", 1003), (1002, "copre", 1003),
                     (1003, "uguale a", 1004)}
    c = _codici(rapporto)
    assert "matrice" in c and "matrice_segni" in c


def test_matrice_con_parole_inglesi():
    righe = [["Context", "1", "2", "3"], ["1", N, "cuts", "covers"], ["2", N, N, "fills"], ["3", N, N, N]]
    out, _ = tg.normalizza_tabella(_grezzo(righe))
    assert set(map(tuple, out.values.tolist())) == {(1, "taglia", 2), (1, "copre", 3), (2, "riempie", 3)}


def test_conteggi_per_fase_non_sono_una_matrice():
    df = pd.DataFrame({"US": [1, 2, 3], 1: [5, 0, 2], 2: [3, 4, 0], 3: [0, 1, 7]})
    out, rapporto = tg.normalizza_tabella(df)
    assert rapporto == [] and out is df


# ---------------------------------------------------------------------------------------------- 6. rapporti nel testo
@pytest.mark.parametrize("testo,atteso", [
    ("copre 12, 13; taglia 4", [("copre", 12), ("copre", 13), ("taglia", 4)]),
    ("fills 1005", [("riempie", 1005)]),
    ("= 22", [("uguale a", 22)]),
    ("under 3/4/5", [("coperto da", 3), ("coperto da", 4), ("coperto da", 5)]),
    ("copre 1001-1004", [("copre", 1001), ("copre", 1002), ("copre", 1003), ("copre", 1004)]),
    ("taglia 1010-12", [("taglia", 1010), ("taglia", 1011), ("taglia", 1012)]),
    ("Cut by 7 and 8. Same as 9", [("tagliato da", 7), ("tagliato da", 8), ("uguale a", 9)]),
    ("couvre 3 et 4 ; coupé par 9", [("copre", 3), ("copre", 4), ("tagliato da", 9)]),
    ("schneidet 5, verfüllt von 6", [("taglia", 5), ("riempito da", 6)]),
    ("cubre 2 y 3, cortado por 7", [("copre", 2), ("copre", 3), ("tagliato da", 7)]),
    ("> 4, < 6", [("copre", 4), ("coperto da", 6)]),
    ("si appoggia a US 1005a", [("si appoggia a", 1005)]),
    ("[['Copre', '1002', '1', 'Sito'], ['Taglia', '1003', '1', 'Sito']]", [("copre", 1002), ("taglia", 1003)]),
    ("", []),
])
def test_rapporti_da_testo(testo, atteso):
    assert tg.rapporti_da_testo(testo) == atteso


def test_rapporti_da_testo_estende_quello_di_importa():
    from stratigrafia3d import importa
    for t in ["copre 1002, 1003; taglia 1005", "covers 3, cut by 4", "uguale a 7", "gli si appoggia 9"]:
        assert tg.rapporti_da_testo(t) == importa._rapporti_da_testo(t)


# ---------------------------------------------------------------------------------------------- 7. identificativi
def test_separa_identificativo():
    s = pd.Series(["US 1005", "1005a", "SU-12", "Ctx 3", "A/1005", 1005, 1006.0, "1005-1006", "n.d.", None,
                   "US 15 bis"])
    out = tg.separa_identificativo(s)
    assert out["numero"].tolist()[:7] == [1005, 1005, 12, 3, 1005, 1005, 1006]
    assert out["prefisso"].tolist()[:5] == ["US", None, "SU", "Ctx", "A"]
    assert out["suffisso"].tolist()[1] == "a" and out["suffisso"].tolist()[10] == "bis"
    assert out["ambiguo"].tolist() == [False, False, False, False, False, False, False, True, True, False, False]
    assert out["numero"].dtype == "Int64" and pd.isna(out["numero"].iloc[9])


def test_sito_e_numero_in_due_colonne():
    df = pd.DataFrame({"Saggio": ["A", "A", "B", "B"], "US": [1, 2, 1, 2]})
    assert tg.trova_sito_numero(df) == ("Saggio", "US")
    assert tg.identificativo_composto(df, "Saggio", "US").tolist() == ["A-1", "A-2", "B-1", "B-2"]
    assert tg.trova_sito_numero(pd.DataFrame({"Saggio": ["A", "B"], "US": [1, 2]})) is None


# ---------------------------------------------------------------------------------------------- 8. misure
def test_misure_nelle_intestazioni_e_nei_valori():
    df = pd.DataFrame({"US": [1, 2, 3, 4],
                       "Prof. (cm)": [45, 30, 12.5, N],
                       "Spessore": ["0,45 m", "45cm", "1.2m", "120 mm"],
                       "Quota (m s.l.m.)": ["101,25", "1.101,10", "100,95", "-"],
                       "Peso (g)": ["1.234,5", "12,5", "3", "0,5"],
                       "Descrizione": ["a", "b", "c", "d"]})
    out, rapporto = tg.normalizza_tabella(df)
    assert "Prof. (m)" in out.columns and "Prof. (cm)" not in out.columns
    assert out["Prof. (m)"].tolist()[:3] == pytest.approx([0.45, 0.30, 0.125])
    assert out["Spessore"].tolist() == pytest.approx([0.45, 0.45, 1.2, 0.12])
    assert out["Quota (m s.l.m.)"].tolist()[:3] == pytest.approx([101.25, 1101.10, 100.95])
    assert np.isnan(out["Quota (m s.l.m.)"].iloc[3])
    assert out["Peso (g)"].tolist() == pytest.approx([1234.5, 12.5, 3.0, 0.5])
    assert out["Descrizione"].tolist() == ["a", "b", "c", "d"]
    c = _codici(rapporto)
    assert c.count("misura_intestazione") == 1 and "misura_valori" in c and c.count("virgola") == 2


def test_numero_con_unita_e_separatori():
    assert tg.numero_con_unita("0,45 m") == (0.45, "m")
    assert tg.numero_con_unita("45cm") == (45.0, "cm")
    assert tg.numero_con_unita("1,234.5") == (1234.5, None)
    assert tg.numero_con_unita("1 234,5") == (1234.5, None)
    assert tg.numero_con_unita("12.05.2024") == (None, None)
    assert tg.numero_con_unita("strato") == (None, None)


def test_colonne_di_rapporti_non_diventano_numeri():
    df = pd.DataFrame({"US": [1, 2, 3], "Copre": ["2,3", "3", N], "Data": ["12,5", "1,2", "3,4"]})
    out, rapporto = tg.normalizza_tabella(df)
    assert rapporto == [] and out is df


# ---------------------------------------------------------------------------------------------- 9. più tabelle
def _foglio_impilato():
    return _grezzo([
        ["Schede US"],
        ["US", "Tipo", "Quota"],
        [1001, "strato", 10.2], [1002, "taglio", 10.0], [1003, "riempimento", 9.8], [1004, "strato", 9.7],
        [N], [N],
        ["Materiali"],
        ["US", "Classe", "NR"],
        [1001, "ceramica", 12], [1003, "vetro", 1],
        [N],
        ["Context", "Sample", "Litres"],
        [1, "S1", 10], [2, "S2", 20],
    ])


def test_dividi_tabelle():
    parti = tg.dividi_tabelle(_foglio_impilato())
    assert list(parti) == ["Schede US", "Materiali", "Tabella 3"]
    fogli = tg.normalizza_foglio(_foglio_impilato(), "Foglio1")
    assert list(fogli) == ["Foglio1 · Schede US", "Foglio1 · Materiali", "Foglio1 · Tabella 3"]
    us, _ = fogli["Foglio1 · Schede US"]
    assert list(us.columns) == ["US", "Tipo", "Quota"] and us["US"].tolist() == [1001, 1002, 1003, 1004]
    mat, _ = fogli["Foglio1 · Materiali"]
    assert mat["NR"].tolist() == [12, 1]
    camp, _ = fogli["Foglio1 · Tabella 3"]
    assert list(camp.columns) == ["Context", "Sample", "Litres"]


def test_normalizza_tabella_su_foglio_impilato_tiene_la_piu_grande():
    out, rapporto = tg.normalizza_tabella(_foglio_impilato())
    assert out["US"].tolist() == [1001, 1002, 1003, 1004]
    assert any(n["codice"] == "tabelle_multiple" and "«Schede US»" in n["messaggio"] for n in rapporto)


def test_riga_vuota_nei_dati_non_divide_la_tabella():
    righe = [["US", "Descrizione"], [1, "humus"], [N, N], [2, "crollo"], [3, "pavimento"]]
    assert len(tg.dividi_tabelle(_grezzo(righe))) == 1
    out, rapporto = tg.normalizza_tabella(_grezzo(righe))
    assert out["US"].tolist() == [1, 2, 3] and _codici(rapporto) == ["righe_vuote"]


def test_foglio_di_solo_testo_con_riga_vuota_non_si_divide():
    righe = [["Fase", "Descrizione"], ["I", "abbandono"], [N, N], ["Periodo", "Descrizione breve"], ["II", "uso"]]
    assert len(tg.dividi_tabelle(_grezzo(righe))) == 1


# ---------------------------------------------------------------------------------------------- 10. colonne larghe
def test_scomponi_colonne_per_materiale():
    df = pd.DataFrame({"US": [1001, 1002], "Ceramica": [12, 0], "Vetro": [1, N], "Ossa": [4, 7],
                       "Note": ["x", "y"]})
    assert tg.colonne_larghe(df) == ["Ceramica", "Vetro", "Ossa"]
    lungo = tg.scomponi_colonne(df, "US")
    assert lungo[["US", "Classe", "NR"]].values.tolist() == [[1001, "Ceramica", 12], [1001, "Vetro", 1],
                                                            [1001, "Ossa", 4], [1002, "Ossa", 7]]
    assert lungo["Note"].tolist() == ["x", "x", "x", "y"]
    df_en = pd.DataFrame({"Context": [1, 2], "Pottery": [3, 1], "Animal bone": [2, 2]})
    assert tg.colonne_larghe(df_en) == ["Pottery", "Animal bone"]
    # la tabella larga è pulita: normalizza_tabella non la scompone da sola
    out, rapporto = tg.normalizza_tabella(df)
    assert out is df and rapporto == []


# ---------------------------------------------------------------------------------------------- generali
def test_messaggi_italiani_con_segnaposto():
    for codice, testo in tg.MESSAGGI.items():
        assert testo[0].isupper() or testo[0] == "{", codice
    _, rapporto = tg.normalizza_tabella(_foglio_impilato())
    assert all(set(n) == {"codice", "messaggio"} for n in rapporto)


def test_veloce_su_10000_righe():
    n = 10000
    df = pd.DataFrame({"US": np.arange(n), "Tipo": ["strato", "taglio"] * (n // 2),
                       "Quota": np.linspace(100, 90, n), "Descrizione": ["testo"] * n,
                       "Spessore": ["0,25"] * n})
    righe = [["Titolo"], [N]] + [list(df.columns)] + df.values.tolist() + [["Totale", N, N, N, N]]
    grezzo = _grezzo(righe)
    t = time.perf_counter()
    out, rapporto = tg.normalizza_tabella(grezzo)
    t1 = time.perf_counter() - t
    assert len(out) == n and out["Spessore"].iloc[0] == pytest.approx(0.25)
    t = time.perf_counter()
    pulita, r2 = tg.normalizza_tabella(df.assign(Spessore=0.25))
    t2 = time.perf_counter() - t
    assert r2 == []
    assert t1 < 1.0 and t2 < 1.0, (t1, t2)


def test_lettura_reale_da_excel(tmp_path):
    """Giro completo da un file Excel con titolo, intestazione su due righe e totale."""
    pytest.importorskip("openpyxl")
    righe = [["Scavo di Roveto - schede US"], [N], ["US", "Quote", N, "Descrizione"], [N, "sup", "inf", N],
             [1001, 101.2, 100.9, "humus"], [1002, 100.9, 100.5, "crollo"], ["Totale", N, N, N]]
    p = tmp_path / "schede.xlsx"
    _grezzo(righe).to_excel(p, header=False, index=False)
    out, rapporto = tg.normalizza_tabella(pd.read_excel(p, header=None), "Foglio1")
    assert list(out.columns) == ["US", "Quote sup", "Quote inf", "Descrizione"]
    assert out["US"].tolist() == [1001, 1002]
    out0, _ = tg.normalizza_tabella(pd.read_excel(p), "Foglio1")       # anche con header=0
    assert list(out0.columns) == ["US", "Quote sup", "Quote inf", "Descrizione"]


def test_campo_valore_riconosciuto_dai_valori():
    """Nomi di colonna sconosciuti: si riconosce dai tipi (ogni campo ha valori dello stesso tipo)."""
    righe = []
    for us, tipo, q in [(1, "strato", 10.2), (2, "taglio", 10.0), (3, "strato", 9.9)]:
        righe += [[us, "Tipo", tipo], [us, "Quota", q]]
    df = pd.DataFrame(righe, columns=["US", "Voce scheda", "Contenuto scheda"])
    out, rapporto = tg.normalizza_tabella(df)
    assert list(out.columns) == ["US", "Tipo", "Quota"] and out["Quota"].tolist() == [10.2, 10.0, 9.9]


def test_riga_totale_senza_numeri():
    """Riga «TOTALE» con le formule non calcolate (celle vuote)."""
    df = pd.DataFrame({"US/USM": [1101, 1102, "TOTALE"], "Tipo": ["US", "USM", N], "NR totale": [3, 4, N]})
    out, rapporto = tg.normalizza_tabella(df)
    assert out["US/USM"].tolist() == [1101, 1102] and _codici(rapporto) == ["totali"]
