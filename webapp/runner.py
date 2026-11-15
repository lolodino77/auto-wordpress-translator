"""Exécution de la pipeline en arrière-plan pour l'interface : une seule exécution à la fois, suivi article par article,
arrêt propre entre deux articles. Le vrai travail est fait par agent.process (mêmes règles et garde-fous que la ligne
de commande)."""
import collections
import datetime
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

STEPS = ["load", "translate", "publish", "done"]


@dataclass
class Item:
    key: str
    label: str
    tags: list[str]
    load: Callable
    status: str = "waiting"  # waiting | running | done | error | skipped
    step: str = ""
    draft_url: str = ""
    error: str = ""
    started: float | None = None
    ended: float | None = None

    def public(self) -> dict:
        return {"key": self.key, "label": self.label, "status": self.status, "step": self.step,
                "draft_url": self.draft_url, "error": self.error,
                "seconds": round((self.ended or time.time()) - self.started) if self.started else 0}


@dataclass
class Run:
    id: str
    mode: str  # "brouillon" (crée les brouillons) | "apercu" (rien n'est envoyé à WordPress)
    items: list[Item]
    status: str = "running"  # running | done | stopped | error
    started: float = field(default_factory=time.time)
    ended: float | None = None
    stop_requested: bool = False
    message: str = ""
    logs: collections.deque = field(default_factory=lambda: collections.deque(maxlen=400))

    def log(self, text: str) -> None:
        self.logs.append(f"{datetime.datetime.now():%H:%M:%S} {text}")

    def public(self) -> dict:
        counts = collections.Counter(i.status for i in self.items)
        return {
            "id": self.id, "mode": self.mode, "status": self.status, "message": self.message,
            "stop_requested": self.stop_requested,
            "seconds": round((self.ended or time.time()) - self.started),
            "total": len(self.items), "done": counts["done"], "errors": counts["error"],
            "skipped": counts["skipped"], "items": [i.public() for i in self.items], "logs": list(self.logs)[-200:],
        }


class _RunLogHandler(logging.Handler):
    def __init__(self, run: Run):
        super().__init__(level=logging.INFO)
        self.run = run

    def emit(self, record):
        self.run.log(record.getMessage())


class RunManager:
    """execute(run) fait le travail dans le fil d'arrière-plan ; injectable pour les tests."""

    def __init__(self, execute: Callable[["Run"], None]):
        self._execute = execute
        self._lock = threading.Lock()
        self.current: Run | None = None

    @property
    def running(self) -> bool:
        return bool(self.current and self.current.status == "running")

    def start(self, mode: str, items: list[Item]) -> Run:
        with self._lock:
            if self.running:
                raise RuntimeError("Une traduction est déjà en cours.")
            run = Run(id=datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), mode=mode, items=items)
            self.current = run
        threading.Thread(target=self._thread, args=(run,), daemon=True, name="traduction").start()
        return run

    def stop(self) -> None:
        if self.running:
            self.current.stop_requested = True
            self.current.log("Arrêt demandé : la traduction s'arrêtera après l'article en cours.")

    def _thread(self, run: Run) -> None:
        handler = _RunLogHandler(run)
        logger = logging.getLogger("agent")
        logger.addHandler(handler)
        try:
            self._execute(run)
            run.status = "stopped" if run.stop_requested and any(i.status == "waiting" for i in run.items) else "done"
        except Exception as e:  # erreur générale (navigateur impossible à ouvrir, réglages…)
            run.status, run.message = "error", str(e)
            run.log(f"ERREUR : {e}")
            for i in run.items:
                if i.status in ("waiting", "running"):
                    i.status, i.error = "error", i.error or "Non traité : " + str(e)
        finally:
            run.ended = time.time()
            logger.removeHandler(handler)


def real_execute(run: Run) -> None:
    """Le vrai travail : ouvre le navigateur une fois, puis traite les articles un par un."""
    import tomllib
    from pathlib import Path

    import agent
    from llm_browser import Browser

    cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
    site = cfg["wordpress"]["site"]
    preview = run.mode == "apercu"
    db = agent.open_db(site)
    categories: list[str] = []
    if not preview:
        try:
            categories = agent.backend(cfg).list_categories(site)
        except Exception as e:
            run.log(f"Catégories du site illisibles ({str(e)[:160]}) : aucune catégorie ne sera proposée.")
    run.log("Ouverture du navigateur (une fenêtre va apparaître : ne la fermez pas).")
    with Browser(cfg["llm"]["profile_dir"], cfg["llm"]["headless"]) as browser:
        for item in run.items:
            if run.stop_requested:
                break
            item.status, item.started = "running", time.time()
            run.log(f"Début : {item.label}")

            def on_step(name: str, item=item) -> None:
                item.step = name

            try:
                draft = agent.process(item.key, item.tags, item.load, cfg, browser, categories,
                                      on_step=on_step, preview=preview)
                item.status, item.draft_url = "done", draft
                if not preview:
                    agent.set_status(db, item.key, "published", draft)
                run.log(f"Terminé : {item.label}" + (f" -> {draft}" if draft else " (aperçu)"))
            except Exception as e:
                item.status, item.error = "error", str(e)
                if not preview:
                    agent.set_status(db, item.key, "error", str(e))
                run.log(f"ÉCHEC : {item.label} : {e}")
            finally:
                item.ended = time.time()
