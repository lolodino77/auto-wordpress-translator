# Mac : à venir

L'architecture est prête : `packaging/common/prepare.py` fait déjà tout le travail commun de la version portable
(Python via `uv`, bibliothèques, navigateur, vérification, conservation des données, réparation si le dossier est
déplacé). Il reste à écrire et **tester sur un vrai Mac** :

1. `Ouvrir le Traducteur.command` (double-cliquable dans le Finder, à la racine du dossier extrait), équivalent de
   `packaging/windows/Ouvrir le Traducteur.bat` : vérification rapide (`prepare.py --check`), sinon téléchargement de
   `uv` pour macOS (`uv-aarch64-apple-darwin.tar.gz` sur puce Apple, `uv-x86_64-apple-darwin.tar.gz` sur Intel) dans
   `programme/runtime/`, puis `uv run --no-project --python 3.12 programme/packaging/common/prepare.py --root programme --uv …`,
   puis ouverture (`programme/.venv/bin/python -m webapp`).
2. Dans `prepare.py` : `create_icon` pour macOS (une petite application `.app` avec `packaging/assets/traducteur.png`),
   puis ajouter `"macos"` à `manifest.SUPPORTED`.
3. Dans `build_package.py` : une entrée `"macos"` dans `BOOTSTRAP`, en gardant les fins de ligne Unix et le droit
   d'exécution du `.command` dans le `.zip`.
4. Gatekeeper : un fichier téléchargé est « mis en quarantaine » ; la notice devra expliquer clic droit > Ouvrir.
