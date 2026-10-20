# -*- coding: utf-8 -*-
"""
Letture architettoniche e cronologiche della sequenza, per il visualizzatore:

* fasi costruttive delle murature: le USM legate tra loro («si lega a») sono un unico cantiere; un muro che si
  appoggia a un altro, o che lo copre, è costruito dopo. Anche i rapporti che passano per gli strati contano
  (un muro fondato su uno strato che copre un altro muro è più recente di quello). La fase è la posizione nella
  sequenza delle sole murature: 0 = le più antiche.
* cronologia dello scavo: le date dei rilievi di ogni unità (modelli del terreno e ortofoto con la data nel
  nome, colonna «Date rilievi» delle schede) danno un giorno per giorno dell'asportazione. L'ultimo DEM proprio
  di un'unità è la superficie lasciata dopo averla scavata: rilevata in più giorni, è stata scavata entro
  l'ultimo. Con un solo rilievo, o nessuno, è stata tolta al più tardi quando è comparsa la prima unità
  sottostante (data stimata); senza unità sottostanti datate resta in posto. I DEM che avvolgono più unità
  («Date rilievi con altre US») dicono quando un'unità era esposta, non quando è stata scavata: contano per la
  comparsa delle unità sottostanti.
"""
import re

import networkx as nx

from . import stratigrafia as st

C_DATE_RILIEVI = "Date rilievi"                    # DEM e ortofoto della sola unità
C_DATE_INSIEME = "Date rilievi con altre US"        # DEM che avvolgono più unità
_DATA_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def data_iso(t):
    """(anno, mese, giorno) -> «2025-09-24»."""
    a, m, g = (int(x or 0) for x in t)
    return f"{a:04d}-{m:02d}-{g:02d}"


def date_dal_testo(v):
    """Le date «AAAA-MM-GG» di una cella (separate da virgole, punti e virgola o spazi), ordinate."""
    if v is None:
        return []
    try:
        if v != v:            # NaN
            return []
    except Exception:
        pass
    out = set()
    for a, m, g in _DATA_RE.findall(str(v)):
        if 1 <= int(m) <= 12 and 1 <= int(g) <= 31:
            out.add(f"{int(a):04d}-{int(m):02d}-{int(g):02d}")
    return sorted(out)


def _grafo_condensato(rap):
    """Grafo delle sole relazioni di sequenza con i gruppi legati contratti e gli eventuali cicli fusi:
    (DAG, unità -> nodo del DAG)."""
    Gc, alias = st.grafo_contratto(rap)
    C = nx.condensation(Gc)
    nodo = {}
    for u in set(rap.grafo.nodes) | set(alias):
        nodo[u] = C.graph["mapping"][alias.get(u, u)]
    return C, nodo


def fasi_murarie(rap, murarie):
    """{usm: {"fase": k, "cantiere": rappresentante dei muri legati, "rapporti": n}} per le murature.

    ``fase`` è il cammino più lungo verso il basso nella sequenza ridotta alle sole murature (0 = più antiche);
    ``rapporti`` il numero di altre murature con cui il muro è in sequenza o legato: con 0 la fase non dice
    nulla (il muro non è confrontabile con gli altri)."""
    murarie = {int(u) for u in murarie}
    if not murarie:
        return {}
    # cantieri: muri legati tra loro (solo tra murature)
    Gs = nx.Graph()
    Gs.add_nodes_from(murarie)
    Gs.add_edges_from((a, b) for a, b in rap.contemporanei if a in murarie and b in murarie)
    cantiere = {}
    for comp in nx.connected_components(Gs):
        r = min(comp)
        for n in comp:
            cantiere[n] = r
    C, nodo = _grafo_condensato(rap)
    # sequenza tra cantieri: un muro è posteriore a un altro se c'è un cammino tra loro nel grafo completo
    W = nx.DiGraph()
    W.add_nodes_from(set(cantiere.values()))
    per_nodo = {}
    for u in murarie:
        if u in nodo:
            per_nodo.setdefault(nodo[u], set()).add(cantiere[u])
    for n, cc in per_nodo.items():
        for v in nx.descendants(C, n):
            for c2 in per_nodo.get(v, ()):
                for c1 in cc:
                    if c1 != c2:
                        W.add_edge(c1, c2)
    # un ciclo tra cantieri (rapporti contraddittori) li fonde: stessa fase
    Wc = nx.condensation(W)
    prof = {}
    for n in reversed(list(nx.topological_sort(Wc))):
        succ = list(Wc.successors(n))
        prof[n] = 0 if not succ else 1 + max(prof[s] for s in succ)
    mp = Wc.graph["mapping"]
    out = {}
    for u in sorted(murarie):
        c = cantiere[u]
        legati = len([x for x in murarie if cantiere[x] == c]) - 1
        n_seq = W.in_degree(c) + W.out_degree(c)
        out[u] = {"fase": int(prof[mp[c]]), "cantiere": int(c), "rapporti": int(legati + n_seq)}
    return out


