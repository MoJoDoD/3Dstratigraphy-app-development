# stratigrafia3d

Ricostruzione 3D delle unità stratigrafiche (US) a partire dalla documentazione di scavo 2D:
poligoni in pianta, quote, profili di sezione (GeoPackage) e schede (Excel).

Questa è la **tappa 1** del progetto: il motore Python, la riga di comando e il formato di progetto `.scavo`.
L'app desktop (tappa 2) userà questo stesso motore.

## Installazione

```
pip install -e .[demo,test]
```

## Uso dalla riga di comando

```
strat3d demo cartella_demo                         # genera lo scavo dimostrativo "Podere Roveto"
strat3d verifica scavo.gpkg schede.xlsx            # controlla dati e rapporti stratigrafici
strat3d crea-progetto scavo.gpkg schede.xlsx -o scavo.scavo
strat3d info scavo.scavo
strat3d ricostruisci scavo.scavo --unita 1016      # ricalcola 1016 e le unità che le stanno sopra
strat3d visualizzatore scavo.scavo -o web/index.html
strat3d esporta-glb scavo.scavo -o scavo.glb --esploso 0.3   # si apre in Blender
```

## Uso da Python

```python
from stratigrafia3d import Scavo, ricostruisci, esporta
s = Scavo.da_sorgenti("scavo.gpkg", "schede.xlsx")
for p in s.verifica():
    print(p)
ricostruisci(s)
s.salva("scavo.scavo")
esporta.visualizzatore(s, "index.html")
```

## Dati in ingresso

**GeoPackage** (nomi in `schema.py`):
- `us_poligoni` (campo `us`) e `usm_poligoni` (campo `usm`)
- `quote` (PointZ, campi `us`, `tipo_quota`: sup, inf, taglio, orlo, rasatura, fondazione)
- facoltativi: `profili_us` (LineStringZ, campi `sezione`, `us`, `interfaccia`: sup, inf, taglio),
  `area_scavo`, `sezioni`, `sezioni_disegno`, `reperti_speciali`, `campioni`

**Excel**: fogli `US` e `Rapporti` obbligatori; `USM`, `Fasi`, `Materiali`, `Reperti_speciali`,
`Campioni`, `Documentazione` facoltativi. Nel foglio Rapporti sono accettate anche le forme inverse
(“coperto da”, “tagliato da”…).

## Il formato `.scavo`

È un GeoPackage: contiene i layer, i fogli Excel come tabelle `tab_<foglio>`, le geometrie ricostruite
(`s3d_modelli`), i parametri (`s3d_progetto`), l'impronta dei file di origine (`s3d_sorgenti`) e il
registro delle operazioni (`s3d_storico`). QGIS lo apre come GeoPackage (scegliendo "Tutti i file" o
rinominandolo in `.gpkg`).

## Metodo

Per ogni US positiva: triangolazione vincolata del poligono; tetto per trend planare + kriging dei
residui; spessore krigato attorno allo spessore medio (a zero sui bordi liberi delle lenti); base
agganciata al tetto delle unità coperte secondo i rapporti. I tagli sono superfici (orlo, fondo e
larghezza della parete stimata dai dati); le USM volumi tra rasatura e fondazione.
Ogni unità riporta quanto è misurata e quanto stimata (`qualita`).

Sullo scavo dimostrativo lo scarto mediano del tetto rispetto al modello di verità è sotto 3 cm per
il 90% delle unità (verificato da `tests/test_scavo_demo.py`).

## Test

```
pytest -q
```

## Licenza

GPL-3.0-or-later (vedi `LICENSE`). Dati dello scavo dimostrativo interamente immaginari.
