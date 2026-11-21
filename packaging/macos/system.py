"""Mac : tout ce qui est propre au Mac dans la version portable (voir packaging/common/system_base.py).

Visé : macOS récent, Mac Apple (M1, M2…) ou Intel. Le lanceur « Ouvrir le Traducteur.command » s'ouvre dans le
Terminal d'un double-clic ; après la préparation, une petite application « Traducteur d'articles.app », fabriquée sur
le Mac lui-même dans le dossier, ouvre le Traducteur sans fenêtre de Terminal."""
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from system_base import PrepareError, System

APP_NAME = "Traducteur d'articles"  # application créée à côté du lanceur : « Traducteur d'articles.app »
APP_EXECUTABLE = "traducteur"  # programme de l'application (Contents/MacOS/traducteur : un script sh)
BUNDLE_ID = "fr.traducteur-articles.portable"
# Disques sans liens symboliques ni droits Unix (clés USB, disques formatés pour Windows) : Python ne peut pas y être
# préparé.
FOREIGN_FS = {"msdos", "exfat", "ntfs", "ufsd_ntfs", "tuxera_ntfs"}


def sh_quote(text) -> str:
    """Un texte entre apostrophes pour sh, quel qu'il soit (espaces, apostrophes, $…)."""
    return "'" + str(text).replace("'", "'\\''") + "'"


def _mount_of(path: Path) -> tuple[str, set[str]]:
    """(type de système de fichiers, options) du volume qui contient `path`, d'après la commande `mount`
    (lignes du type « /dev/disk4s1 on /Volumes/CLÉ USB (msdos, local, nodev, nosuid, noowners) »)."""
    try:
        out = subprocess.run(["mount"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return "", set()
    target = str(path.resolve())
    best, fs, opts = "", "", set()
    for line in out.splitlines():
        m = re.match(r"^.+? on (.+) \(([^()]*)\)$", line)
        if not m:
            continue
        mount, details = m.group(1), [d.strip() for d in m.group(2).split(",")]
        if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) >= len(best):
            best, fs, opts = mount, details[0], set(details[1:])
    return fs, opts


def in_icloud(root: Path, home: Path | None = None) -> bool:
    """Vrai si le dossier est synchronisé par iCloud Drive : directement dans iCloud Drive, ou dans Bureau/Documents
    quand l'option « Dossiers Bureau et Documents » d'iCloud est activée."""
    home = home or Path.home()
    cloud = home / "Library" / "Mobile Documents"
    target = root.resolve()
    if target == cloud or cloud in target.parents:
        return True
    docs = cloud / "com~apple~CloudDocs"
    for name in ("Desktop", "Documents"):
        local = home / name
        if (docs / name).is_dir() and (target == local or local in target.parents):
            return True
    return False


def app_script(folder: Path, launcher: str) -> str:
    """Programme de « Traducteur d'articles.app » : lance le lanceur rangé à côté de l'application (le dossier a pu
    être déplacé), sinon celui de l'endroit où la préparation a été faite (application glissée ailleurs)."""
    return "\n".join([
        "#!/bin/sh",
        f"# {APP_NAME} : ouvre le Traducteur (version portable), sans fenêtre de Terminal.",
        'ICI=$(CDPATH="" cd -- "$(dirname -- "$0")/../../.." && pwd -P)',
        f'LANCEUR="$ICI/{launcher}"',
        f'[ -f "$LANCEUR" ] || LANCEUR={sh_quote(folder / launcher)}',
        'exec /bin/sh "$LANCEUR"',
        "",
    ])


def info_plist(icon: bool) -> bytes:
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_EXECUTABLE,
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSUIElement": True,  # pas d'icône dans le Dock pendant le lancement (le Traducteur est dans le navigateur)
    }
    if icon:
        info["CFBundleIconFile"] = APP_EXECUTABLE
    return plistlib.dumps(info)


def make_icns(png: Path, icns: Path) -> bool:
    """Icône de l'application (.icns) fabriquée à partir du .png, avec les outils fournis avec macOS (sips, iconutil).
    Faux s'ils manquent : l'application marche quand même, avec l'icône par défaut."""
    if not (shutil.which("sips") and shutil.which("iconutil")):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "traducteur.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                px = str(size * scale)
                r = subprocess.run(["sips", "-z", px, px, str(png), "--out", str(iconset / name)], capture_output=True)
                if r.returncode != 0:
                    return False
        return subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                              capture_output=True).returncode == 0


def chromium_binary(root: Path) -> Path | None:
    found = sorted((root / "runtime" / "browsers").glob("chromium-*/chrome-mac*/*.app/Contents/MacOS/*"))
    return found[-1] if found else None


