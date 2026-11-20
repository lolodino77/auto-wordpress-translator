"""Serveur local de l'interface (FastAPI, servi par uvicorn). N'écoute que sur 127.0.0.1 : rien n'est exposé sur Internet.

Protections (le serveur pilote un compte WordPress) :
- seules les requêtes adressées à localhost / 127.0.0.1 sont acceptées (contre le « DNS rebinding ») ;
- toute requête qui modifie quelque chose doit porter l'en-tête X-AWT: 1, qu'un autre site ouvert dans le navigateur
  ne peut pas ajouter (contre les requêtes forgées depuis une autre page).
"""
import json
import re
import threading
import time
import tomllib
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webapp.gemini_login import ChatGPTLogin, GeminiLogin
from webapp.runner import Item, RunManager, real_execute
from webapp.store import Store, StoreError

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
POST_ID = re.compile(r"[?&](?:post|p)=(\d+)")  # n° de l'article dans l'adresse du brouillon
GONE = {"trash", "missing"}  # brouillon mis à la corbeille ou supprimé dans WordPress
ENGINES = {"gemini", "gpt"}
MODES = {"selfhosted", "wpcom"}


STATIC = Path(__file__).parent / "static"


def code_stamp(root: Path) -> float:
    """Date de dernière modification du code Python du programme. Quand elle change (mise à jour), le programme
    redémarre tout seul (voir __main__.py) : sinon l'ancien code continuerait de tourner."""
    stamp = 0.0
    for f in [*Path(root).glob("*.py"), *(Path(root) / "webapp").glob("*.py")]:
        try:
            stamp = max(stamp, f.stat().st_mtime)
        except OSError:  # fichier remplacé pendant la lecture (éditeur, mise à jour en cours)
            pass
    return stamp


def ui_version() -> str:
    """Version de l'interface construite (date de webapp/static/index.html) : la page se recharge quand elle change."""
    try:
        return str((STATIC / "index.html").stat().st_mtime_ns)
    except OSError:
        return ""


# --- modèles des requêtes ---------------------------------------------------------------------------------
class UrlsIn(BaseModel):
    urls: list[str]
    tags: list[str] = []
    illustration: str = ""


class ArticleEdit(BaseModel):
    key: str
    tags: list[str] | None = None
    illustration: str | None = None


class KeyIn(BaseModel):
    key: str


class RunIn(BaseModel):
    keys: list[str] = []  # vide = tous les articles en attente
    mode: str = "brouillon"  # brouillon | apercu
    force: bool = False  # retraduire aussi ce qui a déjà un brouillon


class SettingsIn(BaseModel):
    site: str | None = None
    mode: str | None = None
    engines: list[str] | None = None


class CredentialsIn(BaseModel):
    username: str
    app_password: str


# --- réglages (config.toml) ---------------------------------------------------------------------------------
def read_config(root: Path) -> dict:
    return tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))


def _set_toml(text: str, key: str, value) -> str:
    """Remplace la valeur d'une clé simple de config.toml sans toucher au reste (commentaires, prompt…)."""
    pattern = rf'(?m)^({re.escape(key)}[ \t]*=[ \t]*)(?:"[^"\n]*"|\[[^\]\n]*\])'
    if not re.search(pattern, text):
        raise StoreError(f"Réglage « {key} » introuvable dans config.toml.")
    return re.sub(pattern, lambda m: m.group(1) + json.dumps(value, ensure_ascii=False), text, count=1)


def update_config(root: Path, changes: SettingsIn) -> None:
    path = root / "config.toml"
    text = path.read_text(encoding="utf-8")
    if changes.site is not None:
        site = changes.site.strip().rstrip("/")
        if not site or " " in site or "." not in site:
            raise StoreError("Adresse du site invalide (exemple : parlafoi.fr).")
        text = _set_toml(text, "site", site)
    if changes.mode is not None:
        if changes.mode not in MODES:
            raise StoreError("Type de site inconnu.")
        text = _set_toml(text, "mode", changes.mode)
    if changes.engines is not None:
        engines = [e for e in changes.engines if e in ENGINES]
        if not engines or len(engines) != len(changes.engines):
            raise StoreError("Choisissez au moins un moteur de traduction (gemini ou gpt).")
        text = _set_toml(text, "engines", engines)
    tomllib.loads(text)  # le fichier doit rester valide
    path.write_text(text, encoding="utf-8")


