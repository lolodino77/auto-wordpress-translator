# Version portable pour les coéquipiers (Windows, Mac, Linux)

But : un coéquipier qui ne programme pas reçoit un fichier `.zip`, l'extrait **où il veut**, double-clique sur
**un** fichier, et le Traducteur s'ouvre. Rien d'autre à installer à la main (ni Python, ni Anaconda, ni Node.js),
aucun droit d'administrateur, **rien d'écrit en dehors du dossier** : désinstaller = supprimer le dossier.

## Architecture

```
packaging/
  common/              commun aux trois systèmes (Python, bibliothèque standard uniquement)
    manifest.py        ce qui est le PROGRAMME (dans le .zip, remplacé à chaque mise à jour) et ce qui est DONNÉE
                       DE L'UTILISATEUR (jamais dans le .zip, donc jamais écrasée) ; version de Python
    prepare.py         la préparation dans le dossier : Python + bibliothèques (.venv), navigateur Chromium,
                       vérification, icône ; « --check » dit très vite si elle est nécessaire
  windows/             propre à Windows (prêt et testé)
    Ouvrir le Traducteur.bat   le seul fichier à double-cliquer (mis à la racine du .zip)
    LISEZ-MOI.txt              notice pour les coéquipiers (mise à la racine du .zip)
  macos/, linux/       à venir : voir leur README
  assets/              icône (traducteur.ico pour Windows, traducteur.png pour Mac et Linux)
  build_package.py     fabrique dist/TraducteurWordPress-<Système>.zip
```

Le dossier extrait chez le coéquipier :

```
TraducteurWordPress-Windows/
  Ouvrir le Traducteur.bat       à double-cliquer
  Traducteur d'articles.lnk      icône créée à la première ouverture (même effet, peut être envoyée sur le Bureau)
  LISEZ-MOI.txt
  programme/                     le programme, et tout ce qui s'y ajoute sur l'ordinateur :
    .venv/, runtime/             Python, bibliothèques, navigateur (environ 700 Mo)
    input/, output/, …           ses données (identifiants, liste d'articles, traductions)
    installation.json            ce qui a été préparé, et où
```

À chaque double-clic, `Ouvrir le Traducteur.bat` lance `prepare.py --check` (une fraction de seconde) :

- **prêt** : ouverture immédiate du Traducteur, sans fenêtre noire (`pythonw.exe -m webapp`) ;
- **première fois, nouvelle version, ou dossier déplacé** : téléchargement de l'outil `uv` si besoin, puis
  préparation complète, puis ouverture. Un dossier déplacé est réparé tout seul : l'environnement Python est recréé
  (il garde sinon l'ancien chemin) et l'icône est refaite.

**Pourquoi `uv`** : un seul petit fichier qui fournit la bonne version de Python et installe les bibliothèques, sans
toucher au reste de l'ordinateur. Python est rangé dans `programme/runtime/python`, le navigateur dans
`programme/runtime/browsers` (variable `PLAYWRIGHT_BROWSERS_PATH`, positionnée par `webapp/__main__.py`).

**Données de l'utilisateur** (`manifest.USER_DATA`) : jamais dans le `.zip`. Extraire une nouvelle version par-dessus
l'ancienne remplace donc le programme sans toucher aux identifiants, à la liste d'articles ni aux traductions. Le paquet
ne contient jamais `input/` : la liste d'articles du développeur ne part pas chez les coéquipiers.

`config.toml` fait partie du programme : il est remplacé à chaque mise à jour (consigne donnée au LLM, règles).

## Fabriquer le paquet Windows

Depuis la racine du projet, dans PowerShell (remplacer `python` par celui de l'environnement conda si besoin) :

1. **Reconstruire l'interface** si `frontend/` a été modifié :

   ```powershell
   cd frontend; npm run build; cd ..
   ```

   Chaque construction crée un nouveau fichier `webapp/static/assets/index-<code>.js` (le code change à chaque fois) et
   met à jour `webapp/static/index.html`. Le script refuse de fabriquer le paquet si l'interface construite est plus
   ancienne que `frontend/src` (option `--force` pour passer outre).
2. **Faire suivre par git tout ce qui est nouveau ou modifié** (sans forcément commiter) : seuls les fichiers suivis par
   git sont embarqués, jamais un fichier personnel posé par erreur dans un dossier du programme.

   ```powershell
   git add -A webapp packaging frontend *.py config.toml README.md
   ```

   **Piège classique** : le nouveau fichier `index-<code>.js` n'est pas suivi tant qu'on ne l'a pas ajouté. Sans lui, le
   paquet contient un `index.html` qui pointe vers un fichier absent : **l'interface s'ouvre toute blanche** chez le
   coéquipier. Seuls les fichiers **nouveaux** (« ?? » dans `git status`) sont écartés ; un fichier déjà suivi est
   embarqué dans son état actuel sur le disque, commité ou non.
3. **Fabriquer le paquet** :

   ```powershell
   python packaging/build_package.py windows
   ```

   Résultat : `dist/TraducteurWordPress-Windows.zip` (environ 1,3 Mo). Le script affiche « Ignoré (pas suivi par git) »
   pour chaque fichier du programme qu'il écarte : si la liste mentionne un fichier du programme, refaire l'étape 2.
   Le fichier `VERSION` du paquet porte la date et le commit, avec « modifié » si des changements ne sont pas commités.
4. **Tester** le `.zip` (voir plus bas) dans un dossier d'essai, **pas par-dessus la copie utilisée au quotidien**.
5. Envoyer ce `.zip` aux coéquipiers ; leur notice est le `LISEZ-MOI.txt` qu'il contient. Ils l'extraient **par-dessus**
   l'ancienne version : identifiants, liste d'articles et traductions sont conservés, et le programme se met à jour
   tout seul à la première ouverture (quelques secondes).

## Tester

- `python -m unittest test_packaging` : contenu du paquet, vérification rapide, données (sans Internet).
- Essai réel : extraire le `.zip` dans un dossier d'essai, puis, sans ouvrir le navigateur ni faire de pause :

  ```bat
  set TRADUCTEUR_SANS_LANCEMENT=1
  set TRADUCTEUR_AUTOMATIQUE=1
  "Ouvrir le Traducteur.bat"
  ```

## Google Chrome et connexion à Gemini

La connexion facultative (mais fortement conseillée) à un compte Google dans Gemini (Réglages > « Se connecter à
Gemini ») ouvre **Google Chrome** sur le profil du programme, sans le piloter : Google refuse la connexion dans un
navigateur piloté. Chrome doit donc être installé sur l'ordinateur (le Chromium téléchargé par le programme ne
convient pas pour cette étape ; les traductions utilisent aussi Chrome s'il est présent). Avant chaque article, le
programme règle Gemini sur le meilleur modèle accessible au compte (voir `[llm]` dans `config.toml`).

## Limites connues

- Windows affiche « Windows a protégé votre ordinateur » au premier lancement d'un `.bat` téléchargé : la notice
  explique quoi cliquer. Le supprimer demanderait un programme signé (certificat payant).
- Un dossier dans OneDrive ou au chemin très long peut poser problème : la préparation le signale.
- Supprimer le dossier supprime aussi les données du coéquipier (identifiants, liste, traductions).
