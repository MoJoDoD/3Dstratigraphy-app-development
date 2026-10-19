# -*- coding: utf-8 -*-
"""
Cache dei dati pesanti già ridotti (DEM a 2 cm, ortofoto ridotte, modelli 3D semplificati), accanto alle
impostazioni dell'app (~/.stratigrafia3d/cache). La chiave contiene percorso, data e dimensione del file
d'origine e i parametri della riduzione: se il file cambia, la cache non vale più. Una nuova importazione
dello stesso archivio non decodifica di nuovo centinaia di MB.
"""
import hashlib
import os


def cartella():
    """~/.stratigrafia3d/cache (calcolata ogni volta: segue la cartella dell'utente anche nei test)."""
    return os.path.join(os.path.expanduser("~"), ".stratigrafia3d", "cache")


LIMITE_BYTE = 4 * 2 ** 30            # oltre, si tolgono i file usati meno di recente


def percorso(tipo, origine, *parametri):
    """Percorso del file di cache per ``origine`` ridotto con ``parametri`` (None se l'origine non esiste)."""
    try:
        st = os.stat(origine)
    except OSError:
        return None
    chiave = "|".join([os.path.abspath(origine), str(st.st_mtime_ns), str(st.st_size)] + [str(p) for p in parametri])
    d = os.path.join(cartella(), tipo)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return os.path.join(d, hashlib.sha1(chiave.encode()).hexdigest() + ".npz")


def leggi(p):
    """Byte della cache, o None."""
    if not p or not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            b = f.read()
        os.utime(p)                         # usata adesso: resta tra le più recenti
        return b
    except OSError:
        return None


def scrivi(p, dati):
    if not p:
        return
    try:
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(dati)
        os.replace(tmp, p)
        _sfoltisci()
    except OSError:
        pass


def _sfoltisci():
    """Tiene la cache sotto ``LIMITE_BYTE`` togliendo i file usati meno di recente."""
    try:
        voci = []
        for rad, _, files in os.walk(cartella()):
            for f in files:
                q = os.path.join(rad, f)
                st = os.stat(q)
                voci.append((st.st_mtime, st.st_size, q))
        tot = sum(v[1] for v in voci)
        for _, dim, q in sorted(voci):
            if tot <= LIMITE_BYTE:
                break
            os.remove(q)
            tot -= dim
    except OSError:
        pass
