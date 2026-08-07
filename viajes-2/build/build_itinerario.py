# -*- coding: utf-8 -*-
"""build_itinerario.py — src/<viaje>/viaje.yaml → pages/<viaje>/itinerario.html.

Estructura del repo (los scripts de build/ sirven para cualquier viaje):

    build/                 pipeline + assets compartidos (css/js se copian al release)
    src/<viaje>/           viaje.yaml · plantilla*.html · config.yaml
    pages/<viaje>/         release autocontenida (html + css/js copiados)
    scratch/               herramientas fuera del pipeline (p.ej. migrate_yaml.py)

    ./build-japan.sh | build-japan.bat          corrida rápida del viaje Japón
    python build/build_itinerario.py [viaje]    itinerario (y verificación 1:1)
    python build/build_mapa.py [viaje]          mapa (misma barra de días)

El render vive en render.py (compartido con el mapa). El HTML es una
proyección 1:1 del YAML — verify_roundtrip.py lo comprueba en cada build.
"""
import sys

import render
from common import resolve_trip

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    return render.build_and_verify(resolve_trip(sys.argv), "plantilla.html", "itinerario.html")


if __name__ == "__main__":
    sys.exit(main())
