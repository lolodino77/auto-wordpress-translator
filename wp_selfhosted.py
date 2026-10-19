"""Publication de brouillons sur un WordPress AUTO-HÉBERGÉ (REST API native /wp-json/wp/v2) avec un « mot de passe
d'application » (Utilisateurs > Profil > Mots de passe d'application).

Le mot de passe est lié à UN utilisateur : l'application a exactement les droits de son rôle (Contributeur : créer et
modifier ses propres articles, jamais publier). Identifiants saisis dans le terminal (jamais dans le chat) et
enregistrés dans wp_credentials.json (exclu de Git). Même interface que wp.py : list_categories / create_draft.
"""
import html as htmllib
import json
import logging
from pathlib import Path

import requests
import truststore

truststore.inject_into_ssl()
log = logging.getLogger("agent")
CRED_FILE = Path("wp_credentials.json")
TIMEOUT = 30


def base_url(site: str) -> str:
    site = site.strip().rstrip("/")
    return site if site.startswith("http") else "https://" + site


def _api(site: str, path: str) -> str:
    return f"{base_url(site)}/wp-json/wp/v2/{path.lstrip('/')}"


def _auth() -> tuple[str, str]:
    c = json.loads(CRED_FILE.read_text(encoding="utf-8"))
    return c["username"], c["app_password"]


def me(site: str) -> requests.Response:
    """Identité et droits du compte (context=edit expose rôles et capacités). Réponse brute."""
    return requests.get(_api(site, "users/me"), params={"context": "edit"}, auth=_auth(), timeout=TIMEOUT)


def authorize(site: str, username: str, app_password: str) -> dict:
    """À lancer UNE fois : vérifie les identifiants puis les enregistre. Retourne la description du compte."""
    r = requests.get(_api(site, "users/me"), params={"context": "edit"}, auth=(username, app_password), timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Identifiants refusés par {base_url(site)} : HTTP {r.status_code} {r.text[:300]}")
    CRED_FILE.write_text(json.dumps({"site": base_url(site), "username": username, "app_password": app_password}),
                         encoding="utf-8")
    return r.json()


def list_categories(site: str) -> list[str]:
    # pas de hide_empty : ce paramètre est refusé (403) à un compte Contributeur sur parlafoi.fr
    r = requests.get(_api(site, "categories"), params={"per_page": 100}, auth=_auth(), timeout=TIMEOUT)
    if r.status_code in (401, 403):  # les catégories sont publiques : nouvel essai sans identifiants
        log.warning("Catégories refusées avec identifiants (HTTP %s %s) : nouvel essai anonyme", r.status_code, r.text[:200])
        r = requests.get(_api(site, "categories"), params={"per_page": 100}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Catégories illisibles : HTTP {r.status_code} {r.text[:300]}")
    return [htmllib.unescape(c["name"]) for c in r.json()]


last_warnings: list[str] = []  # avertissements du dernier create_draft (repris dans la fiche de relecture)


def _warn(msg: str) -> None:
    last_warnings.append(msg)
    log.warning(msg)


def _term_id(site: str, taxonomy: str, name: str, create: bool) -> int | None:
    """Identifiant d'une étiquette/catégorie par son nom, ou None. JAMAIS bloquant : si le site restreint l'accès (par
    ex. plugin Kadence/iThemes Security : « itsec_rest_api_access_restricted »), le brouillon est créé sans cette valeur."""
    r = requests.get(_api(site, taxonomy), params={"search": name, "per_page": 100}, auth=_auth(), timeout=TIMEOUT)
    if r.status_code != 200:
        _warn(f"{taxonomy} « {name} » non posé(e) : lecture refusée par le site (HTTP {r.status_code} "
              f"{r.text[:120]}). À ajouter à la main.")
        return None
    for t in r.json():
        if htmllib.unescape(t["name"]).casefold() == name.casefold():
            return t["id"]
    if create:
        c = requests.post(_api(site, taxonomy), json={"name": name}, auth=_auth(), timeout=TIMEOUT)
        if c.status_code in (200, 201):
            return c.json()["id"]
        _warn(f"Impossible de créer {taxonomy} « {name} » (HTTP {c.status_code} {c.text[:120]}) : à créer à la main.")
    return None


def create_draft(site: str, title: str, html: str, tags: list[str], categories: list[str] | None = None,
                 slug: str | None = None) -> str:
    """Crée un brouillon (status=draft, jamais autre chose). Retourne l'adresse de modification dans l'administration."""
    last_warnings.clear()
    payload: dict = {"title": title, "content": html, "status": "draft"}
    if slug:
        payload["slug"] = slug
    tag_ids = [i for i in (_term_id(site, "tags", t, create=True) for t in tags) if i]
    if len(tag_ids) < len(tags):
        _warn(f"{len(tags) - len(tag_ids)} étiquette(s) sur {len(tags)} non posée(s) : {', '.join(tags)}")
    if tag_ids:
        payload["tags"] = tag_ids
    cat_ids = [i for i in (_term_id(site, "categories", c, create=False) for c in (categories or [])) if i]
    if cat_ids:
        payload["categories"] = cat_ids
    if categories and "categories" not in payload:
        _warn(f"Catégorie non posée : {', '.join(categories)} (illisible ou inconnue du site). À choisir à la main.")
    r = requests.post(_api(site, "posts"), json=payload, auth=_auth(), timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Création du brouillon refusée : HTTP {r.status_code} {r.text[:400]}")
    return f"{base_url(site)}/wp-admin/post.php?post={r.json()['id']}&action=edit"