def google_chrome() -> str | None:
    for base in ("/Applications", str(Path.home() / "Applications")):
        exe = Path(base) / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
        if exe.is_file():
            return str(exe)
    return None


def browser_starts(binary: Path) -> bool:
    try:
        return subprocess.run([str(binary), "--version"], capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class MacOS(System):
    NAME = "macos"
    LABEL = "Mac"
    LAUNCHER = "Ouvrir le Traducteur.command"
    TEXT_SUFFIXES = frozenset({".command", ".txt"})  # fins de ligne Unix (un .command en CRLF ne s'exécute pas)
    EOL = b"\n"
    EXECUTABLE = True
    EXTRACT_HINT = ("supprimez le dossier extrait, puis double-cliquez de nouveau sur le .zip dans le Finder pour "
                    "l'extraire.")

    def location_warnings(self, root: Path) -> list[str]:
        warnings = []
        if in_icloud(root):
            warnings.append("Ce dossier est synchronisé par iCloud Drive : environ 700 Mo seront envoyés dans iCloud, "
                            "et le Mac peut retirer des fichiers du disque pour gagner de la place, ce qui casserait "
                            "le programme. Mieux vaut le déplacer dans votre dossier personnel (dans le Finder : menu "
                            "Aller > Départ), par exemple dans un dossier « Traducteur ».")
        fs, opts = _mount_of(root)
        if fs in FOREIGN_FS:
            warnings.append(f"Ce dossier est sur un disque au format {fs} (clé USB, disque pour Windows…), qui ne "
                            "permet pas d'y préparer Python. Si la préparation échoue, déplacez le dossier dans votre "
                            "dossier personnel.")
        elif "noexec" in opts:
            warnings.append("Ce disque interdit de lancer des programmes : déplacez le dossier dans votre dossier "
                            "personnel.")
        return warnings

    def check_system(self, root: Path, python: Path) -> list[str]:
        """Le navigateur téléchargé (Chromium) doit démarrer sur cette version de macOS. Google Chrome, s'il est
        installé, est utilisé à sa place."""
        binary = chromium_binary(root)
        if binary is None or browser_starts(binary):
            return []
        if google_chrome():
            return ["Le navigateur de secours ne démarre pas sur ce Mac. Ce n'est pas gênant : le Traducteur utilise "
                    "Google Chrome, installé sur ce Mac."]
        raise PrepareError("Le navigateur utilisé pour la traduction ne démarre pas sur ce Mac (version de macOS trop "
                           "ancienne ?). Le plus simple : installez Google Chrome (gratuit : google.com/chrome), qui "
                           "sert aussi à se connecter à Gemini, ou mettez macOS à jour (menu Pomme > Réglages "
                           "Système > Général > Mise à jour de logiciels). Puis relancez « Ouvrir le Traducteur ».")

    def create_icon(self, root: Path) -> str:
        """« Traducteur d'articles.app » à côté du lanceur : une vraie application (icône du programme, double-clic,
        glissable dans le Dock) qui ouvre le Traducteur sans fenêtre de Terminal. Fabriquée sur ce Mac, elle n'est pas
        « en quarantaine » : macOS l'ouvre sans avertissement."""
        folder = root.parent
        app = folder / f"{APP_NAME}.app"
        try:
            if app.exists():
                shutil.rmtree(app)
            contents = app / "Contents"
            (contents / "MacOS").mkdir(parents=True)
            (contents / "Resources").mkdir()
            icon = make_icns(root / "packaging" / "assets" / "traducteur.png",
                             contents / "Resources" / f"{APP_EXECUTABLE}.icns")
            (contents / "Info.plist").write_bytes(info_plist(icon))
            exe = contents / "MacOS" / APP_EXECUTABLE
            exe.write_text(app_script(folder, self.LAUNCHER), encoding="utf-8")
            exe.chmod(0o755)
            os.utime(app)  # le Finder relit l'application (et son icône)
        except OSError as e:
            raise PrepareError(f"L'application « {APP_NAME} » n'a pas pu être créée ({e}) : le programme reste "
                               f"utilisable avec « {self.LAUNCHER} ».") from e
        return f"Application « {APP_NAME} » placée à côté de « {self.LAUNCHER} »."

    def ready_message(self) -> list[str]:
        return [f"Les prochaines fois : double-cliquez sur « {APP_NAME} » dans ce dossier",
                "(sans fenêtre de Terminal ; vous pouvez la glisser dans le Dock)."]


SYSTEM = MacOS()
