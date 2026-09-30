# -*- coding: utf-8 -*-
"""Grafo stratigrafico: lettura dei rapporti, controlli, livelli, diagramma di Harris."""
from dataclasses import dataclass, field
import networkx as nx
import numpy as np

from . import schema as sc


@dataclass
class Rapporti:
    """Rapporti normalizzati: archi A -> B con A posteriore (sopra) a B, più i gruppi contemporanei."""
    grafo: nx.DiGraph
    contemporanei: list          # coppie (a, b) legate / uguali
    scartati: list = field(default_factory=list)   # righe non interpretabili

    @property
    def unita(self):
        return set(self.grafo.nodes)


def da_tabella(df, unita_note=()):
    """Costruisce i rapporti dal foglio Rapporti (colonne: US, Rapporto, US correlata).
    Accetta anche le forme inverse ('coperto da', 'tagliato da', ...)."""
    G = nx.DiGraph()
    G.add_nodes_from(int(u) for u in unita_note)
    same, scartati = [], []
    cols = list(df.columns)
    for _, r in df.iterrows():
        try:
            a, t, b = int(r[cols[0]]), str(r[cols[1]]).strip().lower(), int(r[cols[2]])
        except (ValueError, TypeError):
            scartati.append(tuple(r.values[:3]))
            continue
        if t in sc.DA_INVERSO:
            t, a, b = sc.DA_INVERSO[t], b, a
        if t in sc.RAPPORTI_DIRETTI:
            G.add_edge(a, b, t=t)
        elif t in sc.RAPPORTI_CONTEMPORANEI:
            G.add_nodes_from([a, b])
            same.append((a, b))
        else:
            scartati.append((a, t, b))
    return Rapporti(G, same, scartati)


def gruppi_contemporanei(rap):
    Gs = nx.Graph()
    Gs.add_edges_from(rap.contemporanei)
    alias = {}
    for comp in nx.connected_components(Gs):
        rep = min(comp)
        for n in comp:
            alias[n] = rep
    return alias


def grafo_contratto(rap):
    alias = gruppi_contemporanei(rap)
    Gc = nx.DiGraph()
    Gc.add_nodes_from({alias.get(n, n) for n in rap.grafo.nodes})
    Gc.add_edges_from({(alias.get(a, a), alias.get(b, b)) for a, b in rap.grafo.edges
                       if alias.get(a, a) != alias.get(b, b)})
    return Gc, alias


@dataclass
class Problema:
    livello: str        # "errore" | "avviso"
    codice: str
    messaggio: str
    unita: tuple = ()

    def __str__(self):
        u = f" [{', '.join(map(str, self.unita))}]" if self.unita else ""
        return f"{self.livello.upper():7s} {self.codice}: {self.messaggio}{u}"


def controlla(rap, unita_schede=()):
    """Controlli di coerenza: cicli, contraddizioni con i contemporanei, unità sconosciute."""
    out = []
    Gc, alias = grafo_contratto(rap)
    if not nx.is_directed_acyclic_graph(Gc):
        for ciclo in list(nx.simple_cycles(Gc))[:10]:
            out.append(Problema("errore", "ciclo",
                                "sequenza impossibile: ogni unità risulta posteriore alla successiva",
                                tuple(ciclo)))
    for a, b in rap.contemporanei:
        if rap.grafo.has_edge(a, b) or rap.grafo.has_edge(b, a):
            out.append(Problema("errore", "contraddizione",
                                "due unità sono sia contemporanee sia in sequenza", (a, b)))
    if unita_schede:
        ignote = sorted(set(rap.grafo.nodes) - set(unita_schede))
        if ignote:
            out.append(Problema("avviso", "unita-senza-scheda",
                                "rapporti verso unità che non hanno una scheda", tuple(ignote)))
        isolate = sorted(u for u in unita_schede if u not in rap.grafo or rap.grafo.degree(u) == 0)
        isolate = [u for u in isolate if u not in dict(gruppi_contemporanei(rap))]
        if isolate:
            out.append(Problema("avviso", "unita-isolate", "unità senza alcun rapporto", tuple(isolate)))
    for s in rap.scartati:
        out.append(Problema("avviso", "rapporto-non-riconosciuto", f"riga ignorata: {s}"))
    return out


def livelli_dal_basso(rap):
    """Livello = lunghezza del cammino più lungo verso il basso (0 = unità più antiche)."""
    Gc, alias = grafo_contratto(rap)
    depth = {}
    for n in reversed(list(nx.topological_sort(Gc))):
        succ = list(Gc.successors(n))
        depth[n] = 0 if not succ else 1 + max(depth[s] for s in succ)
    return {u: depth[alias.get(u, u)] for u in rap.grafo.nodes}


def profondita_dall_alto(rap):
    """Numero massimo di unità sovrastanti: ordine di asportazione per lo scavo virtuale."""
    G = rap.grafo
    out = {}
    for n in nx.topological_sort(G):
        pred = list(G.predecessors(n))
        out[n] = 0 if not pred else 1 + max(out[p] for p in pred)
    return out


def _impagina(H, contemporanei, iterazioni):
    """Righe dall'alto (le più recenti) e ordine per baricentri, per un solo gruppo di unità collegate."""
    hl = {}
    for n in nx.topological_sort(H):
        pred = list(H.predecessors(n))
        hl[n] = 0 if not pred else 1 + max(hl[p] for p in pred)
    for a, b in contemporanei:
        m = max(hl.get(a, 0), hl.get(b, 0))
        hl[a] = hl[b] = m
    rows = {}
    for n, l in hl.items():
        rows.setdefault(l, []).append(n)
    for l in rows:
        rows[l].sort()
    pos = {}
    for it in range(iterazioni if len(hl) > 2 else 1):
        for l in sorted(rows):
            for i, n in enumerate(rows[l]):
                pos[n] = i
        for l in (sorted(rows) if it % 2 == 0 else sorted(rows, reverse=True)):
            def bc(n):
                nb = [m for m in list(H.predecessors(n)) + list(H.successors(n)) if m in pos]
                return np.mean([pos[m] for m in nb]) if nb else pos[n]
            rows[l].sort(key=bc)
    # le righe partono da 0 anche se i contemporanei hanno lasciato righe vuote
    livelli = {l: i for i, l in enumerate(sorted(rows))}
    maxw = max(len(v) for v in rows.values()) if rows else 0
    nodi = []
    for l, ns in rows.items():
        off = (maxw - len(ns)) / 2
        for i, n in enumerate(ns):
            nodi.append([n, livelli[l], off + i])
    return nodi, len(rows), maxw


def harris(rap, iterazioni=12, larghezza=None, dedotti=()):
    """Impaginazione del diagramma di Harris: riduzione transitiva, righe, ordine per baricentri.

    Ogni gruppo di unità collegate tra loro (una buca con i suoi riempimenti, un settore) è impaginato
    a parte; i gruppi sono poi disposti su più file, i più grandi per primi, e le unità senza rapporti
    in una griglia finale. Ogni nodo porta il numero del gruppo (``g``) e ``gruppi`` dice dove sta
    ciascuno, così il visualizzatore può mostrare la sola sequenza dell'unità scelta.

    ``dedotti`` sono rapporti «copre» ricavati dal programma (l'ordine dei riempimenti): entrano nel
    diagramma, ma sono elencati a parte perché il visualizzatore li disegni tratteggiati."""
    G = rap.grafo
    extra = [(a, b) for a, b in dedotti if a in G and b in G and not G.has_edge(a, b)]
    if extra:
        G = G.copy()
        G.add_edges_from(extra)
        if not nx.is_directed_acyclic_graph(G):
            G, extra = rap.grafo, []
    H = nx.transitive_reduction(G)
    U = nx.Graph()
    U.add_nodes_from(H.nodes)
    U.add_edges_from(H.edges())
    U.add_edges_from((a, b) for a, b in rap.contemporanei if a in U and b in U)
    comps = [sorted(c) for c in nx.connected_components(U)]
    comps.sort(key=lambda c: (-len(c), c[0]))
    blocchi = []
    sole = []
    for c in comps:
        if len(c) == 1 and not G.degree(c[0]):
            sole.append(c[0])
            continue
        dentro = set(c)
        cont = [(a, b) for a, b in rap.contemporanei if a in dentro]
        nodi, righe, col = _impagina(H.subgraph(c), cont, iterazioni)
        blocchi.append((nodi, righe, col))
    if sole:
        lato = max(1, int(np.ceil(np.sqrt(len(sole) * 3))))
        nodi = [[n, i // lato, float(i % lato)] for i, n in enumerate(sorted(sole))]
        blocchi.append((nodi, int(np.ceil(len(sole) / lato)), min(lato, len(sole))))
    # disposizione a scaffali: file di gruppi larghe al massimo «larghezza» colonne
    tot = sum(r * c for _, r, c in blocchi)
    if larghezza is None:
        larghezza = max([c for _, _, c in blocchi] + [int(np.ceil(np.sqrt(tot * 2.5)))], default=0)
    nodes, gruppi = [], []
    x = y = alt = 0
    for g, (nodi, righe, col) in enumerate(blocchi):
        if x and x + col > larghezza:
            x, y, alt = 0, y + alt + 1, 0
        gruppi.append(dict(r=y, c=x, rows=righe, cols=col, n=len(nodi)))
        for n, r, c in nodi:
            nodes.append(dict(id=int(n), r=int(y + r), c=round(x + c, 2), g=g))
        x += col + 1
        alt = max(alt, righe)
    rows = (y + alt) if blocchi else 0
    cols = max((gr["c"] + gr["cols"] for gr in gruppi), default=0)
    return dict(nodes=nodes, edges=[[int(a), int(b)] for a, b in H.edges()],
                same=[[int(a), int(b)] for a, b in rap.contemporanei], rows=rows, cols=cols, gruppi=gruppi,
                dedotti=[[int(a), int(b)] for a, b in extra if H.has_edge(a, b)])
