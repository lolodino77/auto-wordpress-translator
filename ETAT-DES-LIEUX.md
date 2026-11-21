# État des lieux : versions portables (mis à jour le 20/11/2026)

## En bref

| Version portable | Paquet | État |
|---|---|---|
| **Windows** | `dist/TraducteurWordPress-Windows.zip` | ✅ en service, **re-testée de bout en bout** après la réorganisation |
| **Linux** | `dist/TraducteurWordPress-Linux.zip` | ✅ **nouvelle**, testée sur Ubuntu 24.04, Debian 12, Fedora 41, openSUSE Tumbleweed, Arch (dans Docker) ; reste l'essai sur un vrai bureau |
| **Mac** | `dist/TraducteurWordPress-Mac.zip` | 🆕 **écrite**, essayée dans un conteneur qui imite le Mac ; **essai sur un vrai Mac à faire** |

Windows et Linux sont commités et poussés (dernier commit `dea4c78`). La version Mac (ci-dessous, § 3) n'est pas encore
commitée.

## Ce qui a été fait

### 1. Cloisonnement Windows / Linux (architecture)

Tout ce qui est propre à un système vit dans **son** dossier ; le tronc commun n'en connaît aucun.

```
packaging/
  common/
    system_base.py     NOUVEAU : contrat d'un système (classe System) + chargement (load, available, current_platform)
    prepare.py         plus aucun code Windows : délègue au système (icône, avertissements, vérifications)
    manifest.py        plus de LAUNCHER_NAME / SUPPORTED / PLATFORM_ITEMS ; program_files(source, system, tracked)
                       n'embarque de packaging/ que common/, assets/ et le dossier du système visé
  windows/system.py    NOUVEAU : class Windows(System) (code déplacé depuis prepare.py : .lnk, OneDrive, chemins longs)
  linux/
    system.py          NOUVEAU : class Linux(System)
    ouvrir-le-traducteur.sh   NOUVEAU : lanceur en sh POSIX
    LISEZ-MOI.txt      NOUVEAU : notice des coéquipiers Linux
  outils/fabriquer-le-paquet.bat   ancien « Fabriquer le paquet Windows.bat », généralisé (paramètre windows|linux)
  build_package.py     ne connaît plus aucun système : lanceur, notice, fins de ligne, droits Unix viennent de system.py
Fabriquer le paquet Windows.bat    2 lignes → packaging/outils/fabriquer-le-paquet.bat windows Windows
Fabriquer le paquet Linux.bat      NOUVEAU, 2 lignes → … linux Linux
.gitattributes                     NOUVEAU : *.sh en fins de ligne Unix
```

Garde-fou automatique : `test_packaging.Systems.test_common_code_knows_no_particular_system` échoue si du code
propre à un système (`.bat`, `.sh`, PowerShell, `.desktop`, OneDrive, `sys.platform`…) apparaît dans le tronc commun.

### 2. Version portable Linux

- **Un seul paquet pour toutes les distributions de bureau glibc** (Ubuntu, Debian, Mint, Fedora, openSUSE, Arch…),
  PC 64 bits x86_64 ou ARM. Alpine (musl) refusée avec un message clair.
- Lanceur `ouvrir-le-traducteur.sh` en **sh POSIX** (pas besoin de bash), exécutable dans le `.zip` (droits Unix
  écrits même quand le `.zip` est fabriqué sous Windows).
- Sans terminal (double-clic, menu) : se relance dans le terminal du bureau (x-terminal-emulator, GNOME Console,
  Konsole, xfce4-terminal… xterm) ; à défaut, préparation sans fenêtre avec boîtes de message (zenity/kdialog/notify-send).
- Téléchargement de `uv` par curl, sinon wget, sinon python3.
- Après préparation : `Traducteur d'articles.desktop` dans le dossier **et** entrée dans le menu des applications
  (`~/.local/share/applications/traducteur-articles.desktop`) ; `--desinstaller` la retire.
- Ouverture en arrière-plan (setsid/nohup, `TRADUCTEUR_ARRIERE_PLAN=1` → journal `traducteur.log`, erreur de
  démarrage en boîte de message : modifs dans `webapp/__main__.py`).
