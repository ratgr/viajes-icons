# -*- coding: utf-8 -*-
"""render.py — el renderer compartido YAML → fragmentos HTML (días, filas,
options, modales) y el ensamblado de página sobre una plantilla con tokens.

Lo usan build_itinerario.py y build_mapa.py: el markup de los días es EL MISMO
en ambas páginas (proyección 1:1 del YAML, verify_roundtrip la comprueba);
cada página agrega su cromo por CSS/JS estático, no cambiando el HTML.

Uso: render.build_page(trip, "plantilla-X.html", "salida.html")
"""
import html
import math
import os
import re
import shutil
import subprocess
import sys

import yaml

import common
import contract
from common import ASSETS, trip_paths

# estado del viaje activo (lo fija init)
PLACES = LINES = TRANSITS = None
DAYS = []
FOTO_BASE = ""
_LINE_BY_NAME = _LINE_BY_CHIP = None
TRANSIT_STEP = {}


def init(data, foto_base=""):
    """carga los catálogos del viaje en el módulo (los renderers los leen)."""
    global PLACES, LINES, TRANSITS, DAYS, FOTO_BASE
    global _LINE_BY_NAME, _LINE_BY_CHIP, TRANSIT_STEP
    PLACES = data.get("places", {})
    LINES = data.get("lines", {})
    TRANSITS = data.get("transits", {})
    DAYS = data.get("days", [])
    FOTO_BASE = foto_base
    # identidad de línea (frecuencia/horarios) por nombre o por chip
    _LINE_BY_NAME = {v.get("name"): v for v in LINES.values() if v.get("frequency")}
    _LINE_BY_CHIP = {v.get("chip"): v for v in LINES.values() if v.get("frequency") and v.get("chip")}
    # primer step que usa cada transit (da el renglón Sale/Llega de su modal)
    DIAGNOSTICS.clear()
    TRANSIT_STEP = {}
    for day in DAYS:
        for step in day.get("steps", []):
            if "transit" in step:
                TRANSIT_STEP.setdefault(step["transit"], step)


# icono de un paso de transporte (derivado de mode; no vive en el título)
MODE_ICON = {"train": "🚇", "walk": "🚶", "monorail": "🚝", "flight": "✈️",
             "tramite": "🧳", "bus": "🚌", "ferry": "⛴️", "tour": "🚌"}
# vehículo → término japonés para la frase de auxilio del modal de línea
VEH_JP = {"tren": "電車", "bus": "バス", "barco": "船"}
VEH_RO = {"tren": "densha", "bus": "basu", "barco": "fune"}
REF_RE = re.compile(r"@\[(.+?)\]\((.+?)\)")
HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")   # hora 'H:MM' / 'HH:MM'



# ---------------------------------------------------------------- utilidades
def line_meta(tr):
    l = _LINE_BY_NAME.get(tr.get("line")) or _LINE_BY_CHIP.get(tr.get("chip")) or {}
    return {k: l[k] for k in ("frequency", "first_train", "last_train", "frequency_source") if l.get(k)}


def dmin(s):
    """'1 h 05' → 65 · '15 min' → 15 · '2' → 2."""
    s = str(s or "")
    hm = re.search(r"(\d+)\s*h\s*(\d+)?", s)
    if hm:
        return int(hm.group(1)) * 60 + int(hm.group(2) or 0)
    m = re.search(r"(\d+)\s*min", s)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)", s)
    return int(m2.group(1)) if m2 else 0


