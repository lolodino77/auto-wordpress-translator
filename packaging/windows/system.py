"""Windows : tout ce qui est propre à Windows dans la version portable (voir packaging/common/system_base.py)."""
import base64
import shutil
import subprocess
from pathlib import Path

from system_base import PrepareError, System

SHORTCUT_NAME = "Traducteur d'articles"  # raccourci créé à côté du lanceur


def _ps(text) -> str:
    return "'" + str(text).replace("'", "''") + "'"


class Windows(System):
    NAME = "windows"
    LABEL = "Windows"
    LAUNCHER = "Ouvrir le Traducteur.bat"
    TEXT_SUFFIXES = frozenset({".bat", ".cmd", ".txt"})  # fichiers lus par Windows : fins de ligne Windows
    EOL = b"\r\n"
    NOTICE_BOM = True
    EXTRACT_HINT = ("supprimez le dossier extrait, puis refaites clic droit sur le .zip > « Extraire tout… ».")

    def venv_python(self, root: Path) -> Path:
        return root / ".venv" / "Scripts" / "python.exe"

    def location_warnings(self, root: Path) -> list[str]:
        warnings = []
        if "onedrive" in str(root).lower():
            warnings.append("Ce dossier est dans OneDrive : environ 700 Mo seront synchronisés, ce qui peut ralentir "
                            "l'ordinateur. Mieux vaut l'extraire ailleurs, par exemple dans C:\\Traducteur.")
        if len(str(root)) > 90:
            warnings.append("Le chemin de ce dossier est très long : si la préparation échoue, extrayez le .zip plus "
                            "près de la racine du disque, par exemple dans C:\\Traducteur.")
        return warnings

    def remove_tree(self, path: Path) -> None:
        """Supprime un dossier même si certains chemins dépassent la limite historique de Windows (260 caractères) :
        les bibliothèques Python contiennent des fichiers très profonds (lxml…), et le dossier peut être loin de la
        racine."""
        target = str(path.resolve())
        if not target.startswith("\\\\?\\"):
            target = "\\\\?\\" + target
        shutil.rmtree(target)

    def create_icon(self, root: Path) -> str:
        """Raccourci « Traducteur d'articles », avec l'icône du programme, à côté du lanceur (un .bat ne peut pas avoir
        d'icône)."""
        folder = root.parent
        link = folder / f"{SHORTCUT_NAME}.lnk"
        script = f"""
$ErrorActionPreference = 'Stop'
$l = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps(link)})
$l.TargetPath = {_ps(folder / self.LAUNCHER)}
$l.WorkingDirectory = {_ps(folder)}
$l.IconLocation = {_ps(str(root / "packaging" / "assets" / "traducteur.ico") + ",0")}
$l.Description = {_ps("Ouvrir le Traducteur d'articles")}
$l.Save()
"""
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                           capture_output=True)
        if r.returncode != 0:
            print(r.stderr.decode("utf-8", errors="replace")[-1500:])
            raise PrepareError(f"L'icône n'a pas pu être créée (le programme reste utilisable avec « {self.LAUNCHER} »).")
        return f"Icône « {SHORTCUT_NAME} » placée à côté de « {self.LAUNCHER} »."

    def ready_message(self) -> list[str]:
        return [f"Les prochaines fois : double-cliquez sur l'icône « {SHORTCUT_NAME} » de ce dossier",
                "(vous pouvez la glisser sur le Bureau)."]


SYSTEM = Windows()
