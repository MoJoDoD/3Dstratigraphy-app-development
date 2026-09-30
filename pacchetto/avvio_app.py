# Punto di ingresso dell'eseguibile Windows (PyInstaller)
import sys
from stratigrafia3d.app.avvio import avvia

if __name__ == "__main__":
    avvia(sys.argv[1] if len(sys.argv) > 1 else None)
