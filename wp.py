"""Publication de brouillons sur WordPress.com (forfait gratuit) via l'API OAuth2 publique."""
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import truststore

# Utilise le magasin de certificats de Windows : évite « CERTIFICATE_VERIFY_FAILED » quand un
# antivirus/proxy inspecte le HTTPS avec son propre certificat racine.
truststore.inject_into_ssl()

API = "https://public-api.wordpress.com"
TOKEN_FILE = Path("wp_token.json")
REDIRECT = "http://localhost:8765/callback"


def authorize(client_id: str, client_secret: str) -> None:
    """À lancer UNE fois : ouvre le navigateur, récupère le code, sauvegarde le token."""
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(parse_qs(urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Autorisation reçue, vous pouvez fermer cet onglet.".encode())

        def log_message(self, *a):
            pass

    server = HTTPServer(("localhost", 8765), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    webbrowser.open(
        f"{API}/oauth2/authorize?"
        + urlencode({"client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code"})
    )
    while "code" not in got:
        if "error" in got:
            raise RuntimeError(f"Autorisation refusée : {got['error']}")
        time.sleep(0.5)
    r = requests.post(
        f"{API}/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
            "code": got["code"][0],
        },
        timeout=30,
    )
    r.raise_for_status()
    TOKEN_FILE.write_text(json.dumps(r.json()), encoding="utf-8")
    print("Token sauvegardé dans", TOKEN_FILE)


def _headers() -> dict:
    token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["access_token"]
    return {"Authorization": f"Bearer {token}"}


def list_categories(site: str) -> list[str]:
    """Noms des catégories existantes du site (la spec demande de choisir une catégorie)."""
    r = requests.get(f"{API}/rest/v1.1/sites/{site}/categories", params={"number": 100},
                     headers=_headers(), timeout=30)
    r.raise_for_status()
    return [c["name"] for c in r.json().get("categories", [])]


def create_draft(site: str, title: str, html: str, tags: list[str], categories: list[str] | None = None,
                 slug: str | None = None) -> str:
    """Crée un brouillon et retourne son URL d'édition/prévisualisation. `slug` = identifiant de l'URL de l'article."""
    data = {"title": title, "content": html, "status": "draft", "tags": ",".join(tags)}
    if categories:
        data["categories"] = ",".join(categories)
    if slug:
        data["slug"] = slug
    r = requests.post(f"{API}/rest/v1.1/sites/{site}/posts/new", headers=_headers(), data=data, timeout=60)
    r.raise_for_status()
    return r.json().get("URL", "")


if __name__ == "__main__":
    import sys

    authorize(sys.argv[1], sys.argv[2])
