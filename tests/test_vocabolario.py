# -*- coding: utf-8 -*-
"""Vocabolario dei termini: riconoscimento di file, layer, tabelle, colonne e valori in più lingue e sistemi."""
import json
import random
import time

import pytest

from stratigrafia3d import vocabolario as V


@pytest.fixture(scope="module")
def voc():
    return V.Vocabolario(file_utente=False)


def primo(voc, nome, ambito, contesto=None):
    r = voc.riconosci(nome, ambito, contesto)
    return r[0] if r else None


# ---------------------------------------------------------------- normalizzazione
@pytest.mark.parametrize("testo, atteso", [
    ("ContextNumber", ["context", "number"]),
    ("Context_Number", ["context", "number"]),
    ("q.sup", ["q", "sup"]),
    ("US_n", ["us", "n"]),
    ("SGData", ["sg", "data"]),
    ("FindsSummaries", ["finds", "summaries"]),
    ("Höhe-OK", ["hohe", "ok"]),
    ("Unità stratigrafica", ["unita", "stratigrafica"]),
    ("Stansted.shp", ["stansted"]),
    ("schede_US_2021_v2_copy.xlsx", ["schede", "us"]),
    ("us_table", ["us"]),
    ("Modello3D", ["modello", "3d"]),
    ("Peso (g)", ["peso", "g"]),
])
def test_normalizza(testo, atteso):
    assert V.normalizza(testo) == atteso


def test_normalizza_valori_tiene_rumore_e_simboli():
    assert V.normalizza("Layer", rumore=False) == ["layer"]
    assert V.normalizza("Layer") == []
    assert V.normalizza("=", rumore=False) == ["="]
    assert V.normalizza(None) == []


# ---------------------------------------------------------------- colonne
@pytest.mark.parametrize("nome", ["Context Number", "US", "N_US", "Numero US", "UE", "Befund", "SU no.", "CONTEXT_ID",
                                  "n. US", "Context No.", "Kontextnummer", "Spoornummer", "Numéro d'US",
                                  "Número de UE", "us_s", "ContextNumber", "cxt_no"])
def test_colonna_numero_us(voc, nome):
    r = primo(voc, nome, "colonna")
    assert r is not None and r.concetto == "us" and r.canonico == "US", (nome, r)
    assert r.punteggio >= 0.8


def test_motivo_spiega_la_lingua(voc):
    r = primo(voc, "Context Number", "colonna")
    assert r.motivo == "«Context Number» è un termine inglese per il numero di US"
    assert r.lingua == "en"
    s = voc.spiega("Context Number", "colonna")
    assert s.startswith("«Context Number» è un termine inglese") and "«US»" in s


