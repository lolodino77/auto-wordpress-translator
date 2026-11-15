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

        app = create_app(self.root, runs=self.runs, statuses=lambda root, site: self.state,
                         account=lambda root, cfg: {"configured": False}, save_credentials=save_credentials)
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


if __name__ == "__main__":
    unittest.main()
