# Mac : à venir

L'architecture est prête (voir `packaging/README.md`, « Architecture ») : ajouter le Mac = créer ce dossier comme
`packaging/linux/`, sans toucher au tronc commun ni aux autres systèmes. Il reste à écrire et **tester sur un vrai Mac** :

1. `system.py` : `class MacOS(System)` avec `NAME = "macos"`, `LABEL = "Mac"`, `LAUNCHER`, `EXECUTABLE = True`,
   `TEXT_SUFFIXES`/`EOL` Unix, et `create_icon` (une petite application `.app` avec `packaging/assets/traducteur.png`),
   puis `SYSTEM = MacOS()`. `system_base.available()` le trouvera tout seul.
2. `Ouvrir le Traducteur.command` (double-cliquable dans le Finder) : s'inspirer de `packaging/linux/ouvrir-le-traducteur.sh`
   (vérification rapide, téléchargement de `uv-aarch64-apple-darwin.tar.gz` ou `uv-x86_64-apple-darwin.tar.gz`,
   préparation, ouverture en arrière-plan) ; le Finder l'ouvre déjà dans le Terminal.
3. `LISEZ-MOI.txt` : Gatekeeper met un fichier téléchargé « en quarantaine » ; la notice devra expliquer
   clic droit > Ouvrir.
4. Un `Fabriquer le paquet Mac.bat` à la racine (deux lignes, comme celui de Linux).
