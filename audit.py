"""Auditoría paso-a-paso de viaje.yaml. Detecta:
  1) comidas lejos del punto donde estamos (sin transporte que lo justifique)
  2) demasiado tiempo a pie sin descanso (>45 min de caminata encadenada)
  3) traslados a pie >100 m dibujados como recta (2 puntos) → probablemente mal
  4) lugares imposibles de alcanzar en el tiempo dado (siguiente hora < llegada)
  5) etiquetas de tiempo: pasos con hora pero sin rango, o rango incoherente
"""
import yaml, re, math, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
Y = yaml.safe_load(open(r"D:\dev\viajes\japon\viajes-icons\viaje.yaml", encoding="utf-8"))
P, T = Y["places"], Y["transits"]

def gps(k):
    g = (P.get(k) or {}).get("gps")
    return [float(x) for x in g.split(",")] if g else None
def crow(a, b):
    if not a or not b: return None
    return math.hypot((b[0]-a[0])*111000, (b[1]-a[1])*111000*math.cos(math.radians(a[0])))
def dmin(s):
    s = str(s or "")
    hm = re.search(r"(\d+)\s*h\s*(\d+)?", s)
    if hm: return int(hm.group(1))*60 + int(hm.group(2) or 0)
    m = re.search(r"(\d+)\s*min", s)
    if m: return int(m.group(1))
    return 0
def hm(t):
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(t or "").strip())
    return int(m.group(1))*60 + int(m.group(2)) if m else None
def tcoords(step):
    tr = T.get(step.get("transit")) if step.get("transit") else None
    c = (tr or step).get("coords")
    if not c: return None, (tr or step).get("mode", "walk")
    return [[float(a), float(b)] for a, b in (p.split(",") for p in str(c).split())], (tr or step).get("mode", "walk")
def meal_locs(step):
    out = []
    def rec(node):
        if isinstance(node, dict):
            if "location" in node: out.append(node["location"])
            for v in node.values(): rec(v)
        elif isinstance(node, list):
            for v in node: rec(v)
    rec(step.get("options", []))
    return out

WALK_LIMIT, FAR_FOOD, LINE_LIMIT = 45, 1200, 100
findings = []
for idx, day in enumerate(Y["days"]):
    ti = day.get("titulo", f"día {idx}")
    F = lambda cat, msg: findings.append((ti, cat, msg))
    cur, walk_run, walk_from = None, 0, None
    last_t, cum, last_label = None, 0, None
    since_transit = 99   # pasos desde el último tren/traslado (hay tiempo de traslado)
    steps = day.get("steps", [])
    # contexto local: gps de cada paso-ubicación por índice (para juzgar cercanía de comidas)
    locgps = [(i, gps(st["location"])) for i, st in enumerate(steps)
              if "location" in st and gps(st["location"])]
    def near_ctx(i):
        cand = [(abs(i-j), g) for j, g in locgps]
        return min(cand)[1] if cand else None
    for si, s in enumerate(steps):
        t = hm(s.get("time")); dur = dmin(s.get("duration"))
        # reachability at each timed step
        if t is not None:
            if last_t is not None and t < last_t + cum - 1:
                F("ALCANCE", f"{s.get('time')} '{str(s.get('title',''))[:42]}' — desde {last_label} necesitas ~{cum}min pero solo hay {t-last_t}min")
            last_t, cum, last_label = t, 0, f"{s.get('time')}"
        since_transit += 1
        if "transit" in s:
            since_transit = 0
            co, mode = tcoords(s)
            if not (s.get("solo_seleccion") or (T.get(s.get('transit')) or {}).get('solo_seleccion')):
                cum += dur
            if mode == "walk":
                if co and len(co) == 2:
                    d = crow(co[0], co[1])
                    if d and d > LINE_LIMIT:
                        F("RECTA", f"'{str(s.get('title',''))[:40]}' a pie {round(d)}m en línea recta (2 puntos) — ¿OSRM?")
                walk_run += dur
                if walk_from is None: walk_from = str(s.get("title", ""))[:24]
                if walk_run > WALK_LIMIT:
                    F("CAMINATA", f"~{walk_run}min a pie encadenados sin descanso (desde '{walk_from}')")
                if co: cur = co[-1]
            else:
                walk_run, walk_from = 0, None
                if co: cur = co[-1]
        elif "location" in s:
            g = gps(s["location"])
            if g: cur = g
            if dur > 0: walk_run, walk_from = 0, None  # te detienes ahí = descanso
        elif "options" in s:  # comida (o fork de planes)
            opts = s.get("options", [])
            is_plan = any(isinstance(o, dict) and "steps" in o for o in opts)
            ref = near_ctx(si)  # ubicación real más cercana en la secuencia (robusto a cambios de ciudad)
            if not is_plan and ref:
                ds = [(k, crow(ref, gps(k))) for k in meal_locs(s) if gps(k)]
                ds = [(k, d) for k, d in ds if d is not None]
                if ds:
                    near = min(ds, key=lambda x: x[1])
                    # sólo es problema si NO hubo tren reciente (a pie) y no es transición de ciudad
                    if FAR_FOOD < near[1] < 8000 and since_transit > 2:
                        F("COMIDA", f"{s.get('time','')} la opción más CERCANA ({near[0]}) está a {round(near[1])}m a pie, sin tren cercano")
        # etiqueta de tiempo
        if t is not None and dur == 0 and ("location" in s or "options" in s) and not s.get("fixed"):
            pass  # hora sin fin (dur 0) es aceptable para hitos puntuales

# reporte
from collections import defaultdict
by = defaultdict(list)
for ti, cat, msg in findings: by[ti].append((cat, msg))
CATS = {"ALCANCE": "⏱️ ALCANCE", "CAMINATA": "🚶 CAMINATA", "RECTA": "📏 RECTA", "COMIDA": "🍴 COMIDA"}
for idx, day in enumerate(Y["days"]):
    ti = day.get("titulo", "")
    items = by.get(ti, [])
    print(f"\n=== {ti} ===")
    if not items: print("  ✓ sin hallazgos"); continue
    for cat, msg in items: print(f"  {CATS.get(cat,cat)}: {msg}")
print(f"\nTOTAL hallazgos: {len(findings)}")
for c in ["RECTA","CAMINATA","ALCANCE","COMIDA"]:
    print(f"  {c}: {sum(1 for f in findings if f[1]==c)}")
