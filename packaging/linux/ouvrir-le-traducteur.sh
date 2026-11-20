#!/bin/sh
# Traducteur d'articles, VERSION PORTABLE pour Linux : ce fichier est le seul à lancer.
# - déjà prêt : ouvre le Traducteur tout de suite, en arrière-plan (bouton « Quitter » de la page pour l'arrêter) ;
# - première fois, nouvelle version ou dossier déplacé : prépare d'abord le programme dans ce dossier (outil « uv »,
#   Python, bibliothèques, navigateur) via programme/packaging/common/prepare.py, dans une fenêtre de terminal.
# Rien n'est installé ailleurs, sauf l'entrée « Traducteur d'articles » du menu des applications.
# Désinstaller : sh ouvrir-le-traducteur.sh --desinstaller, puis supprimer ce dossier.
# Écrit en sh POSIX (pas de bash requis) : Ubuntu, Debian, Mint, Fedora, openSUSE, Arch, Manjaro…
# Variables facultatives (tests) : TRADUCTEUR_OPTIONS, TRADUCTEUR_SANS_LANCEMENT, TRADUCTEUR_AUTOMATIQUE (pas de pause,
# pas de nouvelle fenêtre de terminal).

TITRE="Traducteur d'articles"
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
LANCEUR="$DIR/$(basename -- "$0")"
P="$DIR/programme"
PY="$P/.venv/bin/python"
MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications/traducteur-articles.desktop"
JOURNAL="$P/traducteur-preparation.log"

# --- Messages ------------------------------------------------------------------------------------------------------
fenetre() {  # boîte de message quand il n'y a pas de terminal pour l'afficher
  if command -v zenity >/dev/null 2>&1; then zenity --info --title="$TITRE" --no-wrap --text="$1" >/dev/null 2>&1
  elif command -v kdialog >/dev/null 2>&1; then kdialog --title "$TITRE" --msgbox "$1" >/dev/null 2>&1
  elif command -v notify-send >/dev/null 2>&1; then notify-send -a "$TITRE" "$TITRE" "$1" >/dev/null 2>&1
  elif command -v xmessage >/dev/null 2>&1; then xmessage -center "$1" >/dev/null 2>&1
  fi
}

pause_fin() {  # laisse le temps de lire le message avant que la fenêtre se ferme
  [ -n "$TRADUCTEUR_AUTOMATIQUE" ] && return 0
  [ -t 0 ] || return 0
  printf '\n  Appuyez sur Entrée pour fermer cette fenêtre. '
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

# --- Désinstallation (retire l'entrée du menu ; le dossier se supprime à la main) ----------------------------------
case "$1" in
  --desinstaller|--retirer-du-menu)
    if [ -f "$MENU" ] && grep -qF "$DIR" "$MENU"; then
      rm -f "$MENU" && echo "  Entrée « $TITRE » retirée du menu des applications."
    else
      echo "  Aucune entrée du menu des applications ne pointe vers ce dossier."
    fi
    echo "  Fermez le Traducteur (bouton « Quitter »), puis supprimez le dossier : $DIR"
    exit 0 ;;
esac

if [ ! -f "$P/packaging/common/prepare.py" ]; then
  MSG="Le dossier « programme » est introuvable à côté de ce fichier.
Le fichier .zip n'a sans doute pas été décompressé : clic droit sur le .zip,
« Extraire ici », puis lancez « ouvrir-le-traducteur.sh » dans le dossier extrait."
  echo; echo "  $MSG"
  [ -t 1 ] || fenetre "$MSG"
  pause_fin
  exit 1
fi

# --- Ouverture (en arrière-plan : survit à la fermeture du terminal) -----------------------------------------------
ouvrir() {
  [ -n "$TRADUCTEUR_SANS_LANCEMENT" ] && exit 0
  cd "$P" || exit 1
  TRADUCTEUR_ARRIERE_PLAN=1  # webapp : journal dans traducteur.log, erreurs de démarrage en boîte de message
  export TRADUCTEUR_ARRIERE_PLAN
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$PY" -m webapp </dev/null >/dev/null 2>&1 &
  else
    nohup "$PY" -m webapp </dev/null >/dev/null 2>&1 &
  fi
  if [ -t 1 ]; then
    echo
    echo "  Le Traducteur s'ouvre dans votre navigateur."
    echo "  Pour l'arrêter : bouton « Quitter », en haut à droite de la page."
    # fenêtre de terminal ouverte pour la préparation : le temps de lire avant qu'elle se ferme
    [ -n "$TRADUCTEUR_DANS_TERMINAL" ] && [ -z "$TRADUCTEUR_AUTOMATIQUE" ] && sleep 5
  fi
  exit 0
}

# --- Déjà prêt ? (vérification rapide) -----------------------------------------------------------------------------
if [ -x "$PY" ] && "$PY" "$P/packaging/common/prepare.py" --root "$P" --check >/dev/null 2>&1; then
  ouvrir
