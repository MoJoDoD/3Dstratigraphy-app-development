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
        u = list(p.unita)
        elenco = (": " + ", ".join(map(str, u[:12])) + (f" … (+{len(u) - 12})" if len(u) > 12 else "")) if u else ""
        print(f"  [{p.livello}] {p.messaggio}{elenco}")
    err = sum(p.livello == "errore" for p in problemi)
    avv = sum(p.livello == "avviso" for p in problemi)
    print(f"{err} errori, {avv} avvisi, {len(problemi) - err - avv} informazioni.")
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


def cmd_riscrivi(a):
    from .progetto import Scavo
    from . import modifiche as md
    s = Scavo.apri(a.progetto)
    if not md.in_attesa(s):
        print("Nessuna modifica da scrivere.")
        return
    r = md.riscrivi(s)
    s.salva(a.progetto)
    print(f"{r['scritte']} modifiche scritte in: {', '.join(r['file']) or '—'}")
    for v, motivo in r["saltate"]:
        print(f"  non scritta: US {v.get('unita')} {v.get('campo') or v.get('rapporto', '')}: {motivo}")
    if r["copie"]:
        print("Copie dei file prima della scrittura: " + ", ".join(r["copie"]))


def cmd_aggiorna(a):
    from .progetto import Scavo
    from .ricostruzione import ricostruisci
    from . import modifiche as md
    s = Scavo.apri(a.progetto)
    cambiate = md.sorgenti_cambiate(s)
    if not cambiate and not a.forza:
        print("I file d'origine non sono cambiati.")
        return
    for c in cambiate:
        print(f"  {c['stato']}: {c['percorso']}")
    nuovo, unita, note = md.ricarica(s, scarta_modifiche=a.scarta)
    if unita:
        ricostruisci(nuovo, unita=unita, log=print)
    nuovo.salva(a.progetto)
    print("; ".join(note) + (f"; ricostruite {len(unita)} unità" if unita else ""))


def cmd_elaborati(a):
    from .progetto import Scavo
    from . import elaborati as el
    s = Scavo.apri(a.progetto)
    if s.modello is None:
        print("Il progetto non ha ancora il modello 3D: esegui prima «strat3d ricostruisci».")
        return 1
    fatti = []
    if a.volumi:
        fatti.append(el.scrivi_tabella_volumi(s, a.volumi))
    if a.piante:
        fatti.append(el.pianta_svg(s, a.piante, scala=a.scala_pianta))
    if a.pianta_dxf:
        fatti.append(el.pianta_dxf(s, a.pianta_dxf))
    if a.sezioni:
        sez = []
        for i, t in enumerate(a.sezione or []):
            v = [float(x) for x in t.split(",")]
            sez.append((f"Sezione {i + 1}", (v[0], v[1]), (v[2], v[3])))
        sez = sez or el.linee_sezione(s) or el.sezioni_centrali(s)
        for p in a.sezioni:
            fatti.append((el.sezioni_dxf if p.lower().endswith(".dxf") else el.sezioni_svg)(s, sez, p))
    if not fatti:
        print("Indica almeno un elaborato: --volumi, --piante, --pianta-dxf, --sezioni")
        return 1
    for f in fatti:
        print("Scritto", f)


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


def cmd_app(a):
    from .app.avvio import avvia
    avvia(a.progetto, finestra=not a.browser, porta=a.porta, browser=not a.senza_browser)


def _carica_ricetta(importa, nome):
    """Una ricetta pronta (per chiave, es. «framework_archaeology») o un file JSON salvato."""
    if os.path.isfile(nome):
        return importa.Abbinamento.carica_profilo(nome)
    pronte = importa.ricette_pronte()
    if nome in pronte:
        return importa.carica_ricetta_pronta(nome)
    raise SystemExit(f"Ricetta «{nome}» non trovata. Ricette pronte: {', '.join(sorted(pronte))}")


def _scelte_da_argomenti(a):
    """Le scelte sull'inventario date da riga di comando: {percorso: {"usa": bool, "ruolo": str}}."""
    scelte = {}
    if getattr(a, "scelte", None):
        import json
        with open(a.scelte, encoding="utf-8") as f:
            scelte.update(json.load(f))

    def chiave(p):          # un file che c'è, oppure il percorso dentro la cartella o l'archivio esaminati
        return os.path.abspath(p) if os.path.exists(p) else p
    for p in getattr(a, "escludi", None) or []:
        scelte[chiave(p)] = dict(scelte.get(chiave(p)) or {}, usa=False)
    for x in getattr(a, "destinazione", None) or []:
        p, _, ruolo = x.rpartition("=")
        if not p or not ruolo:
            raise SystemExit(f"--destinazione «{x}»: scrivi FILE=RUOLO (es. raster/diff.tif=differenza)")
        scelte[chiave(p)] = dict(scelte.get(chiave(p)) or {}, ruolo=ruolo, usa=True)
    return scelte


