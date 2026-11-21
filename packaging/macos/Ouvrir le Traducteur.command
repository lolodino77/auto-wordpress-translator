#!/bin/sh
# Traducteur d'articles, VERSION PORTABLE pour Mac : ce fichier est le seul à ouvrir (double-clic : il s'ouvre dans
# le Terminal).
# - déjà prêt : ouvre le Traducteur tout de suite, en arrière-plan (bouton « Quitter » de la page pour l'arrêter) ;
# - première fois, nouvelle version ou dossier déplacé : prépare d'abord le programme dans ce dossier (outil « uv »,
#   Python, bibliothèques, navigateur) via programme/packaging/common/prepare.py, puis crée l'application
#   « Traducteur d'articles » à côté de ce fichier (pour les fois suivantes, sans fenêtre de Terminal).
# Rien n'est installé ailleurs sur le Mac. Désinstaller : supprimer ce dossier.
# Écrit en sh POSIX (pas de bash ni de zsh requis).
# Variables facultatives (tests) : TRADUCTEUR_OPTIONS, TRADUCTEUR_SANS_LANCEMENT, TRADUCTEUR_AUTOMATIQUE (pas de pause,
# pas de nouvelle fenêtre de Terminal).

TITRE="Traducteur d'articles"
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
LANCEUR="$DIR/$(basename -- "$0")"
P="$DIR/programme"
PY="$P/.venv/bin/python"
JOURNAL="$P/traducteur-preparation.log"

# --- Messages ------------------------------------------------------------------------------------------------------
fenetre() {  # boîte de message quand il n'y a pas de Terminal pour l'afficher
  osascript -e 'on run argv' -e 'display dialog (item 1 of argv) with title (item 2 of argv) buttons {"OK"} default button 1' \
    -e 'end run' "$1" "$TITRE" >/dev/null 2>&1
}

pause_fin() {  # laisse le temps de lire le message avant de fermer la fenêtre
  [ -n "$TRADUCTEUR_AUTOMATIQUE" ] && return 0
  [ -t 0 ] || return 0
  printf '\n  Appuyez sur Entrée, puis fermez cette fenêtre. '
  read -r _ || true
}

echec() {
  echo
  echo "  La préparation n'a pas abouti : le message ci-dessus indique pourquoi."
  echo "  Vous pouvez relancer ce fichier : elle reprendra sans rien perdre."
  [ -t 1 ] || fenetre "La préparation du Traducteur n'a pas abouti.
Le détail est dans le fichier :
$JOURNAL"
  pause_fin
  exit 1
}

if [ ! -f "$P/packaging/common/prepare.py" ]; then
  MSG="Le dossier « programme » est introuvable à côté de ce fichier.
Le fichier .zip n'a sans doute pas été décompressé : double-cliquez sur le .zip
dans le Finder, puis ouvrez « Ouvrir le Traducteur » dans le dossier obtenu."
  echo; echo "  $MSG"
  [ -t 1 ] || fenetre "$MSG"
  pause_fin
  exit 1
fi

# Fichiers téléchargés : macOS les met « en quarantaine » et redemande une confirmation à chaque ouverture. Ce dossier
# vient d'être ouvert volontairement : on lève la quarantaine sur lui seul.
xattr -dr com.apple.quarantine "$DIR" >/dev/null 2>&1

# --- Ouverture (en arrière-plan : survit à la fermeture du Terminal) -----------------------------------------------
ouvrir() {
  [ -n "$TRADUCTEUR_SANS_LANCEMENT" ] && exit 0
  cd "$P" || exit 1
  TRADUCTEUR_ARRIERE_PLAN=1  # webapp : journal dans traducteur.log, erreurs de démarrage en boîte de message
  export TRADUCTEUR_ARRIERE_PLAN
  # Détaché du Terminal (nouvelle session, que le Mac ne sait pas créer depuis sh) : fermer la fenêtre ne l'arrête
  # pas, et le Terminal ne demande pas s'il faut « terminer les processus en cours ».
  "$PY" -c 'import subprocess, sys
subprocess.Popen([sys.executable, "-m", "webapp"], start_new_session=True, stdin=subprocess.DEVNULL,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)' || exit 1
  if [ -t 1 ]; then
    echo
    echo "  Le Traducteur s'ouvre dans votre navigateur. Vous pouvez fermer cette fenêtre."
    echo "  Pour l'arrêter : bouton « Quitter », en haut à droite de la page."
  fi
  exit 0
}

