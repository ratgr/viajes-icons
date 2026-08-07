#!/bin/sh
# corrida rápida: genera pages/2026-Japon (itinerario + mapa, con verificación 1:1)
cd "$(dirname "$0")" || exit 1
python build/build_itinerario.py 2026-Japon "$@" && python build/build_mapa.py 2026-Japon "$@"