def cronologia_scavo(rap, date, murarie=(), insieme=None):
    """Cronologia dello scavo dalle date dei rilievi.

    ``date``: {unità: ["AAAA-MM-GG", ...]} dei rilievi della sola unità; ``insieme``: quelle dei DEM che
    avvolgono più unità. Ritorna {"date": [giorni ordinati], "unita": {u: {"rilievi": [indici dei giorni],
    "insieme": [indici], "rimossa": indice del giorno entro cui è stata asportata o None, "stimata": bool}}},
    oppure None se nessuna unità ha date. Le murature restano in posto."""
    date = {int(u): sorted(set(d)) for u, d in date.items() if d}
    insieme = {int(u): sorted(set(d)) for u, d in (insieme or {}).items() if d}
    if not date and not insieme:
        return None
    giorni = sorted({g for d in list(date.values()) + list(insieme.values()) for g in d})
    ix = {g: i for i, g in enumerate(giorni)}
    murarie = {int(u) for u in murarie}
    C, nodo = _grafo_condensato(rap)
    # il primo giorno in cui compare (è rilevata, da sola o con altre) ciascun nodo del grafo e, per ogni nodo,
    # il primo giorno in cui compare qualcosa sotto di esso
    primo_n = {}
    for dd in (date, insieme):
        for u, d in dd.items():
            if u in nodo:
                n = nodo[u]
                primo_n[n] = min(primo_n.get(n, ix[d[0]]), ix[d[0]])
    sotto = {}
    for n in reversed(list(nx.topological_sort(C))):
        best = None
        for s in C.successors(n):
            for v in (primo_n.get(s), sotto.get(s)):
                if v is not None and (best is None or v < best):
                    best = v
        sotto[n] = best
    unita = {}
    tutte = set(date) | set(insieme) | {u for u in nodo if u not in murarie}
    for u in sorted(tutte):
        ril = [ix[g] for g in date.get(u, [])]
        ins = [ix[g] for g in insieme.get(u, [])]
        rec = {"rilievi": ril, "insieme": ins, "rimossa": None, "stimata": False}
        if u not in murarie:
            if len(ril) >= 2:
                rec["rimossa"] = ril[-1]          # l'ultimo DEM proprio: la superficie dopo lo scavo
            else:
                s = sotto.get(nodo[u]) if u in nodo else None
                if s is not None:
                    # al più tardi quando compare ciò che copre, ma non prima dell'ultimo giorno in cui era rilevata
                    rec["rimossa"] = max([s] + ril + ins)
                    rec["stimata"] = True
        if ril or ins or rec["rimossa"] is not None:
            unita[u] = rec
    return {"date": giorni, "unita": unita}


def date_delle_schede(*tabelle, colonne=(C_DATE_RILIEVI,)):
    """{unità: [date]} dalle schede US/USM (prima colonna numerica = unità)."""
    out = {}
    for df, campo in tabelle:
        if df is None or campo not in df.columns:
            continue
        for col in colonne:
            if col not in df.columns:
                continue
            for u, v in zip(df[campo], df[col]):
                d = date_dal_testo(v)
                if d:
                    try:
                        out.setdefault(int(u), set()).update(d)
                    except (TypeError, ValueError):
                        pass
    return {u: sorted(d) for u, d in out.items()}
