# -*- coding: utf-8 -*-
"""convert_rich.py — traduce el ITINERARIO rico de japon.html (la historia:
notas, duraciones, avisos, forks de comida completos, refs a lugares/líneas)
al schema nuevo, adjuntando geometría de japon-fuente.yaml. Preserva dom 4.
Escribe viaje.yaml + DIFERENCIAS.md."""
import os, re, sys, json, html as _html, unicodedata, math
import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
OLD = yaml.safe_load(open(SD + "/japon-fuente.yaml", encoding="utf-8"))
CUR = yaml.safe_load(open(SD + "/viaje.yaml", encoding="utf-8"))
APP = open(os.path.abspath(SD + "/../viajes/src/japon.html"), encoding="utf-8").read()

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
def grab(n):
    m = re.search(r"\b" + n + r"\s*=\s*\{", APP)
    return json.loads(_bal(APP, m.end() - 1, "{", "}"))
TR = grab("TR"); RD = grab("RD"); LG = grab("LG"); RESTOS = grab("RESTOS"); QUIEN = grab("QUIEN")
TR_BY_NAME = {v[0]: k for k, v in TR.items()}
PAIRS = re.findall(r'data-tl="([^"]+)"\s+data-ride="([^"]+)"', APP)
LINE2RIDES = {}
for ln, rd in PAIRS:
    LINE2RIDES.setdefault(ln, []).append(rd)
report = []

# ---------- coords desde fuente ----------
fu_place = {}   # norm-name -> coord (todos los lugares fuente)
fu_resto = {}   # key -> coord
def normn(name):
    s = re.sub(r"^[\s⭐🍜🏨✈️📍·⛴️🚇🚶🚝🧳🦁🧿★🏴🔘☕🍴🍧]+", "", str(name))
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"\d\d:\d\d\s*·?\s*", "", s)
    return s.strip().lower()
for d in OLD["days"]:
    for p in d.get("places", []):
        fu_place[normn(p["name"])] = p["coord"]
        if p.get("key"):
            fu_resto[p["key"]] = p["coord"]
    for me in d.get("meals", []):
        for o in me.get("opts", []):
            if o.get("key"):
                fu_resto[o["key"]] = o["coord"]

# ---------- catálogo (parte del dom 4 a mano) ----------
places = CUR["places"]; lineas = CUR["lineas"]; transits = CUR["transits"]; days = CUR["days"]
name2key = {normn(v["nombre"]): k for k, v in places.items()}
def clean_name(name):
    s = re.sub(r"^[\s⭐🍜🏨✈️📍·]+", "", str(name))
    return re.sub(r"\s+", " ", s).strip()
def slug(name):
    s = clean_name(name).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"
def maps_of(coord):
    return "https://www.google.com/maps/search/?api=1&query=" + coord if coord else ""
