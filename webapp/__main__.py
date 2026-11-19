"""Lance l'interface : python -m webapp  (puis le navigateur s'ouvre tout seul sur http://127.0.0.1:8710).

Options : --port 8710 (autre port si besoin), --no-browser (ne pas ouvrir le navigateur).

Mise à jour sans redémarrage manuel : le programme tourne en deux étages. Le « gardien » (ce que lance le double-clic)
garde la fenêtre ouverte et relance le serveur chaque fois que celui-ci le demande. Le serveur surveille son propre code
Python : dès qu'un fichier change (mise à jour, correction), il s'arrête proprement et le gardien le relance avec la
nouvelle version, en 1 à 2 secondes. Jamais pendant une traduction : il attend la fin de l'article en cours. La page
ouverte dans le navigateur se reconnecte et se recharge seule si l'interface a changé.

Lancé par l'icône ou « Ouvrir le Traducteur » (pythonw.exe), le programme n'ouvre AUCUNE fenêtre noire : il tourne en arrière-plan, son
journal va dans traducteur.log, et le bouton « Quitter » de l'interface l'arrête. En cas d'échec au démarrage, une boîte
de message l'explique."""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESTART = 3  # code de sortie du serveur : « relance-moi, le code a changé »
CHECK_EVERY = 1.5  # secondes entre deux vérifications du code


LOG_FILE = ROOT / "traducteur.log"
TITLE = "Traducteur d'articles"


def background_mode() -> bool:
    """Vrai quand il n'y a pas de console (pythonw.exe : icône, « Ouvrir le Traducteur ») : plus de print possible."""
    return sys.stdout is None or sys.stderr is None


def redirect_output_to_log() -> None:
    """Sans console, print() et les erreurs iraient nulle part : on les écrit dans traducteur.log (taille limitée)."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.replace(LOG_FILE.with_suffix(".old.log"))
        stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w")
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} démarrage ===", file=stream)
    sys.stdout = sys.stderr = stream


def show_message(text: str) -> None:
    """Boîte de message (Windows) quand il n'y a pas de console où écrire l'erreur."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)
        except Exception:
            pass


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def running_root(port: int) -> str | None:
    """None : port libre. Sinon le dossier du Traducteur qui l'occupe, ou "" si c'est un autre programme (ou une
    ancienne version du Traducteur, qui ne sait pas répondre)."""
    if not _port_busy(port):
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/identity", timeout=3) as r:
            data = json.load(r)
        return data.get("root", "") if data.get("app") == "traducteur-wordpress" else ""
    except Exception:
        return ""


