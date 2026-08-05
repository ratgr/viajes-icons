# -*- coding: utf-8 -*-
"""convert_days.py — traduce japon-fuente.yaml (viejo) → schema nuevo para
TODOS los días, preservando el dom 4 hecho a mano. Enriquece trenes con la
identidad/ride de los diccionarios TR/RD de la app. Reconstruye el orden de
pasos igual que build_leaflet (segmentos d·N + paradas por cercanía + comidas
por hora + hoteles/aeropuertos por conexión). Escribe viaje.yaml y un reporte
de diferencias en DIFERENCIAS.md."""
import os, re, sys, json, math, unicodedata
import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
OLD = yaml.safe_load(open(SD + "/japon-fuente.yaml", encoding="utf-8"))
CUR = yaml.safe_load(open(SD + "/viaje.yaml", encoding="utf-8"))   # tiene dom 4 a mano
APP = open(os.path.abspath(SD + "/../viajes/src/japon.html"), encoding="utf-8").read()
HOST = "https://raw.githubusercontent.com/ratgr/viajes-icons/main/"

# ---- diccionarios de la app ----
def _bal(b, i, op, cl):
    d = 0; j = i; s = False; e = False; q = ""
    while j < len(b):
        c = b[j]
        if s:
            if e: e = False
            elif c == "\\": e = True
            elif c == q: s = False
        else:
            if c in "\"'": s = True; q = c
            elif c == op: d += 1
            elif c == cl:
                d -= 1
                if d == 0: return b[i:j + 1]
        j += 1
def grab(name):
    m = re.search(r"\b" + name + r"\s*=\s*\{", APP)
    return json.loads(_bal(APP, m.end() - 1, "{", "}"))
TR = grab("TR"); RD = grab("RD"); RESTOS = grab("RESTOS"); QUIEN = grab("QUIEN")
PAIRS = re.findall(r'data-tl="([^"]+)"\s+data-ride="([^"]+)"', APP)  # (line, ride)
LINE2RIDES = {}
for ln, rd in PAIRS:
    LINE2RIDES.setdefault(ln, []).append(rd)
TR_BY_NAME = {v[0]: k for k, v in TR.items()}
report = []

# ---- helpers ----
def norm(name):
    s = re.sub(r"^[\s⭐🍜🏨✈️📍·⛴️🚇🚶🚝🧳🦁🧿★🏴🔘☕🍴🍧]+", "", str(name))
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)   # quitar anotaciones entre paréntesis
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"\d\d:\d\d\s*·?\s*", "", s)
    return s.strip().lower()
def clean_name(name):
    s = re.sub(r"^[\s⭐🍜🏨✈️📍·]+", "", str(name))
    s = re.sub(r"\s*\(d\d+\)\s*$", "", s)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"\d\d:\d\d\s*·?\s*", "", s)
    return s.strip()
def slug(name):
    s = clean_name(name).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"
def maps_of(coord):
    return "https://www.google.com/maps/search/?api=1&query=" + coord
def dist(a, b):  # metros aprox (equirectangular)
    la1, lo1 = a; la2, lo2 = b
    x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    y = math.radians(la2 - la1)
    return math.hypot(x, y) * 6371000
def ll(coord):
    a, b = coord.split(","); return (float(a), float(b))
def _stoptime(name):
    m = re.search(r"(\d\d:\d\d)", name); return m.group(1) if m else ""
def day_meta(date_iso):
    m = re.search(r'data-fecha="' + date_iso + r'".*?<span class="theme">(.*?)</span><span class="anchor-tag">Ancla:\s*(.*?)</span>', APP, re.S)
    return (re.sub(r"<[^>]+>", "", m.group(1)), re.sub(r"<[^>]+>", "", m.group(2))) if m else ("", "")

# ---- catálogos existentes (dom 4) ----
places = CUR["places"]; lineas = CUR["lineas"]; transits = CUR["transits"]; days = CUR["days"]
name2key = {norm(v["nombre"]): k for k, v in places.items()}

def ensure_place(name, coord, kind, desc="", hist="", foto="", key_extra=None):
    n = norm(name)
    if n in name2key:
        return name2key[n]
    key = slug(name)
    while key in places:
        key += "-x"
    entry = {"nombre": clean_name(name), "gps": coord, "maps": maps_of(coord)}
    if foto:
        entry["imagen"] = foto
    if desc:
        entry["descripcion"] = desc
    if hist:
        entry["informacion"] = hist
    places[key] = entry
    name2key[n] = key
    return key

def ensure_linea(line_name):
    """clave de línea en lineas: (identidad TR)."""
    trk = TR_BY_NAME.get(line_name) or next((k for k, v in TR.items() if v[0] == line_name), None)
    if not trk:
        return None
    key = slug(line_name)
    if key not in lineas:
        nombre, jp, chip, color, reconoce, extra = TR[trk]
        lineas[key] = {"nombre": nombre, "nombre_jp": jp, "chip": chip, "color": color,
                       "reconoce": reconoce}
    return trk  # devuelve la clave TR para buscar rides