def dist(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return math.hypot(x, y) * 6371000

def place_from_lg(lgkey):
    """data-lg -> clave en places (identidad LG + coord fuente)."""
    d = LG.get(lgkey)
    if not d:
        return None
    nombre = d[0]; n = normn(nombre)
    if n in name2key:
        return name2key[n]
    coord = fu_place.get(n, "")
    desc = re.sub(r"<[^>]+>", "", d[1]) if len(d) > 1 else ""
    hist = re.sub(r"<[^>]+>", "", d[2]) if len(d) > 2 else ""
    key = slug(nombre)
    while key in places:
        key += "-x"
    e = {"nombre": nombre, "gps": coord, "maps": maps_of(coord)}
    if desc: e["descripcion"] = desc.strip()
    if hist: e["informacion"] = hist.strip()
    places[key] = e; name2key[n] = key
    return key

def place_from_resto(rk):
    r = RESTOS.get(rk)
    if not r:
        return None
    nombre = r[0]; n = normn(nombre)
    if n in name2key:
        return name2key[n]
    coord = fu_resto.get(rk, "")
    key = slug(nombre)
    while key in places:
        key += "-x"
    e = {"nombre": nombre, "gps": coord, "maps": maps_of(coord)}
    if len(r) > 2 and r[2]: e["descripcion"] = r[2]
    if len(r) > 3 and r[3]: e["informacion"] = "Recomendado por: " + QUIEN.get(r[3], r[3])
    e["imagen"] = "fachadas/" + rk + ".jpg"
    places[key] = e; name2key[n] = key
    return key

def ensure_generic_place(nombre, coord=""):
    n = normn(nombre)
    if n in name2key:
        return name2key[n]
    key = slug(nombre)
    while key in places:
        key += "-x"
    places[key] = {"nombre": clean_name(nombre), "gps": coord, "maps": maps_of(coord)}
    name2key[n] = key
    return key

# ---------- líneas / rides ----------
def ensure_linea(line_name):
    trk = TR_BY_NAME.get(line_name) or next((k for k, v in TR.items() if v[0] == line_name), None)
    if not trk:
        return None
    key = slug(line_name)
    if key not in lineas:
        nombre, jp, chip, color, reconoce, extra = TR[trk]
        lineas[key] = {"nombre": nombre, "nombre_jp": jp, "chip": chip, "color": color, "reconoce": reconoce}
    return trk

# ---------- geometría por día (fuente) ----------
SEGRE = re.compile(r"^d\d+·\d+\s+(\S+)\s+(?:(\d\d:\d\d)\s+)?(.*)$")
def parse_seg(name):
    m = SEGRE.match(name)
    emoji, time, rest = (m.group(1), m.group(2), m.group(3)) if m else ("", None, name)
    line_part, route = (rest.split(":", 1) if ":" in rest else ("", rest))
    route = route.split("⇒")[0].strip()
    frm = to = None
    if "→" in route:
        frm, to = [x.strip() for x in route.split("→", 1)]
    return emoji.strip(), (time or ""), line_part.strip(), frm, to

# ---------- html -> markdown + @[alt](key) ----------
def strip_tags(s):
    return _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
def to_md(frag, tref):
    s = frag
    s = re.sub(r'<(?:b|span) class="pl"[^>]*data-lg="([^"]+)"[^>]*>(.*?)</(?:b|span)>',
               lambda m: (lambda k: f'@[{strip_tags(m.group(2))}]({k})' if k else strip_tags(m.group(2)))(place_from_lg(m.group(1))), s)
    s = re.sub(r'<a class="rl2"[^>]*data-k="([^"]+)"[^>]*>(.*?)</a>',
               lambda m: (lambda k: f'@[{strip_tags(m.group(2))}]({k})' if k else strip_tags(m.group(2)))(place_from_resto(m.group(1))), s)
    s = re.sub(r'<span class="tl"[^>]*data-tl="([^"]+)"[^>]*data-ride="([^"]+)"[^>]*>(.*?)</span>',
               lambda m: f'@[{strip_tags(re.sub(r"<i[^>]*>.*?</i>", "", m.group(3)))}]({tref(m.group(1), m.group(2))})', s)
    s = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", s, flags=re.S)
    s = re.sub(r"<i[^>]*>.*?</i>", "", s, flags=re.S)
    s = re.sub(r'<span class="d">(.*?)</span>', r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", _html.unescape(s)).strip()

# ---------- parse forks de comida ----------
def parse_fork(frag):
    tiers = []
    for tm in re.finditer(r'<span class="f\d"><b>([^<]+)</b>(.*?)</span>', frag, re.S):
        tier = tm.group(1).strip(); inner = tm.group(2)
        opts = []
        for am in re.finditer(r'<a class="rl2"[^>]*data-k="([^"]+)"[^>]*>(.*?)</a>\s*([^·<]*)', inner):
            pk = place_from_resto(am.group(1))
            precio = am.group(3).strip(" ·")
            opts.append({"location": pk, "precio": precio})
        if opts:
            tiers.append({"title": tier, "options": opts})
    return tiers

# ---------- por día ----------
def day_block(date_iso):
    m = re.search(r'<div class="day" data-fecha="' + date_iso + r'">(.*?)(?=<div class="day"|</section>)', APP, re.S)
    return m.group(1) if m else ""

converted = 0
for di in range(1, len(OLD["days"])):
    od = OLD["days"][di]
    date_iso = f"2026-10-{4 + di:02d}"
    block = day_block(date_iso)
    hm = re.search(r"<h3>(.*?)</h3>.*?theme\">(.*?)</span>.*?anchor-tag\">(?:Ancla:\s*)?(.*?)</span>", block, re.S)
    titulo = strip_tags(hm.group(1)) if hm else od["label"]
    note_d = strip_tags(hm.group(2)) if hm else ""
    ancla = strip_tags(hm.group(3)) if hm else ""

    # segmentos fuente del día (geometría)
    fsegs = []
    for s in od.get("segments", []):
        emoji, time, lp, frm, to = parse_seg(s["name"])
        fsegs.append({"emoji": emoji, "line": lp, "frm": frm, "to": to, "mode": s["mode"],
                      "color": s["color"], "coords": s["coords"], "used": False,
                      "ord": int(re.search(r"·(\d+)", s["name"]).group(1))})
    fsegs.sort(key=lambda x: x["ord"])
    daynum = di + 4
    seg_ctr = [0]
    def new_transit(fseg, dataride=None):
        seg_ctr[0] += 1
        tk = f"d{daynum}-{seg_ctr[0]}"
        tr = {"mode": fseg["mode"], "color": fseg["color"], "coords": fseg["coords"]}
        if fseg["mode"] in ("train", "ferry") and fseg["line"]:
            trk = ensure_linea(fseg["line"])
            if trk:
                nombre, jp, chip, color, reconoce, extra = TR[trk]
                tr.update({"linea": nombre, "nombre_jp": jp, "chip": chip, "reconoce": reconoce})
                rd = RD.get(dataride) if dataride else None
                if not rd:  # buscar por endpoints
                    for r in LINE2RIDES.get(trk, []):
                        ss = RD.get(r, {}).get("s", [])
                        if ss and ss[0][2] == fseg["frm"] and ss[-1][2] == fseg["to"]:
                            rd = RD[r]; break
                if rd:
                    tr["anden"] = rd.get("d", ["", ""]); tr["reverso"] = rd.get("w", "")
                    if rd.get("v"): tr["vehiculo"] = rd["v"]
                    tr["estaciones"] = rd.get("s", [])
        transits[tk] = tr
        return tk
    def tref(line_tl, ride):
        # busca un fseg sin usar de esa línea (por endpoints via ride) y lo enlaza
        rd = RD.get(ride, {}); ss = rd.get("s", [])
        frm = ss[0][2] if ss else None; to = ss[-1][2] if ss else None
        trk = TR_BY_NAME.get(TR.get(line_tl, [None])[0]) or line_tl
        for fs in fsegs:
            if fs["used"]: continue
            if fs["mode"] in ("train", "ferry") and (fs["frm"] == frm and fs["to"] == to):
                fs["used"] = True
                return new_transit(fs, ride)
        # sin geometría: transit inline mínimo con identidad
        seg_ctr[0] += 1; tk = f"d{daynum}-{seg_ctr[0]}"
        trk2 = ensure_linea(TR.get(line_tl, ["", ""])[0])
        tr = {"mode": "train"}
        if trk2:
            nombre, jp, chip, color, reconoce, extra = TR[trk2]
            tr.update({"linea": nombre, "nombre_jp": jp, "chip": chip, "color": color, "reconoce": reconoce})
            if ss:
                tr["anden"] = rd.get("d", ["", ""]); tr["reverso"] = rd.get("w", "")
                if rd.get("v"): tr["vehiculo"] = rd["v"]
                tr["estaciones"] = ss
        transits[tk] = tr
        return tk

    # extraer fork-plans (planes anidados) -> marcador <li>@@PLANS@@</li> (balanceado)
    def extract_fork_plans(bl):
        m = re.search(r'<(div|span) class="fork plans">', bl)
        if not m:
            return None, bl
        tag = m.group(1); i = m.end(); depth = 1; pat = re.compile(r"<(/?)" + tag + r"(?=[\s>])"); pos = i
        # div = elemento suelto (envolver en li); span = dentro de una li (marcador crudo)
        mk = "<li>@@PLANS@@</li>" if tag == "div" else "@@PLANS@@"
        while depth > 0:
            mm = pat.search(bl, pos)
            if not mm:
                return bl[i:], bl[:m.start()] + mk
            depth += -1 if mm.group(1) else 1; pos = mm.end()
        return bl[i:mm.start()], bl[:m.start()] + mk + bl[mm.end():]
    plan_inner, block_r = extract_fork_plans(block)
    plan_opts = []
    if plan_inner:
        for ch in re.split(r'(?=<span class="g\d">)', plan_inner):
            gm = re.match(r'<span class="g\d">\s*<b>(.*?)</b>(.*)', ch, re.S)
            if not gm:
                continue
            ptitle = strip_tags(gm.group(1)); body = gm.group(2)
            minilis = re.findall(r"<li>(.*?)</li>", body, re.S)
            # con <ul class="mini"> → sub-steps; inline (mar13) → la descripción como una nota
            plan_opts.append((ptitle, minilis if minilis else [body]))

    steps = []
    lis = re.findall(r"<li>(.*?)</li>", block_r, re.S)
    def next_walk():
        for fs in fsegs:
            if not fs["used"] and fs["mode"] == "walk":
                fs["used"] = True; return fs
        return None
    def meal_label(t):
        h = int(t[:2]) if re.match(r"\d\d:", t or "") else 12
        return "Desayuno" if h < 11 else ("Comida" if h < 16 else "Cena")
    def idx(h, sub):
        i = h.find(sub); return i if i >= 0 else 10**9
    def emit_row(li, into):
        tm = re.match(r'<span class="t( fix)?">([^<]*)</span>', li)
        fixed = bool(tm and tm.group(1)); time = (tm.group(2).strip() if tm else "")
        rest = li[tm.end():] if tm else li
        has_fork = 'class="fork"' in rest
        if not re.sub(r"<[^>]+>", "", rest).strip() and not has_fork:
            return   # fila vacía (marcador consumido)
        mainhtml, forkhtml = rest, ""
        if has_fork:
            fi = rest.index('<span class="fork">')
            mainhtml, forkhtml = rest[:fi], rest[fi:]
        innr = re.sub(r"^\s*<span>\s*", "", mainhtml)
        starts_d = innr.lstrip().startswith('<span class="d">')
        p_pl = idx(mainhtml, "data-lg="); p_tl = idx(mainhtml, "data-tl=")
        is_tr = starts_d or (p_tl < p_pl)
        is_loc = (p_pl < 10**9) and not is_tr
        base = {}
        if time: base["time"] = time
        if fixed: base["fixed"] = True
        made = []
        def tref_c(line, ride, _m=made):
            k = tref(line, ride); _m.append(k); return k
        primary = None
        if is_loc:
            body = to_md(mainhtml, tref_c)
            pk = place_from_lg(re.search(r'data-lg="([^"]+)"', mainhtml).group(1))
            into.append({"location": pk, **base, "title": body}); primary = "loc"
        elif is_tr:
            body = to_md(mainhtml, tref_c)
            if made:
                into.append({"transit": made[0], **base, "title": body})
            else:
                fs = next_walk()
                into.append({**({"transit": new_transit(fs)} if fs else {}), **base, "title": body})
            primary = "tr"
        elif not has_fork:
            into.append({**base, "title": to_md(mainhtml, tref_c)}); primary = "note"
        if has_fork:
            title = to_md(mainhtml, tref_c) if primary is None else meal_label(time)
            into.append({**({"time": time} if time else {}), "title": title, "options": parse_fork(forkhtml)})

    for li in lis:
        if "@@PLANS@@" in li:
            emit_row(li.replace("@@PLANS@@", ""), steps)     # intro (texto antes del marcador, si hay)
            if plan_opts:
                opts = []
                for ptitle, minilis in plan_opts:
                    psub = []
                    for ml in minilis:
                        emit_row(ml, psub)
                    opts.append({"title": ptitle, "steps": psub})
                it = steps[-1].get("time") if steps else None
                steps.append({**({"time": it} if it else {}), "title": "Elige tu plan del día", "options": opts})
                report.append(f"{date_iso}: {len(opts)} planes anidados ({', '.join(o['title'] for o in opts)})")
        else:
            emit_row(li, steps)

    # tramos embebidos (caminatas/buses entre sitios vecinos): dibujar en el MAPA
    # como pasos hidden-summary (no salen en el itinerario; su duración ya está en la nota)
    def step_ll(st):
        if "location" in st:
            g = places.get(st["location"], {}).get("gps", "")
            if g:
                a, b = g.split(","); return (float(a), float(b))
        if "transit" in st:
            c = transits.get(st["transit"], {}).get("coords", "")
            if c:
                a, b = c.split()[-1].split(","); return (float(a), float(b))
        return None
    n_emb = 0
    for fs in fsegs:
        if fs["used"]:
            continue
        seg_ctr[0] += 1; tk = f"d{daynum}-e{seg_ctr[0]}"
        transits[tk] = {"mode": fs["mode"], "color": fs["color"], "coords": fs["coords"]}
        a0, b0 = fs["coords"].split()[0].split(","); start = (float(a0), float(b0))
        best, bd = len(steps), 1e18
        for i, st in enumerate(steps):
            ll = step_ll(st)
            if ll:
                dd = dist(start, ll)
                if dd < bd:
                    bd, best = dd, i + 1
        title = f"{fs['emoji']} {fs['frm'] or ''} → {fs['to'] or ''}".strip(" →")
        steps.insert(best, {"transit": tk, "hidden-summary": True, "title": title})
        n_emb += 1
    days.append({"titulo": titulo, "note": note_d, "ancla": ancla, "date": date_iso, "steps": steps})
    if n_emb:
        report.append(f"{date_iso}: {n_emb} tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)")
    converted += 1

CUR["days"] = days
yaml.dump(CUR, open(SD + "/viaje.yaml", "w", encoding="utf-8"), allow_unicode=True,
          sort_keys=False, default_flow_style=None, width=100000)
print("convertidos:", converted, "· places:", len(places), "· lineas:", len(lineas), "· transits:", len(transits))
open(SD + "/DIFERENCIAS.md", "w", encoding="utf-8").write(
    "# Diferencias (conversión rica desde japon.html)\n\n" + "\n".join("- " + r for r in report))
print("notas:", len(report))