@pytest.mark.parametrize("nome, concetto", [
    ("USM", "usm"), ("N. USM", "usm"), ("Mauer", "usm"), ("unità stratigrafica muraria", "usm"),
    ("Fill of", "riempie"), ("Coperto da", "coperto da"), ("cut by", "tagliato da"), ("Copre", "copre"),
    ("Si appoggia a", "si appoggia a"), ("Gli si appoggia", "gli si appoggia"), ("Riempito da", "riempito da"),
    ("Same as", "uguale a"), ("Abuts", "si appoggia a"), ("Überlagert von", "coperto da"),
    ("Q_SUP", "sup"), ("top level", "sup"), ("Höhe OK", "sup"), ("Quota max (m)", "sup"), ("Q.INF", "inf"),
    ("Höhe UK", "inf"), ("Quota min (m)", "inf"), ("bottom level", "inf"),
    ("Quota", "quote"), ("Quota (m)", "quote"), ("Elevation", "quote"), ("m AOD", "quote"), ("Höhe ü. NN", "quote"),
    ("Z NGF", "quote"), ("quota_q", "quote"), ("Cota", "quote"), ("Höjd", "quote"),
    ("Tipo quota", "tipo_quota"), ("Level type", "tipo_quota"),
    ("Context Type", "tipo"), ("unita_tipo", "tipo"), ("Befundart", "tipo"),
    ("Spessore", "spessore"), ("Thickness (cm)", "spessore"), ("Mächtigkeit", "spessore"), ("Épaisseur", "spessore"),
    ("Depth", "profondita"), ("Context Depth (m)", "profondita"), ("profondita_max", "profondita"),
    ("Spessore/profondità max (m)", "profondita"),
    ("Quota base usata (rilevata o stimata)", "fondazione"),
    ("Brief Description", "descrizione"), ("Beschreibung", "descrizione"), ("Descrizione", "descrizione"),
    ("Interpretation", "interpretazione"), ("d_interpretativa", "interpretazione"),
    ("d_stratigrafica", "definizione"), ("Definizione", "definizione"),
    ("Colore Munsell", "munsell"), ("Munsell colour", "munsell"), ("Colore HEX", "colore_hex"),
    ("Colour", "colore"), ("Inclusions", "composizione"), ("Componenti", "composizione"),
    ("Consistency", "consistenza"), ("Margini", "margini"), ("Boundary", "margini"),
    ("Phase", "fase"), ("Fase", "fase"), ("Periodo", "periodo"),
    ("SGDeposit Date", "datazione"), ("Lower Date Value", "datazione_da"), ("Upper Date Value", "datazione_a"),
    ("Da (anno)", "datazione_da"), ("A (anno)", "datazione_a"),
    ("Date Recorded", "data_scavo"), ("Data scavo", "data_scavo"), ("Recorded by", "responsabile"),
    ("SG Number", "gruppo"), ("Intervention", "intervento"), ("Feature Number", "evidenza"),
    ("Sample Number", "campioni"), ("Sample Collected for", "analisi"),
    ("Material", "classe"), ("ObjectCount", "conteggio"), ("NR", "conteggio"), ("NMI", "nmi"), ("MNI", "nmi"),
    ("Weight (g)", "peso"), ("Peso (g)", "peso"), ("Box", "cassetta"), ("Tipo / forma", "forma"),
    ("Filename", "file"), ("Soggetto", "soggetto"), ("Caption", "soggetto"), ("Titolo", "titolo"),
    ("Easting", "coord_x"), ("Northing", "coord_y"), ("Rechtswert", "coord_x"),
    ("Site Code", "sito"), ("SITECODE", "sito"), ("Settore", "area"), ("Saggio", "area"),
    ("SECTION_ID", "sezioni"), ("Sezione", "sezioni"),
    ("EntityHandle", "campi_tecnici"), ("geometry", "geometria"),
])
def test_colonne(voc, nome, concetto):
    r = primo(voc, nome, "colonna")
    assert r is not None and r.concetto == concetto, (nome, voc.riconosci(nome, "colonna"))


def test_colonne_canoniche_del_programma(voc):
    assert primo(voc, "Spessore medio (m)", "colonna").canonico == "Spessore medio stimato (m)"
    assert primo(voc, "Context Depth (m)", "colonna").canonico == "Spessore/profondità max (m)"
    assert primo(voc, "Fill of", "colonna").canonico == "riempie"
    assert primo(voc, "Weight", "colonna").canonico == "Peso (g)"


def test_id_da_solo_e_debole(voc):
    r = primo(voc, "ID", "colonna")
    assert r.concetto == "identificativo" and r.punteggio < 0.6
    assert "indizio debole" in r.motivo
    assert voc.migliore("ID", "colonna") is None


def test_nomi_estranei_non_riconosciuti(voc):
    for nome, ambito in [("Stansted.shp", "file"), ("T5 Volume 2", "layer"), ("T5 Volume 2.shp", "file"),
                         ("Defpoints", "layer"), ("Layer 0", "layer"), ("Sheet1", "tabella"), ("Length", "colonna"),
                         ("Orientation", "colonna"), ("Volume", "colonna"), ("Layer", "colonna")]:
        r = voc.riconosci(nome, ambito)
        assert not r or r[0].punteggio < 0.5, (nome, r)


