"""Fabrique le paquet (version portable) à envoyer aux coéquipiers : dist/TraducteurWordPress-<Système>.zip

    python packaging/build_package.py windows

Contenu du .zip (un seul dossier, pour qu'il n'y ait qu'un fichier à double-cliquer) :
    TraducteurWordPress-Windows/
        Ouvrir le Traducteur.bat         <- le seul fichier à double-cliquer (prépare tout la première fois)
        LISEZ-MOI.txt
        programme/                       <- le programme (liste dans packaging/common/manifest.py) + VERSION ;
                                            Python, navigateur et données s'y ajoutent sur l'ordinateur de l'utilisateur

Garde-fous : seuls les fichiers suivis par git sont embarqués (jamais un fichier personnel posé dans un dossier du
programme), jamais de données de l'utilisateur (identifiants, liste d'articles, traductions), et refus de fabriquer
le paquet si l'interface n'a pas été reconstruite après une modification (cd frontend && npm run build)."""
import argparse
import datetime
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging" / "common"))
import manifest as M  # noqa: E402

# Par système : (nom affiché, installateur, notice). Mac et Linux : à écrire (voir packaging/<système>/README.md).
BOOTSTRAP = {
    "windows": ("Windows", f"packaging/windows/{M.LAUNCHER_NAME}", "packaging/windows/LISEZ-MOI.txt"),
}
TEXT_CRLF = {".bat", ".txt", ".cmd"}  # fichiers lus par Windows : fins de ligne Windows


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


def _data(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_CRLF:
        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return data


def build(platform: str, out_dir: Path, force: bool = False) -> Path:
    if platform not in BOOTSTRAP:
        raise SystemExit(f"Paquet {platform} pas encore prêt : seul Windows l'est pour l'instant.")
    if interface_is_stale() and not force:
        raise SystemExit("L'interface a été modifiée sans être reconstruite : lancez « cd frontend » puis « npm run build », "
                         "ou relancez avec --force.")
    label, launcher, notice = BOOTSTRAP[platform]
    tracked = tracked_files()
    files = M.program_files(ROOT, platform, tracked)
    untracked = sorted({f.relative_to(ROOT).as_posix() for f, _ in M.program_files(ROOT, platform)}
                       - {f.relative_to(ROOT).as_posix() for f, _ in files} - {M.VERSION_FILE})
    for rel in untracked:
        print(f"  Ignoré (pas suivi par git) : {rel}")
    folder = f"TraducteurWordPress-{label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{folder}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"{folder}/{Path(launcher).name}", _data(ROOT / launcher))
        z.writestr(f"{folder}/LISEZ-MOI.txt", b"\xef\xbb\xbf" + _data(ROOT / notice))  # BOM : accents corrects partout
        for src, rel in files:
            z.writestr(f"{folder}/programme/{rel}", _data(src))
        z.writestr(f"{folder}/programme/{M.VERSION_FILE}", version() + "\n")
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Fabrique le paquet à envoyer aux coéquipiers.")
    ap.add_argument("platform", choices=M.PLATFORMS)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--force", action="store_true", help="ignorer le contrôle de l'interface construite")
    args = ap.parse_args()
    path = build(args.platform, args.out, args.force)
    with zipfile.ZipFile(path) as z:
        n = len(z.namelist())
    print(f"Paquet prêt : {path} ({path.stat().st_size / 1e6:.1f} Mo, {n} fichiers)")


if __name__ == "__main__":
    main()
