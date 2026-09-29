import subprocess
import sys


def _run(*args):
    return subprocess.run([sys.executable, "-m", "stratigrafia3d", *args], capture_output=True, text=True)


def test_info(progetto):
    _, path = progetto
    r = _run("info", path)
    assert r.returncode == 0 and "Modello 3D: 46" in r.stdout


def test_verifica(progetto):
    _, path = progetto
    r = _run("verifica", path)
    assert r.returncode == 0 and "0 errori" in r.stdout
