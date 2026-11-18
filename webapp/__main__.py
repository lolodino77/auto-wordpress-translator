"""Lance l'interface : python -m webapp  (puis le navigateur s'ouvre tout seul sur http://127.0.0.1:8710).

Options : --port 8710 (autre port si besoin), --no-browser (ne pas ouvrir le navigateur).

Mise à jour sans redémarrage manuel : le programme tourne en deux étages. Le « gardien » (ce que lance le double-clic)
garde la fenêtre ouverte et relance le serveur chaque fois que celui-ci le demande. Le serveur surveille son propre code
Python : dès qu'un fichier change (mise à jour, correction), il s'arrête proprement et le gardien le relance avec la
nouvelle version, en 1 à 2 secondes. Jamais pendant une traduction : il attend la fin de l'article en cours. La page
ouverte dans le navigateur se reconnecte et se recharge seule si l'interface a changé."""
import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESTART = 3  # code de sortie du serveur : « relance-moi, le code a changé »
CHECK_EVERY = 1.5  # secondes entre deux vérifications du code


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


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
    server = uvicorn.Server(uvicorn.Config(create_app(ROOT, runs=runs), host="127.0.0.1", port=port, log_level="warning"))
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
    print("  Pour arrêter : fermez cette fenêtre (ou Ctrl+C). Les mises à jour s'appliquent toutes seules.\n")
    if open_browser:
        threading.Timer(2.0, webbrowser.open, args=(url,)).start()
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

    if args.serve:
        sys.exit(serve(args.port))

    url = f"http://127.0.0.1:{args.port}/"
    if _port_busy(args.port):  # déjà lancée (double-clic répété) : on rouvre simplement la page
        print(f"L'interface tourne déjà : {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    sys.exit(guard(args.port, not args.no_browser))


if __name__ == "__main__":
    main()
