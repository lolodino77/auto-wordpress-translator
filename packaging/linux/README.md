# Linux : version portable

Tout ce qui est propre à Linux est dans ce dossier, et seulement ici (voir `packaging/README.md`, « Architecture ») :

- `system.py` : `class Linux(System)` : avertissements d'emplacement (disque FAT/exFAT/NTFS, option `noexec`, pas
  d'écran graphique), bibliothèques du navigateur manquantes (`ldd`), icône (`Traducteur d'articles.desktop` dans le
  dossier + entrée `traducteur-articles.desktop` du menu des applications).
- `ouvrir-le-traducteur.sh` : le lanceur, en `sh` POSIX (aucune dépendance à bash), mis à la racine du `.zip` avec le
  droit d'exécution. Vérification rapide, sinon téléchargement de `uv` (`uv-<x86_64|aarch64>-unknown-linux-gnu`) et
  préparation dans un terminal du bureau, puis ouverture en arrière-plan. `--desinstaller` retire l'entrée du menu.
- `LISEZ-MOI.txt` : la notice des coéquipiers.

Fabriquer le paquet : `Fabriquer le paquet Linux.bat` (sous Windows) ou `python packaging/build_package.py linux`.
Tester : `packaging/README.md`, partie « Tester ».