- Contrôles avec la **commande exacte selon la distribution** :
  - `libatomic.so.1` manquante (nécessaire à l'outil qui télécharge le navigateur) : `sudo apt install libatomic1`,
    `sudo dnf install libatomic`, `sudo zypper install libatomic1` ;
  - bibliothèques du navigateur manquantes (`ldd`) : simple avertissement si Google Chrome est installé, sinon échec
    expliqué (installer Chrome, ou `sudo …/python -m playwright install-deps chromium` sous Debian/Ubuntu) ;
  - disque FAT/exFAT/NTFS ou `noexec`, absence d'écran graphique : avertissements.
- `llm_browser.py` : Chrome trouvé aussi dans `/opt/google/chrome/chrome`.

### 3. Version portable Mac

Même modèle que Linux, sans rien toucher au tronc commun (le test de cloisonnement connaît maintenant aussi
`.command`, `osascript`, `xattr`, iCloud, `.app`, `macos`, `darwin`) :

```
packaging/macos/
  system.py                      class MacOS(System)
  Ouvrir le Traducteur.command   lanceur sh POSIX (le Finder l'ouvre dans le Terminal)
  LISEZ-MOI.txt                  notice
  README.md                      détails
Fabriquer le paquet Mac.bat      2 lignes → packaging/outils/fabriquer-le-paquet.bat macos Mac
.gitattributes                   + *.command en fins de ligne Unix
webapp/__main__.py               erreur de démarrage affichée par osascript sur Mac
```

- **Premier lancement** : le `.command` vient d'Internet, donc macOS (Gatekeeper) avertit une fois ; la notice
  explique « Ouvrir » (macOS anciens) et « Réglages Système > Confidentialité et sécurité > Ouvrir quand même »
  (récents), ou `sh` + glisser le fichier dans le Terminal (sans avertissement). Le lanceur lève ensuite la
  quarantaine sur son propre dossier (`xattr -dr com.apple.quarantine`).
- **Application `Traducteur d'articles.app`** fabriquée sur le Mac à la fin de la préparation (donc pas en
  quarantaine) : icône `.icns` tirée du `.png` par `sips`/`iconutil` ; son programme est un script sh qui lance le
  lanceur rangé à côté d'elle (elle suit le dossier déplacé) ou, glissée ailleurs, celui de la préparation. Sans
  Terminal quand tout est prêt ; ouvre le Terminal (`open -a Terminal`) si une préparation est nécessaire ; à défaut,
  préparation sans fenêtre avec boîtes de dialogue.
- **Ouverture** détachée du Terminal (nouvelle session créée par Python, le Mac n'ayant pas `setsid`) : fermer la
  fenêtre ne l'arrête pas, pas de question « terminer les processus ».
- `uv` ARM ou Intel d'après `hw.optional.arm64` (bonne version même si le Terminal tourne sous Rosetta).
- Avertissements : dossier synchronisé par iCloud Drive (y compris Bureau/Documents synchronisés), clé USB ou disque
  FAT/exFAT/NTFS, `noexec`. Si le navigateur téléchargé ne démarre pas (macOS trop ancien) : avertissement si Google
  Chrome est installé, sinon échec expliqué (installer Chrome ou mettre macOS à jour).
- **Mise à jour** : sur Mac, glisser un dossier sur son homonyme le REMPLACE (données perdues) : la notice fait
  utiliser `ditto nouveau ancien` dans le Terminal, puis ouvrir l'application (pas de nouvel avertissement).

## Tests

- `python -m unittest test_packaging` : **34 tests OK** (contenu des trois paquets, cloisonnement, .desktop, libatomic,
  application Mac, iCloud, disques externes, navigateur qui ne démarre pas…). `test_webapp` : 41 tests OK.
- **Windows, essai réel** (extraction + `Ouvrir le Traducteur.bat`) : ✅ préparation 5/5, icône créée, le paquet ne
  contient que `common/`, `assets/`, `windows/`.
- **Linux, essais réels dans Docker** (utilisateur normal, `unzip`, puis le lanceur) :

| Distribution | sans libatomic | sans biblio. navigateur | préparation complète | lancement réel | dossier déplacé (espaces) | désinstallation |
|---|---|---|---|---|---|---|
| Ubuntu 24.04 | ✅ message apt | ✅ message | ✅ | ✅ `/api/identity` répond | ✅ | ✅ |
| Debian 12 | ✅ message apt | ✅ message | ✅ | ✅ | ✅ | ✅ |
| Fedora 41 | ✅ message dnf | ✅ message | ✅ | ✅ | ✅ | ✅ |
| openSUSE Tumbleweed | ✅ message zypper | ✅ message | ✅ | ✅ | ✅ | ✅ |
| Arch | ✅ message pacman (`gcc-libs`, voir ci-dessous) | ✅ message | ✅ | ✅ | ✅ | ✅ |

Dans tous les essais du 20/11 (openSUSE, Arch) : « lancement réel » = `/api/identity` répond ; **bouton « Quitter »** :
`POST /api/quit` arrête les 2 processus `webapp` en 1 s. L'essai précédent échouait parce qu'il n'envoyait pas l'en-tête
**`X-AWT: 1`**, exigé par le serveur pour toute requête qui modifie quelque chose (l'interface l'envoie toujours) : sans
lui, réponse « Requête refusée. » et rien ne s'arrête. Ce n'était donc pas un défaut du paquet. « Dossier déplacé » :
vers `~/Mes documents/Essai d'articles/` (espaces et apostrophe) : préparation réparée, entrée du menu mise à jour,
lancement depuis le nouveau dossier.

Remarques :

- Arch a scindé `gcc-libs` : `libatomic` y est maintenant un paquet à part, et `gcc-libs` un méta-paquet qui en dépend.
  Le message `sudo pacman -S gcc-libs` reste juste (il réinstalle `libatomic` si elle manque) et marche aussi sur les
  systèmes Arch/Manjaro plus anciens ; il est gardé tel quel.
- Sur openSUSE, Arch (et Fedora), le téléchargement du navigateur affiche en anglais « BEWARE: your OS is not
  officially supported by Playwright; downloading fallback build for ubuntu24.04-x64. » : message de Playwright, sans
  conséquence (le navigateur fonctionne).
- Pour les bibliothèques du navigateur, seul Debian/Ubuntu reçoit une commande toute faite ; ailleurs, le message
  conseille d'installer Google Chrome (qui apporte tout ce qu'il faut).
- **Correction du 20/11** : sur ce réseau, environ un téléchargement sur trois est coupé en route dans les conteneurs,
  et `curl --retry` ne réessaie pas après une coupure. Le lanceur Linux réessaie maintenant 3 fois le téléchargement de
  `uv` (« Téléchargement interrompu : nouvel essai... »), sauf s'il n'a aucun outil de téléchargement. Vérifié avec un
  faux `curl` coupé deux fois, puis par un essai openSUSE complet avec le nouveau paquet.

- **Mac, essai simulé dans Docker** (pas de Mac disponible) : conteneur Ubuntu (`/bin/sh` = dash, plus strict que
  le sh du Mac, et `bash --posix`, qui est le sh du Mac), avec des imitations de `sysctl`, `xattr`, `osascript` et
  `open`, `uv` Linux à la place de `uv` Mac, et la copie extraite qui se fait passer pour un Mac : c'est donc
  `MacOS` qui prépare et crée l'application. Tout ✅ : lanceur exécutable après `unzip`, quarantaine levée,
  préparation complète, application créée, « déjà prêt » sans nouvelle préparation, double-clic sur l'application
  (ouverture sans Terminal, programme détaché de tout terminal), double-clic sur le `.command` (message, détaché),
  bouton « Quitter » (arrêt en 1 s), dossier déplacé vers `~/Mes documents/Essai d'articles/` (l'application ouvre
  le Terminal, réparation, application refaite avec le nouveau chemin), application glissée dans `~/Applications`
  (retrouve le dossier), préparation sans Terminal (boîte de dialogue + journal), dossier `programme` absent.
  **Pas couvert** : le vrai Finder/Terminal/Gatekeeper, `sips`/`iconutil` (icône), la boîte de dialogue `osascript`,
  le Chromium pour Mac, iCloud.
- Constat en passant : les fichiers `.py` des paquets gardent les fins de ligne de la copie de travail (Windows,
  CRLF, avec `core.autocrlf`). Sans conséquence : Python les lit sans problème (seuls lanceurs et notices doivent être
  convertis, et le sont).

Particularités de ce PC (pas des problèmes du paquet) : Avast inspecte le HTTPS. Il faut injecter son certificat racine
(`Avast Web/Mail Shield Root`, exporté du magasin Windows) dans les conteneurs, et Docker Desktop n'arrive pas à
télécharger les images (coupures) : elles ont été téléchargées depuis Windows par un petit script qui reprend les
coupures, puis chargées avec `docker load`. Les miroirs Arch sont lents : `pacman` relancé jusqu'à 6 fois.

## Reste à faire

1. **Essai sur un vrai Mac** (Apple et, si possible, Intel) : avertissement de Gatekeeper et ce que dit la notice,
   fenêtre du Terminal, application et son icône, Dock, ouverture du navigateur, Chrome et connexion à Gemini,
   mise à jour avec `ditto`. À défaut de Mac, une machine macOS de GitHub Actions pourrait faire l'essai automatique
   (préparation, lancement, Quitter, dossier déplacé), mais pas les fenêtres.
2. Essai sur un **vrai bureau Linux** (avec écran) : double-clic / « Exécuter comme un programme » sous GNOME,
   ouverture du terminal, entrée du menu, ouverture du navigateur, connexion à Gemini avec Chrome.
3. Commiter la version Mac, puis fabriquer les `.zip` avec les `Fabriquer le paquet *.bat`.
4. Facultatif : masquer ou expliquer en français le message anglais « BEWARE… » de Playwright pendant la préparation.

## Fichiers d'essai (dossier temporaire de la session, pas dans le dépôt)

Les scénarios Docker (`essai-linux.sh`, `essai-mac-simule.sh`, et `pull_image.py` pour télécharger les images depuis
Windows) sont dans le
dossier temporaire de la session, pas dans le dépôt. Il se réécrit facilement : extraire le `.zip` en utilisateur normal, puis
`TRADUCTEUR_SANS_LANCEMENT=1 TRADUCTEUR_AUTOMATIQUE=1 ./ouvrir-le-traducteur.sh`, avec les étapes du tableau ci-dessus.