def test_esclusioni(voc):
    # «Area documentata (m²)» è una misura, non l'area di scavo
    assert all(r.concetto != "area" for r in voc.riconosci("Area documentata (m²)", "colonna"))
    # «unità stratigrafica muraria» non è una US
    assert primo(voc, "unità stratigrafica muraria", "colonna").concetto == "usm"


def test_somiglianze(voc):
    for nome, concetto in [("Contex Numbr", "us"), ("Descrizone", "descrizione"), ("Intepretazione", "interpretazione"),
                           ("Hoehe", "quote")]:
        r = primo(voc, nome, "colonna")
        assert r is not None and r.concetto == concetto, (nome, r)
        assert r.punteggio < 0.9 and "somiglia" in r.motivo


# ---------------------------------------------------------------- tabelle, layer, file
@pytest.mark.parametrize("nome, concetto, canonico", [
    ("us_table", "us", "US"),
    ("ContextData", "us", "US"),
    ("Contexts", "us", "US"),
    ("Schede US", "us", "US"),
    ("Befundliste", "us", "US"),
    ("FindsSummaries", "materiali", "Materiali"),
    ("inventario_materiali_table", "materiali", "Materiali"),
    ("Fundliste", "materiali", "Materiali"),
    ("RegisteredSamples", "campioni", "Campioni"),
    ("campioni_table", "campioni", "Campioni"),
    ("ContextsPhotos", "documentazione", "Documentazione"),
    ("Photographs", "documentazione", "Documentazione"),
    ("Elenco foto", "documentazione", "Documentazione"),
    ("periodizzazione_table", "fase", "Fasi"),
    ("Phases", "fase", "Fasi"),
    ("Rapporti", "rapporti", "Rapporti"),
    ("Relations", "rapporti", "Rapporti"),
    ("Reperti_speciali", "reperti", "Reperti_speciali"),
    ("Quote", "quote", "Quote"),
])
def test_tabelle(voc, nome, concetto, canonico):
    r = primo(voc, nome, "tabella")
    assert r is not None and r.concetto == concetto and r.canonico == canonico, (nome, r)


def test_tabelle_gruppi_e_datazioni(voc):
    assert primo(voc, "SGData", "tabella").concetto == "gruppo"
    r = primo(voc, "PermittedDating", "tabella")
    assert r.concetto in ("datazione", "fase") and r.canonico == "Fasi"
    assert primo(voc, "layer_styles", "tabella").concetto == "tabelle_sistema"


@pytest.mark.parametrize("nome, ruolo", [
    ("pyunitastratigrafiche", "us"),
    ("pyunitastratigrafiche_usm", "usm"),
    ("pyarchinit_quote", "quote"),
    ("pyarchinit_sezioni", "sezioni"),
    ("pyarchinit_campionature", "campioni"),
    ("us_poligoni", "us"), ("usm_poligoni", "usm"), ("quote", "quote"), ("profili_us", "profili"),
    ("area_scavo", "area"), ("sezioni_disegno", "sezioni_disegno"), ("reperti_speciali", "reperti"),
    ("linee_fondo", "fondi"), ("griglia_2m", "ignora"), ("hachures", "ignora"),
    ("Spot Heights", "quote"), ("Levels", "quote"), ("Höhenpunkte", "quote"),
    ("Excavation limit", "area"), ("Grabungsgrenze", "area"), ("Trenches", "area"), ("werkput", "area"),
    ("sectionlines", "sezioni"), ("Small finds", "reperti"), ("Samples", "campioni"),
    ("Base of slope", "fondi"), ("Befunde", "us"), ("sporen", "us"), ("Mauern", "usm"),
])
def test_layer(voc, nome, ruolo):
    r = primo(voc, nome, "layer")
    assert r is not None and r.canonico == ruolo, (nome, r)