def add_min(hhmm, mins):
    """'21:45' + 10 → '21:55'."""
    m = HHMM_RE.match(str(hhmm or "").strip())
    if not m:
        return ""
    total = (int(m.group(1)) * 60 + int(m.group(2)) + int(mins or 0)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def hm_min(hhmm):
    """'07:15' → 435 · otra cosa → None."""
    m = HHMM_RE.match(str(hhmm or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def fmt_hm(total):
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def fmt_dur(mins):
    """65 → '1 h 05' · 15 → '15 min'."""
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h} h {m:02d}" if m else f"{h} h"


DIAGNOSTICS = []   # pasos cuyo horario no se puede completar: problema del YAML

# duration: flex · flex(30) · flex(-60) · flex(30-60) · flex(1h) · flex(30-1 h 30)
# — paso elástico con cotas opcionales (cualquier sintaxis de duración)
FLEX_RE = re.compile(r"^flex(?:\((.*)\))?$")


def parse_flex(raw):
    """None si no es flex; si lo es, (min, max) con None en las cotas ausentes."""
    m = FLEX_RE.match(str(raw or "").strip())
    if not m:
        return None
    inner = (m.group(1) or "").strip()
    if not inner:
        return (None, None)
    parts = re.split(r"[-,]", inner, maxsplit=1)   # rango con - o con ,
    lo = dmin(parts[0]) or None if parts[0].strip() else None
    hi = dmin(parts[1]) or None if len(parts) > 1 and parts[1].strip() else None
    return (lo, hi)

WALK_M_PER_MIN = 4000 / 60          # humano a 4 km/h


def _crow_m(a, b):
    """metros aprox entre dos (lat,lng) — equirectangular."""
    dy = (b[0] - a[0]) * 111000
    dx = (b[1] - a[1]) * 111000 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def round_walk(mins):
    """redondeo de caminatas: al múltiplo de 5 que la encierra hasta 45;
    de ahí en adelante, al múltiplo de 15."""
    m5 = max(5, math.ceil(mins / 5) * 5)
    return m5 if m5 <= 45 else math.ceil(mins / 15) * 15


def parse_pts(raw, ctx=""):
    """envoltura de common.parse_pts: aquí un dato roto es un DIAGNÓSTICO,
    no un build muerto (la lógica de parseo vive en common)."""
    return common.parse_pts(raw, ctx, on_error=DIAGNOSTICS.append)


def walk_calc(coords_str, ctx=""):
    """(metros, minutos redondeados) del camino a pie — None si está malformado."""
    pts = parse_pts(coords_str, ctx)
    if not pts or len(pts) < 2:
        return None
    dist = sum(_crow_m(pts[i - 1], pts[i]) for i in range(1, len(pts)))
    return dist, round_walk(dist / WALK_M_PER_MIN)


def step_walk_geometry(s):
    """coords del paso si es una caminata (mode walk propio o de su transit)."""
    tr = TRANSITS.get(s.get("transit"), {}) if s.get("transit") else {}
    mode = s.get("mode") or tr.get("mode")
    coords = tr.get("coords") or s.get("coords")
    return coords if (mode == "walk" and coords) else None


GEO_TELEPORT_M = 100.0   # brinco geométrico que ya cuenta como teletransporte


def _place_pt(key):
    gps = PLACES.get(key, {}).get("gps")
    if not gps:
        return None
    pts = parse_pts(gps, f"places[{key}]")
    return pts[0] if pts else None


def _transit_pts(key):
    coords = TRANSITS.get(key, {}).get("coords")
    if not coords:
        return None
    return parse_pts(coords, f"transits[{key}]")


def check_teleports(steps, sched, ctx=""):
    """Continuidad GEOMÉTRICA de la cadena: el fin de un paso debe coincidir
    (±GEO_TELEPORT_M) con el inicio del siguiente.
      · location→location sin transit de por medio = teletransporte
      · transit que arranca/termina lejos del punto vecino = desconectado
    Un transit declarado SIN coords corta la cadena sin aviso (geometría
    pendiente: el mapa dibuja su conector automático). El aviso va como 🌀
    data-derived en la fila y a DIAGNOSTICS."""
    prev_end = prev_label = prev_kind = None
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or s.get("location") or s.get("transit") or "")
        title = re.sub(r"[*@\[\]]", "", title)[:44]
        start = end = kind = None
        if s.get("location"):
            p = _place_pt(s["location"])
            if p:
                start = end = p
                kind = "location"
        elif s.get("transit"):
            pts = _transit_pts(s["transit"])
            if pts:
                start, end, kind = pts[0], pts[-1], "transit"
            else:
                prev_end = prev_label = prev_kind = None
                continue
        if start is None:
            continue                       # paso sin geometría propia: no mueve
        if prev_end is not None:
            d = _crow_m(prev_end, start)
            if d > GEO_TELEPORT_M:
                if kind == "transit":
                    msg = f"transit arranca a {d:.0f} m del punto anterior «{prev_label}»"
                elif prev_kind == "transit":
                    msg = f"el transit anterior «{prev_label}» termina a {d:.0f} m de este lugar"
                else:
                    msg = f"teletransporte: a {d:.0f} m de «{prev_label}» sin transit de por medio"
                if i < len(sched) and sched[i] is not None:
                    sched[i]["teleport"] = msg
                DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: {msg}")
        prev_end, prev_label, prev_kind = end, title, kind
    return sched


def _step_time_fields(s, i, ctx):
    """campos de horario de UN paso (parse de time-from/time-to/duration/flex
    + validación de la geometría de caminata) — None si el paso no participa."""
    if not isinstance(s, dict) or s.get("hidden-summary"):
        return None
    beg = hm_min(s.get("time-from"))
    end_exp = hm_min(s.get("time-to"))
    raw_dur = s.get("duration")
    flex = parse_flex(raw_dur)                        # se estira a lo que haya
    has_dur = raw_dur not in contract.SKIP_DUR and flex is None
    fo = {"begin": beg, "beg_exp": beg is not None, "beg_derived": False,
          "dur": dmin(raw_dur) if has_dur else None, "dur_exp": has_dur,
          "flex": flex is not None,
          "flex_min": flex[0] if flex else None,
          "flex_max": flex[1] if flex else None,
          "end_exp": end_exp,
          "dur_derived": False, "approx": False, "end": None}
    is_flex = flex is not None
    # los 3 fijados e incompatibles → diagnóstico (⚠️ en la fila)
    if beg is not None and end_exp is not None and has_dur and beg + fo["dur"] != end_exp:
        title = str(s.get("title", ""))[:52]
        fo["conflict"] = (f"time-from {fmt_hm(beg)} + {fo['dur']} min no cuadra "
                          f"con time-to {fmt_hm(end_exp)}")
        DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: {fo['conflict']}")
    if fo["dur"] is None and beg is not None and end_exp is not None and end_exp > beg:
        fo["dur"], fo["dur_derived"] = end_exp - beg, True   # exacta (sin ~)
    # caminatas: la geometría dicta la duración (4 km/h + redondeo);
    # si el YAML trae otra cosa, es un diagnóstico
    coords = step_walk_geometry(s)
    wc = walk_calc(coords, f"{ctx} paso {i + 1}") if coords and not is_flex else None
    if wc:
        dist, esperado = wc
        if fo["dur"] is None:
            fo["dur"], fo["dur_derived"], fo["approx"] = esperado, True, True
        elif fo["dur_exp"] and fo["dur"] != esperado:
            title = str(s.get("title", ""))[:52]
            DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: caminata dice "
                               f"{fo['dur']} min pero el camino mide {dist:.0f} m "
                               f"≈ {esperado} min a 4 km/h")
    return fo


