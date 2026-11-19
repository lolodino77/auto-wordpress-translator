"""Préparation du Traducteur d'articles, VERSION PORTABLE : tout reste dans le dossier extrait du .zip.

Commun à Windows, Mac et Linux : seul le petit lanceur (packaging/<système>/) change. Le lanceur vérifie d'abord, très
vite, si le programme est prêt (« --check ») ; sinon il télécharge l'outil « uv » (qui fournit Python sans rien
installer sur l'ordinateur) et lance la préparation :

    uv run --no-project --python 3.12 programme/packaging/common/prepare.py --root programme --uv <uv>

Rien n'est écrit en dehors du dossier : Python (programme/runtime/python), bibliothèques (programme/.venv), navigateur
(programme/runtime/browsers), données (programme/input, output…). Désinstaller = supprimer le dossier. La préparation
se relance toute seule après une mise à jour (nouvelle version) ou si le dossier a été déplacé ; elle ne perd jamais
les données. N'utilise que la bibliothèque standard de Python."""
import argparse
import base64
import datetime
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as M  # noqa: E402

STATE_FILE = "installation.json"
NOT_READY = 10  # code de sortie de --check : préparation nécessaire


class PrepareError(Exception):
    """Erreur expliquée à l'utilisateur (message en français simple)."""


def step(n: int, total: int, text: str) -> None:
    print(f"\n  [{n}/{total}] {text}", flush=True)


def info(text: str) -> None:
    print(f"        {text}", flush=True)


