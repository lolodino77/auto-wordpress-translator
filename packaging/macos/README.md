# Mac : version portable

Tout ce qui est propre au Mac est dans ce dossier, et seulement ici (voir `packaging/README.md`, « Architecture ») :

- `system.py` : `class MacOS(System)` : avertissements d'emplacement (iCloud Drive, clé USB ou disque FAT/exFAT/NTFS,
  `noexec`), vérification que le navigateur téléchargé démarre (sinon Google Chrome, ou mise à jour de macOS), et
  application `Traducteur d'articles.app` créée dans le dossier (icône `.icns` fabriquée avec `sips` et `iconutil`,
  fournis avec macOS ; programme = petit script sh qui lance le lanceur rangé à côté d'elle, donc elle suit le dossier
  s'il est déplacé).
- `Ouvrir le Traducteur.command` : le lanceur, en `sh` POSIX, mis à la racine du `.zip` avec le droit d'exécution ;
  le Finder l'ouvre dans le Terminal d'un double-clic. Il lève la quarantaine de macOS sur son propre dossier
  (`xattr`), fait la vérification rapide, sinon télécharge `uv` (`uv-<aarch64|x86_64>-apple-darwin`, ARM choisi
  d'après `hw.optional.arm64` même sous Rosetta) et prépare, puis ouvre le Traducteur détaché du Terminal
  (nouvelle session : fermer la fenêtre ne l'arrête pas). Lancé sans Terminal (par l'application) alors qu'une
  préparation est nécessaire, il s'ouvre lui-même dans le Terminal (`open -a Terminal`).
- `LISEZ-MOI.txt` : la notice des coéquipiers (avertissement de Gatekeeper au premier lancement, mise à jour avec
  `ditto` : sur Mac, glisser un dossier sur son homonyme le remplace entièrement).

Pourquoi une application fabriquée sur le Mac plutôt que livrée dans le `.zip` : tout ce qui vient d'Internet est
« en quarantaine », et une application non signée par Apple serait bloquée. Fabriquée sur place, elle ne l'est pas.
Le `.command` du `.zip`, lui, déclenche l'avertissement une seule fois (la notice explique quoi cliquer).

Fabriquer le paquet : `Fabriquer le paquet Mac.bat` (sous Windows) ou `python packaging/build_package.py macos`.
Tester : `packaging/README.md`, partie « Tester ».
