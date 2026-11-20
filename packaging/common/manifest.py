"""Ce qui compose le programme (version portable) : identique pour tous les systèmes. Ce qui est propre à un système
(lanceur, notice, icône…) est dans packaging/<système>/, voir packaging/common/system_base.py.

Deux familles de fichiers dans le dossier « programme » :
- le PROGRAMME (APP_ITEMS) : ce que contient le .zip, remplacé à chaque mise à jour ;
- les DONNÉES DE L'UTILISATEUR (USER_DATA) : identifiants, listes d'articles, traductions, profil du navigateur,
  Python et bibliothèques… Jamais dans le .zip, donc jamais écrasées quand on extrait une nouvelle version par-dessus.

Ce fichier est lu par prepare.py (sur l'ordinateur de l'utilisateur) et par build_package.py (pour fabriquer le .zip)."""
import fnmatch
from pathlib import Path

APP_NAME = "Traducteur d'articles"  # nom affiché (messages)
PYTHON_VERSION = "3.12"
PORT = 8710  # port de l'interface (webapp/__main__.py) ; s'il est pris par un autre programme, le suivant libre
PORTS = range(PORT, PORT + 10)

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


def is_user_data(relative: str) -> bool:
    first = relative.replace("\\", "/").split("/")[0]
    return any(fnmatch.fnmatch(first, pattern) for pattern in USER_DATA)


def _ignored(path: Path) -> bool:
    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in IGNORED)


# Dans packaging/, dossiers embarqués quel que soit le système ; les dossiers des AUTRES systèmes ne le sont pas.
SHARED_PACKAGING = {"common", "assets"}


def program_files(source: Path, system: str | None = None, tracked: set[str] | None = None) -> list[tuple[Path, str]]:
    """Fichiers du programme : [(fichier source, chemin relatif dans le dossier « programme »)].

    system : si donné (« windows », « linux »), le paquet de ce système ne contient de packaging/ que common/, assets/
    et packaging/<system>/ : rien d'un autre système.

    tracked : si donné (fabrication du paquet), seuls les fichiers suivis par git sont pris, pour ne jamais embarquer
    un fichier personnel posé par erreur dans un dossier du programme. Lève FileNotFoundError si un élément manque."""
    items = [(item, item) for item in APP_ITEMS]
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
            parts = rel.split("/")
            if system and parts[0] == "packaging" and len(parts) > 2 and parts[1] not in SHARED_PACKAGING | {system}:
                continue
            if tracked is not None and f.relative_to(source).as_posix() not in tracked:
                continue
            files.append((f, rel))
    version = source / VERSION_FILE
    if version.is_file():
        files.append((version, VERSION_FILE))
    return files