def match_ride(trk, frm, to):
    """entre los rides de la línea, el que empieza en frm y termina en to (romaji)."""
    for rd in LINE2RIDES.get(trk, []):
        s = RD.get(rd, {}).get("s", [])
        if s and s[0][2] == frm and s[-1][2] == to:
            return RD[rd]
    return None

SEGRE = re.compile(r"^d\d+·\d+\s+(\S+)\s+(?:(\d\d:\d\d)\s+)?(.*)$")
def parse_seg(name):
    m = SEGRE.match(name)
    emoji, time, rest = (m.group(1), m.group(2), m.group(3)) if m else ("", None, name)
    if ":" in rest:
        line_part, route = rest.split(":", 1)
    else:
        line_part, route = "", rest
    route = route.split("⇒")[0].strip()
    frm = to = None
    if "→" in route:
        frm, to = [x.strip() for x in route.split("→", 1)]
    return emoji, time, line_part.strip(), frm, to

def resto_place(name, coord):
    n = norm(name)
    if n in name2key:
        return name2key[n]
    # buscar en RESTOS por nombre para foto/desc
    rk = next((k for k, v in RESTOS.items() if norm(v[0]) == n), None)
    desc = RESTOS[rk][2] if rk else ""
    hist = ("Recomendado por: " + QUIEN.get(RESTOS[rk][3], RESTOS[rk][3])) if rk else ""
    foto = ("fachadas/" + rk + ".jpg") if rk else ""
    return ensure_place(name, coord, "resto", desc, hist, foto)

