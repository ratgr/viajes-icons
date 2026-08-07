# -*- coding: utf-8 -*-
"""fix_teleports.py — arregla los teletransportes OBVIOS detectados por
check_teleports (6 ago 2026). Idempotente; imprime lo que tocó y respalda
las coords retiradas en el propio log.

Arreglos:
  A. d4: la caminata oculta «Osaka-Namba → Nippombashi» (d7-e14) estaba tras
     el Parque de Nara; es el regreso — va justo antes del Sakaisuji de vuelta
     (d7-10).
  B. d4: d7-4 («Parque → Tōdai-ji») traía la REVERSA exacta de d7-e14 (la ida
     Nippombashi → Osaka-Namba, desv. máx 1.7 m): esas coords se re-alojan en
     un paso oculto nuevo tras el Sakaisuji de ida (d7-1) con clave propia
     `nippombashi-namba`, y d7-4 queda pendiente de geometría (su caminata
     real en Nara nunca se dibujó).
  C. d5: la caminata oculta «Parque Tennōji + Keitakuen → Abeno Harukas»
     (d8-e8) estaba DESPUÉS del mirador; va antes de él.
  D. coords EXTRANJERAS retiradas (el trazo queda a km de sus dos vecinos —
     es de otro tramo): d8-4, d10-4, d12-4, d13-9, d14-2 → pendientes de
     geometría (conector automático punteado; redibujar con el editor dev).
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from common import resolve_trip, save_yaml, trip_paths

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TRIP = resolve_trip(sys.argv)
SRC_DIR, _p, _c = trip_paths(TRIP)
PATH = os.path.join(SRC_DIR, "viaje.yaml")

Y = yaml.safe_load(open(PATH, encoding="utf-8"))
TR = Y["transits"]
changed = []


def find(steps, **crit):
    for i, s in enumerate(steps):
        if isinstance(s, dict) and all(s.get(k) == v for k, v in crit.items()):
            return i
    return -1


def move_before(steps, i_from, i_to, label):
    if i_from < 0 or i_to < 0 or i_from == i_to:
        return
    s = steps.pop(i_from)
    if i_from < i_to:
        i_to -= 1
    steps.insert(i_to, s)
    changed.append(label)


d4 = Y["days"][3]["steps"]
d5 = Y["days"][4]["steps"]

# A. regreso Namba→Nippombashi a su lugar (antes del Sakaisuji de vuelta)
i_ret = find(d4, transit="d7-e14")
i_ride = find(d4, transit="d7-10")
if i_ret >= 0 and i_ride >= 0 and i_ret != i_ride - 1:
    move_before(d4, i_ret, i_ride, "d4: «Osaka-Namba → Nippombashi» (d7-e14) movida ante el Sakaisuji de vuelta")

# B. re-alojar la ida que vivía en d7-4
if TR.get("d7-4", {}).get("coords") and "nippombashi-namba" not in TR:
    src = TR["d7-4"]
    TR["nippombashi-namba"] = {"mode": "walk", "color": src.get("color", "#7a6f63"),
                               "coords": src["coords"]}
    del TR["d7-4"]["coords"]
    i_ida = find(d4, transit="d7-1")
    if i_ida >= 0 and find(d4, transit="nippombashi-namba") < 0:
        d4.insert(i_ida + 1, {"transit": "nippombashi-namba", "hidden-summary": True,
                              "title": "Nippombashi → Osaka-Namba"})
    changed.append("d4: coords de d7-4 re-alojadas como `nippombashi-namba` (paso oculto tras d7-1); d7-4 pendiente")

# C. caminata Tennōji→Abeno antes del mirador
i_walk = find(d5, transit="d8-e8")
i_mir = find(d5, location="abeno-harukas")
if i_walk >= 0 and i_mir >= 0 and i_walk > i_mir:
    move_before(d5, i_walk, i_mir, "d5: «Parque Tennōji → Abeno Harukas» (d8-e8) movida ante el mirador")

# D. retirar coords extranjeras (quedan aquí respaldadas por el log)
FOREIGN = ["d8-4", "d10-4", "d12-4", "d13-9", "d14-2"]
for k in FOREIGN:
    t = TR.get(k)
    if t and t.get("coords"):
        print(f"— respaldo {k}: {t['coords']}")
        del t["coords"]
        changed.append(f"coords extranjeras retiradas de {k} (pendiente de geometría)")

if changed:
    save_yaml(PATH, Y)
    print("\nCAMBIOS:")
    for c in changed:
        print(" ·", c)
else:
    print("nada que cambiar (ya aplicado)")