# --- valeurs par défaut (remplaçables dans les tests) -------------------------------------------------------
def default_statuses(root: Path, site: str) -> dict[str, tuple[str, str]]:
    import sqlite3

    host = re.sub(r"[^a-z0-9]+", "-", site.lower().removeprefix("https://").removeprefix("http://")).strip("-")
    db_path = root / f"state-{host}.db"  # même fichier que agent.open_db
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as db:
        return {k: (s, i) for k, s, i in db.execute("SELECT url, status, info FROM jobs")}


def default_reconcile(root: Path, cfg: dict) -> None:
    """Met la base locale d'accord avec le site (brouillons mis à la corbeille ou supprimés dans WordPress)."""
    import agent

    db = agent.open_db(cfg["wordpress"]["site"], root)
    try:
        agent.reconcile(db, cfg)
    finally:
        db.close()


def default_draft_states(root: Path, cfg: dict, ids: list[int]) -> dict[int, str]:
    """État réel dans WordPress de brouillons déjà créés (lecture seule) ; {} si le type de site ne le permet pas."""
    import agent

    mod = agent.backend(cfg)
    return mod.post_states(cfg["wordpress"]["site"], ids) if hasattr(mod, "post_states") else {}


def default_account(root: Path, cfg: dict) -> dict:
    """État du compte WordPress utilisé par l'application (lecture seule)."""
    wp = cfg["wordpress"]
    if wp.get("mode", "wpcom") != "selfhosted":
        return {"mode": "wpcom", "configured": (root / "wp_token.json").exists(), "connected": None}
    if not (root / "wp_credentials.json").exists():
        return {"mode": "selfhosted", "configured": False, "connected": False}
    import wp_selfhosted

    try:
        r = wp_selfhosted.me(wp["site"])
    except Exception as e:
        return {"mode": "selfhosted", "configured": True, "connected": False, "error": f"Site injoignable ({str(e)[:120]})"}
    if r.status_code != 200:
        return {"mode": "selfhosted", "configured": True, "connected": False,
                "error": f"Identifiants refusés par le site (code {r.status_code})."}
    return _account_summary(r.json())


def _account_summary(me: dict) -> dict:
    caps = me.get("capabilities", {})
    return {
        "mode": "selfhosted", "configured": True, "connected": True,
        "username": me.get("slug"), "name": me.get("name"), "roles": me.get("roles", []),
        "can_create": bool(caps.get("edit_posts")), "can_publish": bool(caps.get("publish_posts")),
        "can_edit_others": bool(caps.get("edit_others_posts")), "can_delete_others": bool(caps.get("delete_others_posts")),
    }


def default_save_credentials(root: Path, cfg: dict, username: str, app_password: str) -> dict:
    import wp_selfhosted

    try:
        me = wp_selfhosted.authorize(cfg["wordpress"]["site"], username, app_password)
    except Exception as e:
        raise StoreError(f"Connexion refusée : vérifiez le nom d'utilisateur et le mot de passe d'application. ({str(e)[:160]})")
    return _account_summary(me)


