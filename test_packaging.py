"""Tests de la version portable (python -m unittest test_packaging). Sans Internet : ni uv, ni Python, ni Chromium ne
sont téléchargés ; on vérifie le contenu du paquet, la vérification rapide, et ce qui est protégé."""
import ast
import json
import os
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


def copy_program(dest: Path) -> Path:
    """Copie du programme telle qu'on la trouve dans le dossier « programme » d'un .zip extrait."""
    for src, rel in M.program_files(ROOT, "windows"):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    return dest


class Manifest(unittest.TestCase):
    def test_every_program_item_exists(self):
        for item in M.APP_ITEMS + [src for p in M.PLATFORM_ITEMS.values() for src in p]:
            self.assertTrue((ROOT / item).exists(), item)

    def test_every_local_module_imported_by_the_program_is_shipped(self):
        """Un module oublié dans la liste = programme qui ne démarre pas chez le coéquipier."""
        local = {p.stem for p in ROOT.glob("*.py")}
        shipped = {Path(rel).stem for _, rel in M.program_files(ROOT, "windows") if "/" not in rel and rel.endswith(".py")}
        for f, rel in M.program_files(ROOT, "windows"):
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
                    "traducteur.log"]:
            self.assertTrue(M.is_user_data(rel), rel)
        for rel in ["agent.py", "webapp/server.py", "config.toml", "spec/x.pdf"]:
            self.assertFalse(M.is_user_data(rel), rel)


class Readiness(unittest.TestCase):
    """La vérification rapide décide, à chaque double-clic, d'ouvrir tout de suite ou de (re)préparer."""

    def setUp(self):
        self.root = copy_program(Path(tempfile.mkdtemp()) / "TraducteurWordPress-Windows" / "programme")
        (self.root / "VERSION").write_text("2026-11-18 (abc)\n", encoding="utf-8")
        venv = M.venv_python(self.root, M.current_platform())
        venv.parent.mkdir(parents=True)
        venv.write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root.parents[1], ignore_errors=True)

    def mark_prepared(self, **changes):
        state = {"version": prepare.read_version(self.root), "folder": str(self.root),
                 "requirements": prepare.requirements_hash(self.root)} | changes
        (self.root / prepare.STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

    def test_never_prepared(self):
        self.assertFalse(prepare.is_ready(self.root))

    def test_prepared_here_for_this_version(self):
        self.mark_prepared()
        self.assertTrue(prepare.is_ready(self.root))

    def test_new_version_extracted_over_it(self):
        self.mark_prepared(version="2026-01-01 (ancienne)")
        self.assertFalse(prepare.is_ready(self.root))

    def test_folder_moved(self):
        self.mark_prepared(folder=r"C:\ancien\endroit\programme")
        self.assertFalse(prepare.is_ready(self.root))

    def test_new_library_required(self):
        self.mark_prepared(requirements="autre")
        self.assertFalse(prepare.is_ready(self.root))

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
        prepare.check_spec_names(self.root)
        pdf = next((self.root / "spec").glob("Guide*.pdf"))
        pdf.rename(pdf.with_name("Guide de r+®daction.pdf"))  # accents abîmés par une mauvaise décompression
        with self.assertRaises(prepare.PrepareError):
            prepare.check_spec_names(self.root)

    def test_remove_tree_handles_paths_longer_than_260_characters(self):
        deep = self.root / ".venv"
        target = deep
        while len(str(target)) < 300:
            target = target / "dossier-tres-profond"
        long_name = "\\\\?\\" + str(target.resolve()) if sys.platform.startswith("win") else str(target)
        os.makedirs(long_name)
        with open(os.path.join(long_name, "fichier.xsl"), "w") as f:
            f.write("x")
        prepare.remove_tree(deep)
        self.assertFalse(deep.exists())

    def test_risky_locations_are_reported(self):
        self.assertTrue(prepare.location_warnings(Path(r"C:\Users\x\OneDrive\Bureau\Traducteur\programme")))
        self.assertTrue(prepare.location_warnings(Path("C:/" + "a" * 100 + "/programme")))
        self.assertEqual(prepare.location_warnings(Path(r"C:\Traducteur\programme")), [])


class Platforms(unittest.TestCase):
    def test_untested_system_is_refused_clearly(self):
        with patch.object(prepare.M, "current_platform", return_value="linux"), \
                patch.object(sys, "argv", ["prepare.py", "--root", str(Path(tempfile.mkdtemp()))]):
            self.assertEqual(prepare.main(), 2)


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
    def test_windows_portable_package_content(self):
        out = Path(tempfile.mkdtemp())
        try:
            path = build_package.build("windows", out, force=True)
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                top = "TraducteurWordPress-Windows/"
                self.assertTrue(all(n.startswith(top) for n in names))
                # à la racine du dossier extrait : seulement le lanceur, la notice et le dossier « programme »
                self.assertEqual({n[len(top):].split("/")[0] for n in names},
                                 {M.LAUNCHER_NAME, "LISEZ-MOI.txt", "programme"})
                launcher = z.read(top + M.LAUNCHER_NAME)
                self.assertIn(b"\r\n", launcher)
                self.assertNotIn(b"\n", launcher.replace(b"\r\n", b""))  # fins de ligne Windows uniquement
                self.assertTrue(z.read(top + "LISEZ-MOI.txt").startswith(b"\xef\xbb\xbf"))
                self.assertIn(top + "programme/VERSION", names)
                self.assertIn(top + "programme/packaging/common/prepare.py", names)
                self.assertIn(top + "programme/webapp/static/index.html", names)
                for forbidden in ["/input/", "wp_credentials", "wp_token", "/output/", "browser_profile", ".db",
                                  "/frontend/", "test_", "agent.log", "/.claude/", "__pycache__", "/.venv/",
                                  "/runtime/", "installation.json", "Desinstaller", "Installer le"]:
                    self.assertFalse([n for n in names if forbidden in n], forbidden)
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