# ---- convertir cada día viejo (saltando dom 4 = índice 0) ----
NEW_KEYS = ["mié", "mar", "vie", "sáb", "dom", "lun", "jue"]  # solo para slug de día
converted = 0
for di in range(1, len(OLD["days"])):
    od = OLD["days"][di]
    daynum = di + 4  # dom4=día 4; label ya trae el nombre
    dkey = od["key"]
    # --- catálogo de lugares del día ---
    stopinfo = {}   # order -> {key,time,coord,ll}
    site_by_norm = {}
    for p in od.get("places", []):
        if p["kind"] == "site":
            site_by_norm[norm(p["name"])] = p
    hotels = []; restos_sueltos = []
    for p in od.get("places", []):
        k = p["kind"]; coord = p["coord"]
        if k == "stop":
            site = site_by_norm.get(norm(p["name"]))
            key = ensure_place(p["name"], coord, "stop",
                               desc=(site or {}).get("desc", ""), hist=(site or {}).get("hist", ""),
                               foto=(site or {}).get("foto", ""))
            stopinfo[p.get("order", 0)] = {"key": key, "time": str(p.get("time") or _stoptime(p["name"])),
                                           "coord": coord, "ll": ll(coord), "fix": bool(p.get("fixTime"))}
        elif k in ("hotel", "aero"):
            key = ensure_place(p["name"], coord, k)
            hotels.append({"key": key, "time": str(p.get("time", "")), "coord": coord, "ll": ll(coord), "kind": k})
        elif k == "resto":
            resto_place(p["name"], coord)   # al catálogo; se usan en meals
        # site: ya absorbido en stop
    # --- transits del día ---
    segitems = []
    for s in od.get("segments", []):
        emoji, time, line_part, frm, to = parse_seg(s["name"])
        m = re.search(r"·(\d+)", s["name"]); ordn = int(m.group(1)) if m else 999
        tkey = f"d{daynum}-{ordn}"
        tr = {"mode": s["mode"], "color": s["color"], "coords": s["coords"]}
        if s["mode"] in ("train", "ferry") and line_part:
            trk = ensure_linea(line_part)
            if trk:
                nombre, jp, chip, color, reconoce, extra = TR[trk]
                tr["linea"] = nombre; tr["nombre_jp"] = jp; tr["chip"] = chip
                tr["reconoce"] = reconoce
                ride = match_ride(trk, frm, to)
                if ride:
                    tr["anden"] = ride.get("d", ["", ""])
                    tr["reverso"] = ride.get("w", "")
                    if ride.get("v"):
                        tr["vehiculo"] = ride["v"]
                    tr["estaciones"] = ride.get("s", [])
                else:
                    report.append(f"{dkey}: sin ride para «{line_part}: {frm}→{to}» (modal solo identidad)")
        transits[tkey] = tr
        cds = [ll(c) for c in s["coords"].split()]
        segitems.append({"tkey": tkey, "ord": ordn, "time": str(time or ""), "mode": s["mode"],
                         "frm": frm, "to": to, "line": line_part, "emoji": emoji,
                         "coords": cds, "start": cds[0], "end": cds[-1]})
    segitems.sort(key=lambda x: x["ord"])
    # --- meals ---
    meals = []
    for me in od.get("meals", []):
        opts = []
        for o in me.get("opts", []):
            pk = resto_place(o["name"], o["coord"])
            opts.append({"tier": o.get("tier", ""), "location": pk, "precio": o.get("price", "")})
        meals.append({"time": str(me["time"]), "ll": None, "opts": opts})
    # --- reconstruir orden (build_leaflet) ---
    stops = [dict(v, order=o) for o, v in sorted(stopinfo.items())]
    for st in stops:
        best, bd = None, 1e18
        for sg in segitems:
            dd = dist(st["ll"], sg["end"])
            if dd < bd: bd, best = dd, sg["tkey"]
        st["arr"] = best
    arrmap = {}
    for st in stops:
        arrmap.setdefault(st["arr"], []).append(st)
    farS, beforeSeg, afterSeg = [], {}, {}
    for h in hotels:
        bI, bD, side = None, 1e18, "start"
        for sg in segitems:
            da = dist(h["ll"], sg["start"]); db = dist(h["ll"], sg["end"])
            if da < bD: bD, bI, side = da, sg["tkey"], "start"
            if db < bD: bD, bI, side = db, sg["tkey"], "end"
        if bI is None or bD > 30000:
            farS.append(h)
        elif side == "start":
            beforeSeg.setdefault(bI, []).append(h)
        else:
            afterSeg.setdefault(bI, []).append(h)
    seq = []
    for h in farS:
        seq.append(("loc", h))
    added = set()
    for sg in segitems:
        for h in beforeSeg.get(sg["tkey"], []):
            seq.append(("loc", h))
        seq.append(("seg", sg))
        for st in arrmap.get(sg["tkey"], []):
            seq.append(("stop", st)); added.add(st["order"])
        for h in afterSeg.get(sg["tkey"], []):
            seq.append(("loc", h))
    for st in stops:
        if st["order"] not in added:
            seq.append(("stop", st))
    # comidas por hora
    for me in meals:
        pos = len(seq)
        for pi in range(len(seq) - 1, -1, -1):
            kind, it = seq[pi]
            t = it.get("time", "")
            if kind in ("stop",) and re.match(r"^\d\d:\d\d$", t or "") and t <= me["time"]:
                pos = pi + 1; break
        seq.insert(pos, ("meal", me))
    # --- emitir steps ---
    steps = []
    for kind, it in seq:
        if kind == "seg":
            title = (f"{it['emoji']} {it['line']}: @[{it['frm']} → {it['to']}]({it['tkey']})"
                     if it["mode"] in ("train", "ferry") and it["frm"]
                     else f"{it['emoji']} " + (f"{it['frm']} → {it['to']}" if it["frm"] else it["line"] or "traslado"))
            st = {"transit": it["tkey"], "title": title}
            if it["time"]:
                st["time"] = it["time"]
            steps.append(st)
        elif kind == "stop":
            st = {"location": it["key"], "time": it["time"],
                  "title": f"@[{places[it['key']]['nombre']}]({it['key']}) ★"}
            if it.get("fix"):
                st["fixed"] = True
            steps.append(st)
        elif kind == "loc":
            emo = "✈️" if it["kind"] == "aero" else "🏨"
            st = {"location": it["key"], "title": f"{emo} @[{places[it['key']]['nombre']}]({it['key']})"}
            if it["time"]:
                st["time"] = it["time"]; st["fixed"] = True
            steps.append(st)
        elif kind == "meal":
            tiers = {}
            for o in it["opts"]:
                tiers.setdefault(o["tier"], []).append({"location": o["location"], "precio": o["precio"]})
            options = [{"title": t, "options": v} for t, v in tiers.items()]
            steps.append({"time": it["time"], "title": "Comida", "options": options})
    date_iso = f"2026-10-{4 + di:02d}"
    note, ancla = day_meta(date_iso)
    days.append({"titulo": od["label"], "note": note, "ancla": ancla, "date": date_iso, "steps": steps})
    converted += 1

CUR["days"] = days
yaml.dump(CUR, open(SD + "/viaje.yaml", "w", encoding="utf-8"), allow_unicode=True,
          sort_keys=False, default_flow_style=None, width=100000)
print("convertidos:", converted, "días · places:", len(places), "· lineas:", len(lineas), "· transits:", len(transits))
open(SD + "/DIFERENCIAS.md", "w", encoding="utf-8").write(
    "# Diferencias nuevo vs viejo\n\n" + "\n".join("- " + r for r in report) if report else
    "# Diferencias\n\n(sin notas)")
print("reporte:", len(report), "notas -> DIFERENCIAS.md")
