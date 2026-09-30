# -*- coding: utf-8 -*-
"""stratigrafia3d — ricostruzione 3D delle unità stratigrafiche da documentazione di scavo 2D.

Uso tipico::

    from stratigrafia3d import Scavo, ricostruisci, esporta
    s = Scavo.da_sorgenti("scavo.gpkg", "schede.xlsx")
    for p in s.verifica(): print(p)
    ricostruisci(s)
    s.salva("scavo.scavo")
    esporta.visualizzatore(s, "index.html")
"""
__version__ = "0.2.2"

import warnings as _w
# un .scavo è un GeoPackage con un'estensione propria: GDAL lo segnala, ma è voluto
_w.filterwarnings("ignore", message=".*non conformant file extension")

from .progetto import Scavo, Parametri, Modello, UnitaModello  # noqa: F401
from .ricostruzione import ricostruisci, da_ricalcolare  # noqa: F401
from . import esporta  # noqa: F401