def same_dir(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# --- est-ce prêt ? (vérification rapide, à chaque ouverture) ----------------------------------------------------
def read_version(root: Path) -> str:
    f = root / M.VERSION_FILE
    return f.read_text(encoding="utf-8").strip() if f.is_file() else "version de développement"


def requirements_hash(root: Path) -> str:
    return hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()[:16]


def is_ready(root: Path) -> bool:
    """Prêt = préparé ici même (dossier non déplacé), pour cette version et ces bibliothèques."""
    try:
        state = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (same_dir(state.get("folder", ""), root) and state.get("version") == read_version(root)
            and state.get("requirements") == requirements_hash(root)
            and M.venv_python(root, M.current_platform()).exists())


# --- 1. données de l'utilisateur ---------------------------------------------------------------------------------
def ensure_user_folders(root: Path) -> None:
    """À la première ouverture : une liste d'articles vide (jamais celle du développeur)."""
    md_dir = root / "input" / "articles_md"
    md_dir.mkdir(parents=True, exist_ok=True)
    csv = root / "input" / "articles.csv"
    if not csv.exists():
        csv.write_text(M.EMPTY_CSV, encoding="utf-8")


def check_spec_names(root: Path) -> None:
    """Les PDF cités par leur nom dans config.toml doivent exister tels quels (un .zip mal décompressé peut abîmer
    les accents des noms de fichiers : la coupe des passages hors sujet ne s'appliquerait plus)."""
    cfg = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
    spec_dir = root / cfg["specs"]["dir"]
    missing = [name for name in cfg["specs"].get("exclude_after", {}) if not (spec_dir / name).is_file()]
    if missing:
        raise PrepareError(
            "Fichier de règles introuvable : " + ", ".join(missing) + ". Le .zip a peut-être été mal décompressé : "
            "supprimez le dossier extrait, puis refaites clic droit sur le .zip > « Extraire tout… ».")


def location_warnings(root: Path) -> list[str]:
    """Emplacements qui posent problème sans être bloquants."""
    warnings = []
    if "onedrive" in str(root).lower():
        warnings.append("Ce dossier est dans OneDrive : environ 700 Mo seront synchronisés, ce qui peut ralentir "
                        "l'ordinateur. Mieux vaut l'extraire ailleurs, par exemple dans C:\\Traducteur.")
    if len(str(root)) > 90:
        warnings.append("Le chemin de ce dossier est très long : si la préparation échoue, extrayez le .zip plus près "
                        "de la racine du disque, par exemple dans C:\\Traducteur.")
    return warnings


# --- 2. Python et bibliothèques -----------------------------------------------------------------------------
def uv_env(root: Path) -> dict:
    env = dict(os.environ)
    env.update({
        "UV_PYTHON_INSTALL_DIR": str(root / "runtime" / "python"),  # Python rangé dans le dossier
        "UV_PYTHON_PREFERENCE": "only-managed",  # jamais un Python déjà présent (Anaconda…) : tout le monde pareil
        "UV_SYSTEM_CERTS": "1",  # certificats du système : marche derrière un antivirus ou un proxy qui inspecte HTTPS
        "UV_LINK_MODE": "copy",
    })
    return env


def browsers_dir(root: Path) -> Path:
    return root / "runtime" / "browsers"


def _works(python: Path) -> bool:
    try:
        return subprocess.run([str(python), "-c", "import sys"], capture_output=True, timeout=60).returncode == 0
    except OSError:
        return False


def run(cmd: list, error: str, **kw) -> None:
    if subprocess.run([str(c) for c in cmd], **kw).returncode != 0:
        raise PrepareError(error)


def remove_tree(path: Path) -> None:
    """Supprime un dossier, même si certains chemins dépassent la limite historique de Windows (260 caractères) :
    les bibliothèques Python contiennent des fichiers très profonds (lxml…), et le dossier peut être loin de la racine."""
    target = str(path.resolve())
    if sys.platform.startswith("win") and not target.startswith("\\\\?\\"):
        target = "\\\\?\\" + target
    shutil.rmtree(target)


def install_python(root: Path, uv: Path, platform: str) -> Path:
    python = M.venv_python(root, platform)
    env = uv_env(root)
    if not _works(python):  # première fois, ou dossier déplacé (l'environnement Python garde l'ancien chemin)
        if (root / ".venv").exists():
            remove_tree(root / ".venv")
        run([uv, "venv", "--quiet", root / ".venv", "--python", M.PYTHON_VERSION], "Python n'a pas pu être installé.",
            env=env)
    run([uv, "pip", "install", "--python", python, "-r", root / "requirements.txt"],
        "Les bibliothèques du programme n'ont pas pu être installées. Vérifiez la connexion Internet ; si le "
        "Traducteur est ouvert, fermez-le (bouton « Quitter ») ; puis relancez.", env=env)
    return python


# --- 3. navigateur utilisé pour la traduction (Chromium, piloté par Playwright) ------------------------------
def install_browser(python: Path, root: Path) -> None:
    # --no-shell : pas la variante « sans fenêtre » (124 Mo), inutile ici (config.toml : headless = false)
    cmd = [str(python), "-m", "playwright", "install", "--no-shell", "chromium"]
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(browsers_dir(root)))  # dans le dossier : vraiment portable
    if subprocess.run(cmd, cwd=root, env=env).returncode == 0:
        return
    info("Nouvel essai avec les certificats de l'ordinateur (antivirus ou réseau d'entreprise)…")
    env["NODE_OPTIONS"] = "--use-system-ca"
    if subprocess.run(cmd, cwd=root, env=env).returncode != 0:
        raise PrepareError("Le navigateur utilisé pour la traduction n'a pas pu être téléchargé (connexion Internet ?).")


