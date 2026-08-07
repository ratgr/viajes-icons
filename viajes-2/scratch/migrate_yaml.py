# -*- coding: utf-8 -*-
"""migrate_yaml.py — crea/actualiza src/<viaje>/viaje.yaml a partir del upstream
declarado en su config.yaml (`fuente:`), aplicando la limpieza de datos aprobada:

  1. títulos sin ** — el título entero va en bold por diseño, los asteriscos
     eran ruido del pipeline viejo (y en el app familiar producían basura)
  2. pasos de transporte sin emoji inicial — el icono se deriva de `mode` al
     renderizar (build_itinerario.MODE_ICON), no vive en el texto
  3. claves del schema en INGLÉS (el upstream las tiene en español) y
     time → time-from (el schema local también acepta time-to, y
     duration: flex para pasos que explícitamente se estiran)

Los @[refs](clave) y el markdown de las notas se conservan tal cual.
Rerun cada vez que cambie el upstream.
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from common import ROOT, resolve_trip, save_yaml, trip_paths

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TRIP = resolve_trip(sys.argv)
SRC_DIR, _PAGES, CFG = trip_paths(TRIP)
if not CFG.get("source"):
    sys.exit(f"src/{TRIP}/config.yaml no declara `source:`")
SRC = os.path.normpath(os.path.join(ROOT, CFG["source"]))
DST = os.path.join(SRC_DIR, "viaje.yaml")

# emojis de transporte que pueden encabezar un título de transit (con o sin
# selector de variación); cualquier otro emoji (🏪 👋 👘 …) se queda
TRANSPORT = ("🚇", "🚶", "🚝", "🚌", "🧳", "✈️", "✈", "⛴️", "⛴", "🛳️", "🛳", "🚋", "🚊")

# claves del upstream (español) → schema local (inglés); time → time-from
KEY_RENAMES = {
    "titulo": "title", "ancla": "anchor", "time": "time-from",
    "precio": "price", "solo_seleccion": "select-only",
    "lineas": "lines", "linea": "line",
    "nombre": "name", "nombre_jp": "name_jp",
    "descripcion": "description", "informacion": "info",
    "imagen": "image", "horario": "hours", "horario_fuente": "hours_source",
    "frecuencia": "frequency", "frecuencia_fuente": "frequency_source",
    "primer_tren": "first_train", "ultimo_tren": "last_train",
    "reconoce": "recognize", "anden": "platform", "reverso": "reverse",
    "estaciones": "stations", "vehiculo": "vehicle", "guia": "guide",
}


def rename_keys(node):
    if isinstance(node, dict):
        return {KEY_RENAMES.get(k, k): rename_keys(v) for k, v in node.items()}
    if isinstance(node, list):
        return [rename_keys(v) for v in node]
    return node

stats = {"ast": 0, "emoji": 0}
modes = set()


def strip_asterisks(node):
    if "title" in node and "*" in str(node["title"]):
        node["title"] = str(node["title"]).replace("*", "")
        stats["ast"] += 1


def strip_transport_emoji(node):
    t = str(node.get("title") or "")
    for e in TRANSPORT:
        if t.startswith(e):
            node["title"] = t[len(e):].lstrip()
            stats["emoji"] += 1
            return


def walk_steps(steps):
    for s in steps:
        if not isinstance(s, dict):
            continue
        strip_asterisks(s)
        if "transit" in s or s.get("mode"):
            strip_transport_emoji(s)
        if s.get("mode"):
            modes.add(s["mode"])
        for o in s.get("options") or []:
            if isinstance(o, dict):
                strip_asterisks(o)
                if "steps" in o:            # plan anidado
                    walk_steps(o["steps"])


Y = yaml.safe_load(open(SRC, encoding="utf-8"))
for tr in (Y.get("transits") or {}).values():
    if tr.get("mode"):
        modes.add(tr["mode"])
for day in Y.get("days", []):
    walk_steps(day.get("steps", []))
Y = rename_keys(Y)   # claves ES → EN (después de las limpiezas, que leen 'time')

save_yaml(DST, Y)
print(f"viaje.yaml local ← {SRC}")
print(f"  títulos sin asteriscos: {stats['ast']} · emojis de transporte quitados: {stats['emoji']}")
print(f"  modes presentes: {sorted(modes)}")
