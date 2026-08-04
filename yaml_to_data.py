# -*- coding: utf-8 -*-
"""FUENTE ÚNICA: japon-fuente.yaml → viaje-data.json (lo que consume build_leaflet.py).
Reemplaza a los KMLs + build_rutas.py + build_viaje_data.py.
Flujo: editas japon-fuente.yaml → `python yaml_to_data.py` → `python build_leaflet.py`."""
import json
import os
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
Y = yaml.safe_load(open(SD + "/japon-fuente.yaml", encoding="utf-8"))

def latlng(s):
    a, b = str(s).split(",")
    return float(a), float(b)

def place(p):
    la, lo = latlng(p["coord"])
    q = {"name": p["name"], "kind": p["kind"], "lat": la, "lng": lo}
    if p["kind"] == "stop":
        q["order"] = p.get("order", 0)
        q["fixTime"] = bool(p.get("fixTime"))
    else:
        q["tier"] = p.get("tier", "")
        if p["kind"] in ("site", "resto"):
            q["key"] = p.get("key", "")
        else:
            q["time"] = str(p.get("time", ""))
        for k in ("desc", "hist", "foto", "maps"):
            q[k] = p.get(k, "")
    return q

def opt(o):
    la, lo = latlng(o["coord"])
    return {"name": o["name"], "tier": o.get("tier", ""), "key": o.get("key", ""),
            "price": o.get("price", ""), "lat": la, "lng": lo,
            "desc": o.get("desc", ""), "foto": o.get("foto", ""), "maps": o.get("maps", "")}

def seg(s):
    coords = [[float(a), float(b)] for a, b in (t.split(",") for t in str(s["coords"]).split())]
    q = {"name": s["name"], "color": s.get("color", ""), "mode": s["mode"], "coords": coords,
         "dur": s.get("dur", 0), "durTxt": s.get("durTxt", "")}
    if s.get("distTxt"):
        q["distTxt"] = s["distTxt"]
    return q

days = []
for d in Y["days"]:
    days.append({
        "key": d["key"], "label": d["label"],
        "places": [place(p) for p in d.get("places", [])],
        "segments": [seg(s) for s in d.get("segments", [])],
        "meals": [{"time": str(m["time"]), "opts": [opt(o) for o in m.get("opts", [])]} for m in d.get("meals", [])],
        "travelMin": d.get("travelMin", 0), "travelTxt": d.get("travelTxt", ""),
        "startTime": str(d.get("startTime", "")),
    })

json.dump({"days": days, "fixed": []}, open(SD + "/viaje-data.json", "w", encoding="utf-8"), ensure_ascii=False)
tp = sum(len(d["places"]) for d in days)
ts = sum(len(d["segments"]) for d in days)
print(f"viaje-data.json ← japon-fuente.yaml · {len(days)} días · {tp} lugares · {ts} trayectos")
