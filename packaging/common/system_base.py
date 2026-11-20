"""Ce que chaque système (Windows, Linux, plus tard Mac) doit fournir à la version portable.

Tout ce qui est propre à un système vit dans SON dossier, et nulle part ailleurs :

    packaging/<système>/
        system.py        une classe qui hérite de System (ci-dessous) : icône, avertissements, vérifications…
        <lanceur>        le fichier à double-cliquer, mis à la racine du dossier extrait (System.LAUNCHER)
        LISEZ-MOI.txt    la notice des coéquipiers, mise à la racine du dossier extrait (System.NOTICE)

Le code commun (prepare.py, build_package.py) ne teste jamais « si Windows… sinon… » : il demande au système chargé
par load(). Ajouter un système = ajouter un dossier, sans toucher aux autres. N'utilise que la bibliothèque standard."""
import importlib.util
import shutil
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent.parent  # dossier « packaging »


class PrepareError(Exception):
    """Erreur expliquée à l'utilisateur (message en français simple)."""


class System:
    """Valeurs par défaut ; chaque système redéfinit ce qui le concerne."""

    NAME = ""  # "windows", "linux" : nom du dossier packaging/<NAME>
    LABEL = ""  # "Windows", "Linux" : le paquet s'appelle TraducteurWordPress-<LABEL>.zip
    LAUNCHER = ""  # fichier à double-cliquer (dans packaging/<NAME>/), à la racine du dossier extrait
    NOTICE = "LISEZ-MOI.txt"  # notice (dans packaging/<NAME>/), à la racine du dossier extrait
    # Fichiers texte du paquet (par extension) dont les fins de ligne sont converties pour ce système.
    TEXT_SUFFIXES: frozenset[str] = frozenset()
    EOL = b"\n"
    NOTICE_BOM = False  # marque UTF-8 en tête de la notice (le Bloc-notes de Windows en a besoin pour les accents)
    EXECUTABLE = False  # le lanceur doit-il porter le droit d'exécution dans le .zip ?
    # Comment bien extraire le .zip (message quand des fichiers sont abîmés par une mauvaise décompression).
    EXTRACT_HINT = "supprimez le dossier extrait, puis extrayez de nouveau le .zip."

    @property
    def folder(self) -> Path:
        return PACKAGING / self.NAME

    def venv_python(self, root: Path) -> Path:
        """Python de l'environnement du programme (programme/.venv)."""
        return root / ".venv" / "bin" / "python"

    def location_warnings(self, root: Path) -> list[str]:
        """Emplacements du dossier qui posent problème sans être bloquants."""
        return []

    def remove_tree(self, path: Path) -> None:
        shutil.rmtree(path)

    def check_before_browser(self, root: Path, python: Path) -> None:
        """Vérifications propres au système avant le téléchargement du navigateur. Lève PrepareError si l'outil de
        téléchargement ne peut pas fonctionner."""

    def check_system(self, root: Path, python: Path) -> list[str]:
        """Vérifications propres au système, après l'installation du navigateur. Retourne des avertissements ; lève
        PrepareError si le programme ne peut pas fonctionner."""
        return []

    def create_icon(self, root: Path) -> str:
        """Crée l'icône (recréée à chaque préparation : elle suit le dossier s'il est déplacé). Retourne la phrase qui
        dit où elle est. Lève PrepareError en cas d'échec."""
        raise PrepareError("pas d'icône pour ce système")

    def ready_message(self) -> list[str]:
        """Lignes affichées quand le programme est prêt : comment l'ouvrir les prochaines fois."""
        return [f"Les prochaines fois : double-cliquez sur « {self.LAUNCHER} »."]


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def available() -> list[str]:
    """Systèmes prêts : ceux qui ont un packaging/<système>/system.py."""
    return sorted(p.parent.name for p in PACKAGING.glob("*/system.py") if p.parent.name != "common")


def load(name: str | None = None) -> System:
    """Le système demandé (par défaut celui de cet ordinateur). Lève LookupError s'il n'est pas encore pris en charge."""
    name = name or current_platform()
    path = PACKAGING / name / "system.py"
    if name == "common" or not path.is_file():
        raise LookupError(name)
    module_name = f"traducteur_system_{name}"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module.SYSTEM