# --- application ------------------------------------------------------------------------------------------
def create_app(root: Path, runs: RunManager | None = None,
               statuses: Callable[[Path, str], dict] = default_statuses,
               account: Callable[[Path, dict], dict] = default_account,
               save_credentials: Callable[..., dict] = default_save_credentials,
               reconcile: Callable[[Path, dict], None] = default_reconcile,
               draft_states: Callable[[Path, dict, list[int]], dict[int, str]] = default_draft_states,
               quit_callback: Callable[[], None] | None = None,
               gemini: GeminiLogin | None = None,
               chatgpt: ChatGPTLogin | None = None) -> FastAPI:
    root = Path(root).resolve()

    started_stamp = code_stamp(root)
    store = Store(root)
    runs = runs or RunManager(real_execute)
    gemini = gemini or GeminiLogin(root)
    chatgpt = chatgpt or ChatGPTLogin(root)
    app = FastAPI(title="Traducteur WordPress", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "Accès réservé à cet ordinateur."}, status_code=403)
        if (request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get("x-awt") != "1"):
            return JSONResponse({"detail": "Requête refusée."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(StoreError)
    async def store_error(_, exc: StoreError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def cfg() -> dict:
        return read_config(root)

    # --- vérification sur le site de l'état réel des brouillons déjà créés --------------------------------------
    sync_lock = threading.Lock()
    last_sync = [0.0]
    draft_cache: dict[int, str] = {}  # n° de brouillon -> état dans WordPress (draft, publish, trash, missing…)
    sync_error = [""]  # dernière erreur de vérification (site injoignable…), montrée dans l'interface

    def result_post_ids() -> set[int]:
        return {int(m.group(1)) for r in store.results().values()
                if r.get("mode") == "brouillon" and (m := POST_ID.search(r.get("draft_url") or ""))}

    def sync(wait: bool, max_age: float = 0) -> None:
        """wait=True : avant une décision (ajout, lancement, affichage des traductions faites). wait=False : en
        arrière-plan, au plus toutes les 30 s, pour suivre ce qui est fait dans WordPress (brouillon mis à la corbeille…)."""
        def work() -> None:
            c = cfg()
            errors = []
            try:
                reconcile(root, c)  # articles à traduire
            except Exception as e:  # site injoignable : la base locale reste la référence
                errors.append(str(e)[:200])
            try:  # traductions faites
                ids = result_post_ids()
                if ids:
                    draft_cache.update(draft_states(root, c, sorted(ids)))
            except Exception as e:
                errors.append(str(e)[:200])
            finally:
                last_sync[0] = time.time()
                sync_error[0] = " ; ".join(errors)

        if wait:
            with sync_lock:
                if time.time() - last_sync[0] >= max_age:
                    work()
            return
        if time.time() - last_sync[0] < 30 or not sync_lock.acquire(blocking=False):
            return

        def background() -> None:
            try:
                work()
            finally:
                sync_lock.release()

        threading.Thread(target=background, daemon=True, name="verification-brouillons").start()

    def all_articles() -> list[dict]:
        sync(wait=False)
        c = cfg()
        items = store.articles(statuses(root, c["wordpress"]["site"]), store.results())
        if runs.current and runs.current.status == "running":
            active = {i.key: i for i in runs.current.items if i.status in ("waiting", "running")}
            for it in items:
                if it["key"] in active:
                    it["status"] = "running" if active[it["key"]].status == "running" else "queued"
        return items

    # --- identité : quel Traducteur occupe ce port ? (lanceur et installateur) ----------------------------------
    @app.get("/api/identity")
    def identity():
        return {"app": "traducteur-wordpress", "root": str(root), "running": runs.running}

    # --- état général -------------------------------------------------------------------------------------
    @app.get("/api/status")
    def status():
        c = cfg()
        try:
            import templating

            tpl = templating.load_templates(str(root / c.get("templates", {}).get("dir", "articles_templates")))
            templates = {"ok": True, "count": len(tpl.sources)}
        except Exception as e:
            templates = {"ok": False, "count": 0, "error": str(e)}
        spec_dir = root / c.get("specs", {}).get("dir", "spec")
        items = all_articles()
        wp = c["wordpress"]
        creds = (root / ("wp_credentials.json" if wp.get("mode") == "selfhosted" else "wp_token.json")).exists()
        return {
            "site": wp["site"], "mode": wp.get("mode", "wpcom"), "engines": c["llm"]["engines"],
            "account_configured": creds,
            "templates": templates, "specs": len(list(spec_dir.glob("*.pdf"))) if spec_dir.is_dir() else 0,
            "counts": {s: sum(1 for i in items if i["status"] == s) for s in ("pending", "done", "error", "running", "queued")},
            "total": len(items), "running": runs.running,
            "restart_needed": code_stamp(root) > started_stamp + 1,  # redémarrage automatique en attente
            "ui_version": ui_version(),
            "drafts_check_error": sync_error[0],
            "gemini_logged_in": gemini.status().get("logged_in"),  # None : jamais vérifié
            "chatgpt_logged_in": chatgpt.status().get("logged_in"),
        }

    # --- articles -----------------------------------------------------------------------------------------
    @app.get("/api/articles")
    def articles():
        return all_articles()

    @app.post("/api/articles/urls")
    def add_urls(body: UrlsIn):
        r = store.add_urls(body.urls, [t.strip() for t in body.tags], body.illustration)
        # adresses déjà traduites autrefois (brouillon TOUJOURS présent dans WordPress, vérifié sur le site) :
        # elles ne seront pas « à traduire », il faut le dire
        if r["added"]:
            sync(wait=True)
        state = statuses(root, cfg()["wordpress"]["site"])
        r["already_done"] = [{"url": u, "draft_url": state[u][1]} for u in r["added"]
                             if state.get(u, ("", ""))[0] == "published"]
        return r

    @app.post("/api/articles/files")
    async def add_files(files: list[UploadFile] = File(...)):
        added, errors = [], []
        for f in files:
            data = await f.read()
            if len(data) > 5_000_000:
                errors.append(f"« {f.filename} » est trop gros (5 Mo maximum).")
                continue
            try:
                added.append(store.save_md(f.filename or "article.md", data))
            except StoreError as e:
                errors.append(str(e))
        return {"added": added, "errors": errors}

    @app.patch("/api/articles")
    def edit_article(body: ArticleEdit):
        if runs.running:
            raise StoreError("Attendez la fin de la traduction en cours pour modifier un article.")
        store.update_article(body.key, body.tags, body.illustration)
        return {"ok": True}

    @app.post("/api/articles/delete")
    def delete_article(body: KeyIn):
        if runs.running:
            raise StoreError("Attendez la fin de la traduction en cours pour retirer un article.")
        return {"ok": True, "message": store.delete_article(body.key)}

    # --- exécutions ---------------------------------------------------------------------------------------
    @app.post("/api/runs")
    def start_run(body: RunIn):
        if body.mode not in ("brouillon", "apercu"):
            raise StoreError("Mode inconnu.")
        c = cfg()
        if gemini.window_open or chatgpt.window_open:
            raise StoreError("Fermez d'abord la fenêtre de connexion à Gemini ou ChatGPT (bouton « C'est fait » dans Réglages).")
        if body.mode == "brouillon":
            wp = c["wordpress"]
            needed = "wp_credentials.json" if wp.get("mode") == "selfhosted" else "wp_token.json"
            if not (root / needed).exists():
                raise StoreError("Configurez d'abord votre compte WordPress (menu Réglages).")
        import inputs

        sync(wait=True)  # un brouillon mis à la corbeille dans WordPress ne compte plus comme « fait »
        jobs = inputs.csv_jobs(str(store.csv_path)) if store.csv_path.exists() else []
        if store.md_dir.is_dir():
            jobs += inputs.md_jobs(str(store.md_dir))
        state = statuses(root, c["wordpress"]["site"])
        wanted = set(body.keys)
        items, skipped = [], 0
        for key, tags, load in jobs:
            if wanted and key not in wanted:
                continue
            already = state.get(key, ("", ""))[0] == "published"
            if body.mode == "brouillon" and already and not body.force:
                skipped += 1
                continue
            if not wanted and already:
                continue
            items.append(Item(key=key, label=inputs.label(key), tags=tags, load=load))
        if not items:
            raise StoreError("Rien à traduire : " + ("ces articles ont déjà un brouillon." if skipped else
                                                      "aucun article en attente."))
        try:
            run = runs.start(body.mode, items)
        except RuntimeError as e:
            raise StoreError(str(e))
        return run.public()

    @app.get("/api/runs/current")
    def current_run():
        return runs.current.public() if runs.current else None

    @app.post("/api/runs/stop")
    def stop_run():
        runs.stop()
        return {"ok": True}

    # --- résultats ----------------------------------------------------------------------------------------
    def wp_status(r: dict) -> str | None:
        """État du brouillon dans WordPress (None : essai, ou état inconnu)."""
        m = POST_ID.search(r.get("draft_url") or "") if r.get("mode") == "brouillon" else None
        return draft_cache.get(int(m.group(1))) if m else None

    @app.get("/api/results")
    def results():
        sync(wait=True, max_age=30)  # la page doit refléter WordPress (brouillons mis à la corbeille…)
        if result_post_ids() - draft_cache.keys():  # nouveau brouillon, ou vérification précédente ratée : on revérifie
            sync(wait=True, max_age=0)
        items = sorted(store.results().values(), key=lambda r: r.get("date", ""), reverse=True)
        return [{k: r.get(k) for k in ("id", "key", "mode", "date", "title", "source_title", "source_url", "slug",
                                        "draft_url", "engine")}
                | {"warnings": len(r.get("warnings", [])), "wp_status": wp_status(r)} for r in items]

    @app.get("/api/results/{rid}")
    def result(rid: str):
        sync(wait=False)
        r = store.result(rid)
        return r | {"wp_status": wp_status(r)}

    @app.post("/api/results/delete")
    def delete_result(body: KeyIn):
        """Retire une traduction de la liste (le fichier est rangé dans output/results/retires/, jamais effacé)."""
        return {"ok": True, "message": store.archive_result(body.key)}

    # --- réglages et compte ---------------------------------------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        c = cfg()
        return {"site": c["wordpress"]["site"], "mode": c["wordpress"].get("mode", "wpcom"),
                "engines": c["llm"]["engines"], "max_words": c["llm"].get("max_words")}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        if runs.running:
            raise StoreError("Attendez la fin de la traduction en cours pour changer les réglages.")
        update_config(root, body)
        return get_settings()

    @app.get("/api/account")
    def get_account():
        return account(root, cfg())

    @app.post("/api/account")
    def post_account(body: CredentialsIn):
        c = cfg()
        if c["wordpress"].get("mode") != "selfhosted":
            raise StoreError("Pour un site WordPress.com, l'autorisation se fait avec « python agent.py --auth ».")
        if not body.username.strip() or not body.app_password.strip():
            raise StoreError("Indiquez le nom d'utilisateur et le mot de passe d'application.")
        return save_credentials(root, c, body.username.strip(), body.app_password.strip())

    # --- connexion facultative à Gemini et à ChatGPT (fortement conseillée : meilleurs modèles) -------------------
    def register_login(name: str, label: str, login, other, host: str, is_in) -> None:
        """/api/<name> : état ; /api/<name>/login : ouvre la fenêtre ; /api/<name>/close : « C'est fait »."""

        @app.get(f"/api/{name}")
        def login_status(verify: bool = False):
            if verify and not login.window_open and not other.window_open and not runs.running:
                try:  # relit les cookies du profil (connexion expirée ?)
                    from webapp.gemini_login import cookie_names, save_status
                    save_status(root, is_in([{"name": n} for n in cookie_names(cfg()["llm"]["profile_dir"], host)]),
                                login.state_file)
                except OSError:
                    pass  # profil illisible (navigateur ouvert) : on garde le dernier état connu
            return login.status()

        @app.post(f"/api/{name}/login")
        def login_open():
            if runs.running:
                raise StoreError(f"Une traduction est en cours : attendez sa fin pour vous connecter à {label}.")
            if other.window_open:  # même profil de navigateur : une seule fenêtre à la fois
                raise StoreError("Une autre fenêtre de connexion est déjà ouverte : terminez-la d'abord (« C'est fait »).")
            try:
                login.open(cfg()["llm"]["profile_dir"])
            except RuntimeError as e:
                raise StoreError(str(e))
            return login.status()

        @app.post(f"/api/{name}/close")
        def login_close():
            login.close()
            return {"ok": True}

    from webapp.gemini_login import is_chatgpt_logged_in, is_logged_in
    register_login("gemini", "Gemini", gemini, chatgpt, "google.com", is_logged_in)
    register_login("chatgpt", "ChatGPT", chatgpt, gemini, "chatgpt.com", is_chatgpt_logged_in)

    @app.post("/api/quit")
    def quit_program():
        """Bouton « Quitter » : arrête le programme (jamais pendant une traduction)."""
        if quit_callback is None:
            raise StoreError("Ce programme ne peut pas être arrêté depuis l'interface.")
        if runs.running:
            raise StoreError("Une traduction est en cours : attendez sa fin (ou arrêtez-la) avant de quitter.")
        threading.Timer(0.5, quit_callback).start()  # laisse partir la réponse avant l'arrêt
        return {"ok": True}

    @app.post("/api/account/logout")
    def logout():
        """Déconnexion : oublie l'identifiant et le mot de passe d'application enregistrés sur cet ordinateur.
        Le mot de passe reste valable côté WordPress (il se révoque dans le Profil du compte)."""
        if runs.running:
            raise StoreError("Attendez la fin de la traduction en cours pour vous déconnecter.")
        (root / "wp_credentials.json").unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/logs")
    def logs(lines: int = 150):
        f = root / "agent.log"
        if not f.exists():
            return {"lines": []}
        return {"lines": f.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, min(lines, 1000)):]}

    @app.get("/api/{rest:path}")
    def api_not_found(rest: str):
        raise HTTPException(404, "Adresse inconnue.")

    # --- interface (fichiers construits par « npm run build » dans webapp/static) ---------------------------
    static = STATIC
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = (static / path).resolve()
        if path and target.is_file() and static.resolve() in target.parents:
            return FileResponse(target)
        index = static / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse("<p>L'interface n'est pas encore construite : dans le dossier frontend, lancez "
                            "<code>npm install</code> puis <code>npm run build</code>.</p>", status_code=503)

    return app
