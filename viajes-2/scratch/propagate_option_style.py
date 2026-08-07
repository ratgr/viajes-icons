# -*- coding: utf-8 -*-
"""propagate_option_style.py — propaga el estilo de opción ENRIQUECIDA (el que
el usuario armó a mano en la cena del d1) a TODAS las opciones planas de tier:

    {location: X, price: P}
  →
    title: '@[<places[X].name>](X)'
    price: P
    steps:
    - {transit: to-X, title: To <name>}
    - {location: X}
    - {transit: from-X, title: From <name>}

También retira la clave `retorno` (el viejo mecanismo de ida/regreso del mapa:
los sub-pasos to-/from- lo sustituyen). Los transits to-X/from-X quedan como
claves pendientes de geometría. El itinerario visible no cambia (los sub-pasos
solo los muestra el mapa). Idempotente: las opciones ya enriquecidas se dejan.
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from common import ROOT, resolve_trip, save_yaml, trip_paths

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TRIP = resolve_trip(sys.argv)
SRC_DIR, _p, _c = trip_paths(TRIP)
PATH = os.path.join(SRC_DIR, "viaje.yaml")

Y = yaml.safe_load(open(PATH, encoding="utf-8"))
PLACES = Y.get("places", {})
converted = retornos = 0

for day in Y.get("days", []):
    for s in day.get("steps", []):
        if not isinstance(s, dict) or "options" not in s:
            continue
        if s.pop("retorno", None) is not None:
            retornos += 1
        for tier in s["options"]:
            if not isinstance(tier, dict) or "options" not in tier:
                continue    # grupos-plan (steps) no son tiers
            new_items = []
            for x in tier["options"]:
                if isinstance(x, dict) and "location" in x and "steps" not in x and "title" not in x:
                    key = x["location"]
                    name = PLACES.get(key, {}).get("name", key)
                    item = {"title": f"@[{name}]({key})"}
                    if x.get("price"):
                        item["price"] = x["price"]
                    item["steps"] = [
                        {"transit": f"to-{key}", "title": f"To {name}"},
                        {"location": key},
                        {"transit": f"from-{key}", "title": f"From {name}"},
                    ]
                    new_items.append(item)
                    converted += 1
                else:
                    new_items.append(x)
            tier["options"] = new_items

save_yaml(PATH, Y)
print(f"opciones convertidas al estilo enriquecido: {converted} · retorno retirados: {retornos}")
