# -*- coding: utf-8 -*-
"""osm_rail_geometry.py — trae de OSM (Overpass) la geometría REAL de:
  · d5-4  JR San-yō Hiroshima → Miyajimaguchi (railway=rail, sin shinkansen):
          grafo de vías + camino más corto entre los nodos más cercanos a
          las dos estaciones extremas
  · d5-5  ferry JR Miyajimaguchi → Miyajima (route=ferry)

Escribe los coords por REEMPLAZO DE TEXTO de la línea `coords:` del bloque
del transit (los comentarios del YAML quedan intactos). d5-4 además conserva
sus 10 posiciones de estación en una línea nueva `stops:` (el mapa pinta los
puntos de estación desde ahí cuando coords ya es denso).
"""
import heapq
import json
import math
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from common import resolve_trip, trip_paths

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TRIP = resolve_trip(sys.argv)
SRC_DIR, _p, _c = trip_paths(TRIP)
PATH = os.path.join(SRC_DIR, "viaje.yaml")
OVERPASS = "https://overpass-api.de/api/interpreter"


def overpass(q):
    req = urllib.request.Request(OVERPASS, data=("data=" + urllib.parse.quote(q)).encode(),
                                 headers={"User-Agent": "viajes-2 geometry fixer"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def dist(a, b):
    dy = (b[0] - a[0]) * 111000
    dx = (b[1] - a[1]) * 111000 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def rail_path(bbox, src, dst, way_filter):
    """camino más corto sobre el grafo de vías OSM entre los nodos más
    cercanos a src y dst."""
    d = overpass(f"[out:json][timeout:60];way{way_filter}({bbox});(._;>;);out body;")
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    adj = {}
    for e in d["elements"]:
        if e["type"] != "way":
            continue
        nd = e.get("nodes", [])
        for a, b in zip(nd, nd[1:]):
            if a in nodes and b in nodes:
                w = dist(nodes[a], nodes[b])
                adj.setdefault(a, []).append((b, w))
                adj.setdefault(b, []).append((a, w))
    def nearest(pt):
        return min(adj, key=lambda n: dist(nodes[n], pt))
    s, t = nearest(src), nearest(dst)
    # Dijkstra
    dd = {s: 0.0}
    prev = {}
    pq = [(0.0, s)]
    while pq:
        cd, u = heapq.heappop(pq)
        if u == t:
            break
        if cd > dd.get(u, 1e18):
            continue
        for v, w in adj.get(u, []):
            nv = cd + w
            if nv < dd.get(v, 1e18):
                dd[v] = nv
                prev[v] = u
                heapq.heappush(pq, (nv, v))
    if t not in prev and t != s:
        raise SystemExit("sin ruta en el grafo OSM")
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    path.reverse()
    return [nodes[n] for n in path]


def simplify(pts, tol_m=12.0):
    """Douglas-Peucker sencillito para no cargar cientos de vértices."""
    if len(pts) < 3:
        return pts
    def dp(lo, hi):
        a, b = pts[lo], pts[hi]
        worst, wi = -1.0, None
        for i in range(lo + 1, hi):
            # distancia punto-recta aproximada en metros
            t_num = ((pts[i][0]-a[0])*(b[0]-a[0])*111000**2 +
                     (pts[i][1]-a[1])*(b[1]-a[1])*(111000*math.cos(math.radians(a[0])))**2)
            den = dist(a, b)**2 or 1e-9
            t = max(0.0, min(1.0, t_num/den))
            proj = (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t)
            dpm = dist(pts[i], proj)
            if dpm > worst:
                worst, wi = dpm, i
        if worst > tol_m:
            return dp(lo, wi)[:-1] + dp(wi, hi)
        return [pts[lo], pts[hi]]
    return dp(0, len(pts)-1)


def fmt(pts):
    return " ".join(f"{a:.6f},{b:.6f}" for a, b in pts)


def replace_in_block(text, key, field, value, insert_after=None):
    """reemplaza (o inserta tras `insert_after`) la línea `field:` dentro del
    bloque del transit `key` — edición de TEXTO: los comentarios sobreviven."""
    m = re.search(rf"^(  {re.escape(key)}:\n)((?:    .*\n)*)", text, re.M)
    if not m:
        raise SystemExit(f"bloque {key} no encontrado (¿estilo flow?)")
    block = m.group(2)
    line = f"    {field}: {value}\n"
    if re.search(rf"^    {field}:", block, re.M):
        block2 = re.sub(rf"^    {field}:.*\n", line, block, count=1, flags=re.M)
    elif insert_after and re.search(rf"^    {insert_after}:.*\n", block, re.M):
        block2 = re.sub(rf"^(    {re.escape(insert_after)}:.*\n)", rf"\1{line}", block, count=1, flags=re.M)
    else:
        block2 = block + line
    return text[:m.start(2)] + block2 + text[m.end(2):]


text = open(PATH, encoding="utf-8").read()

# --- d5-4: San-yō line Hiroshima → Miyajimaguchi (rail, sin shinkansen/tranvía)
old = re.search(r"^  d5-4:\n(?:    .*\n)*?    coords: (.*)$", text, re.M)
old_pts = old.group(1).strip() if old else ""
hiro, miya = (34.397667, 132.475379), (34.312009, 132.302951)
pts = rail_path("34.29,132.28,34.42,132.49", hiro, miya,
                '["railway"="rail"]["name"!~"新幹線"]["service"!~"yard|siding|spur"]')
pts = simplify([hiro] + pts + [miya])
print(f"d5-4: {len(pts)} pts OSM (antes 10)")
text = replace_in_block(text, "d5-4", "coords", fmt(pts))
if old_pts:
    text = replace_in_block(text, "d5-4", "stops", old_pts, insert_after="coords")

# --- d5-5: ferry Miyajimaguchi → Miyajima
try:
    d = overpass('[out:json][timeout:60];way["route"="ferry"](34.29,132.29,34.325,132.33);(._;>;);out body;')
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    ways = [e for e in d["elements"] if e["type"] == "way" and e.get("nodes")]
    P1, P2 = (34.312009, 132.302951), (34.302560, 132.321660)   # muelles JR
    def score(w):
        a, b = nodes[w["nodes"][0]], nodes[w["nodes"][-1]]
        return min(dist(a, P1) + dist(b, P2), dist(a, P2) + dist(b, P1))
    best = min(ways, key=score, default=None)   # extremos EN los muelles JR
    fpts = [nodes[n] for n in best["nodes"]] if best else []
except Exception as e:
    print("ferry overpass falló:", e)
    fpts = []
if not fpts:
    fpts = [(34.312009, 132.302951), (34.302560, 132.321660)]   # línea recta muelle a muelle
# orientar: arranca en Miyajimaguchi
if dist(fpts[0], (34.312009, 132.302951)) > dist(fpts[-1], (34.312009, 132.302951)):
    fpts.reverse()
print(f"d5-5: {len(fpts)} pts")
text = replace_in_block(text, "d5-5", "coords", fmt(simplify(fpts)))

open(PATH, "w", encoding="utf-8", newline="\n").write(text)
print("viaje.yaml actualizado (solo líneas coords/stops de d5-4 y d5-5)")