def same_dir(a: str | Path, b: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def choose_port(first: int, root: Path, probe=running_root, tries: int = 10) -> tuple[int, bool]:
    """(port, déjà ouvert). Déjà ouvert : CE Traducteur tourne sur ce port (double-clic répété). Sinon le premier port
    libre à partir de `first` : un autre programme (ou un autre exemplaire du Traducteur, par exemple la version de
    développement) peut occuper 8710 sans empêcher celui-ci de démarrer."""
    for port in range(first, first + tries):
        occupant = probe(port)
        if occupant is None:
            return port, False
        if occupant and same_dir(occupant, root):
            return port, True
    raise SystemExit(f"Aucun port libre entre {first} et {first + tries - 1} : fermez d'autres programmes, puis relancez.")


def should_restart(stamp_now: float, started: float, previous: float, running: bool) -> bool:
    """Le code a changé depuis le démarrage, n'a plus bougé depuis la vérification précédente (plusieurs fichiers
    modifiés d'affilée : on attend la fin), et aucune traduction n'est en cours."""
    return stamp_now > started + 1 and stamp_now == previous and not running


def serve(port: int) -> int:
    """Étage serveur. Retourne RESTART si le code a changé (le gardien relance alors le programme)."""
    import uvicorn

    from webapp.runner import RunManager, real_execute
    from webapp.server import code_stamp, create_app

    for _ in range(40):  # l'ancien serveur libère le port pendant un redémarrage
        if not _port_busy(port):
            break
        time.sleep(0.25)
    runs = RunManager(real_execute)
    holder: dict = {}

    def quit_program() -> None:  # bouton « Quitter » de l'interface
        holder["server"].should_exit = True

    server = uvicorn.Server(uvicorn.Config(create_app(ROOT, runs=runs, quit_callback=quit_program), host="127.0.0.1",
                                           port=port, log_level="warning"))
    holder["server"] = server
    started = code_stamp(ROOT)
    restart = threading.Event()

    def watch() -> None:
        previous = started
        waiting_shown = False
        while not server.should_exit:
            time.sleep(CHECK_EVERY)
            now = code_stamp(ROOT)
            if now > started + 1 and runs.running and not waiting_shown:
                print("  Nouvelle version prête : elle s'appliquera à la fin de la traduction en cours.")
                waiting_shown = True
            if should_restart(now, started, previous, runs.running):
                restart.set()
                server.should_exit = True
                return
            previous = now

    threading.Thread(target=watch, daemon=True, name="surveillance-du-code").start()
    server.run()
    return RESTART if restart.is_set() else 0


def guard(port: int, open_browser: bool) -> int:
    """Étage gardien : garde la fenêtre ouverte et relance le serveur après chaque mise à jour du code."""
    from webapp.server import code_stamp

    url = f"http://127.0.0.1:{port}/"
    print("\n  Traducteur WordPress : " + ("l'interface s'ouvre dans votre navigateur." if open_browser
                                         else "ouvrez l'adresse ci-dessous dans votre navigateur."))
    print(f"  Adresse : {url}")
    if background_mode():
        print("  Pour arrêter : bouton « Quitter » de l'interface. Les mises à jour s'appliquent toutes seules.\n")
    else:
        print("  Pour arrêter : fermez cette fenêtre (ou Ctrl+C), ou bouton « Quitter » de l'interface. "
              "Les mises à jour s'appliquent toutes seules.\n")
    if open_browser:
        def open_when_ready() -> None:
            for _ in range(60):  # le serveur met 1 à 3 secondes à répondre
                if running_root(port):
                    break
                time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=open_when_ready, daemon=True, name="ouverture-navigateur").start()
    command = [sys.executable, "-m", "webapp", "--serve", "--port", str(port)]
    first = True
    while True:
        try:
            code = subprocess.run(command, cwd=ROOT).returncode
        except KeyboardInterrupt:
            return 0
        if code == RESTART:
            print(f"  {time.strftime('%H:%M:%S')} Nouvelle version détectée : redémarrage automatique…")
            first = False
            continue
        if code == 0:
            return 0
        if first:  # ne démarre pas du tout : on montre l'erreur (le lanceur garde la fenêtre ouverte)
            if background_mode():
                show_message("Le Traducteur n'a pas pu démarrer.\n\nLe détail est dans le fichier :\n" + str(LOG_FILE))
            return code
        # une mise à jour contient une erreur : on attend la correction suivante au lieu de fermer la fenêtre
        print("  La nouvelle version ne démarre pas (erreur ci-dessus). Nouvel essai dès la prochaine modification du code…")
        broken = code_stamp(ROOT)
        try:
            while code_stamp(ROOT) == broken:
                time.sleep(CHECK_EVERY)
        except KeyboardInterrupt:
            return 0
        time.sleep(CHECK_EVERY)  # laisser finir l'écriture des fichiers
        print(f"  {time.strftime('%H:%M:%S')} Code modifié : nouvel essai de démarrage…")


def main() -> None:
    ap = argparse.ArgumentParser(description="Interface locale du traducteur WordPress")
    ap.add_argument("--port", type=int, default=8710)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)  # étage serveur (lancé par le gardien)
    args = ap.parse_args()
    os.chdir(ROOT)  # la pipeline utilise des chemins relatifs (config.toml, input/, output/…)
    if (ROOT / "runtime" / "browsers").is_dir():  # version portable : navigateur rangé dans le dossier du programme
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "runtime" / "browsers"))
    if background_mode():
        redirect_output_to_log()

    if args.serve:
        sys.exit(serve(args.port))

    port, already = choose_port(args.port, ROOT)
    url = f"http://127.0.0.1:{port}/"
    if already:  # déjà lancé (double-clic répété) : on rouvre simplement la page
        print(f"L'interface tourne déjà : {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    if port != args.port:
        print(f"\n  (Le port {args.port} est déjà pris par un autre programme : le Traducteur utilise le port {port}.)")
    sys.exit(guard(port, not args.no_browser))


if __name__ == "__main__":
    main()
