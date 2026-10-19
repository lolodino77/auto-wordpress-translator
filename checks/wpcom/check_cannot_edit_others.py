"""Test : l'application ne peut NI modifier NI supprimer l'article d'un autre auteur.
Usage : python checks/wpcom/check_cannot_edit_others.py

Choisit un article publié qui n'appartient pas au compte de l'application (auteur autre que celui des brouillons de
l'app), puis :
  A. tente d'en changer le titre ;
  B. tente de le supprimer (WordPress le met alors à la corbeille).
Affiche chaque fois la réponse BRUTE du serveur et relit l'article. Si une action est passée, le script annule aussitôt
(titre/contenu remis, ou restauration depuis la corbeille) et le dit clairement.
Sortie 0 = les deux actions refusées (OK) ; 1 = au moins une est passée (puis annulée) ; 2 = test non concluant.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet
sys.path.insert(0, str(ROOT))  # pour importer wp.py / wp_selfhosted.py
os.chdir(ROOT)  # config.toml, wp_token.json, wp_credentials.json sont lus depuis la racine du projet

import json
import sys
import tomllib

import requests
import truststore

truststore.inject_into_ssl()
site = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]["site"]
headers = {"Authorization": "Bearer " + json.load(open("wp_token.json", encoding="utf-8"))["access_token"]}
api = f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts"


def raw(resp):
    """Réponse EXACTE du serveur, telle quelle (code, motif, corps non modifié)."""
    print(f"   HTTP {resp.status_code} {resp.reason}")
    print("   --- corps brut ---")
    print(resp.text)
    print("   --- fin du corps brut ---")


def read(pid):
    return requests.get(f"{api}/{pid}", headers=headers, timeout=30)


# 0. repérer un article qui n'appartient pas au compte de l'application
posts = requests.get(api, headers=headers, timeout=30,
                     params={"number": 100, "status": "publish,pending,draft,private", "type": "post"}).json()["posts"]
mine = {p["author"]["login"] for p in posts if p["status"] in ("draft", "pending")}
foreign = [p for p in posts if p["author"]["login"] not in mine and p["status"] == "publish"]
if not mine or not foreign:
    print(f"Test non concluant : comptes de l'app = {sorted(mine)}, articles publiés d'autres auteurs = {len(foreign)}")
    sys.exit(2)
target = foreign[0]
pid = target["ID"]
caps = target["capabilities"]
print(f"Article visé : n° {pid} « {target['title']} », statut {target['status']}, auteur « {target['author']['login']} »")
print(f"Compte de l'application : {sorted(mine)} | droits indiqués par WordPress : "
      f"modifier={caps.get('edit_post')}, supprimer={caps.get('delete_post')}, publier={caps.get('publish_post')}")
orig = {"title": target["title"], "content": target["content"], "status": target["status"]}
failures = []

# A. tentative de modification du titre
new_title = orig["title"] + " [TEST-MODIFICATION]"
print(f"\nA. Tentative de MODIFICATION : titre -> « {new_title} ». Réponse exacte du serveur :")
raw(requests.post(f"{api}/{pid}", headers=headers, data={"title": new_title}, timeout=30))
after = read(pid).json()
print(f"   Titre après la tentative : « {after.get('title')} » | statut : {after.get('status')}")
if (after.get("title"), after.get("content"), after.get("status")) != (orig["title"], orig["content"], orig["status"]):
    failures.append("modification")
    print("   !!! la modification est PASSÉE. Remise de l'original :")
    raw(requests.post(f"{api}/{pid}", headers=headers, data=orig, timeout=30))
else:
    print("   OK : modification refusée, article intact.")

# B. tentative de suppression (WordPress.com : POST /posts/{id}/delete = mise à la corbeille)
print(f"\nB. Tentative de SUPPRESSION de l'article n° {pid}. Réponse exacte du serveur :")
raw(requests.post(f"{api}/{pid}/delete", headers=headers, timeout=30))
state = read(pid)
status = state.json().get("status") if state.status_code == 200 else None
print(f"   Relecture de l'article : HTTP {state.status_code}, statut : {status}")
if state.status_code == 200 and status == orig["status"]:
    print("   OK : suppression refusée, l'article est toujours publié.")
else:
    failures.append("suppression")
    print("   !!! la suppression est PASSÉE (ou l'article n'est plus lisible). Tentative de restauration :")
    restored = requests.post(f"{api}/{pid}/restore", headers=headers, timeout=30)
    raw(restored)
    back = read(pid)
    print(f"   Après restauration : HTTP {back.status_code}, statut : "
          f"{back.json().get('status') if back.status_code == 200 else 'illisible'}")
    print(f"   Si l'article n'est pas revenu : restaurez-le à la main (WordPress > Articles > Corbeille, n° {pid}).")

print()
if failures:
    print(f"ÉCHEC DU GARDE-FOU : l'application a pu faire : {', '.join(failures)} sur l'article d'un autre auteur.")
    sys.exit(1)
print("OK : modification ET suppression de l'article d'un autre auteur refusées. Article intact.")
sys.exit(0)