def test_file(voc):
    assert primo(voc, r"C:\scavi\ortofoto_2019.tif", "file").canonico == "ortofoto"
    assert primo(voc, "/dati/DTM_1m.tif", "file").canonico == "dem"
    assert primo(voc, "schede_US_2021_v2_def.xlsx", "file").concetto == "us"
    assert primo(voc, "fotogrammetria_saggio.obj", "file").concetto in ("modello_3d", "area")


# ---------------------------------------------------------------- contesto
def test_contesto_quota_in_layer_di_punti(voc):
    senza = primo(voc, "Z", "colonna")
    con = primo(voc, "Z", "colonna", {"layer": "spot heights", "geometria": "punto"})
    assert senza.concetto == con.concetto == "quote"
    assert con.punteggio > senza.punteggio
    assert "contesto" in con.motivo and "geometria" in con.motivo


def test_contesto_scioglie_ambiguita(voc):
    # «Type» nei materiali è la forma del reperto, nelle schede è il tipo di unità
    assert primo(voc, "Type", "colonna", {"tabella": "FindsSummaries"}).concetto == "forma"
    assert primo(voc, "Type", "colonna", {"tabella": "ContextData"}).concetto == "tipo"
    # anche le colonne vicine aiutano
    assert primo(voc, "Type", "colonna", ["Context Number", "Fill of", "Interpretation"]).concetto == "tipo"
    assert primo(voc, "Type", "colonna", "FindsSummaries").concetto == "forma"


def test_contesto_geometria_sbagliata_penalizza(voc):
    giusta = primo(voc, "Spot heights", "layer", {"geometria": "punto"})
    sbagliata = primo(voc, "Spot heights", "layer", {"geometria": "poligono"})
    assert giusta.punteggio > sbagliata.punteggio


# ---------------------------------------------------------------- valori
@pytest.mark.parametrize("valore, campo, atteso", [
    ("Cut", "tipo", "negativa"), ("cut feature", "tipo", "negativa"), ("Taglio", "tipo", "negativa"),
    ("negativa", "tipo", "negativa"), ("Interfaccia di distruzione", "tipo", "negativa"), ("N", "tipo", "negativa"),
    ("Creusement", "tipo", "negativa"), ("Nedgrävning", "tipo", "negativa"),
    ("Deposit", "tipo", "positiva"), ("Layer", "tipo", "positiva"), ("Fill", "tipo", "positiva"),
    ("Masonry", "tipo", "positiva"), ("Strato", "tipo", "positiva"), ("Verfüllung", "tipo", "positiva"),
    ("Skeleton", "tipo", "positiva"), ("P", "tipo", "positiva"),
    ("fills", "rapporto", "riempie"), ("Fill of", "rapporto", "riempie"), ("is cut by", "rapporto", "tagliato da"),
    ("cuts", "rapporto", "taglia"), ("=", "rapporto", "uguale a"), ("same as", "rapporto", "uguale a"),
    (">", "rapporto", "copre"), ("<", "rapporto", "coperto da"), ("above", "rapporto", "copre"),
    ("below", "rapporto", "coperto da"), ("Covers", "rapporto", "copre"), ("Sealed by", "rapporto", "coperto da"),
    ("Abutted by", "rapporto", "gli si appoggia"), ("Bonded with", "rapporto", "si lega a"),
    ("Filled by", "rapporto", "riempito da"), ("Copre", "rapporto", "copre"),
    ("Si appoggia a", "rapporto", "si appoggia a"), ("Gli si appoggia", "rapporto", "gli si appoggia"),
    ("wird überlagert von", "rapporto", "coperto da"), ("recouvre", "rapporto", "copre"),
    ("coupé par", "rapporto", "tagliato da"), ("rellena", "rapporto", "riempie"),
    ("skärs av", "rapporto", "tagliato da"),
    ("gelijk aan", "rapporto", "uguale a"),
    ("top", "tipo_quota", "sup"), ("Superficie", "tipo_quota", "sup"), ("I", "tipo_quota", "inf"),
    ("bottom", "tipo_quota", "inf"), ("Fondo taglio", "tipo_quota", "taglio"), ("Rim", "tipo_quota", "orlo"),
    ("Cresta", "tipo_quota", "rasatura"), ("Foundation", "tipo_quota", "fondazione"), ("q.sup", "tipo_quota", "sup"),
    ("Oberkante", "tipo quota", "sup"),
])
def test_valori(voc, valore, campo, atteso):
    assert voc.riconosci_valore(valore, campo) == atteso