def _snap_forward(info, next_begin):
    """pasada adelante: inicio = fin del anterior; duración = hueco al siguiente."""
    cursor = None
    for i, fo in enumerate(info):
        if fo is None:
            continue
        if fo["begin"] is None and cursor is not None:
            fo["begin"], fo["beg_derived"] = cursor, True
        if fo["dur"] is None and fo["begin"] is not None:
            nb = next_begin(i)
            if nb is not None and nb > fo["begin"]:
                fo["dur"], fo["dur_derived"], fo["approx"] = nb - fo["begin"], True, True
        if fo["flex"]:
            # cotas del flex: acotan el relleno; sin relleno, cae al mínimo
            if fo["dur"] is None:
                fo["dur"] = fo["flex_min"]
            if fo["dur"] is not None:
                if fo["flex_min"]:
                    fo["dur"] = max(fo["dur"], fo["flex_min"])
                if fo["flex_max"]:
                    fo["dur"] = min(fo["dur"], fo["flex_max"])
                fo["dur_derived"], fo["approx"] = True, True
        if fo["end_exp"] is not None:
            fo["end"] = fo["end_exp"]
        elif fo["begin"] is not None and fo["dur"]:
            fo["end"] = fo["begin"] + fo["dur"]
        cursor = fo["end"] if fo["end"] is not None else fo["begin"]


def _snap_backward(info, next_begin):
    """pasada atrás: con duración pero sin inicio → fin = inicio del siguiente;
    PERO un time-to explícito propio manda: inicio = fin − duración (antes
    el snap al siguiente PISABA el fin explícito sin avisar)."""
    for i in range(len(info) - 1, -1, -1):
        fo = info[i]
        if fo is None or fo["begin"] is not None or not fo["dur"]:
            continue
        if fo["end_exp"] is not None:
            fo["begin"], fo["beg_derived"] = fo["end_exp"] - fo["dur"], True
            continue
        nb = next_begin(i)
        if nb is not None:
            fo["end"] = nb
            fo["begin"], fo["beg_derived"] = nb - fo["dur"], True


def _report_gaps(steps, info, ctx):
    """diagnóstico: pasos que tras los snaps siguen sin 2 de {inicio, fin,
    duración}, o con los 3 fijados encimándose con el paso siguiente."""
    def next_begin(i):
        for j in range(i + 1, len(info)):
            if info[j] and info[j]["beg_exp"]:
                return info[j]["begin"]
        return None

    for i, (s, fo) in enumerate(zip(steps, info)):
        if fo is None:
            continue
        title = str(s.get("title", ""))[:52]
        if fo["begin"] is None:
            DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: sin inicio anclable (ni arriba ni abajo)")
        elif not fo["dur"] and "location" not in s and not fo["flex"]:
            DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: solo inicio — falta duración o fin")
        elif fo["beg_exp"] and fo["dur"] and not fo["dur_derived"] and not fo["flex"] and fo.get("conflict") is None:
            # los 3 valores fijados (inicio + duración explícitos y el inicio
            # del siguiente como fin): si se enciman, no son compatibles
            nb = next_begin(i)
            if nb is not None and fo["begin"] + fo["dur"] > nb:
                exceso = fo["begin"] + fo["dur"] - nb
                fo["conflict"] = (f"termina {fmt_hm(fo['begin'] + fo['dur'])} pero lo "
                                  f"siguiente empieza {fmt_hm(nb)} (encimados {exceso} min)")
                DIAGNOSTICS.append(f"{ctx} paso {i + 1} «{title}»: {fo['conflict']}")


