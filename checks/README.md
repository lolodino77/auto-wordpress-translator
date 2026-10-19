# Contrôles des droits du compte de l'application

Essais **à lancer à la main** (ils contactent le vrai site), à ne pas confondre avec `python -m unittest test_rules`
qui ne vérifie que le code avec un faux réseau. Lancer depuis n'importe où : chaque script se place à la racine du projet.

| Dossier | Pour quel site | Script | Ce qu'il fait |
|---|---|---|---|
| `checks/` | les deux modes | `whoami.py` | lecture seule : compte, rôle et droits |
| `checks/selfhosted/` | WordPress auto-hébergé (`mode = "selfhosted"`, ex. parlafoi.fr) | `check_permissions.py` | modifier et supprimer l'article d'un autre auteur (refusé), créer un brouillon vide (accepté), le publier (refusé), puis le mettre à la corbeille |
| `checks/wpcom/` | WordPress.com (`mode = "wpcom"`) | `check_cannot_publish.py` | crée un article de test et tente de le publier |
| `checks/wpcom/` | WordPress.com | `check_cannot_edit_others.py` | tente de modifier puis de supprimer l'article d'un autre auteur |
| `checks/wpcom/` | WordPress.com | `check_edit_scope.py` | lecture seule : liste des articles et droits indiqués |

Chaque essai affiche la réponse brute du serveur et annule aussitôt toute action interdite qui passerait par erreur.
