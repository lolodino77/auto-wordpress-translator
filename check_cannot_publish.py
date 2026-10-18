"""Test : l'application WordPress ne peut pas publier. Usage : python check_cannot_publish.py

Crée un nouvel article de test (brouillon), tente de le publier, affiche le résultat.
Sortie 0 = publication refusée (OK) ; 1 = publiée (le script la remet aussitôt en brouillon) ; 2 = non concluant.
La copie de test reste à supprimer à la main dans WordPress.
"""
import json
import re
import sys
import tomllib

import requests
import truststore

import wp

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


# 1. nouvel article de test, créé en brouillon par la fonction habituelle de l'agent
try:
    url = wp.create_draft(site, "[TEST NE PAS PUBLIER] article jetable", "<p>Article jetable. À supprimer.</p>", [])
except requests.HTTPError as e:
    print("1. ÉCHEC de la création de l'article de test. Erreur exacte du serveur :")
    raw(e.response)
    sys.exit(2)
pid = re.search(r"p=(\d+)", url).group(1)
print(f"1. Article de test créé : n° {pid} (brouillon)")

# 2. tentative de publication : on affiche la réponse brute, sans la résumer
print("2. Tentative de publication (status=publish). Réponse exacte du serveur :")
resp = requests.post(f"{api}/{pid}", headers=headers, data={"status": "publish"}, timeout=30)
raw(resp)
try:
    body = resp.json()
except ValueError:
    body = {}
print(f"   Lecture : erreur={body.get('error')!r} | message={body.get('message')!r} | "
      f"status={body.get('status')!r} | capabilities={body.get('capabilities')}")

# 3. verdict d'après le statut réel de l'article
final = requests.get(f"{api}/{pid}", headers=headers, timeout=30).json()["status"]
if final == "publish":
    requests.post(f"{api}/{pid}", headers=headers, data={"status": "draft"}, timeout=30)  # on annule aussitôt
    print("3. !!! ÉCHEC : l'article a été PUBLIÉ (remis en brouillon). Le compte autorisé peut publier : "
          "refaites 'python agent.py --auth' avec le compte Contributeur.")
    sys.exit(1)
if final in ("draft", "pending"):
    print(f"3. OK : publication refusée, l'article est resté « {final} ». Supprimez l'article de test n° {pid}.")
    sys.exit(0)
print(f"3. Non concluant : statut « {final} ».")
sys.exit(2)
