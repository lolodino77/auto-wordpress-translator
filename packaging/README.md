# Version portable pour les coéquipiers (Windows, Linux, Mac)

But : un coéquipier qui ne programme pas reçoit un fichier `.zip`, l'extrait **où il veut**, lance **un** fichier, et
le Traducteur s'ouvre. Rien d'autre à installer à la main (ni Python, ni Anaconda, ni Node.js), aucun droit
d'administrateur, **rien d'écrit en dehors du dossier** (sauf, sous Linux, l'entrée du menu des applications) :
désinstaller = supprimer le dossier.

## Architecture : un dossier par système, un tronc commun qui n'en connaît aucun

```
packaging/
  common/                 COMMUN à tous les systèmes (Python, bibliothèque standard uniquement)
    manifest.py           ce qui est le PROGRAMME (dans le .zip, remplacé à chaque mise à jour) et ce qui est DONNÉE
                          DE L'UTILISATEUR (jamais dans le .zip, donc jamais écrasée) ; version de Python
    system_base.py        le CONTRAT d'un système (classe System) et son chargement (load) : tout ce qui diffère
                          d'un système à l'autre passe par là
    prepare.py            la préparation dans le dossier : Python + bibliothèques (.venv), navigateur Chromium,
                          vérification, puis appelle le système pour l'icône ; « --check » dit très vite si elle est
                          nécessaire
  windows/                PROPRE À WINDOWS (prêt et testé)
    system.py             class Windows(System) : python.exe dans Scripts\, avertissements OneDrive et chemin long,
                          suppression des chemins > 260 caractères, raccourci .lnk (PowerShell)
    Ouvrir le Traducteur.bat   le seul fichier à double-cliquer (mis à la racine du .zip)
    LISEZ-MOI.txt              notice (mise à la racine du .zip, fins de ligne Windows + BOM)
  linux/                  PROPRE À LINUX (prêt, testé dans des conteneurs de plusieurs distributions)
    system.py             class Linux(System) : disque FAT/NTFS ou « noexec », bibliothèques du navigateur
                          manquantes (ldd), fichier .desktop + entrée du menu des applications
    ouvrir-le-traducteur.sh    le seul fichier à lancer (sh POSIX, pas de bash requis ; mis à la racine du .zip)
    LISEZ-MOI.txt              notice (fins de ligne Unix)
  macos/                  PROPRE AU MAC (prêt ; lanceur essayé dans un conteneur, essai sur un vrai Mac à faire)
    system.py             class MacOS(System) : iCloud Drive, clé USB ou disque FAT/exFAT/NTFS, navigateur qui ne
                          démarre pas (macOS trop ancien), application « Traducteur d'articles.app » fabriquée sur le Mac
    Ouvrir le Traducteur.command   le seul fichier à ouvrir (sh POSIX ; le Finder l'ouvre dans le Terminal)
    LISEZ-MOI.txt              notice (fins de ligne Unix ; avertissement de macOS au premier lancement)
  assets/                 icônes (traducteur.ico pour Windows, traducteur.png pour Linux et Mac)
  outils/                 outils du développeur, jamais embarqués : fabriquer-le-paquet.bat
  build_package.py        fabrique dist/TraducteurWordPress-<Système>.zip ; ne connaît aucun système : il lit lanceur,
                          notice, fins de ligne et droit d'exécution dans packaging/<système>/system.py
```

Règles du cloisonnement (vérifiées par `test_packaging.Systems`) :

- `common/` et `build_package.py` ne contiennent **aucun** test « si Windows… sinon… » ni rien de propre à un système
  (`.bat`, `.sh`, `.command`, PowerShell, `.desktop`, OneDrive, iCloud, osascript…). Seul `system_base.current_platform()` traduit `sys.platform` en
  nom de dossier.
- Le paquet d'un système ne contient de `packaging/` que `common/`, `assets/` et **son** dossier : le paquet Linux n'a
  aucun `.bat`, le paquet Windows aucun fichier Linux (`manifest.program_files(…, system)`).
- Ajouter un système = ajouter un dossier `packaging/<système>/` avec `system.py` (une classe qui hérite de `System`
  et `SYSTEM = …`), le lanceur et la notice. Rien à modifier ailleurs : `system_base.available()` le trouve.

Le dossier extrait chez le coéquipier (même forme partout) :

```
TraducteurWordPress-<Système>/
  <lanceur>                      à double-cliquer : « Ouvrir le Traducteur.bat » / « ouvrir-le-traducteur.sh » /
                                 « Ouvrir le Traducteur.command »
  <icône>                        créée à la première ouverture : « Traducteur d'articles.lnk » / « .desktop » / « .app »
  LISEZ-MOI.txt
  programme/                     le programme, et tout ce qui s'y ajoute sur l'ordinateur :
    .venv/, runtime/             Python, bibliothèques, navigateur (environ 700 Mo)
    input/, output/, …           ses données (identifiants, liste d'articles, traductions)
    installation.json            ce qui a été préparé, et où
```

À chaque ouverture, le lanceur lance `prepare.py --check` (une fraction de seconde) :

- **prêt** : ouverture immédiate du Traducteur en arrière-plan, sans fenêtre (Windows : `pythonw.exe -m webapp` ;
  Linux et Mac : `python -m webapp` détaché du terminal avec `TRADUCTEUR_ARRIERE_PLAN=1`, journal dans
  `traducteur.log`) ;
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

## Linux en détail

- **Distributions visées** : toute distribution de bureau récente avec glibc (Ubuntu, Debian, Mint, Fedora, openSUSE,
  Arch, Manjaro, Pop!_OS…), PC 64 bits Intel/AMD ou ARM. Pas Alpine (musl) : le lanceur le dit clairement.
- **Lancement** : GNOME n'exécute plus un script d'un double-clic ; la notice indique clic droit > « Exécuter comme un
  programme » (ou `sh ouvrir-le-traducteur.sh`). Les fois suivantes, l'entrée « Traducteur d'articles » du **menu des
  applications** (`~/.local/share/applications/traducteur-articles.desktop`) marche sur tous les bureaux.
  `sh ouvrir-le-traducteur.sh --desinstaller` la retire.
- **Fenêtre de préparation** : lancé sans terminal (double-clic, menu), le lanceur se relance dans le terminal du bureau
  (`x-terminal-emulator`, GNOME Console, Konsole, xfce4-terminal…, xterm en dernier recours). S'il n'en trouve aucun, la
  préparation tourne sans fenêtre (journal `programme/traducteur-preparation.log`) avec un message au début et à la fin.
- **Téléchargement** : `curl`, sinon `wget`, sinon le `python3` du système. Le `.zip` porte les droits Unix (lanceur
  exécutable) ; si un outil d'extraction les perd, `sh ouvrir-le-traducteur.sh` marche quand même.
- **Bibliothèques du navigateur** : Chromium a besoin de bibliothèques du système, présentes sur presque tous les
  bureaux. S'il en manque (`ldd`), la préparation le dit : avec Google Chrome installé, simple avertissement (Chrome
  est utilisé) ; sinon échec expliqué (installer Chrome, ou sous Debian/Ubuntu
  `sudo programme/.venv/bin/python -m playwright install-deps chromium`).

