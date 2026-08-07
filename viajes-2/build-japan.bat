@echo off
rem corrida rapida: genera pages/2026-Japon (itinerario + mapa, verificacion 1:1)
cd /d "%~dp0"
python build/build_itinerario.py 2026-Japon %* || exit /b 1
python build/build_mapa.py 2026-Japon %*
