"""Fabrique le paquet (version portable) à envoyer aux coéquipiers : dist/TraducteurWordPress-<Système>.zip

    python packaging/build_package.py windows      (ou linux)

Contenu du .zip (un seul dossier, pour qu'il n'y ait qu'un fichier à double-cliquer) :
    TraducteurWordPress-<Système>/
        <lanceur>                        <- le seul fichier à double-cliquer (prépare tout la première fois) :
                                            « Ouvrir le Traducteur.bat » (Windows), « ouvrir-le-traducteur.sh » (Linux)
        LISEZ-MOI.txt
        programme/                       <- le programme (liste dans packaging/common/manifest.py) + VERSION ;
                                            Python, navigateur et données s'y ajoutent sur l'ordinateur de l'utilisateur

Ce qui est propre à un système (lanceur, notice, fins de ligne, droit d'exécution) vient de packaging/<système>/system.py :
ce script n'en connaît aucun. Il tourne sur n'importe quel système (le paquet Linux se fabrique aussi sous Windows).

Garde-fous : seuls les fichiers suivis par git sont embarqués (jamais un fichier personnel posé dans un dossier du
programme), jamais de données de l'utilisateur (identifiants, liste d'articles, traductions), rien d'un autre système,
et refus de fabriquer le paquet si l'interface n'a pas été reconstruite après une modification (cd frontend && npm run build)."""
import argparse
import datetime
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging" / "common"))
import manifest as M  # noqa: E402
from system_base import System, available, load  # noqa: E402

FILE_MODE = 0o644  # droits Unix des fichiers dans le .zip (Linux et Mac les appliquent à l'extraction)
EXEC_MODE = 0o755
REGULAR_FILE = 0o100000


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def tracked_files() -> set[str]:
    return set(git("ls-files", "-z").split("\0")) - {""}


def version() -> str:
    try:
        commit = git("rev-parse", "--short", "HEAD").strip()
        dirty = bool(git("status", "--porcelain", "--untracked-files=no").strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, dirty = "inconnu", False
    return f"{datetime.date.today():%Y-%m-%d} ({commit}{', modifié' if dirty else ''})"


def interface_is_stale() -> bool:
    """Vrai si le code de l'interface (frontend/src) est plus récent que l'interface construite (webapp/static)."""
    built = ROOT / "webapp" / "static" / "index.html"
    sources = [f for f in (ROOT / "frontend" / "src").rglob("*") if f.is_file()] + list((ROOT / "frontend" / "public").rglob("*.*"))
    return not built.exists() or (bool(sources) and max(f.stat().st_mtime for f in sources) > built.stat().st_mtime + 2)


def _data(path: Path, system: System) -> bytes:
    """Contenu du fichier, fins de ligne converties pour le système s'il s'agit d'un fichier texte qu'il lit."""
    data = path.read_bytes()
    if path.suffix.lower() in system.TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\n", system.EOL)
    return data


def _write(z: zipfile.ZipFile, name: str, data: bytes | str, executable: bool = False) -> None:
    """Écrit un fichier avec des droits Unix explicites (create_system = Unix) : sans cela, un .zip fabriqué sous
    Windows perd le droit d'exécution du lanceur quand il est extrait sous Linux. Sans effet sous Windows."""
    info = zipfile.ZipInfo(name, date_time=datetime.datetime.now().timetuple()[:6])
    info.create_system = 3
    info.external_attr = (REGULAR_FILE | (EXEC_MODE if executable else FILE_MODE)) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data, compresslevel=9)


def build(platform: str, out_dir: Path, force: bool = False) -> Path:
    try:
        system = load(platform)
    except LookupError:
        raise SystemExit(f"Paquet {platform} pas encore prêt. Systèmes disponibles : {', '.join(available())}.")
    if interface_is_stale() and not force:
        raise SystemExit("L'interface a été modifiée sans être reconstruite : lancez « cd frontend » puis « npm run build », "
                         "ou relancez avec --force.")
    tracked = tracked_files()
    files = M.program_files(ROOT, system.NAME, tracked)
    untracked = sorted({f.relative_to(ROOT).as_posix() for f, _ in M.program_files(ROOT, system.NAME)}
                       - {f.relative_to(ROOT).as_posix() for f, _ in files} - {M.VERSION_FILE})
    for rel in untracked:
        print(f"  Ignoré (pas suivi par git) : {rel}")
    folder = f"TraducteurWordPress-{system.LABEL}"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{folder}.zip"
    notice = (b"\xef\xbb\xbf" if system.NOTICE_BOM else b"") + _data(system.folder / system.NOTICE, system)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        _write(z, f"{folder}/{system.LAUNCHER}", _data(system.folder / system.LAUNCHER, system), system.EXECUTABLE)
        _write(z, f"{folder}/{system.NOTICE}", notice)
        for src, rel in files:
            _write(z, f"{folder}/programme/{rel}", _data(src, system))
        _write(z, f"{folder}/programme/{M.VERSION_FILE}", version() + "\n")
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Fabrique le paquet à envoyer aux coéquipiers.")
    ap.add_argument("platform", choices=available())
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--force", action="store_true", help="ignorer le contrôle de l'interface construite")
    args = ap.parse_args()
    path = build(args.platform, args.out, args.force)
    with zipfile.ZipFile(path) as z:
        n = len(z.namelist())
    print(f"Paquet prêt : {path} ({path.stat().st_size / 1e6:.1f} Mo, {n} fichiers)")


if __name__ == "__main__":
    main()
