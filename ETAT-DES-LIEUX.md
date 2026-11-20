# État des lieux : versions portables (mis à jour le 20/11/2026)

## En bref

| Version portable | Paquet | État |
|---|---|---|
| **Windows** | `dist/TraducteurWordPress-Windows.zip` | ✅ en service, **re-testée de bout en bout** après la réorganisation |
| **Linux** | `dist/TraducteurWordPress-Linux.zip` | ✅ **nouvelle**, testée sur Ubuntu 24.04, Debian 12, Fedora 41, openSUSE Tumbleweed, Arch (dans Docker) ; reste l'essai sur un vrai bureau |
| Mac | — | ⏳ à venir : architecture prête (`packaging/macos/README.md`), rien d'écrit |

Le travail des deux versions est commité (commits `e878a0f` et `7a3ef05`). Depuis : lanceur Linux plus robuste aux
téléchargements coupés (voir « Tests »), pas encore commité.

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

## Tests

- `python -m unittest test_packaging` : **27 tests OK** (contenu des deux paquets, cloisonnement, .desktop, libatomic…).
  `test_webapp` : 41 tests OK.
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

Particularités de ce PC (pas des problèmes du paquet) : Avast inspecte le HTTPS. Il faut injecter son certificat racine
(`Avast Web/Mail Shield Root`, exporté du magasin Windows) dans les conteneurs, et Docker Desktop n'arrive pas à
télécharger les images (coupures) : elles ont été téléchargées depuis Windows par un petit script qui reprend les
coupures, puis chargées avec `docker load`. Les miroirs Arch sont lents : `pacman` relancé jusqu'à 6 fois.

## Reste à faire

1. Essai sur un **vrai bureau Linux** (avec écran) : double-clic / « Exécuter comme un programme » sous GNOME,
   ouverture du terminal, entrée du menu, ouverture du navigateur, connexion à Gemini avec Chrome.
2. Commiter la correction du lanceur, puis fabriquer les deux `.zip` avec les deux `Fabriquer le paquet *.bat`.
3. Facultatif : masquer ou expliquer en français le message anglais « BEWARE… » de Playwright pendant la préparation.
4. Plus tard : version Mac (`packaging/macos/README.md`).

## Fichiers d'essai (dossier temporaire de la session, pas dans le dépôt)

Le scénario Docker (`essai-linux.sh`, et `pull_image.py` pour télécharger les images depuis Windows) est dans le
dossier temporaire de la session, pas dans le dépôt. Il se réécrit facilement : extraire le `.zip` en utilisateur normal, puis
`TRADUCTEUR_SANS_LANCEMENT=1 TRADUCTEUR_AUTOMATIQUE=1 ./ouvrir-le-traducteur.sh`, avec les étapes du tableau ci-dessus.