def test_valori_sconosciuti(voc):
    assert voc.riconosci_valore("Unknown", "tipo") is None
    assert voc.riconosci_valore("", "rapporto") is None
    assert voc.riconosci_valore(None, "rapporto") is None
    assert voc.riconosci_valore(float("nan"), "tipo") is None


def test_valori_campo_dal_contesto(voc):
    assert voc.riconosci_valore("Cut", contesto="Context Type") == "negativa"
    assert voc.riconosci_valore("Cut", contesto="Level type") == "taglio"


def test_riconosci_valore_con_ambito(voc):
    r = voc.riconosci("Fill", "valore", "Context Type")
    assert r[0].concetto == "positiva"


# ---------------------------------------------------------------- lingue
def test_lingue_limitano_i_termini(voc):
    assert primo(voc, "Mächtigkeit", "colonna").concetto == "spessore"
    assert voc.riconosci("Mächtigkeit", "colonna", lingue=["it", "en"]) == []
    assert primo(voc, "Spessore", "colonna", None).lingua == "it"


def test_ambito_sconosciuto(voc):
    with pytest.raises(ValueError):
        voc.riconosci("US", "foglio")


# ---------------------------------------------------------------- estensioni dell'utente
def test_termini_della_ricetta():
    v = V.Vocabolario(file_utente=False, extra={"us": ["Kontekst-ID"], "quote": {"pl": ["wysokość"]}})
    r = v.riconosci("Kontekst-ID", "colonna")[0]
    assert r.concetto == "us" and "ricetta" in r.motivo
    assert v.riconosci("Wysokość", "colonna")[0].concetto == "quote"
    v.estendi({"campioni": ["Próbka"]})
    assert v.riconosci("Próbka", "colonna")[0].concetto == "campioni"


def test_termini_utente_prevalgono(tmp_path):
    f = tmp_path / "vocabolario.json"
    # in questo archivio «Deposit» è la colonna con la definizione, non il numero di US
    f.write_text(json.dumps({"definizione": {"termini": {"en": ["Deposit"]}},
                             "us": {"termini": {"xx": ["Nummer Kontext"]}}}), encoding="utf-8")
    v = V.Vocabolario(file_utente=str(f))
    r = v.riconosci("Deposit", "colonna")
    assert r[0].concetto == "definizione" and all(x.concetto != "us" for x in r)
    assert "aggiunto dall'utente" in r[0].motivo
    assert v.riconosci("Nummer Kontext", "colonna")[0].concetto == "us"
    # i valori integrati restano
    assert v.riconosci_valore("Deposit", "tipo") == "positiva"


def test_aggiungi_salva_nel_file_utente(tmp_path, monkeypatch):
    f = tmp_path / "config" / "vocabolario.json"
    monkeypatch.setattr(V, "FILE_UTENTE", str(f))
    V.ricarica()
    try:
        assert V.riconosci("Grabungsbefund-Nr", "colonna") == [] or \
            V.riconosci("Grabungsbefund-Nr", "colonna")[0].punteggio < 0.97
        V.aggiungi("us", "Grabungsbefund-Nr", lingua="de")
        r = V.riconosci("Grabungsbefund-Nr", "colonna")[0]
        assert r.concetto == "us" and r.punteggio >= 0.95
        dati = json.loads(f.read_text(encoding="utf-8"))
        assert dati["us"]["termini"]["de"] == ["Grabungsbefund-Nr"]
        # un nuovo vocabolario rilegge il file
        v2 = V.Vocabolario()
        assert v2.riconosci("Grabungsbefund-Nr", "colonna")[0].concetto == "us"
        # un concetto nuovo richiede la descrizione
        with pytest.raises(KeyError):
            v2.aggiungi("concetto_inesistente", "xyz")
        v2.aggiungi("ossa", "Knochen", lingua="de", descrizione="i resti ossei", ambiti=["colonna", "tabella"])
        r = v2.riconosci("Knochen", "tabella")[0]
        assert r.concetto == "ossa" and "resti ossei" in r.motivo
        assert set(json.loads(f.read_text(encoding="utf-8"))) == {"us", "ossa"}
    finally:
        V.ricarica()


