"""Tests de la version portable (python -m unittest test_packaging). Sans Internet : ni uv, ni Python, ni Chromium ne
sont téléchargés ; on vérifie le contenu des paquets, la vérification rapide, ce qui est protégé, et le cloisonnement
des systèmes (tout ce qui est propre à Windows ou à Linux reste dans packaging/<système>/)."""
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "packaging" / "common"))
sys.path.insert(0, str(ROOT / "packaging"))
import build_package  # noqa: E402
import manifest as M  # noqa: E402
import prepare  # noqa: E402
import system_base  # noqa: E402

SYSTEM = system_base.load()  # le système de cet ordinateur
WINDOWS, LINUX = system_base.load("windows"), system_base.load("linux")
LINUX_MODULE = sys.modules[type(LINUX).__module__]


def copy_program(dest: Path) -> Path:
    """Copie du programme telle qu'on la trouve dans le dossier « programme » d'un .zip extrait."""
    for src, rel in M.program_files(ROOT, SYSTEM.NAME):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    return dest


class Manifest(unittest.TestCase):
    def test_every_program_item_exists(self):
        for item in M.APP_ITEMS:
            self.assertTrue((ROOT / item).exists(), item)

    def test_every_local_module_imported_by_the_program_is_shipped(self):
        """Un module oublié dans la liste = programme qui ne démarre pas chez le coéquipier."""
        local = {p.stem for p in ROOT.glob("*.py")}
        shipped = {Path(rel).stem for _, rel in M.program_files(ROOT) if "/" not in rel and rel.endswith(".py")}
        for f, rel in M.program_files(ROOT):
            if not rel.endswith(".py") or rel.startswith("packaging/"):
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
                for name in names:
                    top = name.split(".")[0]
                    if top in local:
                        self.assertIn(top, shipped, f"{rel} importe {top}.py, absent du paquet")

    def test_user_data_patterns(self):
        for rel in ["input/articles.csv", "output/x.html", "browser_profile/Default/x", "wp_credentials.json",
                    "state-parlafoi-fr.db", ".venv/Scripts/python.exe", "runtime/uv.exe", "installation.json",
                    "traducteur.log", "traducteur-preparation.log"]:
            self.assertTrue(M.is_user_data(rel), rel)
        for rel in ["agent.py", "webapp/server.py", "config.toml", "spec/x.pdf"]:
            self.assertFalse(M.is_user_data(rel), rel)