def derive_schedule(steps, ctx=""):
    """Horario por paso, completado por SNAP a los vecinos:
      · sin inicio → snap ARRIBA (fin del paso anterior) o ABAJO (inicio del
        siguiente − duración propia)
      · sin duración → snap ABAJO (hueco hasta el próximo inicio explícito)
    Regla: cada paso debe quedar con 2 de {inicio, fin, duración}. Un LUGAR
    con solo inicio es un ancla válida (llegas y punto); cualquier otro paso
    incompleto es un problema del YAML → va a DIAGNOSTICS.
    Todo lo inferido se marca data-derived al render."""
    n = len(steps)
    info = [_step_time_fields(s, i, ctx) for i, s in enumerate(steps)]

    def next_begin(i):
        for j in range(i + 1, n):
            if info[j] and info[j]["beg_exp"]:
                return info[j]["begin"]
        return None

    _snap_forward(info, next_begin)
    _snap_backward(info, next_begin)
    _report_gaps(steps, info, ctx)
    # tiempo LIBRE tras cada paso: hueco entre su fin y el próximo inicio YA
    # RESUELTO (explícito o derivado — contar solo explícitos duplicaba el
    # hueco cuando en medio había pasos con inicio encadenado)
    def next_resolved_begin(i):
        for j in range(i + 1, n):
            if info[j] and info[j]["begin"] is not None:
                return info[j]["begin"]
        return None

    for i, fo in enumerate(info):
        if fo is None or fo["end"] is None:
            continue
        nb = next_resolved_begin(i)
        if nb is not None and nb > fo["end"]:
            fo["free"] = nb - fo["end"]
    return [{} if fo is None else
            {"start": fo["begin"], "start_derived": fo["beg_derived"],
             "dur": fo["dur"], "dur_derived": fo["dur_derived"],
             "approx": fo.get("approx"), "flex": fo.get("flex"),
             "flex_min": fo.get("flex_min"), "flex_max": fo.get("flex_max"),
             "end": fo["end"], "end_exp": fo.get("end_exp"),
             "conflict": fo.get("conflict"), "free": fo.get("free")}
            for fo in info]


class RefLog(set):
    """set que además recuerda el orden de primera aparición."""

    def __init__(self):
        super().__init__()
        self.order = []

    def add(self, k):
        if k not in self:
            self.order.append(k)
        super().add(k)


