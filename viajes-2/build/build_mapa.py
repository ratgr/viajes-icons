# -*- coding: utf-8 -*-
"""build_mapa.py — src/<viaje>/viaje.yaml → pages/<viaje>/mapa.html.

La barra lateral del mapa ES el itinerario: mismos días/filas/modales que
genera render.py (proyección 1:1 del YAML, verificada). El cromo del mapa
(casillas, colapso por día, mapa base Leaflet) lo agregan mapa.css/mapa.js
en el navegador — el HTML servido no cambia.

Por ahora: barra lateral + mapa base. Las capas (marcadores/rutas) vienen después.
"""
import json
import sys

import render
from common import resolve_trip

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ------------------------------------------------- anclas precalculadas
# Para cada paso con `transit:` SIN geometría (el conector automático del
# mapa) se precalcula aquí el par {prev, next}: el punto del vecino con
# geometría más cercano DENTRO de su misma rama y su mismo día — la misma
# regla que neighborAnchors/sameBranch en mapa.js, pero en build (mapa.js
# los lee de GEO.anchors por id de fila y solo rastrea en vivo si faltan).

def _step_anchor_pt(s, end):
    """punto de anclaje de un paso: lugar → su gps; transporte → su último/
    primer vértice (según sea el vecino previo o el siguiente) — espejo de
    anchorPoint en mapa.js."""
    key = s.get("location") or s.get("transit")
    p = render._place_pt(key)
    if p:
        return [p[0], p[1]]
    pts = render._transit_pts(key)
    if pts:
        q = pts[-1] if end else pts[0]
        return [q[0], q[1]]
    return None


def _same_branch(path_el, path_cand):
    """espejo de sameBranch (mapa.js): el candidato es vecino válido si el
    paso base cuelga de cada conjunto de options ancestro del candidato por
    el MISMO contenedor (opción/plan); candidato fuera de todo conjunto
    siempre es válido. Las rutas son tuplas (conjunto, contenedor) de afuera
    hacia adentro."""
    for k, (set_id, cont_id) in enumerate(path_cand):
        if k >= len(path_el) or path_el[k] != (set_id, cont_id):
            return False       # fuera del conjunto, o en OTRA opción del mismo
    return True


def _collect_rows(day, num):
    """pasos con location/transit del día, aplanados en orden del documento:
    (id extendido, paso, ruta-de-rama) — la MISMA lista y los MISMOS ids
    dN-rMM[-gG[-oO]-sS] que emiten render_day/render_options/render_option."""
    out = []

    def visit(s, sid, path):
        if not isinstance(s, dict):
            return
        if s.get("location") or s.get("transit"):
            out.append((sid, s, path))
        for gi, o in enumerate(s.get("options") or [], 1):
            if not isinstance(o, dict):
                continue
            if "steps" in o:               # plan: el grupo mismo es el contenedor
                for si, sub in enumerate(o["steps"], 1):
                    visit(sub, f"{sid}-g{gi}-s{si}", path + ((sid, f"g{gi}"),))
            else:                          # tier: contenedor = cada opción
                for oi, x in enumerate(o.get("options") or [], 1):
                    if not isinstance(x, dict):
                        continue
                    for si, sub in enumerate(x.get("steps") or [], 1):
                        visit(sub, f"{sid}-g{gi}-o{oi}-s{si}",
                              path + ((sid, f"g{gi}-o{oi}"),))

    for i, s in enumerate(day.get("steps", [])):
        visit(s, f"d{num}-r{i + 1:02d}", ())
    return out


def anchors_tokens():
    """GEO['anchors']: id de fila → {prev, next} para cada transit sin coords
    (el rastreo queda acotado al día, como el conector automático)."""
    anchors = {}
    for num, day in enumerate(render.DAYS, 1):
        rows = _collect_rows(day, num)
        for i, (sid, s, path) in enumerate(rows):
            if s.get("location") or not s.get("transit"):
                continue                   # el conector automático es solo transit
            key = s["transit"]
            if render._place_pt(key) or render._transit_pts(key):
                continue                   # con geometría propia no hay conector
            prev = nxt = None
            for j in range(i - 1, -1, -1):
                if not _same_branch(path, rows[j][2]):
                    continue               # no anclar en OTRA opción
                prev = _step_anchor_pt(rows[j][1], True)
                if prev:
                    break
            for j in range(i + 1, len(rows)):
                if not _same_branch(path, rows[j][2]):
                    continue
                nxt = _step_anchor_pt(rows[j][1], False)
                if nxt:
                    break
            anchors[sid] = {"prev": prev, "next": nxt}
    return anchors


def geo_tokens():
    """geometría por clave YAML para el mapa: gps de places, coords de transits.
    (Se inyecta como JSON aparte: las coordenadas no son parte de las filas.)"""
    locs = {}
    for key, pl in render.PLACES.items():
        gps = pl.get("gps")
        if gps:
            pt = render.parse_pts(gps, f"places[{key}]")
            if not pt:
                continue          # malformado: ya quedó en DIAGNOSTICS
            locs[key] = [pt[0][0], pt[0][1]]
    transits = {}
    for key, tr in render.TRANSITS.items():
        coords = tr.get("coords")
        if coords:
            parsed = render.parse_pts(coords, f"transits[{key}]")
            if not parsed:
                continue
            pts = [[a, b] for a, b in parsed]
            entry = {"coords": pts, "color": tr.get("color", "#7a6f63"),
                     "mode": tr.get("mode", "walk")}
            # rieles: cada vértice ES una estación ([código, jp, romaji]) —
            # el mapa las pinta como paradas con nombre si las cuentas calzan
            stations = tr.get("stations")
            if stations:
                entry["stations"] = [
                    (s[2] or s[1]) if isinstance(s, list) and len(s) >= 3 else str(s)
                    for s in stations
                ]
            # stops: posiciones de estación cuando coords ya es el trazo DENSO
            # (geometría OSM) y perdió la alineación 1 vértice = 1 estación
            stops = tr.get("stops")
            if stops:
                sp = render.parse_pts(stops, f"transits[{key}].stops")
                if sp:
                    entry["stops"] = [[a, b] for a, b in sp]
            transits[key] = entry
    # caja del viaje (vista inicial del mapa) + nombre del viaje (identidad
    # para el modo dev, en vez de olfatear la URL)
    pts = list(locs.values()) + [p for t in transits.values() for p in t["coords"]]
    geo = {"locations": locs, "transits": transits, "trip": _TRIP[0],
           "anchors": anchors_tokens()}
    if pts:
        geo["bbox"] = [min(p[0] for p in pts), min(p[1] for p in pts),
                       max(p[0] for p in pts), max(p[1] for p in pts)]
    return {"<!--GEO-->": json.dumps(geo, ensure_ascii=False)}


_TRIP = [""]   # fijado por main antes del build (geo_tokens corre dentro)


def main():
    _TRIP[0] = resolve_trip(sys.argv)
    return render.build_and_verify(_TRIP[0], "plantilla-mapa.html", "mapa.html",
                                   extra=geo_tokens)


if __name__ == "__main__":
    sys.exit(main())
