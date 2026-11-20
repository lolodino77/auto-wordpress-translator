# État des lieux : versions portables (mis à jour le 20/11/2026)

## En bref

| Version portable | Paquet | État |
|---|---|---|
| **Windows** | `dist/TraducteurWordPress-Windows.zip` | ✅ en service, **re-testée de bout en bout** après la réorganisation |
| **Linux** | `dist/TraducteurWordPress-Linux.zip` | ✅ **nouvelle**, testée sur Ubuntu 24.04, Debian 12, Fedora 41 ; essais openSUSE et Arch à finir |
| Mac | — | ⏳ à venir : architecture prête (`packaging/macos/README.md`), rien d'écrit |

⚠️ **Rien n'est commité** : tout le travail ci-dessous est dans l'arbre de travail, et les nouveaux fichiers sont
seulement ajoutés à l'index (`git add`, nécessaire pour qu'ils entrent dans les paquets).

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
| openSUSE Tumbleweed | ✅ message zypper | ✅ message | ⏳ relancé (il manquait `libXfixes3` dans la liste de paquets *de l'essai*) | ⏳ | ⏳ | ⏳ |
| Arch | ❌ pas testé : les miroirs Arch ne répondent pas depuis ce réseau (Avast inspecte le HTTPS) | | | | | |

Remarque : dans Docker, il faut injecter le certificat racine d'Avast (`Avast Web/Mail Shield Root`) : propre à ce
PC, pas un problème du paquet.

## Reste à faire

1. Finir les essais openSUSE (en cours) et Arch (essayer depuis un autre réseau ou un autre miroir).
2. Vérifier le bouton **« Quitter »** sous Linux : dans l'essai, 2 processus restaient 3 s après `POST /api/quit`
   (l'appel n'envoyait peut-être pas les bons en-têtes ; essai relancé avec `Content-Type` et 8 s d'attente).
3. Essai sur un **vrai bureau Linux** (avec écran) : double-clic / « Exécuter comme un programme » sous GNOME,
   ouverture du terminal, entrée du menu, ouverture du navigateur, connexion à Gemini avec Chrome.
4. Commiter (rien n'est commité), puis fabriquer les deux `.zip` avec les deux `Fabriquer le paquet *.bat`.
5. Plus tard : version Mac (`packaging/macos/README.md`).

## Fichiers d'essai (sur le PC d'origine seulement, dossier temporaire)

Le scénario Docker (`essai-linux.sh`, `lancer-essais.sh`) est dans le dossier temporaire de la session, pas dans le
dépôt. Il se réécrit facilement : extraire le `.zip` en utilisateur normal, puis
`TRADUCTEUR_SANS_LANCEMENT=1 TRADUCTEUR_AUTOMATIQUE=1 ./ouvrir-le-traducteur.sh`, avec les étapes du tableau ci-dessus.
