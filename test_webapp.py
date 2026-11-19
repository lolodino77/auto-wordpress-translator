"""Tests de l'API de l'interface (python -m unittest test_webapp). Aucun navigateur, aucun appel à WordPress :
la traduction est simulée et le compte WordPress est remplacé par des fonctions de test."""
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from webapp.runner import RunManager
from webapp.server import create_app

HERE = Path(__file__).parent
H = {"X-AWT": "1"}
LONG_MD = "---\ntitle: Un article\nurl: https://example.com/a\n---\n" + "Mot " * 80


class WebappTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        shutil.copy(HERE / "config.toml", self.root / "config.toml")
        shutil.copytree(HERE / "articles_templates", self.root / "articles_templates")
        (self.root / "input").mkdir()
        self.state: dict = {}
        self.release = threading.Event()
        self.release.set()
        self.executed: list[str] = []

        def execute(run):
            for item in run.items:
                self.release.wait(5)
                if run.stop_requested:
                    break
                item.status, item.draft_url = "done", "https://example.com/?p=1"
                self.executed.append(item.key)

        self.runs = RunManager(execute)
        self.saved = []

        def save_credentials(root, cfg, user, pwd):
            self.saved.append((user, pwd))
            return {"connected": True, "username": user, "roles": ["contributor"], "can_publish": False}

        self.sync_calls = 0
        self.after_sync: dict = {}  # ce que « le site » révèle à la vérification (ex. brouillon mis à la corbeille)

        def reconcile(root, cfg):
            self.sync_calls += 1
            self.state.update(self.after_sync)

        self.wp_states: dict = {}  # état des brouillons « sur le site » (n° -> draft, trash…)
        self.wp_error = ""  # simule un site injoignable
        self.draft_checks: list = []

        def draft_states(root, cfg, ids):
            self.draft_checks.append(list(ids))
            if self.wp_error:
                raise RuntimeError(self.wp_error)
            return {i: self.wp_states.get(i, "unknown") for i in ids}

        app = create_app(self.root, runs=self.runs, statuses=lambda root, site: self.state,
                         account=lambda root, cfg: {"configured": False}, save_credentials=save_credentials,
                         reconcile=reconcile, draft_states=draft_states)
        self.c = TestClient(app, base_url="http://127.0.0.1:8710")

    def tearDown(self):
        self.release.set()
        shutil.rmtree(self.root, ignore_errors=True)

    def wait_run(self):
        for _ in range(100):
            if not self.runs.running:
                return
            time.sleep(0.02)
        self.fail("l'exécution ne s'est pas terminée")

    # --- protections ---------------------------------------------------------------------------------
    def test_other_host_refused(self):
        r = self.c.get("/api/status", headers={"Host": "evil.example.com"})
        self.assertEqual(r.status_code, 403)

    def test_localhost_accepted(self):
        self.assertEqual(self.c.get("/api/status", headers={"Host": "localhost:8710"}).status_code, 200)

    def test_change_without_header_refused(self):
        r = self.c.post("/api/articles/urls", json={"urls": ["https://example.com/a"]})
        self.assertEqual(r.status_code, 403)
        self.assertFalse((self.root / "input" / "articles.csv").exists())

    def test_unknown_api_is_404(self):
        self.assertEqual(self.c.get("/api/nope").status_code, 404)

    # --- articles -----------------------------------------------------------------------------------
    def test_add_urls_dedup_and_invalid(self):
        r = self.c.post("/api/articles/urls", headers=H, json={
            "urls": ["https://example.com/first-post", "pas une adresse", "https://example.com/first-post/", ""],
            "tags": ["Bible", " Foi "], "illustration": "Une image"}).json()
        self.assertEqual(r["added"], ["https://example.com/first-post"])
        self.assertEqual(r["invalid"], ["pas une adresse"])
        self.assertEqual(r["duplicates"], ["https://example.com/first-post/"])
        csv_text = (self.root / "input" / "articles.csv").read_text(encoding="utf-8")
        self.assertTrue(csv_text.startswith("url,tags,illustration"))
        items = self.c.get("/api/articles").json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "First post")
        self.assertEqual(items[0]["tags"], ["Bible", "Foi"])
        self.assertEqual(items[0]["status"], "pending")

    def test_add_url_already_translated_is_reported(self):
        self.state = {"https://example.com/old": ("published", "https://parlafoi.fr/?p=7")}
        r = self.c.post("/api/articles/urls", headers=H,
                        json={"urls": ["https://example.com/old", "https://example.com/new"]}).json()
        self.assertEqual(r["added"], ["https://example.com/old", "https://example.com/new"])
        self.assertEqual(r["already_done"], [{"url": "https://example.com/old", "draft_url": "https://parlafoi.fr/?p=7"}])

    def test_trashed_draft_is_checked_on_site_before_add(self):
        old = "https://parlafoi.fr/wp-admin/post.php?post=7&action=edit"
        self.state = {"https://example.com/old": ("published", old)}
        self.after_sync = {"https://example.com/old": ("removed", old)}  # mis à la corbeille dans WordPress
        r = self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/old"]}).json()
        self.assertGreaterEqual(self.sync_calls, 1)
        self.assertEqual(r["already_done"], [])  # plus de faux « déjà traduit »
        item = self.c.get("/api/articles").json()[0]
        self.assertEqual(item["status"], "pending")
        self.assertIn("corbeille", item["note"])
        self.assertEqual(item["draft_url"], "")

    def test_trashed_draft_can_be_translated_again(self):
        (self.root / "wp_credentials.json").write_text("{}", encoding="utf-8")
        old = "https://parlafoi.fr/wp-admin/post.php?post=7&action=edit"
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/old"]})
        self.state = {"https://example.com/old": ("published", old)}
        self.after_sync = {"https://example.com/old": ("removed", old)}
        r = self.c.post("/api/runs", headers=H, json={"mode": "brouillon"})
        self.assertEqual(r.status_code, 200, r.text)
        self.wait_run()
        self.assertEqual(self.executed, ["https://example.com/old"])

    def test_status_from_state_db(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a", "https://example.com/b"]})
        self.state = {"https://example.com/a": ("published", "https://parlafoi.fr/?p=9"),
                      "https://example.com/b": ("error", "Gemini indisponible")}
        items = {i["key"]: i for i in self.c.get("/api/articles").json()}
        self.assertEqual(items["https://example.com/a"]["status"], "done")
        self.assertEqual(items["https://example.com/a"]["draft_url"], "https://parlafoi.fr/?p=9")
        self.assertEqual(items["https://example.com/b"]["error"], "Gemini indisponible")
        st = self.c.get("/api/status").json()
        self.assertEqual(st["counts"]["done"], 1)
        self.assertEqual(st["counts"]["error"], 1)
        self.assertTrue(st["templates"]["ok"])

    def test_upload_md(self):
        files = [("files", ("Mon article.md", LONG_MD.encode(), "text/markdown")),
                 ("files", ("court.md", b"trop court", "text/markdown")),
                 ("files", ("image.png", b"\x89PNG", "image/png")),
                 ("files", ("../../evil.md", LONG_MD.encode(), "text/markdown"))]
        r = self.c.post("/api/articles/files", headers=H, files=files).json()
        self.assertEqual(r["added"], ["md:Mon article.md", "md:evil.md"])
        self.assertEqual(len(r["errors"]), 2)
        self.assertTrue((self.root / "input" / "articles_md" / "evil.md").exists())
        self.assertFalse((self.root / "evil.md").exists())
        again = self.c.post("/api/articles/files", headers=H,
                            files=[("files", ("Mon article.md", LONG_MD.encode(), "text/markdown"))]).json()
        self.assertEqual(again["added"], ["md:Mon article (2).md"])
        titles = [i["title"] for i in self.c.get("/api/articles").json()]
        self.assertIn("Un article", titles)

    def test_edit_url_and_md(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        self.c.post("/api/articles/files", headers=H, files=[("files", ("x.md", LONG_MD.encode(), "text/markdown"))])
        r = self.c.patch("/api/articles", headers=H,
                         json={"key": "https://example.com/a", "tags": ["Un", "Deux", ""], "illustration": "Légende"})
        self.assertEqual(r.status_code, 200)
        r = self.c.patch("/api/articles", headers=H, json={"key": "md:x.md", "illustration": "Photo : X"})
        self.assertEqual(r.status_code, 200)
        items = {i["key"]: i for i in self.c.get("/api/articles").json()}
        self.assertEqual(items["https://example.com/a"]["tags"], ["Un", "Deux"])
        self.assertEqual(items["https://example.com/a"]["illustration"], "Légende")
        self.assertEqual(items["md:x.md"]["illustration"], "Photo : X")
        text = (self.root / "input" / "articles_md" / "x.md").read_text(encoding="utf-8")
        self.assertIn("title: Un article", text)
        self.assertIn("Mot Mot", text)
        self.assertEqual(self.c.patch("/api/articles", headers=H,
                                      json={"key": "md:../config.toml", "illustration": "x"}).status_code, 400)

    def test_delete_moves_md_to_trash(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        self.c.post("/api/articles/files", headers=H, files=[("files", ("x.md", LONG_MD.encode(), "text/markdown"))])
        self.assertEqual(self.c.post("/api/articles/delete", headers=H, json={"key": "md:x.md"}).status_code, 200)
        self.assertTrue((self.root / "input" / "corbeille" / "x.md").exists())
        self.c.post("/api/articles/delete", headers=H, json={"key": "https://example.com/a"})
        self.assertEqual(self.c.get("/api/articles").json(), [])
        self.assertEqual(self.c.post("/api/articles/delete", headers=H, json={"key": "https://nope.com/z"}).status_code, 400)

    # --- traductions --------------------------------------------------------------------------------
    def test_run_needs_account_for_drafts(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        r = self.c.post("/api/runs", headers=H, json={"mode": "brouillon"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("compte WordPress", r.json()["detail"])

    def test_preview_run_and_single_run_at_a_time(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a", "https://example.com/b"]})
        self.release.clear()
        r = self.c.post("/api/runs", headers=H, json={"mode": "apercu"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 2)
        self.assertEqual({i["status"] for i in self.c.get("/api/articles").json()}, {"queued"})
        again = self.c.post("/api/runs", headers=H, json={"mode": "apercu"})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.c.post("/api/articles/delete", headers=H,
                                     json={"key": "https://example.com/a"}).status_code, 400)
        self.release.set()
        self.wait_run()
        cur = self.c.get("/api/runs/current").json()
        self.assertEqual(cur["status"], "done")
        self.assertEqual(cur["done"], 2)

    def test_drafts_skip_already_done_unless_forced(self):
        (self.root / "wp_credentials.json").write_text("{}", encoding="utf-8")
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a", "https://example.com/b"]})
        self.state = {"https://example.com/a": ("published", "https://parlafoi.fr/?p=9")}
        self.c.post("/api/runs", headers=H, json={"mode": "brouillon"})
        self.wait_run()
        self.assertEqual(self.executed, ["https://example.com/b"])
        r = self.c.post("/api/runs", headers=H, json={"mode": "brouillon", "keys": ["https://example.com/a"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("déjà un brouillon", r.json()["detail"])
        self.c.post("/api/runs", headers=H, json={"mode": "brouillon", "keys": ["https://example.com/a"], "force": True})
        self.wait_run()
        self.assertEqual(self.executed, ["https://example.com/b", "https://example.com/a"])

    def test_stop_after_current(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a", "https://example.com/b"]})
        self.release.clear()
        self.c.post("/api/runs", headers=H, json={"mode": "apercu"})
        self.c.post("/api/runs/stop", headers=H)
        self.release.set()
        self.wait_run()
        self.assertEqual(self.c.get("/api/runs/current").json()["status"], "stopped")

    # --- résultats ----------------------------------------------------------------------------------
    def test_results(self):
        d = self.root / "output" / "results"
        d.mkdir(parents=True)
        (d / "brouillon-a.json").write_text(json.dumps({
            "id": "brouillon-a", "key": "https://example.com/a", "mode": "brouillon", "date": "2026-11-15T10:00:00",
            "title": "Titre FR", "html": "<p>x</p>", "warnings": ["w"]}), encoding="utf-8")
        lst = self.c.get("/api/results").json()
        self.assertEqual(lst[0]["title"], "Titre FR")
        self.assertEqual(lst[0]["warnings"], 1)
        self.assertNotIn("html", lst[0])
        self.assertEqual(self.c.get("/api/results/brouillon-a").json()["html"], "<p>x</p>")
        self.assertIn(self.c.get("/api/results/..%2Fconfig").status_code, (400, 404))
        self.assertEqual(self.c.get("/api/results/Config.TOML").status_code, 400)
        self.assertEqual(self.c.get("/api/results/inexistant").status_code, 400)

    def write_result(self, rid, mode, post=None):
        d = self.root / "output" / "results"
        d.mkdir(parents=True, exist_ok=True)
        url = f"https://parlafoi.fr/wp-admin/post.php?post={post}&action=edit" if post else ""
        (d / f"{rid}.json").write_text(json.dumps({"id": rid, "key": f"https://example.com/{rid}", "mode": mode,
                                                   "date": "2026-11-18T10:00:00", "title": rid, "html": "<p>x</p>",
                                                   "draft_url": url, "warnings": []}), encoding="utf-8")

    def test_results_follow_real_draft_state_in_wordpress(self):
        self.write_result("brouillon-a", "brouillon", 7)
        self.write_result("brouillon-b", "brouillon", 8)
        self.write_result("brouillon-c", "brouillon", 9)
        self.write_result("apercu-d", "apercu")
        self.wp_states = {7: "trash", 8: "draft", 9: "publish"}
        states = {r["id"]: r["wp_status"] for r in self.c.get("/api/results").json()}
        self.assertEqual(states, {"brouillon-a": "trash", "brouillon-b": "draft", "brouillon-c": "publish", "apercu-d": None})
        self.assertEqual(self.c.get("/api/results/brouillon-a").json()["wp_status"], "trash")

    def test_unverified_state_is_reported_not_assumed(self):
        self.write_result("brouillon-a", "brouillon", 7)
        self.wp_error = "site injoignable"
        r = self.c.get("/api/results").json()
        self.assertIsNone(r[0]["wp_status"])  # inconnu : l'interface affiche « État non vérifié », pas « Brouillon »
        self.assertIn("site injoignable", self.c.get("/api/status").json()["drafts_check_error"])
        self.wp_error = ""
        self.wp_states = {7: "trash"}
        self.assertEqual(self.c.get("/api/results").json()[0]["wp_status"], "trash")  # revérifié aussitôt
        self.assertEqual(self.c.get("/api/status").json()["drafts_check_error"], "")

    def test_new_draft_is_checked_without_waiting(self):
        self.write_result("brouillon-a", "brouillon", 7)
        self.wp_states = {7: "draft", 8: "trash"}
        self.c.get("/api/results")
        self.write_result("brouillon-b", "brouillon", 8)  # traduction terminée entre-temps
        states = {r["id"]: r["wp_status"] for r in self.c.get("/api/results").json()}
        self.assertEqual(states, {"brouillon-a": "draft", "brouillon-b": "trash"})
        self.assertIn([7, 8], self.draft_checks)

    def test_restart_needed_when_code_changes_while_running(self):
        import os
        self.assertFalse(self.c.get("/api/status").json()["restart_needed"])
        f = self.root / "pipeline.py"
        f.write_text("# nouvelle version", encoding="utf-8")
        later = time.time() + 60
        os.utime(f, (later, later))
        self.assertTrue(self.c.get("/api/status").json()["restart_needed"])

    def test_quit_button(self):
        calls = []
        app = create_app(self.root, runs=self.runs, statuses=lambda r, s: {}, quit_callback=lambda: calls.append("quit"))
        c = TestClient(app, base_url="http://127.0.0.1:8710")
        self.assertEqual(c.post("/api/quit").status_code, 403)  # sans en-tête
        self.assertEqual(c.post("/api/quit", headers=H).status_code, 200)
        for _ in range(40):
            if calls:
                break
            time.sleep(0.05)
        self.assertEqual(calls, ["quit"])

    def test_quit_refused_during_a_translation_and_without_callback(self):
        self.assertEqual(self.c.post("/api/quit", headers=H).status_code, 400)  # pas de callback : tests, dev
        calls = []
        app = create_app(self.root, runs=self.runs, statuses=lambda r, s: {}, quit_callback=lambda: calls.append(1))
        c = TestClient(app, base_url="http://127.0.0.1:8710")
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        self.release.clear()
        self.c.post("/api/runs", headers=H, json={"mode": "apercu"})
        r = c.post("/api/quit", headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertIn("traduction", r.json()["detail"])
        self.release.set()
        self.wait_run()
        time.sleep(0.8)
        self.assertEqual(calls, [])

    def test_identity_says_which_copy_answers(self):
        r = self.c.get("/api/identity").json()
        self.assertEqual(r["app"], "traducteur-wordpress")
        self.assertEqual(Path(r["root"]), self.root.resolve())
        self.assertFalse(r["running"])

    def test_status_gives_interface_version(self):
        self.assertIn("ui_version", self.c.get("/api/status").json())

    def test_archive_result_moves_file_and_hides_it(self):
        self.write_result("brouillon-a", "brouillon", 7)
        r = self.c.post("/api/results/delete", headers=H, json={"key": "brouillon-a"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue((self.root / "output" / "results" / "retires" / "brouillon-a.json").exists())
        self.assertEqual(self.c.get("/api/results").json(), [])
        self.assertEqual(self.c.post("/api/results/delete", headers=H, json={"key": "../config"}).status_code, 400)
        self.assertEqual(self.c.post("/api/results/delete", json={"key": "brouillon-a"}).status_code, 403)  # sans en-tête

    # --- réglages et compte -------------------------------------------------------------------------
    def test_settings_keep_rest_of_config(self):
        before = (self.root / "config.toml").read_text(encoding="utf-8")
        r = self.c.put("/api/settings", headers=H, json={"site": "https://exemple.fr/", "engines": ["gpt", "gemini"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["site"], "https://exemple.fr")
        self.assertEqual(r.json()["engines"], ["gpt", "gemini"])
        after = (self.root / "config.toml").read_text(encoding="utf-8")
        self.assertEqual(len(before.splitlines()), len(after.splitlines()))
        self.assertIn("{headings_info}", after)
        self.assertEqual(self.c.put("/api/settings", headers=H, json={"engines": ["claude"]}).status_code, 400)
        self.assertEqual(self.c.put("/api/settings", headers=H, json={"site": "pas un site"}).status_code, 400)

    def test_logout_forgets_credentials(self):
        f = self.root / "wp_credentials.json"
        f.write_text("{}", encoding="utf-8")
        self.assertEqual(self.c.post("/api/account/logout").status_code, 403)  # sans en-tête
        self.assertTrue(f.exists())
        self.assertEqual(self.c.post("/api/account/logout", headers=H).status_code, 200)
        self.assertFalse(f.exists())
        self.assertEqual(self.c.post("/api/account/logout", headers=H).status_code, 200)  # déjà déconnecté : sans erreur

    def test_account_credentials(self):
        r = self.c.post("/api/account", headers=H, json={"username": " autotraduction ", "app_password": "abcd efgh"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.saved, [("autotraduction", "abcd efgh")])
        self.assertNotIn("abcd", r.text)
        self.assertEqual(self.c.post("/api/account", headers=H, json={"username": "", "app_password": ""}).status_code, 400)

    def test_spa_fallback(self):
        r = self.c.get("/articles")
        self.assertIn(r.status_code, (200, 503))
        self.assertIn("text/html", r.headers["content-type"])


class AutoRestart(unittest.TestCase):
    """Mise à jour sans redémarrage manuel : le serveur se relance quand son code change, jamais pendant une traduction."""

    def test_restart_rules(self):
        from webapp.__main__ import should_restart
        self.assertFalse(should_restart(100.0, 100.0, 100.0, False))  # rien n'a changé
        self.assertFalse(should_restart(200.0, 100.0, 150.0, False))  # fichiers encore en cours d'écriture : on attend
        self.assertTrue(should_restart(200.0, 100.0, 200.0, False))  # changé puis stable : on redémarre
        self.assertFalse(should_restart(200.0, 100.0, 200.0, True))  # traduction en cours : jamais

    def test_code_stamp_follows_python_files(self):
        import os
        from webapp.server import code_stamp
        root = Path(tempfile.mkdtemp())
        self.assertEqual(code_stamp(root), 0.0)
        (root / "webapp").mkdir()
        f = root / "webapp" / "x.py"
        f.write_text("x = 1", encoding="utf-8")
        os.utime(f, (1000, 1000))
        self.assertEqual(code_stamp(root), 1000)
        (root / "notes.txt").write_text("pas du code", encoding="utf-8")
        self.assertEqual(code_stamp(root), 1000)
        shutil.rmtree(root, ignore_errors=True)


class GeminiConnection(unittest.TestCase):
    """Connexion facultative à Gemini : fenêtre ouverte à la demande, jamais en même temps qu'une traduction."""

    def setUp(self):
        from webapp.gemini_login import GeminiLogin
        self.root = Path(tempfile.mkdtemp())
        shutil.copy(HERE / "config.toml", self.root / "config.toml")
        shutil.copytree(HERE / "articles_templates", self.root / "articles_templates")
        (self.root / "input").mkdir()
        (self.root / "wp_credentials.json").write_text("{}", encoding="utf-8")
        self.window = threading.Event()
        self.logged = False

        def session(profile_dir, on_check, should_stop):  # fenêtre simulée : se « connecte » puis attend la fermeture
            self.window.set()
            on_check(self.logged)
            for _ in range(200):
                if should_stop():
                    break
                time.sleep(0.01)
            on_check(self.logged)

        self.gemini = GeminiLogin(self.root, session=session)
        self.release = threading.Event()
        self.runs = RunManager(lambda run: self.release.wait(5))
        self.c = TestClient(create_app(self.root, runs=self.runs, statuses=lambda r, s: {},
                                       reconcile=lambda r, c: None, draft_states=lambda r, c, i: {}, gemini=self.gemini),
                            base_url="http://127.0.0.1:8710")

    def tearDown(self):
        self.gemini.close()
        self.release.set()
        shutil.rmtree(self.root, ignore_errors=True)

    def wait_closed(self):
        for _ in range(200):
            if not self.gemini.window_open:
                return
            time.sleep(0.01)

    def test_never_checked_at_first(self):
        st = self.c.get("/api/gemini").json()
        self.assertIsNone(st["logged_in"])
        self.assertFalse(st["window_open"])
        self.assertIsNone(self.c.get("/api/status").json()["gemini_logged_in"])

    def test_login_window_records_the_connection(self):
        self.logged = True
        self.assertEqual(self.c.post("/api/gemini/login").status_code, 403)  # sans en-tête
        self.assertTrue(self.c.post("/api/gemini/login", headers=H).json()["window_open"])
        self.assertTrue(self.window.wait(2))
        self.assertEqual(self.c.post("/api/gemini/login", headers=H).status_code, 400)  # une seule fenêtre
        self.c.post("/api/gemini/close", headers=H)
        self.wait_closed()
        st = self.c.get("/api/gemini").json()
        self.assertFalse(st["window_open"])
        self.assertTrue(st["logged_in"])
        self.assertTrue(self.c.get("/api/status").json()["gemini_logged_in"])

    def test_no_translation_while_the_login_window_is_open(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        self.c.post("/api/gemini/login", headers=H)
        self.assertTrue(self.window.wait(2))
        r = self.c.post("/api/runs", headers=H, json={"mode": "brouillon"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Gemini", r.json()["detail"])

    def test_no_login_window_during_a_translation(self):
        self.c.post("/api/articles/urls", headers=H, json={"urls": ["https://example.com/a"]})
        self.release.clear()
        self.assertEqual(self.c.post("/api/runs", headers=H, json={"mode": "brouillon"}).status_code, 200)
        r = self.c.post("/api/gemini/login", headers=H)
        self.assertEqual(r.status_code, 400)
        self.assertIn("traduction est en cours", r.json()["detail"])

    def test_google_session_cookies(self):
        from webapp.gemini_login import is_logged_in
        self.assertFalse(is_logged_in([{"name": "NID"}, {"name": "AEC"}]))  # visiteur anonyme
        self.assertTrue(is_logged_in([{"name": "NID"}, {"name": "__Secure-1PSID"}]))

    def test_login_read_from_the_profile_on_disk(self):
        """La fenêtre de connexion n'est pas pilotée (Google le refuse) : la connexion se lit dans le profil."""
        import sqlite3
        from webapp.gemini_login import cookie_names
        profile = self.root / "profil"
        self.assertEqual(cookie_names(str(profile)), set())  # profil jamais ouvert
        (profile / "Default" / "Network").mkdir(parents=True)
        con = sqlite3.connect(profile / "Default" / "Network" / "Cookies")
        con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB)")
        con.executemany("INSERT INTO cookies VALUES (?, ?, ?)",
                        [(".google.com", "__Secure-1PSID", b"x"), ("gemini.google.com", "NID", b"x"), (".exemple.fr", "SID", b"x")])
        con.commit()
        con.close()
        self.assertEqual(cookie_names(str(profile)), {"__Secure-1PSID", "NID"})  # seulement Google, seulement les noms

    def test_chrome_required_for_the_login_window(self):
        from unittest import mock
        import webapp.gemini_login as gl
        with mock.patch("llm_browser.installed_chrome", return_value=None):
            with self.assertRaises(RuntimeError) as e:
                gl.chromium_path()
        self.assertIn("Google Chrome", str(e.exception))


if __name__ == "__main__":
    unittest.main()
