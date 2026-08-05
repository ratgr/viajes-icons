# -*- coding: utf-8 -*-
"""compile_mapa.py — viaje.yaml (schema nuevo) → día extra en viaje-data.json.

Transforma el día del viaje.yaml (places/transits/steps) al formato que
consume build_leaflet.py (places[kind/lat/lng/...], segments, meals) y lo
AÑADE al final de viaje-data.json como un día "v2" SIN quitar los viejos
(idempotente: reemplaza cualquier día v2 previo). Luego reconstruye el mapa.
"""
import os, re, sys, json, math, subprocess, urllib.request
import yaml
from modales import render_place_modal, render_line_modal, add_min

# ---- ruteo a pie real (OSRM) con caché en disco ----
_OSRM_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".osrm-cache.json")
try:
    _osrm = json.load(open(_OSRM_CACHE_PATH, encoding="utf-8"))
except Exception:
    _osrm = {}

def osrm_walk(a, b):
    """a,b = 'lat,lng'. Devuelve [[lat,lng]...] ruteado a pie; cae a recta si falla."""
    key = f"{a}->{b}"
    if key in _osrm:
        return _osrm[key]
    la1, lo1 = a.split(","); la2, lo2 = b.split(",")
    url = ("https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
           f"{lo1},{la1};{lo2},{la2}?overview=full&geometries=geojson")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            j = json.load(r)
        coords = [[c[1], c[0]] for c in j["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        coords = [[float(la1), float(lo1)], [float(la2), float(lo2)]]
    _osrm[key] = coords
    return coords

def osrm_save():
    json.dump(_osrm, open(_OSRM_CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)

def _crow(a, b):
    dy = (b[0] - a[0]) * 111000
    dx = (b[1] - a[1]) * 111000 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)
def _rlen(co):
    return sum(_crow(co[i - 1], co[i]) for i in range(1, len(co)))

def osrm_walk_clean(a, b):
    """rutea a→b; si OSRM se dispara (punto muerto, ej. acceso metro Namba: la red peatonal
    está desconectada ahí en OSM), busca el punto ruteable-limpio MÁS CERCANO al destino."""
    co = osrm_walk(a, b)
    A = [float(x) for x in a.split(",")]; B = [float(x) for x in b.split(",")]
    straight = _crow(A, B)
    if not (len(co) >= 2 and straight > 30 and _rlen(co) > 1.5 * straight):
        return co
    coslat = math.cos(math.radians(B[0]))
    for dm in (45, 80, 120):                       # anillos crecientes alrededor del destino
        best = None
        for ang in range(0, 360, 30):
            dla = dm * math.cos(math.radians(ang)) / 111000
            dlo = dm * math.sin(math.radians(ang)) / (111000 * coslat)
            c2 = osrm_walk(a, f"{B[0] + dla},{B[1] + dlo}")
            if len(c2) >= 2 and _rlen(c2) < 1.45 * straight:
                if best is None or _rlen(c2) < _rlen(best):
                    best = c2
        if best is not None:
            return best + [B]                      # ruta limpia + tramo corto al punto exacto (cierra el hueco)
    return co

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
Y = yaml.safe_load(open(SD + "/viaje.yaml", encoding="utf-8"))
PLACES = Y.get("places", {})
TRANSITS = Y.get("transits", {})
LINEAS = Y.get("lineas", {})
_LINE_N = {v.get("nombre"): v for v in LINEAS.values() if v.get("frecuencia")}
_LINE_C = {v.get("chip"): v for v in LINEAS.values() if v.get("frecuencia") and v.get("chip")}
def line_meta(tr):
    l = _LINE_N.get(tr.get("linea")) or _LINE_C.get(tr.get("chip")) or {}
    return {k: l[k] for k in ("frecuencia", "primer_tren", "ultimo_tren", "frecuencia_fuente") if l.get(k)}
HOST = "https://raw.githubusercontent.com/ratgr/viajes-icons/main/"
APP_URL = "https://ratgr.github.io/viajes-icons/app/japon.html"
EMOJI = {"train": "🚇", "walk": "🚶", "monorail": "🚝", "flight": "✈️", "tramite": "🧳"}

def latlng(s):
    a, b = str(s).split(",")
    return float(a), float(b)

def dmin(s):
    s = str(s or "")
    hm = re.search(r"(\d+)\s*h\s*(\d+)?", s)      # "1 h 05", "1 h"
    if hm:
        return int(hm.group(1)) * 60 + int(hm.group(2) or 0)
    m = re.search(r"(\d+)\s*min", s)               # "15 min", "10 min (o 15 a pie)"
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)", s)
    return int(m2.group(1)) if m2 else 0

def hm2min(s):
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(s or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None

def trng(s):
    """rango 'desde – hasta' desde time + duration; si dur 0 → solo la hora."""
    t = str(s.get("time", "")).strip()
    d = dmin(s.get("duration"))
    return f"{t} – {add_min(t, d)}" if (t and d > 0) else t

def foto(pl):
    im = pl.get("imagen")
    if not im:
        return ""
    return im if im.startswith("http") else (HOST + im)   # URL absoluta (Google Maps) tal cual

def next_point_after(steps, i):
    """siguiente punto del itinerario tras el paso i: gps del próximo lugar,
    o el FINAL del próximo tramo con geometría (a donde te lleva)."""
    for j in range(i + 1, len(steps)):
        nx = steps[j]
        if "location" in nx:
            pl = PLACES.get(nx["location"])
            if pl and pl.get("gps"):
                return pl["gps"]
        elif "transit" in nx:
            trn = TRANSITS.get(nx["transit"])
            csrc = trn.get("coords") if trn else nx.get("coords")
            if csrc and not (nx.get("solo_seleccion") or (trn and trn.get("solo_seleccion"))):
                return str(csrc).split()[0]    # INICIO del siguiente tramo (donde rejuntas / abordas) "lat,lng"
    return None

HOTELS = {"royal-park", "keio-prelia", "rose-garden"}
# hotel donde se DUERME cada noche, por índice de día (0 = dom 4)
HOTEL_BY_DAY = {0: "royal-park", 1: "royal-park", 2: "royal-park", 3: "royal-park",
                4: "keio-prelia", 5: "keio-prelia", 6: "keio-prelia", 7: "keio-prelia",
                8: "rose-garden", 9: "rose-garden", 10: "rose-garden", 11: "rose-garden",
                12: "rose-garden", 13: "rose-garden", 14: "rose-garden"}

def kind_of(key, pl):
    if "Aeropuerto" in pl.get("nombre", ""):
        return "aero"
    if key in HOTELS:
        return "hotel"
    return "stop"

def build_day(day, idx):
    places, segments, meals = [], [], []
    segN = stopN = 0
    travelMin = 0
    startTime = ""
    end_max = None           # minutos del final más tardío del día (último paso)
    info_transits = []
    steps = day.get("steps", [])
    last_loc_gps = None      # último lugar visitado (para la ida de comidas)
    for i, s in enumerate(steps):
        tt = s.get("time")
        if tt:
            if not startTime:
                startTime = str(tt)
            em = hm2min(tt)
            if em is not None:
                end_max = max(end_max or 0, em + dmin(s.get("duration")))
        if "location" in s:
            key = s["location"]; pl = PLACES.get(key, {})
            if not pl.get("gps"):
                continue   # lugar sin coordenada → no va al mapa (sí al itinerario)
            la, lo = latlng(pl["gps"]); k = kind_of(key, pl)
            last_loc_gps = pl["gps"]
            if k == "stop":
                stopN += 1
                nm = f"{stopN}. {s.get('time','')} · {pl['nombre']} (d4)"
                places.append({"name": nm, "kind": "stop", "lat": la, "lng": lo, "seqi": i,
                               "order": stopN, "fixTime": bool(s.get("fixed")), "trange": trng(s)})
                places.append({"name": pl["nombre"], "kind": "site", "lat": la, "lng": lo, "seqi": i,
                               "tier": "", "key": key, "desc": pl.get("descripcion", ""),
                               "fix": bool(s.get("fixed")), "trange": trng(s),
                               "hist": pl.get("informacion", ""), "foto": foto(pl),
                               "maps": pl.get("maps", ""),
                               "pop": render_place_modal(key, pl, HOST, APP_URL)})
            else:
                emo = "✈️" if k == "aero" else "🏨"
                places.append({"name": f"{emo} {pl['nombre']}", "kind": k, "lat": la, "lng": lo, "seqi": i,
                               "tier": "", "fix": bool(s.get("fixed")),
                               "time": str(s.get("time", "")), "trange": trng(s),
                               "desc": pl.get("descripcion", ""), "hist": pl.get("informacion", ""),
                               "foto": foto(pl), "maps": pl.get("maps", ""),
                               "pop": render_place_modal(key, pl, HOST, APP_URL)})
        elif "transit" in s:
            tr = TRANSITS.get(s["transit"])
            mode = (tr or s).get("mode", "walk")
            dur = dmin(s.get("duration"))
            coords_src = tr.get("coords") if tr else s.get("coords")
            if not coords_src:
                # sin geometría alguna → fila del panel (lateral), sin línea
                info_transits.append({"title": s.get("title", ""), "durTxt": str(s.get("duration", "")), "seqi": i,
                                      "time": str(s.get("time", "")), "trange": trng(s), "fix": bool(s.get("fixed")),
                                      "mode": mode, "color": (tr or s).get("color") or "#9aa0a6"})
                continue
            # segmento REAL (participa del paso-a-paso y la selección)
            segN += 1
            coords = [[float(a), float(b)] for a, b in
                      (t.split(",") for t in str(coords_src).split())]
            off = bool(s.get("solo_seleccion") or (tr and tr.get("solo_seleccion")))
            color = (tr or s).get("color") or "#7a6f63"
            if tr and tr.get("estaciones"):
                ab = f"{tr['estaciones'][0][2]} → {tr['estaciones'][-1][2]}"
            else:
                ab = re.sub(r"^[^\w]+", "", s.get("title", "")).strip()
            if not off:
                travelMin += dur
            seg = {"name": f"d{idx + 1}·{segN} {EMOJI.get(mode,'•')} {ab}", "seqi": i,
                   "color": color, "mode": mode, "coords": coords, "off": off,
                   "fix": bool(s.get("fixed")),
                   "dur": dur, "durTxt": "~" + str(s.get("duration", "")), "trange": trng(s)}
            if tr and tr.get("nombre_jp"):   # tren → popup rico (guía de línea + ride + horario)
                ident = {"nombre": tr.get("linea", s["transit"]), "nombre_jp": tr["nombre_jp"],
                         "chip": tr.get("chip", ""), "color": color, "reconoce": tr.get("reconoce", ""),
                         **line_meta(tr)}
                ride = {kk: tr[kk] for kk in ("anden", "reverso", "estaciones", "vehiculo") if kk in tr}
                horario = {"origen": tr["estaciones"][0][2], "destino": tr["estaciones"][-1][2],
                           "desde": str(s.get("time", "")), "hasta": add_min(s.get("time"), dur)}
                seg["pop"] = render_line_modal(s["transit"], ident, ride, tr.get("guia"), horario)
            segments.append(seg)
        elif "options" in s and any("steps" in o for o in s.get("options", [])):
            # planes en paralelo → grupo SELECCIONABLE (como comidas): elige tu plan
            popts = []
            for plan in s["options"]:
                elems = []   # geometría del plan (líneas y puntos)
                for ss in plan.get("steps", []):
                    if "transit" in ss:
                        tr = TRANSITS.get(ss["transit"])
                        if tr and tr.get("coords"):
                            coords = [[float(a), float(b)] for a, b in
                                      (t.split(",") for t in str(tr["coords"]).split())]
                            e = {"line": coords, "color": tr.get("color", "#7a6f63"), "mode": tr.get("mode", "walk"),
                                 "name": re.sub(r"@\[(.+?)\]\(.+?\)", r"\1", str(ss.get("title", "")))}
                            if tr.get("nombre_jp"):
                                ident = {"nombre": tr.get("linea", ss["transit"]), "nombre_jp": tr["nombre_jp"],
                                         "chip": tr.get("chip", ""), "color": tr.get("color", "#555"),
                                         "reconoce": tr.get("reconoce", ""), **line_meta(tr)}
                                ride = {kk: tr[kk] for kk in ("anden", "reverso", "estaciones", "vehiculo") if kk in tr}
                                e["pop"] = render_line_modal(ss["transit"], ident, ride, tr.get("guia"))
                            elems.append(e)
                    elif "location" in ss:
                        pl = PLACES.get(ss["location"], {})
                        if pl.get("gps"):
                            la, lo = latlng(pl["gps"])
                            elems.append({"pt": [la, lo], "color": "#b23a2a", "name": pl["nombre"],
                                          "pop": render_place_modal(ss["location"], pl, HOST, APP_URL)})
                popts.append({"name": plan.get("title", ""), "elems": elems})
            meals.append({"plan": True, "seqi": i, "time": str(s.get("time", "")), "trange": trng(s), "fix": bool(s.get("fixed")), "options": popts})
            continue
        elif "options" in s:
            # opt-in: ida (del punto anterior) y regreso (al SIGUIENTE punto), rutas reales OSRM
            ruta = bool(s.get("retorno"))
            desde = last_loc_gps if ruta else None                 # de dónde vienes
            hacia = next_point_after(steps, i) if ruta else None   # a dónde sigues (siguiente lugar/tramo)
            opts = []
            for tier in s["options"]:
                for o in tier.get("options", []):
                    pl = PLACES.get(o["location"], {})
                    opt = {"name": pl.get("nombre", o["location"]), "tier": tier.get("title", ""),
                           "key": o["location"], "price": o.get("precio", ""),
                           "desc": pl.get("descripcion", ""),
                           "foto": foto(pl), "maps": pl.get("maps", ""),
                           "pop": render_place_modal(o["location"], pl, HOST, APP_URL)}
                    if pl.get("gps"):                                     # con ancla → marcador + rutas OSRM
                        la, lo = latlng(pl["gps"])
                        opt["lat"], opt["lng"] = la, lo
                        if desde:
                            opt["ida"] = osrm_walk_clean(desde, pl["gps"])   # de dónde vienes → resto
                        if hacia:
                            opt["reg"] = osrm_walk_clean(pl["gps"], hacia)    # resto → siguiente punto
                    else:                                                # genérica sin lugar fijo → solo fila de panel
                        opt["nogeo"] = True
                    opts.append(opt)
            meals.append({"seqi": i, "time": str(s.get("time", "")), "trange": trng(s), "fix": bool(s.get("fixed")), "opts": opts})
    # marcador del hotel donde se DUERME esa noche (aunque no sea un paso explícito del día)
    hk = HOTEL_BY_DAY.get(idx)
    if hk and not any(p.get("kind") == "hotel" for p in places):
        hp = PLACES.get(hk, {})
        if hp.get("gps"):
            hla, hlo = latlng(hp["gps"])
            places.append({"name": f"🏨 {hp['nombre']}", "kind": "hotel", "lat": hla, "lng": hlo, "seqi": 9990,
                           "tier": "", "time": "", "trange": "",
                           "desc": hp.get("descripcion", ""), "hist": hp.get("informacion", ""),
                           "foto": foto(hp), "maps": hp.get("maps", ""),
                           "pop": render_place_modal(hk, hp, HOST, APP_URL)})
    # TIEMPOS MUERTOS: hueco ≥20 min que sigue a una ACTIVIDAD REAL terminada (lugar/comida con
    # duración) y antes de la próxima hora agendada. Los tránsitos sin duración explícita infieren
    # su duración del próximo paso con hora (para no contar el viaje como tiempo libre).
    gaps = []
    cursor = None; cur_seqi = None; cur_real = False
    for gi, gs in enumerate(steps):
        gt = hm2min(gs.get("time")); gdu = dmin(gs.get("duration"))
        is_real = ("location" in gs) or ("options" in gs) or ("transit" in gs)  # paso real (no una nota suelta)
        is_plan = "options" in gs and any(isinstance(o, dict) and "steps" in o for o in gs.get("options", []))
        if gt is not None:
            if cursor is not None and cur_real and gt - cursor >= 20:
                gaps.append({"seqi": cur_seqi + 0.5, "mins": gt - cursor,
                             "desde": f"{cursor // 60 % 24:02d}:{cursor % 60:02d}",
                             "hasta": f"{gt // 60 % 24:02d}:{gt % 60:02d}"})
            if gdu == 0 and ("transit" in gs or is_plan):  # tránsito / fork de planes → llenar hasta el próximo paso con hora
                for j in range(gi + 1, len(steps)):
                    nt = hm2min(steps[j].get("time"))
                    if nt is not None:
                        if nt > gt:
                            gdu = nt - gt
                        break
            cursor = gt + gdu; cur_seqi = gi; cur_real = is_real
        elif cursor is not None:
            cursor += gdu; cur_seqi = gi
            if is_real:
                cur_real = True
    # largo del día: del primer paso al último (no el commute time)
    if startTime and end_max is not None:
        endStr = f"{end_max // 60 % 24:02d}:{end_max % 60:02d}"
        travelTxt = f"{startTime}–{endStr}"
    else:
        travelTxt = ""
    return {"key": f"d{idx}", "label": str(day.get("titulo", f"día {idx}")),
            "places": places, "segments": segments, "meals": meals, "infoTransits": info_transits,
            "gaps": gaps, "travelMin": travelMin, "travelTxt": travelTxt.strip(), "startTime": startTime}

new_days = [build_day(d, i) for i, d in enumerate(Y["days"])]
osrm_save()   # persistir caché de rutas a pie

# el mapa es SOLO el generado desde viaje.yaml (reemplaza los días viejos)
json.dump({"days": new_days, "fixed": []}, open(SD + "/viaje-data.json", "w", encoding="utf-8"), ensure_ascii=False)
new_day = new_days[0]
print(f"{len(new_days)} días · dom4: {len(new_day['places'])} lugares · {len(new_day['segments'])} trayectos · "
      f"{sum(len(m['opts']) for m in new_day['meals'])} opciones de comida · viaje {new_day['travelTxt']}")
r = subprocess.run([sys.executable, SD + "/build_leaflet.py"], capture_output=True, text=True, encoding="utf-8")
print(r.stdout.strip() or r.stderr.strip())
