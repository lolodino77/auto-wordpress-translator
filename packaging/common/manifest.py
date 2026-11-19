"""Ce qui compose le programme (version portable), commun à Windows, Mac et Linux.

Deux familles de fichiers dans le dossier « programme » :
- le PROGRAMME (APP_ITEMS + PLATFORM_ITEMS) : ce que contient le .zip, remplacé à chaque mise à jour ;
- les DONNÉES DE L'UTILISATEUR (USER_DATA) : identifiants, listes d'articles, traductions, profil du navigateur,
  Python et bibliothèques… Jamais dans le .zip, donc jamais écrasées quand on extrait une nouvelle version par-dessus.

Ce fichier est lu par prepare.py (sur l'ordinateur de l'utilisateur) et par build_package.py (pour fabriquer le .zip)."""
import fnmatch
import sys
from pathlib import Path

APP_NAME = "Traducteur d'articles"  # nom affiché (icône, messages)
SHORTCUT_NAME = "Traducteur d'articles"  # icône créée à côté du lanceur
LAUNCHER_NAME = "Ouvrir le Traducteur.bat"  # le fichier à double-cliquer (Windows), à la racine du dossier extrait
PYTHON_VERSION = "3.12"
PORT = 8710  # port de l'interface (webapp/__main__.py) ; s'il est pris par un autre programme, le suivant libre
PORTS = range(PORT, PORT + 10)

PLATFORMS = ("windows", "macos", "linux")
SUPPORTED = {"windows"}  # testés de bout en bout ; macos et linux : architecture prête, lanceurs à écrire

# Le programme : remplacé à chaque mise à jour.
APP_ITEMS = [
    # code de la traduction
    "agent.py", "bible.py", "extract.py", "inputs.py", "llm_browser.py", "pipeline.py", "rules.py", "specs.py",
    "templating.py", "wp.py", "wp_selfhosted.py",
    # réglages et règles de la revue
    "config.toml", "bible_abbreviations.toml", "requirements.txt", "articles_templates", "spec",
    # interface (code du serveur + interface déjà construite) et préparation (première ouverture, réparation)
    "webapp", "packaging",
]
# Fichiers propres à un système, dans le dossier « programme » : {chemin dans le dépôt: chemin dans le paquet}.
# (Windows : le lanceur est à la racine du dossier extrait, voir build_package.py ; rien d'autre ici.)
PLATFORM_ITEMS = {
    "windows": {},
    "macos": {
        "Lancer le traducteur.command": "Lancer le traducteur.command",
        "lancer-le-traducteur.sh": "lancer-le-traducteur.sh",
    },
    "linux": {"lancer-le-traducteur.sh": "lancer-le-traducteur.sh"},
}
# Fichier écrit par build_package.py : version du paquet (une nouvelle version relance la préparation).
VERSION_FILE = "VERSION"

# Données de l'utilisateur, dans le dossier « programme » : jamais dans le .zip, donc jamais écrasées.
USER_DATA = [
    "input", "output", "browser_profile", "wp_credentials.json", "wp_token.json", "agent.log", "state-*.db",
    ".venv", "runtime", "installation.json", "traducteur*.log", "gemini_session.json",
]
IGNORED = ["__pycache__", "*.pyc", ".DS_Store", "Thumbs.db"]

# Liste vide créée à la première ouverture (jamais celle du développeur).
EMPTY_CSV = "url,tags,illustration\n"


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def venv_python(root: Path, platform: str) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if platform == "windows" else "bin/python")


def is_user_data(relative: str) -> bool:
    first = relative.replace("\\", "/").split("/")[0]
    return any(fnmatch.fnmatch(first, pattern) for pattern in USER_DATA)


def _ignored(path: Path) -> bool:
    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in IGNORED)


def program_files(source: Path, platform: str, tracked: set[str] | None = None) -> list[tuple[Path, str]]:
    """Fichiers du programme : [(fichier source, chemin relatif dans le dossier « programme »)].

    tracked : si donné (fabrication du paquet), seuls les fichiers suivis par git sont pris, pour ne jamais embarquer
    un fichier personnel posé par erreur dans un dossier du programme. Lève FileNotFoundError si un élément manque."""
    items = [(item, item) for item in APP_ITEMS] + list(PLATFORM_ITEMS[platform].items())
    files: list[tuple[Path, str]] = []
    for src_rel, dst_rel in items:
        src = source / src_rel
        if src.is_file():
            candidates = [(src, dst_rel)]
        elif src.is_dir():
            candidates = [(f, (Path(dst_rel) / f.relative_to(src)).as_posix()) for f in sorted(src.rglob("*")) if f.is_file()]
        else:
            raise FileNotFoundError(f"élément du programme introuvable : {src_rel}")
        for f, rel in candidates:
            if _ignored(f.relative_to(source)) or is_user_data(rel):
                continue
            if tracked is not None and f.relative_to(source).as_posix() not in tracked:
                continue
            files.append((f, rel))
    version = source / VERSION_FILE
    if version.is_file():
        files.append((version, VERSION_FILE))
    return files