## Mac en détail

- **Visé** : macOS récent, Mac Apple (M1, M2…) ou Intel (`uv` ARM choisi d'après `hw.optional.arm64`, même si le
  Terminal tourne sous Rosetta).
- **Premier lancement** : tout ce qui vient d'Internet est « en quarantaine ». Le double-clic sur
  `Ouvrir le Traducteur.command` affiche donc un avertissement de macOS (Gatekeeper) : « Ouvrir » sur les versions
  anciennes, « Réglages Système > Confidentialité et sécurité > Ouvrir quand même » sur les récentes ; ou, sans
  avertissement, `sh` + glisser le fichier dans le Terminal. La notice l'explique. Le lanceur lève ensuite la
  quarantaine sur son propre dossier (`xattr`), pour que la question ne revienne pas.
- **Application** : à la fin de la préparation, `Traducteur d'articles.app` est fabriquée dans le dossier (icône
  `.icns` tirée de `traducteur.png` par `sips`/`iconutil`, fournis avec macOS). Fabriquée sur le Mac, elle n'est pas en
  quarantaine : pas d'avertissement. Son programme est un petit script sh qui lance le lanceur rangé à côté d'elle
  (elle suit le dossier s'il est déplacé ; glissée ailleurs, elle retrouve le dossier de la préparation). Sans
  fenêtre de Terminal quand tout est prêt ; si une préparation est nécessaire, elle ouvre le Terminal elle-même.
- **Ouverture** : `python -m webapp` dans une nouvelle session (le Mac n'a pas `setsid`) : fermer la fenêtre du
  Terminal ne l'arrête pas, et le Terminal ne demande pas de « terminer les processus ». Une erreur de démarrage
  s'affiche dans une boîte de dialogue (`osascript`, dans `webapp/__main__.py`).
- **Mise à jour** : sur Mac, glisser un dossier sur son homonyme le REMPLACE (données perdues). La notice fait
  utiliser `ditto nouveau ancien` dans le Terminal, qui ajoute sans effacer.
- **Pas d'essai sur un vrai Mac à ce jour** : voir `ETAT-DES-LIEUX.md`.

## Fabriquer les paquets

**Double-cliquer sur `Fabriquer le paquet Windows.bat`, `Fabriquer le paquet Linux.bat` ou `Fabriquer le paquet
Mac.bat`** (racine du projet, sous Windows : les paquets Linux et Mac se fabriquent aussi depuis Windows). Tous
appellent `packaging/outils/fabriquer-le-paquet.bat`,
qui enchaîne tout seul, sans rien taper :

1. reconstruction de l'interface (`npm run build`, après `npm ci` la toute première fois) ;
2. `git add` des fichiers nouveaux ou modifiés du programme (sans commiter) ;
3. suppression forcée de l'ancienne copie dézippée `dist/TraducteurWordPress-<Système>/` (le dossier d'essai : le
   Traducteur qui tourne dedans est arrêté, et ses données, identifiants compris, sont perdues), puis fabrication de
   `dist/TraducteurWordPress-<Système>.zip` (environ 1,3 Mo) et ouverture du dossier `dist`.

Il faut seulement Git, Node.js et l'environnement conda du projet (`setup_env.ps1`). En cas d'erreur, la fenêtre reste
ouverte avec le message. Ensuite :

- **Tester** le `.zip` (voir plus bas) dans un dossier d'essai, **pas par-dessus la copie utilisée au quotidien**.
- Envoyer ce `.zip` aux coéquipiers ; leur notice est le `LISEZ-MOI.txt` qu'il contient. Ils l'extraient **par-dessus**
  l'ancienne version : identifiants, liste d'articles et traductions sont conservés, et le programme se met à jour
  tout seul à la première ouverture (quelques secondes).

Pourquoi ces étapes (le script s'en charge) :

- Chaque construction de l'interface crée un nouveau `webapp/static/assets/index-<code>.js`. Seuls les fichiers suivis
  par git sont embarqués : sans le `git add`, le paquet aurait un `index.html` qui pointe vers un fichier absent et
  **l'interface s'ouvrirait toute blanche** chez le coéquipier. Un fichier déjà suivi est embarqué dans son état actuel
  sur le disque, commité ou non.
- `build_package.py` refuse de fabriquer le paquet si l'interface est plus ancienne que `frontend/src`, et affiche
  « Ignoré (pas suivi par git) » pour chaque fichier du programme qu'il écarte. Le fichier `VERSION` du paquet porte la
  date et le commit, avec « modifié » si des changements ne sont pas commités.

À la main (équivalent du script, sur n'importe quel système), depuis la racine : `cd frontend; npm run build; cd ..`,
puis `git add -A webapp packaging frontend *.py config.toml README.md`, puis
`python packaging/build_package.py windows` (ou `linux`, ou `macos`).

## Tester

- `python -m unittest test_packaging` : contenu des trois paquets, cloisonnement des systèmes, vérification rapide,
  données (sans Internet).
- Essai réel sous Windows : extraire le `.zip` dans un dossier d'essai, puis, sans ouvrir le navigateur ni faire de pause :

  ```bat
  set TRADUCTEUR_SANS_LANCEMENT=1
  set TRADUCTEUR_AUTOMATIQUE=1
  "Ouvrir le Traducteur.bat"
  ```

- Essai réel sous Linux (ou dans un conteneur Docker `ubuntu`, `debian`, `fedora`, `archlinux`, `opensuse/tumbleweed`,
  en utilisateur normal) :

  ```sh
  unzip TraducteurWordPress-Linux.zip && cd TraducteurWordPress-Linux
  TRADUCTEUR_SANS_LANCEMENT=1 TRADUCTEUR_AUTOMATIQUE=1 ./ouvrir-le-traducteur.sh
  ```

  Puis lancement réel (`TRADUCTEUR_AUTOMATIQUE=1 ./ouvrir-le-traducteur.sh`, `curl http://127.0.0.1:8710/api/identity`)
  et bouton « Quitter » : `curl -X POST -H 'X-AWT: 1' http://127.0.0.1:8710/api/quit`. L'en-tête `X-AWT: 1` est
  obligatoire (le serveur refuse toute requête qui modifie quelque chose sans lui, comme l'interface l'envoie).
  Derrière un antivirus ou un proxy qui inspecte le HTTPS, injecter son certificat racine dans le conteneur.
- Essai réel sur Mac : double-cliquer sur le `.zip`, puis, dans le Terminal, sans ouvrir le navigateur :

  ```sh
  cd ~/Downloads/TraducteurWordPress-Mac
  TRADUCTEUR_SANS_LANCEMENT=1 TRADUCTEUR_AUTOMATIQUE=1 "./Ouvrir le Traducteur.command"
  ```

  puis double-clic sur `Traducteur d'articles.app` (ouverture sans Terminal), bouton « Quitter », dossier déplacé.

## Google Chrome et connexion à Gemini

La connexion facultative (mais fortement conseillée) à un compte Google dans Gemini (Réglages > « Se connecter à
Gemini ») ouvre **Google Chrome** sur le profil du programme, sans le piloter : Google refuse la connexion dans un
navigateur piloté. Chrome doit donc être installé sur l'ordinateur (le Chromium téléchargé par le programme ne
convient pas pour cette étape ; les traductions utilisent aussi Chrome s'il est présent). Avant chaque article, le
programme règle Gemini sur le meilleur modèle accessible au compte (voir `[llm]` dans `config.toml`).

## Limites connues

- Windows affiche « Windows a protégé votre ordinateur » au premier lancement d'un `.bat` téléchargé : la notice
  explique quoi cliquer. Le supprimer demanderait un programme signé (certificat payant).
- Windows : un dossier dans OneDrive ou au chemin très long peut poser problème : la préparation le signale.
- Linux : un dossier sur une clé USB ou une partition Windows (FAT, exFAT, NTFS) ne permet pas de préparer Python :
  la préparation le signale. Pas de prise en charge d'Alpine (musl).
- Supprimer le dossier supprime aussi les données du coéquipier (identifiants, liste, traductions).