fi

# --- Préparation nécessaire : dans une fenêtre de terminal, pour suivre l'avancement ---------------------------------
dans_un_terminal() {  # relance ce fichier dans le terminal du bureau ; retourne 1 si aucun n'est trouvé
  TRADUCTEUR_DANS_TERMINAL=1
  export TRADUCTEUR_DANS_TERMINAL
  case "${XDG_CURRENT_DESKTOP:-}" in
    *KDE*) ordre="konsole" ;;
    *GNOME*|*Unity*|*Pantheon*|*Budgie*) ordre="kgx ptyxis gnome-terminal" ;;
    *XFCE*) ordre="xfce4-terminal" ;;
    *MATE*) ordre="mate-terminal" ;;
    *X-Cinnamon*|*Cinnamon*) ordre="gnome-terminal" ;;
    *LXQt*) ordre="qterminal" ;;
    *) ordre="" ;;
  esac
  for t in $ordre x-terminal-emulator kgx ptyxis gnome-terminal konsole xfce4-terminal mate-terminal tilix terminator \
           alacritty kitty foot wezterm xterm; do
    command -v "$t" >/dev/null 2>&1 || continue
    case "$t" in
      kgx|ptyxis|gnome-terminal) "$t" -- sh "$LANCEUR" ;;
      xfce4-terminal|mate-terminal|terminator) "$t" -x sh "$LANCEUR" ;;
      kitty|foot) "$t" sh "$LANCEUR" ;;
      wezterm) "$t" start -- sh "$LANCEUR" ;;
      qterminal) continue ;;  # n'accepte qu'une commande en une seule chaîne : chemin avec espaces mal compris
      *) "$t" -e sh "$LANCEUR" ;;  # x-terminal-emulator (Debian, Ubuntu, Mint…), konsole, tilix, alacritty, xterm
    esac && return 0
  done
  return 1
}

if [ ! -t 1 ] && [ -z "$TRADUCTEUR_DANS_TERMINAL" ] && [ -z "$TRADUCTEUR_AUTOMATIQUE" ]; then
  dans_un_terminal && exit 0
  # Aucun terminal trouvé : préparation sans fenêtre, avec un message au début et à la fin.
  fenetre "Préparation du Traducteur (quelques minutes la première fois).
Il s'ouvrira tout seul dans votre navigateur à la fin."
  # (en cas d'échec, c'est la préparation elle-même qui affiche le message : echec ci-dessus)
  TRADUCTEUR_AUTOMATIQUE=1 TRADUCTEUR_DANS_TERMINAL=1 exec sh "$LANCEUR" >"$JOURNAL" 2>&1
fi

echo
echo "  =========================================================="
echo "    $TITRE : préparation du programme"
echo "    Gardez cette fenêtre ouverte jusqu'à la fin."
echo "  =========================================================="

# --- Outil « uv » (fournit Python sans rien installer sur l'ordinateur) --------------------------------------------
telecharger() {  # $1 = adresse, $2 = fichier ; 3 essais : un antivirus ou un réseau instable coupe parfois en route
  for essai in 1 2 3; do
    telecharger_une_fois "$1" "$2"; r=$?
    [ "$r" = 0 ] && return 0
    [ "$r" = 100 ] && return 1  # aucun outil de téléchargement : inutile de réessayer
    [ "$essai" = 3 ] || { echo "  Téléchargement interrompu : nouvel essai..."; sleep 3; }
  done
  return 1
}

telecharger_une_fois() {  # curl, sinon wget, sinon Python du système
  if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$1" "$2"
  else
    echo "  Ni curl, ni wget, ni python3 : impossible de télécharger. Installez curl, puis relancez."
    return 100  # (code propre : curl, wget et python ne l’utilisent pas)
  fi
}

UV="$P/runtime/uv"
if [ ! -x "$UV" ]; then
  case "$(uname -m)" in
    x86_64|amd64) ARCH=x86_64 ;;
    aarch64|arm64) ARCH=aarch64 ;;
    *) echo; echo "  Ce processeur ($(uname -m)) n'est pas pris en charge : il faut un PC 64 bits (Intel, AMD ou ARM)."
       echec ;;
  esac
  if ldd --version 2>&1 | grep -qi musl; then
    echo; echo "  Cette distribution (bibliothèque C « musl », comme Alpine) n'est pas prise en charge :"
    echo "  le navigateur utilisé pour la traduction n'y fonctionne pas. Utilisez Ubuntu, Debian, Fedora, Mint…"
    echec
  fi
  echo
  echo "  Téléchargement de l'outil de préparation..."
  TMP=$(mktemp -d "${TMPDIR:-/tmp}/uv-traducteur.XXXXXX") || echec
  if telecharger "https://github.com/astral-sh/uv/releases/latest/download/uv-$ARCH-unknown-linux-gnu.tar.gz" \
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
