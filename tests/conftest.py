import os
import warnings
import pytest

os.environ["S3D_LINGUA"] = "it"          # i test controllano i testi italiani, qualunque sia la lingua del sistema

warnings.filterwarnings("ignore", message=".*Axes3D.*")


@pytest.fixture(scope="session", autouse=True)
def vocabolario_utente_separato(tmp_path_factory):
    """I termini insegnati dall'utente nell'app (~/.stratigrafia3d/vocabolario.json) non cambiano i test."""
    from stratigrafia3d import vocabolario as V
    vecchio = V.FILE_UTENTE
    V.FILE_UTENTE = str(tmp_path_factory.mktemp("vocabolario") / "vocabolario.json")
    V.ricarica()
    yield
    V.FILE_UTENTE = vecchio
    V.ricarica()


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    """Scavo dimostrativo generato una volta per tutta la sessione di test."""
    from stratigrafia3d.demo.genera import genera
    d = tmp_path_factory.mktemp("demo")
    return genera(d, anteprime_png=False, verbose=False)


@pytest.fixture(scope="session")
def progetto(demo, tmp_path_factory):
    """Progetto .scavo ricostruito dallo scavo dimostrativo."""
    from stratigrafia3d import Scavo, ricostruisci
    s = Scavo.da_sorgenti(demo["gpkg"], demo["xlsx"])
    ricostruisci(s)
    path = str(tmp_path_factory.mktemp("prj") / "roveto.scavo")
    s.salva(path)
    return s, path
