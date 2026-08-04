# -*- coding: utf-8 -*-
"""viaje-data.json: por día → {label, places[], segments[]}.
Segmentos y paradas ordenadas salen de japon-rutas.kml (carpetas por día).
Lugares (sitios/restos/hoteles) salen de japon-puntos.kml, asignados al día por
la descripción (EN EL PLAN / días). Coords ya son Google-exactas."""
import html
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = r"C:/Users/Ricardo/AppData/Local/Temp/claude/d--dev-tamper-finances/81928241-1549-48b6-9a85-7eac7bb94ebc/scratchpad"
rut = open(SD + "/japon-rutas.kml", encoding="utf-8").read()
pun = open(SD + "/japon-puntos.kml", encoding="utf-8").read()

DIAS_ORD = ["dom 4", "lun 5", "mar 6", "mié 7", "jue 8", "vie 9", "sáb 10",
            "dom 11", "lun 12", "mar 13", "mié 14", "jue 15", "vie 16", "sáb 17", "dom 18"]
DIA_FULL = {
 "dom 4": "dom 4 · Osaka", "lun 5": "lun 5 · Hiroshima + Miyajima", "mar 6": "mar 6 · USJ",
 "mié 7": "mié 7 · Nara", "jue 8": "jue 8 · → Kioto", "vie 9": "vie 9 · Kioto este",
 "sáb 10": "sáb 10 · Arashiyama", "dom 11": "dom 11 · Kioto oeste", "lun 12": "lun 12 · → Tokio",
 "mar 13": "mar 13 · Tokio viejo", "mié 14": "mié 14 · Hakone", "jue 15": "jue 15 · Shibuya",
 "vie 16": "vie 16 · subgrupos", "sáb 17": "sáb 17 · Tsukiji", "dom 18": "dom 18 · regreso"}

def unesc(t):
    return html.unescape(t or "")

def kml_color_to_hex(c):
    # aabbggrr -> #rrggbb
    if not c or len(c) != 8:
        return "#888888"
    return "#" + c[6:8] + c[4:6] + c[2:4]

# ---- segmentos + paradas por día desde rutas ----
dias = {d: {"label": DIA_FULL[d], "places": [], "segments": []} for d in DIAS_ORD}
NOMDIA_RE = re.compile(r"<Folder><name>((?:dom|lun|mar|mié|jue|vie|sáb) \d+)[^<]*</name>([\s\S]*?)</Folder>")
for m in NOMDIA_RE.finditer(rut):
    dkey = m.group(1)
    if dkey not in dias:
        continue
    blk = m.group(2)
    for pm in re.finditer(r"<Placemark>([\s\S]*?)</Placemark>", blk):
        p = pm.group(1)
        nom = unesc((re.search(r"<name>([^<]*)</name>", p) or [None, ""])[1])
        style = (re.search(r"<styleUrl>#([^<]+)</styleUrl>", p) or [None, ""])[1]
        if "<Point>" in p:  # parada numerada
            c = re.search(r"<coordinates>([^<]+)</coordinates>", p)
            if c:
                lon, lat = c.group(1).split(",")[:2]
                dias[dkey]["places"].append({
                    "name": nom, "lat": float(lat), "lng": float(lon),
                    "kind": "stop", "order": int((re.match(r"(\d+)\.", nom) or [0, 0])[1]),
                })
        else:  # segmento (LineString / MultiGeometry)
            color = "#888888"
            sm = re.search(r"l([0-9a-fA-F]{8})(\d+)", style)
            if sm:
                color = kml_color_to_hex(sm.group(1))
            # coords: tomar TODAS las LineString y unir la más larga como línea principal
            lines = re.findall(r"<coordinates>([^<]+)</coordinates>", p)
            best = max(lines, key=len) if lines else ""
            pts = []
            for pair in best.split():
                xy = pair.split(",")
                if len(xy) >= 2:
                    pts.append([float(xy[1]), float(xy[0])])  # [lat,lng]
            if len(pts) >= 2:
                mode = "walk" if "🚶" in nom else ("bus" if "🚌" in nom else ("ferry" if "⛴" in nom else ("tour" if "🚡" in nom else "train")))
                dias[dkey]["segments"].append({
                    "name": nom, "color": color, "mode": mode, "coords": pts,
                })

# ---- lugares (sitios/restos/hoteles) por día desde puntos ----
MESES = {"dom 4", "lun 5", "mar 6", "mié 7", "jue 8", "vie 9", "sáb 10", "dom 11",
         "lun 12", "mar 13", "mié 14", "jue 15", "vie 16", "sáb 17", "dom 18"}
def dias_en_texto(t):
    return [d for d in DIAS_ORD if d in t]

for pm in re.finditer(r"<Placemark>([\s\S]*?)</Placemark>", pun):
    p = pm.group(1)
    nom = unesc((re.search(r"<name>([^<]*)</name>", p) or [None, ""])[1])
    desc = unesc((re.search(r"<!\[CDATA\[([\s\S]*?)\]\]>", p) or [None, ""])[1])
    c = re.search(r"<coordinates>([^<]+)</coordinates>", p)
    if not c:
        continue
    lon, lat = c.group(1).split(",")[:2]
    style = (re.search(r"<styleUrl>#([^<]+)</styleUrl>", p) or [None, ""])[1]
    kind = "site" if style.startswith("sitio") else ("hotel" if style in ("hotel", "aero") else "resto")
    tier = {"take": "Take", "ai": "Ai", "shu": "Shu"}.get(style, "")
    ds = dias_en_texto(desc)
    if kind == "hotel":
        # hoteles: al primer día de su bloque (aprox) — asignar a todos los días de su ciudad no; ponerlos como capa aparte simple
        ds = ds or []
    obj = {"name": nom, "lat": float(lat), "lng": float(lon), "kind": kind, "tier": tier,
           "desc": re.sub(r"<[^>]+>", " ", desc)[:220].strip(), "maps": "https://www.google.com/maps/search/?api=1&query=%.6f,%.6f" % (float(lat), float(lon))}
    for d in ds:
        if d in dias:
            dias[d]["places"].append(dict(obj))

# hoteles y aeropuertos: capa fija (no por día)
fijos = []
for pm in re.finditer(r"<Placemark>([\s\S]*?)</Placemark>", pun):
    p = pm.group(1)
    style = (re.search(r"<styleUrl>#([^<]+)</styleUrl>", p) or [None, ""])[1]
    if style not in ("hotel", "aero"):
        continue
    nom = unesc((re.search(r"<name>([^<]*)</name>", p) or [None, ""])[1])
    c = re.search(r"<coordinates>([^<]+)</coordinates>", p)
    lon, lat = c.group(1).split(",")[:2]
    fijos.append({"name": nom, "lat": float(lat), "lng": float(lon), "kind": "hotel" if style == "hotel" else "aero"})

out = {"days": [dict(dias[d], key=d) for d in DIAS_ORD], "fixed": fijos}
open(SD + "/viaje-data.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
tot_pl = sum(len(d["places"]) for d in out["days"])
tot_sg = sum(len(d["segments"]) for d in out["days"])
print(f"días: {len(out['days'])} · lugares: {tot_pl} · segmentos: {tot_sg} · fijos: {len(fijos)}")
for d in out["days"]:
    print(f"  {d['key']:7} pl={len(d['places']):2} sg={len(d['segments']):2}")