def test_file_utente_illeggibile(tmp_path):
    f = tmp_path / "vocabolario.json"
    f.write_text("{non è json", encoding="utf-8")
    v = V.Vocabolario(file_utente=str(f))
    assert v.errori and v.riconosci("US", "colonna")[0].concetto == "us"


# ---------------------------------------------------------------- struttura dei dati
def test_struttura_json():
    v = V.Vocabolario(file_utente=False)
    assert not v.errori
    lingue = set()
    for c, d in v._def.items():
        assert d["descrizione"], c
        assert d["_ambiti"] <= set(V.AMBITI), c
        for k in d.get("contesti") or []:
            assert k in v._def, (c, k)
        lingue |= set(d.get("termini") or {})
    assert {"it", "en", "fr", "de", "es", "sv", "nl"} <= lingue
    # i ruoli dei layer e i valori del motore hanno tutti un concetto
    from stratigrafia3d import schema as sc
    ruoli = {v.canonico(c, "layer") for c in v.concetti("layer")}
    assert {"us", "usm", "quote", "profili", "fondi", "area", "sezioni", "sezioni_disegno", "reperti",
            "campioni"} <= ruoli
    valori = {v.canonico(c, "valore") for c in v.concetti("valore")}
    assert set(sc.INVERSI) | set(sc.INVERSI.values()) | sc.TIPI_QUOTA | {"positiva", "negativa"} <= valori
    fogli = {v.canonico(c, "tabella") for c in v.concetti("tabella")}
    assert {sc.S_US, sc.S_USM, sc.S_RAPPORTI, sc.S_FASI, sc.S_MATERIALI, sc.S_RS, sc.S_CAMPIONI, sc.S_DOC,
            sc.S_QUOTE} <= fogli


def test_rapporti_del_programma_riconosciuti_come_valori(voc):
    from stratigrafia3d import importa
    for k, atteso in importa.RAPPORTI_INGLESE.items():
        assert voc.riconosci_valore(k, "rapporto") == atteso, k
    for k in importa.RAPPORTI_COLONNE:
        assert voc.riconosci_valore(k, "rapporto") == k
    for tipo, sinonimi in importa.SINONIMI_TIPO.items():
        for s in sinonimi:
            assert voc.riconosci_valore(s, "tipo_quota") == tipo, s


# ---------------------------------------------------------------- velocità
def test_velocita():
    basi = ["Context Number", "Fill of", "Brief Description", "Höhe OK", "Q_SUP", "Quota (m)", "Sample Number",
            "Material", "Weight (g)", "Box", "Phase", "Munsell", "Colore", "Spessore", "Depth", "Easting",
            "Northing", "Feature", "Intervention", "SG Number"]
    altre = ["alpha", "beta", "gamma", "delta", "note", "campo", "valore", "misura", "kappa", "omega", "sigma",
             "rho", "lambda", "theta", "iota"]
    rnd = random.Random(7)
    nomi = {f"{rnd.choice(basi)} {rnd.choice(altre)}{rnd.choice(['', '_a', '_bis', '_tot'])} {rnd.choice(altre)}"
            for _ in range(5000)}
    nomi = sorted(nomi)[:1000]
    nomi += ["".join(rnd.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rnd.randint(4, 14))) for _ in range(1000)]
    t = time.perf_counter()
    v = V.Vocabolario(file_utente=False)
    for n in nomi:
        v.riconosci(n, "colonna")
    assert time.perf_counter() - t < 1.0