def md(s, refs=None):
    """markdown mínimo (**b**, *i*, saltos de línea) + refs @[alt](clave)."""
    if s is None:
        return ""
    s = html.escape(str(s).strip(), quote=False)

    def _ref(m):
        alt, key = m.group(1), m.group(2)
        if refs is not None:
            refs.add(key)
        tr = TRANSITS.get(key, {})
        chip = ""
        if tr.get("color"):
            cls = "line-chip" if tr.get("chip") else "line-chip dot"
            chip = f'<i class="{cls}" style="--lc:{tr["color"]}">{html.escape(tr.get("chip", ""))}</i>'
        return f'<a class="modal-link" href="#{contract.MODAL_PREFIX}{key}">{chip}{alt}</a>'

    s = REF_RE.sub(_ref, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s.replace("\n", "<br>")


# ---------------------------------------------------------------- filas del día
def mode_icon(n):
    """icono del transporte como nodo de texto real (copiable), marcado derivado."""
    if "transit" not in n and not n.get("mode"):
        return ""
    mode = n.get("mode") or TRANSITS.get(n.get("transit"), {}).get("mode", "walk")
    ic = MODE_ICON.get(mode, "")
    return f'<i class="icon" data-derived="mode">{ic}</i> ' if ic else ""


def row_text(n, refs, sc=None):
    """<b.title> - <span.duration> - <span.note> — campos separados, no un blob.
    El separador vive DENTRO del span que sigue: ocultar un campo por CSS
    (p.ej. la nota en la barra del mapa) se lleva su separador consigo.
    Sin duration en el YAML, se emite la inferida (~hueco) marcada derivada.
    Convención *-show: `X-show` sustituye lo MOSTRADO; el dato base viaja en
    data-value (verify lo reconstruye) y el show es dato explícito (verde)."""
    sc = sc or {}
    parts = []
    if n.get("title"):
        title = contract.clean_title(n["title"], strip=False)
        show = n.get("title-show")
        if show:
            shown = md(contract.clean_title(show, strip=False), refs)
            base = html.escape(title, quote=True)
            parts.append(f'<b class="title" data-value="{base}">{mode_icon(n)}{shown}</b>')
        else:
            parts.append(f'<b class="title">{mode_icon(n)}{md(title, refs)}</b>')
    elif n.get("location") and PLACES.get(n["location"], {}).get("name"):
        # paso-lugar sin título: el LUGAR MISMO como título derivado (ref
        # clickeable al catálogo, igual que en cualquier otro texto)
        key = n["location"]
        ref = md(f"@[{PLACES[key]['name']}]({key})", refs)
        parts.append(f'<b class="title" data-derived="title">{mode_icon(n)}{ref}</b>')
    raw_dur = n.get("duration")
    flex = parse_flex(raw_dur) if raw_dur is not None else None
    dur_show = n.get("duration-show")
    sep = f'<span class="sep">{contract.SEP}</span>' if parts else ""
    if dur_show and raw_dur not in contract.SKIP_DUR:
        base = html.escape(str(raw_dur), quote=True)
        parts.append(f'<span class="duration" data-value="{base}">{sep}{html.escape(str(dur_show))}</span>')
    elif flex is not None:
        # elástica: rango ~min–max si tiene cotas; min+ · ≤max · relleno+
        lo, hi = flex
        if lo and hi:
            unit_lo = str(lo) if (lo < 60 and hi < 60) else fmt_dur(lo)
            val = f"~{unit_lo}–{fmt_dur(hi)}"
        elif lo:
            val = f">{fmt_dur(lo)}"
        elif hi:
            val = f"≤{fmt_dur(hi)}"
        else:
            val = fmt_dur(sc["dur"]) + "+" if sc.get("dur") else "flex"
        parts.append(f'<span class="duration" data-derived="duration">{sep}{val}</span>')
    elif raw_dur not in contract.SKIP_DUR:
        parts.append(f'<span class="duration">{sep}{html.escape(str(raw_dur))}</span>')
    elif sc.get("dur") and sc.get("dur_derived"):
        tilde = "~" if sc.get("approx") else ""
        parts.append(f'<span class="duration" data-derived="duration">{sep}{tilde}{fmt_dur(sc["dur"])}</span>')
    if n.get("note"):
        sep = f'<span class="sep">{contract.SEP}</span>' if parts else ""
        show = n.get("note-show")
        if show:
            base = html.escape(str(n["note"]).strip(), quote=True)
            parts.append(f'<span class="note" data-value="{base}">{sep}{md(str(show).strip(), refs)}</span>')
        else:
            parts.append(f'<span class="note">{sep}{md(str(n["note"]).strip(), refs)}</span>')
    return "".join(parts)


def time_cell(n, sc=None):
    """hora explícita + (derivados: inicio encadenado si falta, y la hora-fin).
    El itinerario esconde lo derivado por CSS; el mapa muestra DESDE–HASTA."""
    sc = sc or {}
    t = str(n.get("time-from") or "")
    cls = "time fixed" if n.get("fixed") else "time"
    dt = f' datetime="{t}"' if HHMM_RE.match(t) else ""
    inner = html.escape(t)
    if not t and sc.get("start_derived"):
        inner = f'<span class="from" data-derived="from">{fmt_hm(sc["start"])}</span>'
    # time-to explícito va CRUDO (el verify lo compara literal: normalizarlo
    # rompía el round-trip con grafías tipo '9:05') y SIEMPRE se emite,
    # aunque no haya inicio del cual colgarlo
    if n.get("time-to") is not None:
        inner += f'<span class="to">{contract.TIME_TO_DASH}{html.escape(str(n["time-to"]))}</span>'   # explícito: verde
    elif sc.get("end") is not None and inner:
        inner += f'<span class="to" data-derived="to">{contract.TIME_TO_DASH}{fmt_hm(sc["end"])}</span>'
    if sc.get("conflict"):
        inner += (f'<span class="warn" data-derived="conflict" '
                  f'title="{html.escape(sc["conflict"])}">⚠️</span>')
    if sc.get("teleport"):
        inner += (f'<span class="warn" data-derived="teleport" '
                  f'title="{html.escape(sc["teleport"])}">🌀</span>')
    return f'<time class="{cls}"{dt}>{inner}</time>'


def render_option(opt, refs, base=None):
    """opción de tier — plana {location, price} o ENRIQUECIDA {title, price,
    steps}: la ida/lugar/regreso viven como sub-pasos propios (el itinerario
    no los muestra; el mapa sí, seleccionables). base = id extendido
    dN-rMM-gG-oO para que sus sub-pasos sean editables en modo dev."""
    if "steps" in opt or "title" in opt:
        out = md(str(opt.get("title", "")), refs)
        if opt.get("price"):
            out += f' <span class="price">{html.escape(str(opt["price"]))}</span>'
        if opt.get("steps"):
            subs = "\n".join(render_li(s, refs, f"{base}-s{si + 1}" if base else None)
                             for si, s in enumerate(opt["steps"]))
            out += f'<ul class="steps">\n{subs}\n</ul>'
        return out
    return resto_link(opt, refs)


def resto_link(opt, refs):
    """opción hoja { location: acchichi, precio: ¥600 }."""
    key = opt.get("location")
    nombre = html.escape(PLACES.get(key, {}).get("name", key or "?"))
    if key:
        refs.add(key)
    lk = f'<a class="modal-link" href="#{contract.MODAL_PREFIX}{key}">{nombre}</a>' if key else nombre
    precio = opt.get("price")
    return lk + (f' <span class="price">{html.escape(str(precio))}</span>' if precio else "")


def render_options(node, refs, ctx="", row_id=None):
    """options unificadas: MISMO markup para tiers de comida y planes en
    paralelo (en el YAML son la misma clave). El CSS decide el render por
    item: con sub-steps (:has) = tarjeta plan, sin ellos = cajita tier.
    row_id = id de la fila padre: los sub-pasos reciben ids extendidos
    dN-rMM-gG-sS (plan) / dN-rMM-gG-oO-sS (tier) para el editor dev."""
    items = []
    for gi, o in enumerate(node.get("options", []), 1):
        if not isinstance(o, dict):
            continue
        if "steps" in o:
            plan_title = contract.clean_title(o.get("title", ""), strip=False)
            title = md(plan_title, refs)
            sched = derive_schedule(o["steps"], f'{ctx} plan «{plan_title[:24]}»')
            check_teleports(o["steps"], sched, f'{ctx} plan «{plan_title[:24]}»')
            subs = "\n".join(
                render_li(s, refs, f"{row_id}-g{gi}-s{i + 1}" if row_id else None,
                          sc=sched[i], ctx=ctx)
                for i, s in enumerate(o["steps"]))
            # data-opt: la marca del CONTENEDOR de elección (sufijo 1-based del
            # id extendido) — mapa.js resuelve la rama elegida sin recorrer el DOM
            items.append(f'<li data-kind="plan" data-opt="g{gi}"><b>{title}</b>'
                         f'<ul class="steps">\n{subs}\n</ul></li>')
        else:
            label = html.escape(str(o.get("title", "")))
            extra = f' class="{html.escape(str(o["class"]))}"' if o.get("class") else ""
            # cada opción envuelta (span.option) y separador en span.sep: el
            # itinerario fluye inline; el mapa las apila una por línea
            # cada opción lleva su data-opt (contenedor de elección, ver arriba)
            inner = '<span class="sep"> · </span>'.join(
                f'<span class="option" data-opt="g{gi}-o{oi + 1}">'
                f'{render_option(x, refs, f"{row_id}-g{gi}-o{oi + 1}" if row_id else None)}'
                f'</span>'
                for oi, x in enumerate(o.get("options", [])))
            items.append(f'<li data-kind="tier" data-tier="{label}"{extra}><b>{label}</b>{inner}</li>')
    return '<ul class="options">' + "".join(items) + "</ul>"


def render_li(n, refs, row_id=None, sc=None, ctx=""):
    body = row_text(n, refs, sc)
    if "options" in n:
        body += render_options(n, refs, ctx or row_id or "", row_id)
    elif "transit" in n:
        # los trayectos van en gris para que resalten los lugares
        body = f'<span class="transit">{body}</span>'
    # la fila lleva TODO su paso YAML: claves como data-*, flags como clase
    attrs = f' id="{row_id}"' if row_id else ""
    if n.get("hidden-summary"):
        attrs += ' class="hidden-summary"'
    if n.get("location"):
        attrs += f' data-location="{html.escape(str(n["location"]))}"'
    elif n.get("transit"):
        attrs += f' data-transit="{html.escape(str(n["transit"]))}"'
    if n.get("mode"):
        attrs += f' data-mode="{html.escape(str(n["mode"]))}"'
    if n.get("select-only"):
        attrs += " data-select-only"
    dur_str = str(n.get("duration") or "").strip()
    if FLEX_RE.match(dur_str):
        inner = contract.norm_flex(dur_str[4:])   # el spec, sin 'flex'
        attrs += f' data-flex="{inner}"' if inner else " data-flex"
    if sc and sc.get("free"):
        attrs += f' data-free="{sc["free"]}"'   # hueco libre tras el paso (derivado)
    return f'    <li{attrs}>{time_cell(n, sc)}<div class="body">{body}</div></li>'


def render_day(day, refs, num):
    """num = día 1..N → ancla corta #d1 (la fecha queda en data-fecha)."""
    titulo = html.escape(day.get("title", ""))
    note = html.escape(day.get("note", ""))
    ancla = html.escape(day.get("anchor", ""))
    fecha = day.get("date")
    fecha = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    head = (f'<header class="day-head"><h3>{titulo}</h3>'
            f'<span class="note">{note}</span>'
            f'<span class="anchor">{contract.ANCHOR_LABEL}{ancla}</span></header>')
    # TODOS los pasos van al DOM (hidden-summary incluidos, ocultos por CSS):
    # la fila rNN es EXACTAMENTE el paso N del YAML
    sched = derive_schedule(day.get("steps", []), f"d{num}")
    check_teleports(day.get("steps", []), sched, f"d{num}")
    lis = "\n".join(render_li(s, refs, f"d{num}-r{i + 1:02d}", sched[i], ctx=f"d{num}")
                    for i, s in enumerate(day.get("steps", [])))
    return (f'  <section class="day" id="d{num}" data-fecha="{fecha}">{head}\n'
            f'  <ul class="steps">\n{lis}\n  </ul></section>')


def nav_link(day, num):
    label = str(day.get("title", "")).split("·")[0].strip() or f"día {num}"
    return f'<a href="#d{num}">{html.escape(label)}</a>'


# ---------------------------------------------------------------- modales
def render_place_modal(key, pl):
    nombre = html.escape(pl.get("name", key))
    out = [f"<h3>{nombre}</h3>"]
    if pl.get("image"):
        im = pl["image"]
        src = im if im.startswith("http") else FOTO_BASE + im
        out.append(f'<img src="{html.escape(src)}" alt="{nombre}" loading="lazy">')
    if pl.get("description"):
        out.append(f"<p>{md(pl['description'])}</p>")
    if pl.get("info"):
        out.append(f'<p class="modal-note">{md(pl["info"])}</p>')
    if pl.get("hours"):
        src = ' <span class="src-tag">· Google Maps</span>' if pl.get("hours_source") == "maps" else ""
        out.append(f'<p class="modal-note">🕒 <b>Horario:</b> {html.escape(str(pl["hours"]))}{src}</p>')
    if pl.get("maps"):
        out.append(f'<a class="modal-btn" href="{html.escape(pl["maps"])}" target="_blank" rel="noopener">Abrir en Maps ↗</a>')
    inner = "\n  ".join(out)
    return f'<div class="modal" id="{contract.MODAL_PREFIX}{key}">\n  {inner}\n</div>'


def render_line_modal(key, ident, ride=None, guia=None, horario=None):
    color = ident.get("color", "#555")
    chip = ident.get("chip", "")
    jp = html.escape(ident.get("name_jp", ""))
    nombre = html.escape(ident.get("name", key))
    rng = ""
    if horario and horario.get("desde") and horario.get("hasta"):
        rng = (f' <span class="h3-range" data-derived="schedule">· {html.escape(str(horario["desde"]))}'
               f' – {html.escape(str(horario["hasta"]))}</span>')
    h = [f"<h3>{nombre}{rng}</h3>"]

    # banner con el nombre en japonés y el chip de la línea
    badge = f'<div class="badge-row"><span class="badge">{html.escape(chip)}</span></div>' if chip else ""
    h.append(f'<div class="line-banner"><div class="jp" lang="ja">{jp}</div>{badge}</div>')

    if ident.get("frequency"):
        row = f'🔄 Pasa <b>{html.escape(str(ident["frequency"]))}</b>'
        if ident.get("first_train") or ident.get("last_train"):
            row += (f' · 🚉 {html.escape(str(ident.get("first_train", "")))}'
                    f'–{html.escape(str(ident.get("last_train", "")))}')
        src = ident.get("frequency_source")
        h.append(f'<p class="freq{" has-src" if src else ""}">{row}</p>')
        if src:
            h.append(f'<div class="freq-src"><a href="{html.escape(str(src))}" '
                     f'target="_blank" rel="noopener">horario oficial ↗</a></div>')

    # renglón Sale {desde} · origen → destino · Llega {hasta} (calculado)
    if horario and (horario.get("desde") or horario.get("hasta")):
        o = html.escape(str(horario.get("origen", "")))
        d = html.escape(str(horario.get("destino", "")))
        desde = html.escape(str(horario.get("desde", "")))
        hasta = html.escape(str(horario.get("hasta", "")))
        h.append(f'<div class="ride" data-derived="schedule">'
                 f'<span>🟢 <b>Sale {desde}</b><br><span class="stn">{o}</span></span>'
                 f'<span class="arrow">→</span>'
                 f'<span class="arr">🔴 <b>Llega {hasta}</b><br><span class="stn">{d}</span></span></div>')

    if ride:
        anden = ride.get("platform", ["", ""])
        veh = ride.get("vehicle", "tren")
        ic, lab, word = {"barco": ("🛳️", "Embarcadero correcto", "muelle"),
                         "bus": ("🚏", "Parada correcta", "lado")}.get(veh, ("🧭", "Andén correcto", "andén"))
        h.append(f'<p class="platform">{ic} <b>{lab}:</b> letrero '
                 f'<b class="sign" lang="ja">{html.escape(str(anden[0]))}</b> — {html.escape(str(anden[1]))}</p>')
        if ride.get("reverse"):
            h.append(f'<p class="reverse">⚠️ Si la primera parada es '
                     f'<b>{html.escape(str(ride["reverse"]))}</b>, van al revés: bajarse y cruzar de {word}.</p>')
        est = ride.get("stations", [])
        if est:
            h.append('<div class="stations">')
            for i, st in enumerate(est):
                code, sjp, srom = (list(st) + ["", "", ""])[:3]
                tag = ' 🟢 <small data-derived="pos"><b>SUBIR</b></small>' if i == 0 else (
                    ' 🔴 <small data-derived="pos"><b>BAJAR</b></small>' if i == len(est) - 1 else "")
                dot = f'<span class="station-code">{html.escape(str(code))}</span> ' if code else "· "
                h.append(f'<div class="station">{dot}<b lang="ja">{html.escape(str(sjp))}</b> '
                         f'<span class="romaji">{html.escape(str(srom))}</span>{tag}</div>')
            h.append("</div>")
            # frase para enseñar el teléfono: «¿voy bien en este tren/bus/barco?»
            dest = est[-1]
            djp, drom = html.escape(str(dest[1])), html.escape(str(dest[2]))
            eki = "駅" if (veh == "tren" and "駅" not in str(dest[1]) and "ターミナル" not in str(dest[1])) else ""
            h.append(f'<div class="phrase" data-derived="phrase">'
                     f'<div class="jp" lang="ja">すみません、{djp}{eki}へ行きたいです。この{VEH_JP.get(veh, "電車")}で合っていますか？</div>'
                     f'<div class="romaji">Sumimasen, {drom}{"-eki" if eki else ""} e ikitai desu. '
                     f'Kono {VEH_RO.get(veh, "densha")} de atte imasu ka?</div>'
                     f'<div class="gloss">«Disculpe, quiero ir a {drom}. ¿Voy bien en este {veh}?» — '
                     f'muéstrale el teléfono a cualquier local o uniformado.</div></div>')

    reconoce = html.escape(ident.get("recognize", ""))
    tail = f'<b>Se reconoce:</b> {reconoce}{" — letra <b>" + html.escape(chip) + "</b>" if chip else ""}.'
    texto = guia or ident.get("extra", "")
    if texto:
        tail += f"<br><br>{md(texto)}"
    h.append(f'<p class="recognize">{tail}</p>')   # en un elemento: el corte del popup lo puede ocultar
    inner = "\n  ".join(h)
    return f'<div class="modal" id="{contract.MODAL_PREFIX}{key}" style="--lc:{color}">\n  {inner}\n</div>'


def render_modal(key):
    if key in PLACES:
        return render_place_modal(key, PLACES[key])
    if key in TRANSITS and TRANSITS[key].get("name_jp"):
        tr = TRANSITS[key]
        ident = {"name": tr.get("line", key), "name_jp": tr.get("name_jp", ""),
                 "chip": tr.get("chip", ""), "color": tr.get("color", "#555"),
                 "recognize": tr.get("recognize", ""), **line_meta(tr)}
        ride = {k: tr[k] for k in ("platform", "reverse", "stations", "vehicle") if k in tr}
        st = TRANSIT_STEP.get(key, {})
        horario = None
        if tr.get("stations") and st.get("time-from"):
            horario = {"origen": tr["stations"][0][2], "destino": tr["stations"][-1][2],
                       "desde": str(st["time-from"]), "hasta": add_min(st["time-from"], dmin(st.get("duration")))}
        return render_line_modal(key, ident, ride, tr.get("guide"), horario)
    if key in LINES:
        return render_line_modal(key, LINES[key])
    return f'<div class="modal" id="{contract.MODAL_PREFIX}{key}"><h3>{html.escape(key)}</h3></div>'

# ---------------------------------------------------------------- ensamblado
def build_page(trip, template_name, out_name, extra=None):
    """src/<trip>/viaje.yaml + src/<trip>/<template> → pages/<trip>/<out>.
    `extra`: callable (corre tras init) que devuelve tokens adicionales."""
    src_dir, pages_dir, cfg = trip_paths(trip)
    data = yaml.safe_load(open(os.path.join(src_dir, "viaje.yaml"), encoding="utf-8"))
    # la llave del config es photo_base (esquema en inglés); se leía foto_base
    # y la base quedaba SIEMPRE vacía — rutas relativas de imagen rotas
    init(data, cfg.get("photo_base", cfg.get("foto_base", "")))

    refs = RefLog()
    days = "\n\n".join(render_day(d, refs, i + 1) for i, d in enumerate(DAYS))
    nav = "".join(nav_link(d, i + 1) for i, d in enumerate(DAYS))
    modals = "\n".join(render_modal(k) for k in refs.order)

    tokens = {"<!--NAV-->": nav, "<!--DAYS-->": days, "<!--MODALS-->": modals}
    if extra:
        tokens.update(extra())
    page = open(os.path.join(src_dir, template_name), encoding="utf-8").read()
    for token, value in tokens.items():
        assert token in page, f"{template_name} sin {token}"
        page = page.replace(token, value, 1)
    os.makedirs(pages_dir, exist_ok=True)
    with open(os.path.join(pages_dir, out_name), "w", encoding="utf-8") as f:
        f.write(page)
    # el release es autocontenido: css/js compartidos (y vendor/, p.ej.
    # Leaflet local — sin CDN la página sirve de verdad viajando) se copian
    # junto a la página
    for asset in os.listdir(ASSETS):
        src = os.path.join(ASSETS, asset)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(pages_dir, asset), dirs_exist_ok=True)
        else:
            shutil.copyfile(src, os.path.join(pages_dir, asset))
    print(f"pages/{trip}/{out_name} · {len(DAYS)} días · {len(refs.order)} modales · {len(page) // 1024} KB")
    if DIAGNOSTICS:
        print(f"⚠️ horario incompleto en el YAML ({len(DIAGNOSTICS)} pasos):")
        for d in DIAGNOSTICS:
            print("  ·", d)


def build_and_verify(trip, template_name, out_name, extra=None):
    """build_page + verify_roundtrip.py en subproceso (aislado a propósito:
    el verificador relee YAML y HTML desde cero, sin el estado de este
    módulo); imprime su veredicto y regresa el código de salida."""
    build_page(trip, template_name, out_name, extra=extra)
    r = subprocess.run([sys.executable, os.path.join(common.BUILD, "verify_roundtrip.py"),
                        trip, out_name],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode
