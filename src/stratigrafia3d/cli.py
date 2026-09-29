# -*- coding: utf-8 -*-
"""Riga di comando: ``strat3d <comando> ...`` (``strat3d -h`` per l'elenco)."""
import argparse
import os
import sys
import time

from . import __version__


def _stampa_problemi(problemi):
    if not problemi:
        print("Nessun problema trovato.")
        return 0
    for p in problemi:
        print(" ", p)
    err = sum(p.livello == "errore" for p in problemi)
    print(f"{err} errori, {len(problemi) - err} avvisi.")
    return err


def cmd_demo(a):
    from .demo.genera import genera
    r = genera(a.cartella, seed=a.seme, anteprime_png=not a.senza_anteprime, verbose=not a.silenzioso)
    print(f"Scavo dimostrativo creato:\n  {r['gpkg']}\n  {r['xlsx']}")


def cmd_verifica(a):
    from .progetto import Scavo
    s = Scavo.apri(a.sorgente) if a.sorgente.endswith(".scavo") else Scavo.da_sorgenti(a.sorgente, a.excel)
    return 1 if _stampa_problemi(s.verifica()) else 0


def cmd_crea(a):
    from .progetto import Scavo
    from .ricostruzione import ricostruisci
    t0 = time.time()
    s = Scavo.da_sorgenti(a.gis, a.excel)
    err = _stampa_problemi(s.verifica())
    if err and not a.forza:
        print("Correggi gli errori o usa --forza.")
        return 1
    m = ricostruisci(s, log=print)
    s.salva(a.output)
    print(f"{len(m.unita)} unità ricostruite in {time.time() - t0:.1f} s -> {a.output}")
    return 0


def cmd_ricostruisci(a):
    from .progetto import Scavo
    from .ricostruzione import ricostruisci, da_ricalcolare
    s = Scavo.apri(a.progetto)
    unita = da_ricalcolare(s, a.unita) if a.unita else None
    m = ricostruisci(s, unita=unita, log=print)
    s.salva(a.progetto)
    print(f"Ricalcolate {len(unita) if unita else len(m.unita)} unità.")


def cmd_info(a):
    from .progetto import Scavo
    print(Scavo.apri(a.progetto).riepilogo())


def cmd_visualizzatore(a):
    from .progetto import Scavo
    from . import esporta
    s = Scavo.apri(a.progetto)
    print("Scritto", esporta.visualizzatore(s, a.output))


def cmd_glb(a):
    from .progetto import Scavo
    from . import esporta
    s = Scavo.apri(a.progetto)
    print("Scritto", esporta.glb(s, a.output, esploso=a.esploso))


def main(argv=None):
    p = argparse.ArgumentParser(prog="strat3d", description="Ricostruzione 3D delle unità stratigrafiche.")
    p.add_argument("--version", action="version", version=f"stratigrafia3d {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="genera lo scavo dimostrativo (GeoPackage + Excel)")
    d.add_argument("cartella"); d.add_argument("--seme", type=int, default=1974)
    d.add_argument("--senza-anteprime", action="store_true"); d.add_argument("--silenzioso", action="store_true")
    d.set_defaults(f=cmd_demo)

    v = sub.add_parser("verifica", help="controlla dati e rapporti (GeoPackage + Excel, oppure .scavo)")
    v.add_argument("sorgente"); v.add_argument("excel", nargs="?")
    v.set_defaults(f=cmd_verifica)

    c = sub.add_parser("crea-progetto", help="importa GIS + Excel, ricostruisce il 3D, salva il .scavo")
    c.add_argument("gis"); c.add_argument("excel"); c.add_argument("-o", "--output", required=True)
    c.add_argument("--forza", action="store_true", help="procede anche se la verifica trova errori")
    c.set_defaults(f=cmd_crea)

    r = sub.add_parser("ricostruisci", help="ricalcola il modello 3D di un progetto")
    r.add_argument("progetto"); r.add_argument("--unita", type=int, nargs="+",
                                               help="solo queste unità e quelle che stanno sopra")
    r.set_defaults(f=cmd_ricostruisci)

    i = sub.add_parser("info", help="riepilogo di un progetto"); i.add_argument("progetto"); i.set_defaults(f=cmd_info)

    w = sub.add_parser("visualizzatore", help="crea la pagina web 3D autonoma")
    w.add_argument("progetto"); w.add_argument("-o", "--output", required=True); w.set_defaults(f=cmd_visualizzatore)

    g = sub.add_parser("esporta-glb", help="esporta il modello in glTF binario (Blender, MeshLab…)")
    g.add_argument("progetto"); g.add_argument("-o", "--output", required=True)
    g.add_argument("--esploso", type=float, default=0.0, help="distanza verticale tra livelli (m)")
    g.set_defaults(f=cmd_glb)

    a = p.parse_args(argv)
    if a.cmd == "verifica" and not a.sorgente.endswith(".scavo") and not a.excel:
        p.error("con un GeoPackage serve anche il file Excel")
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
