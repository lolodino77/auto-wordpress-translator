"""Test (site auto-hébergé, ex. parlafoi.fr) : le compte de l'application n'a PAS les droits interdits.
Usage : python checks/selfhosted/check_permissions.py ["Titre exact de l'article d'un autre auteur"]

Étapes, avec la réponse BRUTE du serveur à chaque tentative :
  A. tente de MODIFIER l'article d'un autre auteur (par défaut « Malebranche contre les fausses généralisations ») ;
  B. tente de le SUPPRIMER (WordPress le mettrait à la corbeille) ;
  C. CRÉE un article de test vide, en brouillon (cela doit marcher) ;
  D. tente de le PUBLIER (doit être refusé) ;
  E. range l'article de test à la corbeille (le compte peut supprimer ses propres articles non publiés).
Si une action interdite passe, le script l'annule aussitôt (titre remis, article restauré, test remis en brouillon).
Une connexion coupée par le serveur n'est jamais comptée comme un succès : l'état réel de l'article est relu.
Sortie 0 = tout est refusé comme prévu ; 1 = au moins une action interdite est passée (puis annulée) ; 2 = non concluant.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet
sys.path.insert(0, str(ROOT))  # pour importer wp.py / wp_selfhosted.py
os.chdir(ROOT)  # config.toml, wp_token.json, wp_credentials.json sont lus depuis la racine du projet

import sys
import time
import tomllib

import requests

import wp_selfhosted as ws

TARGET_TITLE = sys.argv[1] if len(sys.argv) > 1 else "Malebranche contre les fausses généralisations"
site = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]["site"]
auth = ws._auth()
failures = []


def send(method, path, tries=1, **kw):
    """Envoie une requête. None si le serveur coupe la connexion sans répondre (jamais interprété comme un succès)."""
    for i in range(1, tries + 1):
        try:
            return requests.request(method, ws._api(site, path), auth=auth, timeout=30, **kw)
        except requests.ConnectionError as e:
            print(f"   (connexion coupée par le serveur, essai {i}/{tries} : {type(e).__name__})")
            time.sleep(6)
    return None


def raw(resp):
    """Réponse EXACTE du serveur, telle quelle."""
    if resp is None:
        print("   AUCUNE RÉPONSE : le serveur a coupé la connexion (rien ne prouve que l'action ait été faite ou non).")
        return
    print(f"   HTTP {resp.status_code} {resp.reason}")
    print("   --- corps brut ---")
    print(resp.text)
    print("   --- fin du corps brut ---")


def read_json(path, tries=3, **params):
    r = send("GET", path, tries=tries, params=params)
    return r.json() if r is not None and r.status_code == 200 else None


# 0. identité du compte et article visé (lectures : réessayées)
me = read_json("users/me", context="edit")
if not me:
    print("Test non concluant : impossible de lire le compte (identifiants ou connexion).")
    sys.exit(2)
caps = me["capabilities"]
print(f"Compte de l'application : « {me['slug']} » (n° {me['id']}), rôle(s) {me['roles']}, "
      f"publish_posts={bool(caps.get('publish_posts'))}, edit_others_posts={bool(caps.get('edit_others_posts'))}")

found = read_json("posts", search=TARGET_TITLE, status="publish", _embed="author", per_page=20) or []
exact = [p for p in found if p["title"]["rendered"].strip() == TARGET_TITLE]
if len(exact) != 1:
    print(f"Test non concluant : {len(exact)} article(s) publié(s) au titre exact « {TARGET_TITLE} » (1 attendu).")
    sys.exit(2)
target = exact[0]
tid = target["id"]
author_name = (target.get("_embedded", {}).get("author") or [{}])[0].get("name")
print(f"Article visé : n° {tid} « {TARGET_TITLE} », statut {target['status']}, auteur n° {target['author']} « {author_name} »")
if target["author"] == me["id"]:
    print("Test non concluant : cet article appartient au compte de l'application.")
    sys.exit(2)


def snapshot(p):
    return (p["modified_gmt"], p["status"], p["title"]["rendered"], p["content"]["rendered"])


before = snapshot(target)


def unchanged():
    p = read_json(f"posts/{tid}")
    return (p is not None and snapshot(p) == before), p


# A. modification
print(f"\nA. Tentative de MODIFICATION de l'article n° {tid} (titre + ' [TEST-MODIFICATION]'). Réponse exacte du serveur :")
raw(send("POST", f"posts/{tid}", json={"title": TARGET_TITLE + " [TEST-MODIFICATION]"}))
same, _ = unchanged()
if same:
    print("   OK : modification refusée, article intact (titre, contenu, statut et date de modification identiques).")
else:
    failures.append("modification d'un article d'un autre auteur")
    print("   !!! la modification est PASSÉE (ou l'état n'est plus lisible). Remise du titre d'origine :")
    raw(send("POST", f"posts/{tid}", json={"title": TARGET_TITLE}))

# B. suppression (sans force : WordPress mettrait l'article à la corbeille)
print(f"\nB. Tentative de SUPPRESSION de l'article n° {tid}. Réponse exacte du serveur :")
raw(send("DELETE", f"posts/{tid}"))
same, now = unchanged()
if same:
    print("   OK : suppression refusée, l'article est toujours publié et intact.")
else:
    failures.append("suppression d'un article d'un autre auteur")
    print("   !!! la suppression est PASSÉE (ou l'article n'est plus lisible). Tentative de restauration :")
    raw(send("POST", f"posts/{tid}", json={"status": "publish"}))
    print(f"   Si l'article n'est pas revenu, restaurez-le depuis la corbeille de WordPress (n° {tid}).")

# C. création d'un article de test vide (brouillon)
print("\nC. CRÉATION d'un article de test vide, en brouillon (doit réussir) :")
c = send("POST", "posts", json={"title": "[TEST NE PAS PUBLIER] article vide", "content": "", "status": "draft"})
if c is None or c.status_code not in (200, 201):
    raw(c)
    print("Test non concluant : la création a échoué, les étapes D et E ne peuvent pas être faites.")
    sys.exit(1 if failures else 2)
new = c.json()
nid = new["id"]
print(f"   HTTP {c.status_code} : créé n° {nid}, statut « {new['status']} », auteur n° {new['author']}, lien {new.get('link')}")

# D. tentative de publication du test
print(f"\nD. Tentative de PUBLICATION de l'article de test n° {nid} (status=publish). Réponse exacte du serveur :")
raw(send("POST", f"posts/{nid}", json={"status": "publish"}))
state = read_json(f"posts/{nid}", context="edit")
final = state.get("status") if state else None
print(f"   Statut réel de l'article de test après la tentative : « {final} »")
if final == "publish" or final is None:
    failures.append("publication" if final == "publish" else "publication (état illisible)")
    print("   !!! l'article de test est PUBLIÉ (ou son état est inconnu). Remise en brouillon :")
    raw(send("POST", f"posts/{nid}", json={"status": "draft"}))
else:
    print("   OK : publication refusée, l'article de test reste non publié.")

# E. rangement : l'article de test va à la corbeille (suppression de SON article non publié, autorisée)
print(f"\nE. Rangement : mise à la corbeille de l'article de test n° {nid}. Réponse exacte du serveur :")
d = send("DELETE", f"posts/{nid}")
print("   AUCUNE RÉPONSE" if d is None else f"   HTTP {d.status_code} {d.reason}"
      + ("" if d.status_code in (200, 201) else f" | {d.text[:300]}"))

print()
if failures:
    print(f"ÉCHEC DU GARDE-FOU : l'application a pu faire : {', '.join(failures)}.")
    sys.exit(1)
print("OK : modification et suppression de l'article d'un autre auteur refusées ; création en brouillon possible ; "
      "publication refusée.")
sys.exit(0)