class Readiness(unittest.TestCase):
    """La vérification rapide décide, à chaque double-clic, d'ouvrir tout de suite ou de (re)préparer."""

    def setUp(self):
        self.root = copy_program(Path(tempfile.mkdtemp()) / "TraducteurWordPress-Essai" / "programme")
        (self.root / "VERSION").write_text("2026-11-18 (abc)\n", encoding="utf-8")
        venv = SYSTEM.venv_python(self.root)
        venv.parent.mkdir(parents=True)
        venv.write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root.parents[1], ignore_errors=True)

    def mark_prepared(self, **changes):
        state = {"version": prepare.read_version(self.root), "folder": str(self.root),
                 "requirements": prepare.requirements_hash(self.root)} | changes
        (self.root / prepare.STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

    def test_never_prepared(self):
        self.assertFalse(prepare.is_ready(self.root, SYSTEM))

    def test_prepared_here_for_this_version(self):
        self.mark_prepared()
        self.assertTrue(prepare.is_ready(self.root, SYSTEM))

    def test_new_version_extracted_over_it(self):
        self.mark_prepared(version="2026-01-01 (ancienne)")
        self.assertFalse(prepare.is_ready(self.root, SYSTEM))

    def test_folder_moved(self):
        self.mark_prepared(folder=r"C:\ancien\endroit\programme")
        self.assertFalse(prepare.is_ready(self.root, SYSTEM))

    def test_new_library_required(self):
        self.mark_prepared(requirements="autre")
        self.assertFalse(prepare.is_ready(self.root, SYSTEM))

    def test_check_option_exit_codes(self):
        with patch.object(sys, "argv", ["prepare.py", "--root", str(self.root), "--check"]):
            self.assertEqual(prepare.main(), prepare.NOT_READY)
            self.mark_prepared()
            self.assertEqual(prepare.main(), 0)


class UserData(unittest.TestCase):
    def setUp(self):
        self.root = copy_program(Path(tempfile.mkdtemp()) / "programme")

    def tearDown(self):
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def test_first_opening_gets_an_empty_list_never_the_developer_one(self):
        self.assertFalse((self.root / "input").exists())  # le dossier input/ du développeur n'est pas dans le paquet
        prepare.ensure_user_folders(self.root)
        self.assertEqual((self.root / "input" / "articles.csv").read_text(encoding="utf-8"), M.EMPTY_CSV)
        self.assertTrue((self.root / "input" / "articles_md").is_dir())
        (self.root / "input" / "articles.csv").write_text("url\nhttps://a.example/b\n", encoding="utf-8")
        prepare.ensure_user_folders(self.root)  # une nouvelle préparation ne vide pas la liste
        self.assertIn("a.example", (self.root / "input" / "articles.csv").read_text(encoding="utf-8"))

    def test_spec_names_from_config_are_checked(self):
        prepare.check_spec_names(self.root, SYSTEM)
        pdf = next((self.root / "spec").glob("Guide*.pdf"))
        pdf.rename(pdf.with_name("Guide de r+®daction.pdf"))  # accents abîmés par une mauvaise décompression
        with self.assertRaises(prepare.PrepareError) as e:
            prepare.check_spec_names(self.root, SYSTEM)
        self.assertIn(SYSTEM.EXTRACT_HINT, str(e.exception))  # conseil propre au système

    def test_remove_tree_handles_paths_longer_than_260_characters(self):
        deep = self.root / ".venv"
        target = deep
        while len(str(target)) < 300:
            target = target / "dossier-tres-profond"
        long_name = "\\\\?\\" + str(target.resolve()) if SYSTEM is WINDOWS else str(target)
        os.makedirs(long_name)
        with open(os.path.join(long_name, "fichier.xsl"), "w") as f:
            f.write("x")
        SYSTEM.remove_tree(deep)
        self.assertFalse(deep.exists())

    def test_risky_locations_are_reported_on_windows(self):
        self.assertTrue(WINDOWS.location_warnings(Path(r"C:\Users\x\OneDrive\Bureau\Traducteur\programme")))
        self.assertTrue(WINDOWS.location_warnings(Path("C:/" + "a" * 100 + "/programme")))
        self.assertEqual(WINDOWS.location_warnings(Path(r"C:\Traducteur\programme")), [])


class Systems(unittest.TestCase):
    """Chaque système est cloisonné dans packaging/<système>/ ; le code commun n'en connaît aucun."""

    def test_available_systems(self):
        self.assertEqual(system_base.available(), ["linux", "windows"])
        for system in (WINDOWS, LINUX):
            self.assertTrue((system.folder / system.LAUNCHER).is_file(), system.NAME)
            self.assertTrue((system.folder / system.NOTICE).is_file(), system.NAME)

    def test_common_code_knows_no_particular_system(self):
        words = ["powershell", ".bat", ".sh", "scripts", ".desktop", "taskkill", "onedrive", "linux", "windows"]
        for f in [ROOT / "packaging" / "build_package.py", *(ROOT / "packaging" / "common").glob("*.py")]:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):  # le code seul : ni commentaires (perdus par ast), ni docstrings
                body = getattr(node, "body", None)
                if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
                    body[0].value.value = ""
            if f.name == "system_base.py":  # seul endroit qui associe sys.platform à un nom de système
                tree.body = [n for n in tree.body if getattr(n, "name", "") != "current_platform"]
            code = ast.unparse(tree).lower()
            for word in words:
                found = re.search(re.escape(word) + r"\b", code)
                self.assertIsNone(found, f"{f.name} contient « {word} » : à ranger dans packaging/<système>/")
            self.assertNotIn("sys.platform", code, f.name)

    def test_unsupported_system_is_refused_clearly(self):
        with patch.object(prepare, "load", side_effect=LookupError("macos")), \
                patch.object(sys, "argv", ["prepare.py", "--root", str(Path(tempfile.mkdtemp()))]):
            self.assertEqual(prepare.main(), 2)
        for name in ("macos", "common", "assets"):
            with self.assertRaises(LookupError):
                system_base.load(name)


class LinuxSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_launcher_is_posix_sh_with_unix_line_endings(self):
        data = (LINUX.folder / LINUX.LAUNCHER).read_bytes()
        self.assertTrue(data.startswith(b"#!/bin/sh\n"))
        self.assertNotIn(b"\r", data)
        for bashism in (b"[[", b"function ", b"$'", b"local "):
            self.assertNotIn(bashism, data)

    def test_desktop_exec_quotes_spaces_and_special_characters(self):
        exec_arg = LINUX_MODULE.desktop_exec_arg
        self.assertEqual(exec_arg("/home/a b/x.sh"), '"/home/a b/x.sh"')
        # " et $ échappés par \ (règle de Exec), puis chaque \ doublé (règle des valeurs) ; % doublé
        self.assertEqual(exec_arg('/home/l"a$/x.sh'), '"/home/l\\\\"a\\\\$/x.sh"')
        self.assertEqual(exec_arg("/home/100%/x.sh"), '"/home/100%%/x.sh"')

    def test_icon_in_folder_and_application_menu(self):
        root = self.tmp / "Traducteur d'essai" / "programme"
        root.mkdir(parents=True)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.tmp / "data")}), \
                patch.object(LINUX_MODULE.shutil, "which", return_value=None):
            LINUX.create_icon(root)
        for f in (root.parent / "Traducteur d'articles.desktop", self.tmp / "data" / "applications" / LINUX_MODULE.MENU_FILE):
            text = f.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("[Desktop Entry]\n"))
            self.assertIn("Terminal=false", text)
            self.assertIn("traducteur.png", text)
            self.assertIn(LINUX.LAUNCHER + '"', text)

    def test_missing_libatomic_gives_the_exact_command_for_the_distribution(self):
        python = self.tmp / "programme" / ".venv" / "bin" / "python"
        node = python.parent.parent / "lib" / "python3.12" / "site-packages" / "playwright" / "driver" / "node"
        node.parent.mkdir(parents=True)
        node.write_text("")
        with patch.object(LINUX_MODULE, "missing_libraries", return_value=[]):
            LINUX.check_before_browser(self.tmp / "programme", python)  # rien ne manque : pas d'erreur
        with patch.object(LINUX_MODULE, "missing_libraries", return_value=["libatomic.so.1"]):
            for pm, command in [("apt-get", "sudo apt install libatomic1"), ("dnf", "sudo dnf install libatomic"),
                                ("zypper", "sudo zypper install libatomic1")]:
                with patch.object(LINUX_MODULE, "package_manager", return_value=pm), \
                        self.assertRaises(system_base.PrepareError) as e:
                    LINUX.check_before_browser(self.tmp / "programme", python)
                self.assertIn(command, str(e.exception))

    def test_missing_system_libraries(self):
        root = self.tmp / "programme"
        chrome = root / "runtime" / "browsers" / "chromium-1200" / "chrome-linux" / "chrome"
        chrome.parent.mkdir(parents=True)
        chrome.write_text("")
        with patch.object(LINUX_MODULE, "missing_libraries", return_value=[]):
            self.assertEqual(LINUX.check_system(root, Path("python")), [])
        with patch.object(LINUX_MODULE, "missing_libraries", return_value=["libgbm.so.1"]):
            with patch.object(LINUX_MODULE, "google_chrome", return_value="/usr/bin/google-chrome"):
                self.assertTrue(LINUX.check_system(root, Path("python")))  # simple avertissement : Chrome sert
            with patch.object(LINUX_MODULE, "google_chrome", return_value=None), \
                    self.assertRaises(system_base.PrepareError):
                LINUX.check_system(root, Path("python"))


