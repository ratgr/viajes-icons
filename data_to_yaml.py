# -*- coding: utf-8 -*-
"""Siembra japon-fuente.yaml desde viaje-data.json (una sola vez). Después la fuente
es el YAML: se edita a mano y `yaml_to_data.py` regenera viaje-data.json.
Coordenadas como strings compactas: place -> `coord: "lat,lng"`, tramo -> `coords: "lat,lng lat,lng ..."`."""
import json
import os
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(SD + "/viaje-data.json", encoding="utf-8"))

def cc(o):
    return f"{o['lat']:.6f},{o['lng']:.6f}"

def place(p):
    o = {"name": p["name"], "kind": p["kind"]}
    if p["kind"] == "stop":
        o["order"] = p.get("order", 0)
        o["fixTime"] = bool(p.get("fixTime"))
    else:
        o["tier"] = p.get("tier", "")
        if p["kind"] in ("site", "resto"):
            o["key"] = p.get("key", "")
        else:
            o["time"] = p.get("time", "")
    o["coord"] = cc(p)
    for k in ("desc", "hist", "foto", "maps"):
        if p.get(k):
            o[k] = p[k]
    return o

def opt(o):
    r = {"name": o["name"], "tier": o.get("tier", ""), "key": o.get("key", ""),
         "price": o.get("price", ""), "coord": cc(o)}
    for k in ("desc", "foto", "maps"):
        if o.get(k):
            r[k] = o[k]
    return r

def seg(s):
    o = {"name": s["name"], "mode": s["mode"], "dur": s.get("dur", 0), "durTxt": s.get("durTxt", "")}
    if s.get("distTxt"):
        o["distTxt"] = s["distTxt"]
    o["color"] = s.get("color", "")
    o["coords"] = " ".join(f"{la:.6f},{lo:.6f}" for la, lo in s["coords"])
    return o

days = []
for d in D["days"]:
    days.append({
        "key": d["key"], "label": d["label"], "travelMin": d.get("travelMin", 0),
        "travelTxt": d.get("travelTxt", ""), "startTime": d.get("startTime", ""),
        "places": [place(p) for p in d["places"]],
        "meals": [{"time": m["time"], "opts": [opt(o) for o in m["opts"]]} for m in d.get("meals", [])],
        "segments": [seg(s) for s in d["segments"]],
    })

with open(SD + "/japon-fuente.yaml", "w", encoding="utf-8") as f:
    yaml.dump({"days": days}, f, allow_unicode=True, sort_keys=False,
              default_flow_style=False, width=100000000)
print(f"japon-fuente.yaml sembrado · {len(days)} días")
