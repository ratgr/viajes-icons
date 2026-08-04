# -*- coding: utf-8 -*-
"""3 KML para My Maps (10 capas c/u = 5 días × {lugares, rutas}).
Importar cada uno en su propio mapa (borrando capas antes)."""
import html as H
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = r"C:/Users/Ricardo/AppData/Local/Temp/claude/d--dev-tamper-finances/81928241-1549-48b6-9a85-7eac7bb94ebc/scratchpad"
DATA = json.load(open(SD + "/viaje-data.json", encoding="utf-8"))

def esc(t):
    return H.escape(str(t or ""), quote=False)

def kml_color(hexc, a="ff"):
    hexc = hexc.lstrip("#")
    if len(hexc) != 6:
        return "ff888888"
    return a + hexc[4:6] + hexc[2:4] + hexc[0:2]

# estilos de punto (íconos teñibles Google) e íconos numerados
PIN = {
 "site": ("ff2a3ab2", "https://maps.google.com/mapfiles/kml/shapes/star.png"),
 "stop": ("ff2a3ab2", "https://maps.google.com/mapfiles/kml/shapes/star.png"),
 "hotel": ("ff00a5f0", "https://maps.google.com/mapfiles/kml/shapes/lodging.png"),
 "aero": ("ffb75a29", "https://maps.google.com/mapfiles/kml/shapes/airports.png"),
 "resto": ("ff8a7f72", "https://maps.google.com/mapfiles/kml/shapes/dining.png"),
}
TIERCOL = {"Take": "ff4a7d3a", "Ai": "ffa06b2c", "Shu": "ff2a3ab2"}
NUM = "https://maps.google.com/mapfiles/kml/paddle/%s.png"

def build_map(dias, fijos, nombre, archivo):
    styles, seen = [], set()
    def style(sid, color, icon, scale=1.0):
        if sid in seen:
            return sid
        seen.add(sid)
        styles.append(f'<Style id="{sid}"><IconStyle><color>{color}</color><scale>{scale}</scale>'
                      f'<Icon><href>{icon}</href></Icon></IconStyle></Style>')
        return sid
    def linestyle(sid, color, w):
        if sid in seen:
            return sid
        seen.add(sid)
        styles.append(f'<Style id="{sid}"><LineStyle><color>{color}</color><width>{w}</width></LineStyle></Style>')
        return sid

    folders = []
    for d in dias:
        # capa de LUGARES del día
        pms = []
        for p in d["places"]:
            if p["kind"] == "stop" and p.get("order"):
                sid = style(f"n{min(p['order'],10)}", "ffffffff", NUM % min(p["order"], 10), 1.0)
            elif p["kind"] == "resto":
                col = TIERCOL.get(p.get("tier"), "ff8a7f72")
                sid = style(f"resto_{p.get('tier','x')}", col, PIN["resto"][1])
            else:
                pi = PIN.get(p["kind"], PIN["resto"])
                sid = style(f"k_{p['kind']}", pi[0], pi[1])
            desc = esc(p.get("desc", "")) + (f'<br/><a href="{esc(p["maps"])}">Google Maps</a>' if p.get("maps") else "")
            pms.append(f'<Placemark><name>{esc(p["name"])}</name><styleUrl>#{sid}</styleUrl>'
                       f'<description><![CDATA[{desc}]]></description>'
                       f'<Point><coordinates>{p["lng"]:.6f},{p["lat"]:.6f},0</coordinates></Point></Placemark>')
        folders.append(f'<Folder><name>{esc(d["key"])} · lugares</name>' + "".join(pms) + "</Folder>")
        # capa de RUTAS del día
        segs = []
        for s in d["segments"]:
            w = 3 if s["mode"] == "walk" else (6 if s["mode"] == "train" else 5)
            sid = linestyle(f"L{s['color'].lstrip('#')}{w}", kml_color(s["color"]), w)
            coords = " ".join(f"{lng:.6f},{lat:.6f},0" for lat, lng in s["coords"])
            segs.append(f'<Placemark><name>{esc(s["name"])}</name><styleUrl>#{sid}</styleUrl>'
                        f'<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString></Placemark>')
        folders.append(f'<Folder><name>{esc(d["key"])} · rutas</name>' + "".join(segs) + "</Folder>")

    k = ['<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f"<name>{esc(nombre)}</name>"]
    k += styles + folders
    k.append("</Document></kml>")
    open(SD + "/" + archivo, "w", encoding="utf-8").write("\n".join(k))
    n = "\n".join(k)
    return n.count("<Folder>"), n.count("<Placemark>"), len(n) // 1024

days = DATA["days"]
partes = [
 (days[0:5], "Japón 2026 — parte 1 (dom4–jue8)", "mymap-1.kml"),
 (days[5:10], "Japón 2026 — parte 2 (vie9–mar13)", "mymap-2.kml"),
 (days[10:15], "Japón 2026 — parte 3 (mié14–dom18)", "mymap-3.kml"),
]
for dias, nombre, arch in partes:
    f, pm, kb = build_map(dias, DATA["fixed"], nombre, arch)
    print(f"{arch}: {f} capas · {pm} placemarks · {kb} KB")