class PortChoice(unittest.TestCase):
    """Un autre programme (ou un autre exemplaire du Traducteur) sur le port 8710 ne doit pas empêcher celui-ci de
    démarrer ; un double-clic répété rouvre simplement la page."""

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        from webapp.__main__ import choose_port
        self.choose = choose_port
        self.me = Path(tempfile.gettempdir()) / "TraducteurWordPress-Windows" / "programme"

    def test_free_port_is_used(self):
        self.assertEqual(self.choose(8710, self.me, probe=lambda p: None), (8710, False))

    def test_port_taken_by_another_program_or_copy_moves_to_next(self):
        occupied = {8710: "", 8711: r"C:\dev\auto-wordpress-translator"}  # autre programme, puis version de dév.
        self.assertEqual(self.choose(8710, self.me, probe=lambda p: occupied.get(p)), (8712, False))

    def test_this_copy_already_open_is_reused(self):
        occupied = {8710: r"C:\dev\auto-wordpress-translator", 8711: str(self.me)}
        self.assertEqual(self.choose(8710, self.me, probe=lambda p: occupied.get(p)), (8711, True))

    def test_no_free_port_is_explained(self):
        with self.assertRaises(SystemExit):
            self.choose(8710, self.me, probe=lambda p: "", tries=3)


class Package(unittest.TestCase):
    FORBIDDEN = ["/input/", "wp_credentials", "wp_token", "/output/", "browser_profile", ".db", "/frontend/", "test_",
                 "agent.log", "/.claude/", "__pycache__", "/.venv/", "/runtime/", "installation.json",
                 "packaging/macos/", "lancer-le-traducteur", "Lancer le traducteur"]

    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def check_common(self, names: list[str], top: str, system) -> None:
        self.assertTrue(all(n.startswith(top) for n in names))
        # à la racine du dossier extrait : seulement le lanceur, la notice et le dossier « programme »
        self.assertEqual({n[len(top):].split("/")[0] for n in names}, {system.LAUNCHER, system.NOTICE, "programme"})
        for required in ["VERSION", "packaging/common/prepare.py", "packaging/common/system_base.py",
                         f"packaging/{system.NAME}/system.py", "webapp/static/index.html"]:
            self.assertIn(top + "programme/" + required, names)
        other = {"windows": "linux", "linux": "windows"}[system.NAME]
        for forbidden in self.FORBIDDEN + [f"packaging/{other}/"]:
            self.assertFalse([n for n in names if forbidden in n], forbidden)

    def test_windows_portable_package_content(self):
        path = build_package.build("windows", self.out, force=True)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            top = "TraducteurWordPress-Windows/"
            self.check_common(names, top, WINDOWS)
            launcher = z.read(top + WINDOWS.LAUNCHER)
            self.assertIn(b"\r\n", launcher)
            self.assertNotIn(b"\n", launcher.replace(b"\r\n", b""))  # fins de ligne Windows uniquement
            self.assertTrue(z.read(top + "LISEZ-MOI.txt").startswith(b"\xef\xbb\xbf"))

    def test_linux_portable_package_content(self):
        path = build_package.build("linux", self.out, force=True)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            top = "TraducteurWordPress-Linux/"
            self.check_common(names, top, LINUX)
            launcher = z.getinfo(top + LINUX.LAUNCHER)
            self.assertEqual(launcher.create_system, 3)  # droits Unix appliqués à l'extraction
            self.assertEqual((launcher.external_attr >> 16) & 0o777, 0o755)  # exécutable
            self.assertEqual((z.getinfo(top + "programme/agent.py").external_attr >> 16) & 0o777, 0o644)
            self.assertNotIn(b"\r", z.read(top + LINUX.LAUNCHER))  # un .sh en CRLF ne s'exécute pas
            notice = z.read(top + "LISEZ-MOI.txt")
            self.assertNotIn(b"\r", notice)
            self.assertFalse(notice.startswith(b"\xef\xbb\xbf"))
            self.assertFalse([n for n in names if n.endswith(".bat")])


if __name__ == "__main__":
    unittest.main()
