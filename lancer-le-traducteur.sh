#!/usr/bin/env bash
# Mac et Linux : ouvre l'interface du traducteur dans le navigateur. Fermer cette fenêtre arrête le programme.
# (Sur Mac, « Lancer le traducteur.command » appelle ce fichier : double-cliquez sur celui-là.)
cd "$(dirname "$0")" || exit 1
ENVNAME=auto-wordpress-translator
PY=""
for base in "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/opt/anaconda3" "$HOME/opt/miniconda3" \
            "/opt/anaconda3" "/opt/miniconda3" "/opt/homebrew/anaconda3" "/opt/homebrew/Caskroom/miniconda/base" \
            "/usr/local/anaconda3" "/usr/local/miniconda3"; do
  if [ -x "$base/envs/$ENVNAME/bin/python" ]; then PY="$base/envs/$ENVNAME/bin/python"; break; fi
done
if [ -z "$PY" ] && command -v conda >/dev/null 2>&1; then
  PY="$(conda run -n "$ENVNAME" python -c 'import sys; print(sys.executable)' 2>/dev/null)"
fi
if [ -z "$PY" ]; then
  echo
  echo "  L'environnement « $ENVNAME » est introuvable."
  echo "  Faites d'abord l'installation : voir le fichier README.md, partie Installation."
  echo
  read -r -p "Appuyez sur Entrée pour fermer cette fenêtre."
  exit 1
fi
"$PY" -m webapp || read -r -p "Le programme s'est arrêté avec une erreur (message ci-dessus). Entrée pour fermer."