def cmd_importa(a):
    from . import importa
    from .ricostruzione import ricostruisci
    if not a.file and not a.profilo:
        print("Indica i file o le cartelle da importare (oppure --profilo).")
        return 1
    scelte = _scelte_da_argomenti(a)
    if a.profilo and not a.file:
        # profilo salvato con i percorsi dei suoi file
        abb = importa.Abbinamento.carica_profilo(a.profilo)
        for n in importa.applica_scelte_inventario(abb, scelte) if scelte else []:
            print("  ", n)
    else:
        abb = importa.proponi(a.file, scelte=scelte or None)          # file, cartelle e archivi zip
        ricetta = a.ricetta or a.profilo       # con i file indicati il profilo vale come ricetta
        if ricetta:
            abb, note = importa.applica_ricetta(abb, _carica_ricetta(importa, ricetta))
            abb.note.extend(note)
        for n in abb.note:
            print("  ", n)
        for r in abb.layers:
            print(f"   {r.layer:30s} -> {r.ruolo:10s} {r.motivo}")
    if a.quota_superficie is not None:
        abb.superficie = {"tipo": "costante", "quota": a.quota_superficie, "abbassa": 0.0}
    if a.abbassa is not None:
        abb.superficie = dict(abb.superficie or {"tipo": "nessuna"}, abbassa=a.abbassa)
    if a.salva_profilo:
        abb.salva_profilo(a.salva_profilo)
        print("Profilo salvato in", a.salva_profilo)
    s = importa.applica(abb, log=lambda m: print("  ", m))
    err = _stampa_problemi(s.verifica())
    if a.output:
        if err and not a.forza:
            print("Correggi gli errori o usa --forza.")
            return 1
        ricostruisci(s)
        s.salva(a.output)
        print("Progetto salvato in", a.output)
    return 0


