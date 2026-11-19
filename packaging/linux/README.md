# Linux : à venir

L'architecture est prête : `packaging/common/prepare.py` fait déjà tout le travail commun de la version portable
(Python via `uv`, bibliothèques, navigateur, vérification, conservation des données, réparation si le dossier est
déplacé). Il reste à écrire et **tester sur un vrai Linux** :

1. `ouvrir-le-traducteur.sh`, équivalent de `packaging/windows/Ouvrir le Traducteur.bat` : vérification rapide
   (`prepare.py --check`), sinon téléchargement de `uv` pour Linux (`uv-x86_64-unknown-linux-gnu.tar.gz` ou
   `uv-aarch64-unknown-linux-gnu.tar.gz`) dans `programme/runtime/`, puis
   `uv run --no-project --python 3.12 programme/packaging/common/prepare.py --root programme --uv …`.
2. Chromium a besoin de bibliothèques du système : `python -m playwright install --with-deps chromium` les installe,
   mais demande le mot de passe administrateur (`sudo`). À prévoir dans la notice.
3. Dans `prepare.py` : `create_icon` pour Linux (un fichier `.desktop` avec `packaging/assets/traducteur.png`), puis
   ajouter `"linux"` à `manifest.SUPPORTED`.
4. Dans `build_package.py` : une entrée `"linux"` dans `BOOTSTRAP`, en gardant les fins de ligne Unix et le droit
   d'exécution du `.sh` dans le `.zip`.
