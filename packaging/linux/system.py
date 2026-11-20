"""Linux : tout ce qui est propre à Linux dans la version portable (voir packaging/common/system_base.py).

Visé : toute distribution de bureau récente avec la bibliothèque C « glibc » (Ubuntu, Debian, Mint, Fedora, openSUSE,
Arch, Manjaro, Pop!_OS, elementary, Zorin…), processeur Intel/AMD 64 bits ou ARM 64 bits. Pas Alpine (musl) : le
navigateur piloté par Playwright n'y fonctionne pas."""
import os
import shutil
import subprocess
from pathlib import Path

from system_base import PrepareError, System

ICON_NAME = "Traducteur d'articles"  # fichier .desktop à côté du lanceur, et entrée du menu des applications
MENU_FILE = "traducteur-articles.desktop"  # dans ~/.local/share/applications
# Systèmes de fichiers sans liens symboliques ni droit d'exécution (clés USB, partitions Windows) : Python ne peut
# pas y être préparé.
FOREIGN_FS = {"vfat", "msdos", "exfat", "ntfs", "ntfs3", "fuseblk"}


def _mount_of(path: Path) -> tuple[str, set[str]]:
    """(type de système de fichiers, options) du montage qui contient `path`, d'après /proc/mounts."""
    best, fs, opts = "", "", set()
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", set()
    target = str(path.resolve())
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        mount = parts[1].replace("\\040", " ")
        if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) >= len(best):
            best, fs, opts = mount, parts[2], set(parts[3].split(","))
    return fs, opts


def desktop_exec_arg(path: Path) -> str:
    """Un chemin comme argument de la clé Exec d'un fichier .desktop (spécification freedesktop : guillemets,
    caractères réservés échappés, puis échappement de la valeur elle-même)."""
    quoted = '"' + "".join("\\" + c if c in '"`$\\' else c for c in str(path)) + '"'
    return quoted.replace("\\", "\\\\").replace("%", "%%")


def desktop_value(text) -> str:
    return str(text).replace("\\", "\\\\").replace("\n", " ")


def desktop_entry(folder: Path, launcher: str, icon: Path) -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={ICON_NAME}",
        "Comment=Traduire des articles et les envoyer en brouillon dans WordPress",
        f"Exec={desktop_exec_arg(folder / launcher)}",
        f"Path={desktop_value(folder)}",
        f"Icon={desktop_value(icon)}",
        "Terminal=false",
        "Categories=Office;",
        "StartupNotify=false",
        "",
    ])


def chromium_binary(root: Path) -> Path | None:
    found = sorted((root / "runtime" / "browsers").glob("chromium-*/chrome-linux*/chrome"))
    return found[-1] if found else None


def missing_libraries(binary: Path) -> list[str]:
    """Bibliothèques du système dont le navigateur a besoin et qui manquent (d'après ldd)."""
    if not shutil.which("ldd"):
        return []
    try:
        out = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({line.split("=>")[0].strip() for line in out.splitlines() if "not found" in line})


# Petites bibliothèques dont a besoin l'outil de téléchargement du navigateur (Node.js de Playwright), absentes de
# certaines installations minimales : nom du paquet selon le gestionnaire de paquets de la distribution.
NODE_LIBRARIES = {"libatomic.so.1": {"apt-get": "libatomic1", "dnf": "libatomic", "zypper": "libatomic1",
                                     "pacman": "gcc-libs"}}
INSTALL = {"apt-get": "sudo apt install", "dnf": "sudo dnf install", "zypper": "sudo zypper install",
           "pacman": "sudo pacman -S"}


def package_manager() -> str | None:
    return next((pm for pm in INSTALL if shutil.which(pm)), None)


def playwright_node(python: Path) -> Path | None:
    found = sorted(python.parent.parent.glob("lib/python*/site-packages/playwright/driver/node"))
    return found[-1] if found else None


def google_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable"):
        if shutil.which(name):
            return shutil.which(name)
    return "/opt/google/chrome/chrome" if Path("/opt/google/chrome/chrome").is_file() else None