def cmd_inventario(a):
    from . import importa
    for p in a.percorsi:
        if not os.path.exists(p):
            print(f"«{p}» non esiste.")
            return 1
    inv = importa.inventaria(a.percorsi, profondita_max=a.profondita, limite_file=a.limite)
    if a.json:
        import json
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(importa._jsonabile(inv), f, ensure_ascii=False, indent=1)
        print("Inventario salvato in", a.json)
    m = importa._modulo_inventario()
    riassunto = m.riassunto_testo(inv) if m is not None and hasattr(m, "riassunto_testo") else None
    if riassunto is not None and not (a.tutti or a.elenco):
        print(riassunto)
        return 0
    voci = [v for v in inv.get("voci") or [] if a.tutti or v.get("categoria") != "ignorato"]
    print(f"{'File':60s} {'Categoria':10s} {'Destinazione':40s} {'Punteggio':>9s}")
    for v in voci:
        rel = str(v.get("relativo") or v.get("nome") or v.get("percorso"))
        rel = rel if len(rel) <= 60 else "…" + rel[-59:]
        pt = v.get("punteggio")
        dest = str(v.get("destinazione") or "—")
        dest = dest if len(dest) <= 40 else dest[:39] + "…"
        print(f"{rel:60s} {str(v.get('categoria') or ''):10s} {dest:40s} "
              f"{(f'{pt:.2f}' if isinstance(pt, (int, float)) else '—'):>9s}")
    if riassunto is not None:
        print(riassunto)
        return 0
    for n in inv.get("note") or []:
        print("  ", importa._testo_nota(n))
    print(f"{len(voci)} file, {len(inv.get('file_proposta') or [])} proposti per l'importazione.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="strat3d", description="Ricostruzione 3D delle unità stratigrafiche.")
    p.add_argument("--version", action="version", version=f"stratigrafia3d {__version__}")
    p.add_argument("--lingua", choices=["it", "en"],
                   help="lingua degli elaborati e del visualizzatore esportati (predefinita: quella dell'app)")
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

    rs = sub.add_parser("riscrivi", help="scrive nei file d'origine le modifiche fatte nell'app")
    rs.add_argument("progetto"); rs.set_defaults(f=cmd_riscrivi)
    ag = sub.add_parser("aggiorna", help="rilegge i file d'origine cambiati e ricostruisce le unità toccate")
    ag.add_argument("progetto"); ag.add_argument("--scarta", action="store_true",
                                                 help="scarta le modifiche fatte nell'app non ancora scritte")
    ag.add_argument("--forza", action="store_true", help="rilegge anche se i file sembrano uguali")
    ag.set_defaults(f=cmd_aggiorna)

    el = sub.add_parser("elaborati", help="tabella dei volumi, piante e sezioni (SVG, DXF) dal modello 3D")
    el.add_argument("progetto")
    el.add_argument("--volumi", help="tabella Excel dei volumi")
    el.add_argument("--piante", help="piante per fase (.svg)")
    el.add_argument("--scala-pianta", type=int, default=200)
    el.add_argument("--pianta-dxf", help="pianta in coordinate reali (.dxf)")
    el.add_argument("--sezioni", nargs="+", help="sezioni dal modello (.svg e/o .dxf)")
    el.add_argument("--sezione", action="append", metavar="E1,N1,E2,N2",
                    help="traccia di una sezione (ripetibile); senza, quelle del GIS o due centrali")
    el.set_defaults(f=cmd_elaborati)

    i = sub.add_parser("info", help="riepilogo di un progetto"); i.add_argument("progetto"); i.set_defaults(f=cmd_info)

    w = sub.add_parser("visualizzatore", help="crea la pagina web 3D autonoma")
    w.add_argument("progetto"); w.add_argument("-o", "--output", required=True); w.set_defaults(f=cmd_visualizzatore)

    g = sub.add_parser("esporta-glb", help="esporta il modello in glTF binario (Blender, MeshLab…)")
    g.add_argument("progetto"); g.add_argument("-o", "--output", required=True)
    g.add_argument("--esploso", type=float, default=0.0, help="distanza verticale tra livelli (m)")
    g.set_defaults(f=cmd_glb)

    ap = sub.add_parser("app", help="apre l'applicazione (finestra o browser)")
    ap.add_argument("progetto", nargs="?"); ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--browser", action="store_true", help="usa il browser invece della finestra")
    ap.add_argument("--senza-browser", action="store_true", help="non apre nulla, avvia solo il server")
    ap.set_defaults(f=cmd_app)

    im = sub.add_parser("importa", help="import flessibile di file qualsiasi (GIS, DXF, Excel), anche di intere "
                                        "cartelle o archivi zip, con abbinamento automatico")
    im.add_argument("file", nargs="*", help="file, cartelle o archivi zip")
    im.add_argument("--profilo", help="usa un profilo di abbinamento salvato (con file o cartelle: come ricetta)")
    im.add_argument("--ricetta", help="applica una ricetta: pronta (es. framework_archaeology) o file JSON")
    im.add_argument("--salva-profilo"); im.add_argument("-o", "--output", help="crea il progetto .scavo")
    im.add_argument("--forza", action="store_true")
    im.add_argument("--quota-superficie", type=float, help="superficie di riferimento piana a questa quota (m)")
    im.add_argument("--abbassa", type=float, help="abbassa la superficie di riferimento (es. arativo asportato, m)")
    im.add_argument("--escludi", action="append", metavar="FILE",
                    help="non usare questo file della cartella (dati, foto o documenti; ripetibile)")
    im.add_argument("--destinazione", action="append", metavar="FILE=RUOLO",
                    help="usa il file con questo ruolo (es. us, quote, schede_us, rapporti, materiali, dem, "
                         "differenza, ortofoto, foto, disegno; ripetibile)")
    im.add_argument("--scelte", metavar="JSON",
                    help="file JSON con le scelte sull'inventario: {percorso: {\"usa\": false, \"ruolo\": \"…\"}}")
    im.set_defaults(f=cmd_importa)

    iv = sub.add_parser("inventario", help="esamina cartelle o archivi zip: cosa contengono e cosa importare")
    iv.add_argument("percorsi", nargs="+", metavar="CARTELLA_O_ZIP")
    iv.add_argument("--profondita", type=int, default=8, help="livelli di sottocartelle da esaminare")
    iv.add_argument("--limite", type=int, default=20000, help="numero massimo di file da esaminare")
    iv.add_argument("--elenco", action="store_true", help="elenca i file uno per uno, prima del riassunto")
    iv.add_argument("--tutti", action="store_true", help="elenca anche i file ignorati")
    iv.add_argument("--json", help="salva l'inventario completo in un file JSON")
    iv.set_defaults(f=cmd_inventario)

    a = p.parse_args(argv)
    if a.lingua:
        os.environ["S3D_LINGUA"] = a.lingua
    if a.cmd == "verifica" and not a.sorgente.endswith(".scavo") and not a.excel:
        p.error("con un GeoPackage serve anche il file Excel")
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
