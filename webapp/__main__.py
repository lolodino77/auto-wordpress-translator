"""Lance l'interface : python -m webapp  (puis le navigateur s'ouvre tout seul sur http://127.0.0.1:8710).

Options : --port 8710 (autre port si besoin), --no-browser (ne pas ouvrir le navigateur)."""
import argparse
import os
import socket
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Interface locale du traducteur WordPress")
    ap.add_argument("--port", type=int, default=8710)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}/"

    if _port_busy(args.port):  # déjà lancée (double-clic répété) : on rouvre simplement la page
        print(f"L'interface tourne déjà : {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    os.chdir(ROOT)  # la pipeline utilise des chemins relatifs (config.toml, input/, output/…)
    import uvicorn

    from webapp.server import create_app

    print("\n  Traducteur WordPress : l'interface s'ouvre dans votre navigateur.")
    print(f"  Adresse : {url}")
    print("  Pour arrêter : fermez cette fenêtre (ou Ctrl+C).\n")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(ROOT), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
