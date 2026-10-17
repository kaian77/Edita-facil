#!/bin/bash
# Dê dois cliques neste arquivo para abrir o Edita Fácil.
cd "$(dirname "$0")"
set -e

if ! command -v python3 >/dev/null 2>&1; then
  echo "Instale o Python em https://www.python.org/downloads/ e abra este arquivo de novo."
  open "https://www.python.org/downloads/"
  read -r -p "Enter para fechar"; exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Instalando o ffmpeg..."; brew install ffmpeg
  else
    echo "Falta o ffmpeg. Instale o Homebrew (https://brew.sh) e rode: brew install ffmpeg"
    open "https://brew.sh"
    read -r -p "Enter para fechar"; exit 1
  fi
fi
if [ ! -x .venv/bin/python ] || ! cmp -s requirements.txt .venv/instalado.txt; then
  echo; echo "Preparando o Edita Fácil (só na primeira vez, leva alguns minutos)..."; echo
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/instalado.txt
fi
.venv/bin/python -m server
