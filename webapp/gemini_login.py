"""Connexion facultative (mais fortement conseillée) à un compte Google dans Gemini, et à un compte ChatGPT.

Sans compte, Gemini ne donne accès qu'à ses modèles les plus limités : traductions moins bonnes, refus plus fréquents
(« Cela dépasse mes capacités »). La connexion se fait UNE fois, à la main, dans le même profil de navigateur que les
traductions (config.toml : [llm] profile_dir) : Google la mémorise ensuite. Le programme ne voit ni ne saisit jamais le
mot de passe Google ; il regarde seulement si les cookies de session Google sont présents.
Même principe pour ChatGPT (cookie de session de chatgpt.com). Les deux sites partagent le même profil de navigateur :
une seule fenêtre de connexion à la fois."""
import datetime
import json
import threading
from pathlib import Path
from typing import Callable

STATE_FILE = "gemini_session.json"
CHATGPT_STATE_FILE = "chatgpt_session.json"
GEMINI_URL = "https://gemini.google.com/app"
CHATGPT_URL = "https://chatgpt.com/"
GOOGLE_AUTH_COOKIES = {"__Secure-1PSID", "SID", "__Secure-3PSID"}  # présents seulement quand on est connecté
CHATGPT_SESSION_COOKIE = "__Secure-next-auth.session-token"  # parfois découpé en « .0 », « .1 » ; absent hors connexion


def is_logged_in(cookies: list[dict]) -> bool:
    return any(c.get("name") in GOOGLE_AUTH_COOKIES for c in cookies)


def is_chatgpt_logged_in(cookies: list[dict]) -> bool:
    return any(str(c.get("name", "")).startswith(CHATGPT_SESSION_COOKIE) for c in cookies)


def save_status(root: Path, logged_in: bool, state_file: str = STATE_FILE) -> None:
    (Path(root) / state_file).write_text(json.dumps({
        "logged_in": logged_in, "checked": datetime.datetime.now().isoformat(timespec="seconds"),
    }), encoding="utf-8")


def load_status(root: Path, state_file: str = STATE_FILE) -> dict:
    try:
        return json.loads((Path(root) / state_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"logged_in": None, "checked": None}  # jamais vérifié


def cookie_names(profile_dir: str, host: str = "google.com") -> set[str]:
    """Noms des cookies Google enregistrés dans le profil (lus sur le disque : seuls les noms, jamais les valeurs).
    Lève OSError si le fichier est inaccessible (navigateur encore ouvert sur certains systèmes)."""
    import shutil
    import sqlite3
    import tempfile

    profile = Path(profile_dir)
    db = next((f for f in (profile / "Default" / "Network" / "Cookies", profile / "Default" / "Cookies") if f.is_file()), None)
    if db is None:
        return set()
    with tempfile.TemporaryDirectory() as tmp:  # copie : ne jamais toucher au fichier du navigateur
        copy = Path(tmp) / "Cookies"
        shutil.copyfile(db, copy)
        con = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT name FROM cookies WHERE host_key LIKE ?", (f"%{host}",)).fetchall()
        except sqlite3.Error as e:
            raise OSError(str(e)) from e
        finally:
            con.close()
    return {name for (name,) in rows}


def chromium_path() -> str:
    """Le Google Chrome de l'ordinateur, le même que pour les traductions (llm_browser.installed_chrome).
    Le Chromium fourni avec Playwright ne convient pas : Google refuse d'y connecter un compte."""
    from llm_browser import installed_chrome

    chrome = installed_chrome()
    if not chrome:
        raise RuntimeError("Google Chrome est nécessaire pour se connecter. Installez-le (gratuit, "
                           "google.com/chrome), puis réessayez")
    return chrome


def close_gently(proc) -> None:
    """Ferme le navigateur comme si l'utilisateur cliquait sur la croix, pour qu'il enregistre la connexion."""
    import subprocess
    import sys

    if proc.poll() is not None:
        return
    if sys.platform.startswith("win"):  # sans /F : demande de fermeture normale des fenêtres
        subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        proc.terminate()  # SIGTERM : Chromium se ferme proprement
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(5)


def browser_session(profile_dir: str, on_check: Callable[[bool], None], should_stop: Callable[[], bool],
                    url: str = GEMINI_URL, host: str = "google.com", check: Callable[[list[dict]], bool] = is_logged_in) -> None:
    """Ouvre Gemini (ou, selon `url`, ChatGPT) dans le profil des traductions et attend que l'utilisateur ferme la fenêtre (ou « C'est fait »).

    Le navigateur est lancé comme un navigateur NORMAL, sans être piloté : Google refuse la connexion dans un
    navigateur piloté par un programme (« Ce navigateur ou cette application ne sont peut-être pas sécurisés »).
    La connexion est donc vérifiée en lisant les noms des cookies du profil, pas en pilotant la fenêtre."""
    import subprocess
    import time

    profile = Path(profile_dir).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([chromium_path(), f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--new-window", url])
    try:
        while proc.poll() is None and not should_stop():
            time.sleep(1)
            try:  # pendant que la fenêtre est ouverte : possible seulement si le système laisse lire le fichier
                if check([{"name": n} for n in cookie_names(str(profile), host)]):
                    on_check(True)
            except OSError:
                pass
    finally:
        close_gently(proc)
    try:
        on_check(check([{"name": n} for n in cookie_names(str(profile), host)]))
    except OSError:
        pass  # état inconnu : la prochaine traduction le vérifiera


def chatgpt_session(profile_dir: str, on_check: Callable[[bool], None], should_stop: Callable[[], bool]) -> None:
    return browser_session(profile_dir, on_check, should_stop, url=CHATGPT_URL, host="chatgpt.com",
                           check=is_chatgpt_logged_in)


class GeminiLogin:
    """Une seule fenêtre de connexion à la fois ; jamais pendant une traduction (même profil de navigateur)."""
    state_file = STATE_FILE
    thread_name = "connexion-gemini"

    def __init__(self, root: Path, session: Callable | None = None):
        self.root = Path(root)
        self._session = session or self.default_session
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.window_open = False
        self.error = ""

    default_session = staticmethod(browser_session)

    def status(self) -> dict:
        return load_status(self.root, self.state_file) | {"window_open": self.window_open, "error": self.error}

    def open(self, profile_dir: str) -> None:
        with self._lock:
            if self.window_open:
                raise RuntimeError("La fenêtre de connexion à Gemini est déjà ouverte.")
            self.window_open, self.error = True, ""
            self._stop.clear()
        threading.Thread(target=self._run, args=(profile_dir,), daemon=True, name=self.thread_name).start()

    def close(self) -> None:
        self._stop.set()

    def _run(self, profile_dir: str) -> None:
        try:
            self._session(profile_dir, lambda ok: save_status(self.root, ok, self.state_file), self._stop.is_set)
        except Exception as e:  # navigateur impossible à ouvrir (profil déjà utilisé…)
            self.error = f"La fenêtre de connexion n'a pas pu s'ouvrir ({str(e).splitlines()[0][:160]})."
        finally:
            self.window_open = False


class ChatGPTLogin(GeminiLogin):
    """Même chose pour ChatGPT (chatgpt.com), avec son propre fichier d'état."""
    state_file = CHATGPT_STATE_FILE
    thread_name = "connexion-chatgpt"
    default_session = staticmethod(chatgpt_session)