class Linux(System):
    NAME = "linux"
    LABEL = "Linux"
    LAUNCHER = "ouvrir-le-traducteur.sh"
    TEXT_SUFFIXES = frozenset({".sh", ".txt", ".desktop"})  # fins de ligne Unix (un .sh en CRLF ne s'exécute pas)
    EOL = b"\n"
    EXECUTABLE = True
    EXTRACT_HINT = ("supprimez le dossier extrait, puis extrayez de nouveau le .zip (clic droit > « Extraire ici », "
                    "ou dans un terminal : unzip TraducteurWordPress-Linux.zip).")

    def location_warnings(self, root: Path) -> list[str]:
        fs, opts = _mount_of(root)
        warnings = []
        if fs in FOREIGN_FS:
            warnings.append(f"Ce dossier est sur un disque au format {fs} (clé USB, partition Windows…), qui ne permet "
                            "pas d'y préparer Python. Si la préparation échoue, extrayez le .zip dans votre dossier "
                            "personnel, par exemple ~/Traducteur.")
        elif "noexec" in opts:
            warnings.append("Ce disque interdit de lancer des programmes (option « noexec ») : extrayez le .zip dans "
                            "votre dossier personnel, par exemple ~/Traducteur.")
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            warnings.append("Aucun écran graphique détecté : le Traducteur a besoin d'une session de bureau pour "
                            "ouvrir son navigateur.")
        return warnings

    def check_before_browser(self, root: Path, python: Path) -> None:
        """L'outil qui télécharge le navigateur (Node.js, fourni avec Playwright) a besoin de libatomic, absente de
        certaines installations : sans elle, le téléchargement échouerait avec un message trompeur."""
        node = playwright_node(python)
        missing = missing_libraries(node) if node else []
        if not missing:
            return
        pm = package_manager()
        packages = sorted({NODE_LIBRARIES.get(lib, {}).get(pm or "", "") for lib in missing} - {""})
        if pm and packages:
            how = f"Dans un terminal, tapez :   {INSTALL[pm]} {' '.join(packages)}   (votre mot de passe sera demandé)"
        else:
            how = ("Installez-la avec le gestionnaire de logiciels de votre distribution (paquet « libatomic1 » ou "
                   "« libatomic »)")
        raise PrepareError(f"Il manque une petite bibliothèque du système ({', '.join(missing)}). {how}, "
                           "puis relancez « ouvrir-le-traducteur.sh ».")

    def check_system(self, root: Path, python: Path) -> list[str]:
        """Le navigateur téléchargé (Chromium) a besoin de bibliothèques du système, présentes sur presque tous les
        bureaux mais parfois pas toutes. Google Chrome, s'il est installé, est utilisé à sa place (et apporte tout ce
        qu'il lui faut)."""
        binary = chromium_binary(root)
        missing = missing_libraries(binary) if binary else []
        if not missing:
            return []
        chrome = google_chrome()
        listed = ", ".join(missing[:12]) + (" …" if len(missing) > 12 else "")
        if chrome:
            return [f"Il manque au navigateur de secours des bibliothèques du système ({listed}). Ce n'est pas gênant : "
                    "le Traducteur utilise Google Chrome, installé sur cet ordinateur."]
        how = ("Le plus simple : installez Google Chrome (gratuit : google.com/chrome) ; il installe tout ce qu'il "
               "faut, et il sert aussi à se connecter à Gemini.")
        if shutil.which("apt-get"):
            how += (" Autre possibilité (Ubuntu, Debian, Mint…), dans un terminal : "
                    f"sudo \"{python}\" -m playwright install-deps chromium")
        raise PrepareError(f"Il manque des bibliothèques du système pour le navigateur ({listed}). {how} "
                           "Puis relancez « ouvrir-le-traducteur.sh ».")

    def create_icon(self, root: Path) -> str:
        """Un fichier « Traducteur d'articles.desktop » (avec l'icône) à côté du lanceur, et la même entrée dans le
        menu des applications de l'utilisateur (~/.local/share/applications), le seul endroit d'où tous les bureaux
        (GNOME, KDE, Xfce, Cinnamon, MATE…) lancent une application d'un double-clic sans réglage."""
        folder = root.parent
        entry = desktop_entry(folder, self.LAUNCHER, root / "packaging" / "assets" / "traducteur.png")
        local = folder / f"{ICON_NAME}.desktop"
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        menu = data_home / "applications" / MENU_FILE
        try:
            for path in (local, menu):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry, encoding="utf-8")
                path.chmod(0o755)
        except OSError as e:
            raise PrepareError(f"L'icône n'a pas pu être créée ({e}) : le programme reste utilisable avec "
                               f"« {self.LAUNCHER} ».") from e
        if shutil.which("gio"):  # GNOME : autorise le lancement depuis le Bureau ou le gestionnaire de fichiers
            subprocess.run(["gio", "set", str(local), "metadata::trusted", "true"], capture_output=True)
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(menu.parent)], capture_output=True)
        return (f"« {ICON_NAME} » ajouté au menu des applications, et placé à côté de « {self.LAUNCHER} ».")

    def ready_message(self) -> list[str]:
        return [f"Les prochaines fois : « {ICON_NAME} » dans le menu des applications",
                f"(ou « {self.LAUNCHER} » dans ce dossier)."]


SYSTEM = Linux()
