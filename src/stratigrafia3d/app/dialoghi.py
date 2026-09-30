# -*- coding: utf-8 -*-
"""Finestre di dialogo native per scegliere file e percorsi di salvataggio.

Con la finestra dell'app (pywebview) si usano i suoi dialoghi; altrimenti si apre un
dialogo Tk in un processo separato (sicuro rispetto ai thread del server).
Se nessuno dei due è disponibile si restituisce None e l'interfaccia chiede il percorso a mano."""
import json
import subprocess
import sys

FINESTRA = None          # impostata da avvio.py quando c'è la finestra pywebview

FILTRI = {
    "scavo": ("Progetto stratigrafia3d", "*.scavo"),
    "dati": ("Dati di scavo", "*.gpkg *.shp *.geojson *.json *.dxf *.csv *.xlsx *.xls *.ods"),
    "gis": ("GIS e CAD", "*.gpkg *.shp *.geojson *.json *.dxf *.csv"),
    "excel": ("Schede", "*.xlsx *.xls *.ods *.csv"),
    "glb": ("glTF binario", "*.glb"),
    "html": ("Pagina web", "*.html"),
    "json": ("Profilo di abbinamento", "*.json"),
}

_TK = r"""
import json, sys, tkinter as tk
from tkinter import filedialog
a = json.loads(sys.argv[1])
r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
ft = [tuple(x) for x in a["filtri"]] + [("Tutti i file", "*.*")]
if a["tipo"] == "apri":
    p = filedialog.askopenfilenames(filetypes=ft) if a["multiplo"] else filedialog.askopenfilename(filetypes=ft)
    p = list(p) if a["multiplo"] else ([p] if p else [])
else:
    p = filedialog.asksaveasfilename(filetypes=ft, initialfile=a.get("nome") or "", defaultextension=a.get("est") or "")
    p = [p] if p else []
print(json.dumps(p))
"""


def scegli(tipo="apri", filtri=("dati",), multiplo=False, nome=None):
    """Ritorna una lista di percorsi (vuota se annullato) oppure None se nessun dialogo è disponibile."""
    ft = [FILTRI[f] for f in filtri if f in FILTRI]
    est = ft[0][1].split()[0].lstrip("*") if ft and tipo == "salva" else ""
    if FINESTRA is not None:
        try:
            import webview
            kind = webview.OPEN_DIALOG if tipo == "apri" else webview.SAVE_DIALOG
            tipi = tuple(f"{d} ({p.replace(' ', ';')})" for d, p in ft) + ("Tutti i file (*.*)",)
            r = FINESTRA.create_file_dialog(kind, allow_multiple=multiplo, file_types=tipi,
                                            save_filename=nome or "")
            if r is None:
                return []
            return [r] if isinstance(r, str) else list(r)
        except Exception:
            pass
    try:
        out = subprocess.run([sys.executable, "-c", _TK, json.dumps(dict(tipo=tipo, filtri=ft, multiplo=multiplo,
                                                                         nome=nome, est=est))],
                             capture_output=True, text=True, timeout=600)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout.strip() or "[]")
    except Exception:
        return None
