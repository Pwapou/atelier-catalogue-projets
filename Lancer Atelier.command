#!/bin/zsh
cd -- "${0:A:h}"
if [[ ! -f dist/index.html ]]; then
  echo "Construisez l’interface : npm install puis npm run build."
  read -r "?Appuyez sur Entrée pour fermer."
  exit 1
fi
echo "Ouvrez http://127.0.0.1:8766 dans votre navigateur."
echo "Gardez ce terminal ouvert. Ctrl+C pour arrêter Atelier."
if [[ -x /opt/homebrew/bin/python3 ]]; then
  /opt/homebrew/bin/python3 server.py --port 8766
else
  python3 server.py --port 8766
fi