# --- Déjà prêt ? (vérification rapide) -----------------------------------------------------------------------------
if [ -x "$PY" ] && "$PY" "$P/packaging/common/prepare.py" --root "$P" --check >/dev/null 2>&1; then
  ouvrir
fi

# --- Préparation nécessaire : dans une fenêtre de Terminal, pour suivre l'avancement --------------------------------
# (lancé par l'application « Traducteur d'articles », il n'y a pas de fenêtre : on en ouvre une)
if [ ! -t 1 ] && [ -z "$TRADUCTEUR_DANS_TERMINAL" ] && [ -z "$TRADUCTEUR_AUTOMATIQUE" ]; then
  open -a Terminal "$LANCEUR" && exit 0
  # Terminal introuvable : préparation sans fenêtre, avec un message au début et à la fin.
  fenetre "Préparation du Traducteur (quelques minutes la première fois).
Il s'ouvrira tout seul dans votre navigateur à la fin." &
  # (en cas d'échec, c'est la préparation elle-même qui affiche le message : echec ci-dessus)
  TRADUCTEUR_AUTOMATIQUE=1 TRADUCTEUR_DANS_TERMINAL=1 exec /bin/sh "$LANCEUR" >"$JOURNAL" 2>&1
fi

echo
echo "  =========================================================="
echo "    $TITRE : préparation du programme"
echo "    Gardez cette fenêtre ouverte jusqu'à la fin."
echo "  =========================================================="

# --- Outil « uv » (fournit Python sans rien installer sur le Mac) --------------------------------------------------
telecharger() {  # $1 = adresse, $2 = fichier ; 3 essais : un antivirus ou un réseau instable coupe parfois en route
  for essai in 1 2 3; do
    curl -fsSL --retry 3 -o "$2" "$1" && return 0
    [ "$essai" = 3 ] || { echo "  Téléchargement interrompu : nouvel essai..."; sleep 3; }
  done
  return 1
}

UV="$P/runtime/uv"
if [ ! -x "$UV" ]; then
  # Mac Apple (M1, M2…) : version ARM, même si le Terminal tourne en mode Intel (Rosetta)
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then ARCH=aarch64; else ARCH=x86_64; fi
  echo
  echo "  Téléchargement de l'outil de préparation..."
  TMP=$(mktemp -d "${TMPDIR:-/tmp}/uv-traducteur.XXXXXX") || echec
  if telecharger "https://github.com/astral-sh/uv/releases/latest/download/uv-$ARCH-apple-darwin.tar.gz" \
       "$TMP/uv.tar.gz" && tar -xzf "$TMP/uv.tar.gz" -C "$TMP" && mkdir -p "$P/runtime" \
       && cp "$(find "$TMP" -type f -name uv | head -n 1)" "$UV" && chmod +x "$UV"; then
    rm -rf "$TMP"
  else
    rm -rf "$TMP" "$UV"
    echo
    echo "  Impossible de télécharger l'outil de préparation."
    echo "  Vérifiez la connexion Internet, puis relancez ce fichier."
    echec
  fi
fi

UV_PYTHON_INSTALL_DIR="$P/runtime/python"
UV_PYTHON_PREFERENCE=only-managed
UV_SYSTEM_CERTS=1
UV_LINK_MODE=copy
export UV_PYTHON_INSTALL_DIR UV_PYTHON_PREFERENCE UV_SYSTEM_CERTS UV_LINK_MODE
# shellcheck disable=SC2086  # TRADUCTEUR_OPTIONS : plusieurs options séparées par des espaces
"$UV" run --no-project --python 3.12 "$P/packaging/common/prepare.py" --root "$P" --uv "$UV" $TRADUCTEUR_OPTIONS || echec
ouvrir