# --- 4. vérification ----------------------------------------------------------------------------------------
def check_program(python: Path, root: Path) -> None:
    check_spec_names(root)
    code = "import webapp.server, agent, pipeline, extract, wp_selfhosted; print('ok')"
    r = subprocess.run([str(python), "-c", code], cwd=root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0 or "ok" not in r.stdout:
        print(r.stderr[-2000:])
        raise PrepareError("Le programme ne démarre pas (détail ci-dessus).")


# --- 5. icône (propre à chaque système) ---------------------------------------------------------------------
def _ps(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def create_icon_windows(root: Path) -> Path:
    """Raccourci « Traducteur d'articles », avec l'icône du programme, à côté du lanceur (un .bat ne peut pas avoir
    d'icône). Recréé à chaque préparation : il suit donc le dossier s'il a été déplacé."""
    folder = root.parent
    link = folder / f"{M.SHORTCUT_NAME}.lnk"
    script = f"""
$ErrorActionPreference = 'Stop'
$l = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps(link)})
$l.TargetPath = {_ps(folder / M.LAUNCHER_NAME)}
$l.WorkingDirectory = {_ps(folder)}
$l.IconLocation = {_ps(str(root / "packaging" / "assets" / "traducteur.ico") + ",0")}
$l.Description = {_ps("Ouvrir le " + M.APP_NAME)}
$l.Save()
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                       capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", errors="replace")[-1500:])
        raise PrepareError(f"L'icône n'a pas pu être créée (le programme reste utilisable avec « {M.LAUNCHER_NAME} »).")
    return link


def create_icon(root: Path, platform: str) -> Path | None:
    if platform == "windows":
        return create_icon_windows(root)
    return None  # Mac, Linux : à écrire (voir packaging/<système>/README.md)


# --- programme principal -----------------------------------------------------------------------------------
def find_instance(root: Path) -> dict | None:
    """Le Traducteur de CE dossier est-il ouvert ? Retourne son identité ({"root", "running"…}) ou None.
    Un autre programme, ou un autre exemplaire du Traducteur, ne compte pas : il ne gêne en rien."""
    for port in M.PORTS:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/identity", timeout=3) as r:
                data = json.load(r)
        except Exception:
            continue
        if data.get("app") == "traducteur-wordpress" and data.get("root") and same_dir(data["root"], root):
            return data
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Prépare le {M.APP_NAME} dans son dossier (version portable).")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="dossier « programme »")
    ap.add_argument("--uv", type=Path, default=Path(shutil.which("uv") or "uv"), help="outil uv")
    ap.add_argument("--check", action="store_true", help=f"vérification rapide : code {NOT_READY} si préparation nécessaire")
    ap.add_argument("--no-icon", action="store_true", help="ne pas créer l'icône (tests)")
    ap.add_argument("--ignore-running", action="store_true", help="ne pas vérifier si le programme est ouvert")
    ap.add_argument("--experimental", action="store_true", help="autoriser un système pas encore testé")
    args = ap.parse_args()
    root = args.root.resolve()

    if args.check:
        return 0 if is_ready(root) else NOT_READY
    platform = M.current_platform()
    if platform not in M.SUPPORTED and not args.experimental:
        print(f"\n  Ce système ({platform}) n'est pas encore pris en charge : seul Windows l'est pour l'instant.")
        return 2
    version = read_version(root)
    first = not (root / STATE_FILE).exists()
    print(f"\n  {M.APP_NAME} : {version}\n  Dossier : {root.parent}")
    print("  " + ("Première ouverture : préparation du programme (quelques minutes, une seule fois)." if first else
                  "Mise à jour ou dossier déplacé : préparation du programme (moins d'une minute en général)."))
    for w in location_warnings(root):
        print(f"\n  ATTENTION : {w}")
    total = 4 if args.no_icon else 5
    try:
        instance = None if args.ignore_running else find_instance(root)
        if instance and instance.get("running"):
            raise PrepareError("Une traduction est en cours dans le Traducteur : attendez qu'elle se termine "
                               "(menu « Traduction »), puis relancez.")
        step(1, total, "Vérification des fichiers")
        check_spec_names(root)
        ensure_user_folders(root)

        step(2, total, "Python et ses bibliothèques")
        python = install_python(root, args.uv, platform)

        step(3, total, "Navigateur utilisé pour la traduction (environ 200 Mo la première fois)")
        install_browser(python, root)

        step(4, total, "Vérification du programme")
        check_program(python, root)
        info("Le programme démarre correctement.")

        if not args.no_icon:
            step(5, total, "Icône")
            create_icon(root, platform)
            info(f"Icône « {M.SHORTCUT_NAME} » placée à côté de « {M.LAUNCHER_NAME} ».")

        (root / STATE_FILE).write_text(json.dumps({
            "version": version, "folder": str(root), "requirements": requirements_hash(root), "systeme": platform,
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except PrepareError as e:
        print(f"\n  ÉCHEC : {e}")
        return 1
    print("\n  ============================================================")
    print("    Le Traducteur est prêt ! Il s'ouvre dans votre navigateur.")
    print(f"    Les prochaines fois : double-cliquez sur l'icône « {M.SHORTCUT_NAME} » de ce dossier")
    print("    (vous pouvez la glisser sur le Bureau).")
    print("  ============================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
