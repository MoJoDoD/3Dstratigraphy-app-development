import warnings
import pytest

warnings.filterwarnings("ignore", message=".*Axes3D.*")


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
