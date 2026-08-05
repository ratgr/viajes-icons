#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compile_itinerario.py — viaje.yaml -> bloque de itinerario HTML.

Genera, por cada día, un <div class="day"> con la misma pinta que el
itinerario hecho a mano en ../viajes/src/japon.html (reusa .slots/.fork/
.f1-3/.rl2/.t.fix), y ANEXA el resultado al fondo de la sección
itinerario, entre marcadores <!-- COMPILE:START/END -->, SIN borrar lo
que ya está escrito. Al final, tras un <hr>, pega los modales de cada
lugar referenciado con @[alt](clave).

Reglas de render de una fila (nodo):
  *TITLE* - duration - note        (markdown; duration/note si existen)
  columna izquierda .t = time      (rojo .fix si fixed, gris si no)
  transit  -> travel (aquí solo la fila; el mapa va aparte)
  location -> punto
  options  -> grupos (tiers); el grupo activo se ve, los demás fantasma
"""
import os, re, sys, html
import yaml
from modales import render_line_modal, add_min   # modal de línea centralizado (con horario)

def dmin(s):
    s = str(s or "")
    hm = re.search(r"(\d+)\s*h\s*(\d+)?", s)
    if hm:
        return int(hm.group(1)) * 60 + int(hm.group(2) or 0)
    m = re.search(r"(\d+)\s*min", s)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)", s)
    return int(m2.group(1)) if m2 else 0

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SD, "viaje.yaml")
DST = os.path.abspath(os.path.join(SD, "..", "viajes", "src", "japon.html"))
FOTO_BASE = "https://ratgr.github.io/viajes-icons/"

START = "<!-- COMPILE:START (viaje.yaml -> no editar a mano) -->"
END = "<!-- COMPILE:END -->"

# tier title -> clase de color existente (.f3 matcha, .f2 ai, .f1 shu)
TIER_CLASS = {"Take": "f3", "Ai": "f2", "Shu": "f1"}

data = yaml.safe_load(open(SRC, encoding="utf-8"))
PLACES = data.get("places", {})
LINEAS = data.get("lineas", {})
TRANSITS = data.get("transits", {})
_LINE_N = {v.get("nombre"): v for v in LINEAS.values() if v.get("frecuencia")}
_LINE_C = {v.get("chip"): v for v in LINEAS.values() if v.get("frecuencia") and v.get("chip")}
def _line_meta(tr):
    l = _LINE_N.get(tr.get("linea")) or _LINE_C.get(tr.get("chip")) or {}
    return {k: l[k] for k in ("frecuencia", "primer_tren", "ultimo_tren", "frecuencia_fuente") if l.get(k)}

# ---- markdown mínimo + extensión @[alt](clave) --------------------
REF_RE = re.compile(r"@\[(.+?)\]\((.+?)\)")

def md(s, refs=None):
    if s is None:
        return ""
    s = str(s).strip()
    s = html.escape(s, quote=False)
    def _ref(m):
        alt, key = m.group(1), m.group(2)
        if refs is not None:
            refs.add(key)
        # chip de color de línea si la clave es un transit con identidad
        tr = TRANSITS.get(key, {})
        chip = ""
        if tr.get("color"):
            lcls = "lc" if tr.get("chip") else "lc lcd"
            chip = f'<i class="{lcls}" style="background:{tr["color"]}">{html.escape(tr.get("chip",""))}</i>'
        return f'<a class="mlink" href="#m-{key}">{chip}{alt}</a>'
    s = REF_RE.sub(_ref, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = s.replace("\n", "<br>")   # respeta los saltos de línea del YAML
    return s

def node_kind(n):
    if "location" in n:
        return "location"
    if "transit" in n:
        return "transit"
    if "options" in n:
        return "options"
    return "?"

def row_text(n, refs):
    """*TITLE* - duration - note  (markdown compilado)."""
    parts = []
    title = n.get("title")
    if title:
        parts.append(f"**{title}**")
    dur = n.get("duration")
    if dur not in (None, 0, "0"):
        parts.append(str(dur))
    note = n.get("note")
    if note:
        parts.append(str(note).strip())   # conserva \n; md() los vuelve <br>
    return md(" - ".join(parts), refs)

def time_cell(n):
    t = n.get("time") or ""
    cls = "t fix" if n.get("fixed") else "t"
    return f'<span class="{cls}">{html.escape(str(t))}</span>'

def resto_link(opt, refs):
    """opción hoja tipo { location: acchichi, precio: ¥600 }."""
    key = opt.get("location")
    pl = PLACES.get(key, {})
    nombre = html.escape(pl.get("nombre", key or "?"))
    if key:
        refs.add(key)
    lk = f'<a class="rl2 mlink" href="#m-{key}">{nombre}</a>' if key else nombre
    precio = opt.get("precio")
    return lk + (f' {html.escape(str(precio))}' if precio else "")

def render_fork(node, refs):
    """options node -> .fork con un grupo por tier; no activos = fantasma."""
    groups = []
    for tier in node.get("options", []):
        cls = TIER_CLASS.get(tier.get("title", ""), "f0")
        label = html.escape(tier.get("title", ""))
        inner = " · ".join(resto_link(o, refs) for o in tier.get("options", []))
        groups.append(f'<span class="{cls}"><b>{label}</b>{inner}</span>')
    return '<span class="fork">' + "".join(groups) + "</span>"

def render_plans(node, refs):
    """options node donde cada opción tiene sub-steps (planes en paralelo)."""
    out = ['<div class="plans">']
    for i, pl in enumerate(node.get("options", [])):
        gcls = f"g{min(i + 1, 3)}"          # colores g1/g2/g3 (morado/oro/rosa) como el viejo
        title = md(pl.get("title", ""), refs)
        subs = "\n".join(render_li(s, refs) for s in pl.get("steps", []) if not s.get("hidden-summary"))
        out.append(f'<div class="plan {gcls}"><div class="plan-h"><b>{title}</b></div>'
                   f'<ul class="slots">\n{subs}\n</ul></div>')
    out.append("</div>")
    return "".join(out)

def render_li(n, refs):
    k = node_kind(n)
    if k == "options":
        if any("steps" in o for o in n.get("options", [])):   # planes anidados
            body = row_text(n, refs) + render_plans(n, refs)
        else:
            body = row_text(n, refs) + render_fork(n, refs)
    else:
        body = row_text(n, refs)
    # los trayectos van en gris (.d) para que resalten los lugares
    inner = f'<span class="d">{body}</span>' if k == "transit" else body
    return f"    <li>{time_cell(n)}<span>{inner}</span></li>"

def render_day(day, refs):
    titulo = html.escape(day.get("titulo", ""))
    note = html.escape(day.get("note", ""))
    ancla = html.escape(day.get("ancla", ""))
    fecha = day.get("date")
    fecha = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
    head = (
        f'<div class="day-head"><h3>{titulo}</h3>'
        f'<span class="theme">{note}</span>'
        f'<span class="anchor-tag">Ancla: {ancla}</span></div>'
    )
    lis = "\n".join(render_li(s, refs) for s in day.get("steps", []) if not s.get("hidden-summary"))
    return (
        f'  <div class="day" data-fecha="{fecha}">{head}\n'
        f'  <ul class="slots">\n{lis}\n  </ul></div>'
    )

def render_place_modal(key, pl):
    nombre = html.escape(pl.get("nombre", key))
    out = [f'<div class="cmodal" id="m-{key}"><h3>{nombre}</h3>']
    if pl.get("imagen"):
        _im = pl["imagen"]
        _src = _im if _im.startswith("http") else f"{FOTO_BASE}{_im}"   # URL absoluta (Maps) tal cual
        out.append(f'<img src="{_src}" alt="{nombre}" loading="lazy" '
                   f'onerror="this.style.display=&#39;none&#39;">')
    if pl.get("descripcion"):
        out.append(f"<p>{md(pl['descripcion'])}</p>")
    if pl.get("informacion"):
        out.append(f'<p class="cmodal-info">{md(pl["informacion"])}</p>')
    if pl.get("horario"):
        hf = str(pl.get("horario_fuente", ""))
        if hf == "maps":
            src = ' <span style="opacity:.55;font-size:11px">· Google Maps</span>'
        elif hf.startswith("http"):
            src = f' <a href="{html.escape(hf)}" target="_blank" rel="noopener" style="opacity:.6;font-size:11px">fuente ↗</a>'
        else:
            src = ""
        out.append(f'<p class="cmodal-info">🕒 <b>Horario:</b> {html.escape(str(pl["horario"]))}{src}</p>')
    if pl.get("maps"):
        out.append(f'<a class="cmbtn" href="{html.escape(pl["maps"])}" target="_blank" rel="noopener">Abrir en Maps ↗</a>')
    out.append("</div>")
    return "".join(out)


# transit → su step (para el horario desde/hasta del modal)
TRANSIT_STEP = {}
for _d in data.get("days", []):
    for _s in _d.get("steps", []):
        if "transit" in _s:
            TRANSIT_STEP.setdefault(_s["transit"], _s)

# colores de tema de la app (el modal se adapta a claro/oscuro)
SOFT, BOX = "var(--ink-soft)", "var(--paper-2)"

def render_modal(key):
    if key in PLACES:
        return render_place_modal(key, PLACES[key])
    if key in TRANSITS and TRANSITS[key].get("nombre_jp"):
        tr = TRANSITS[key]
        # identidad copiada en el propio transit (no compartida)
        ident = {"nombre": tr.get("linea", key), "nombre_jp": tr.get("nombre_jp", ""),
                 "chip": tr.get("chip", ""), "color": tr.get("color", "#555"),
                 "reconoce": tr.get("reconoce", ""), **_line_meta(tr)}
        ride = {k: tr[k] for k in ("anden", "reverso", "estaciones", "vehiculo") if k in tr}
        st = TRANSIT_STEP.get(key, {})
        horario = None
        if tr.get("estaciones") and st.get("time"):
            horario = {"origen": tr["estaciones"][0][2], "destino": tr["estaciones"][-1][2],
                       "desde": str(st["time"]), "hasta": add_min(st["time"], dmin(st.get("duration")))}
        return render_line_modal(key, ident, ride, tr.get("guia"), horario, SOFT, BOX)
    if key in LINEAS:
        return render_line_modal(key, LINEAS[key], None, soft=SOFT, box=BOX)
    return f'<div class="cmodal" id="m-{key}"><h3>{html.escape(key)}</h3></div>'

# ---- construir bloque ---------------------------------------------
refs = set()
ref_order = []           # orden de primera aparición
class OrderedRefs(set):
    def add(self, k):
        if k not in self:
            ref_order.append(k)
        super().add(k)
refs = OrderedRefs()

days_html = "\n\n".join(render_day(d, refs) for d in data.get("days", []))
modals_html = "\n".join(render_modal(k) for k in ref_order)

STYLE = """<style>
  /* --- compilado desde viaje.yaml --- */
  .mlink { color: inherit; text-decoration: underline dotted; text-underline-offset: 2px; cursor: pointer; }
  .mlink:hover { color: var(--shu); }
  .plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 8px; }
  @media (max-width: 900px) { .plans { grid-template-columns: 1fr; } }
  .plan { border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px 8px; }
  .plan-h { font-size: 13.5px; border-bottom: 1px solid var(--line); padding-bottom: 4px; margin-bottom: 2px; }
  .plan-h b { font-size: 13.5px; }
  .plan .slots li { grid-template-columns: 52px minmax(0,1fr); font-size: 13px; padding: 4px 0; }
  #cmodals { display: none; }
  .cmodal h3 { margin: 0 0 8px; font-size: 18px; }
  .cmodal img { max-width: 100%; border-radius: 6px; margin: 0 0 10px; display: block; }
  .cmodal p { margin: 0 0 8px; font-size: 14px; }
  .cmodal-info { color: var(--ink-soft); font-size: 13px; }
  .cmbtn { display: inline-block; margin-top: 4px; border: 1px solid var(--line); background: var(--paper-2); color: var(--ink); border-radius: 6px; padding: 6px 14px; font: 600 13px "Segoe UI", system-ui, sans-serif; text-decoration: none; }
  /* popup overlay */
  .cpop { position: fixed; inset: 0; z-index: 60; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.45); padding: 16px; box-sizing: border-box; }
  .cpop.open { display: flex; }
  .cpop-card { position: relative; background: var(--card); border-top: 5px solid var(--shu); border-radius: 8px; max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; box-shadow: 0 12px 50px rgba(0,0,0,.35); padding: 22px 24px; box-sizing: border-box; }
  .cpop-card .cmodal { border: none; margin: 0; padding: 0; }
  .cpop-x { position: absolute; top: 8px; right: 12px; border: none; background: transparent; font-size: 24px; line-height: 1; color: var(--ink-soft); cursor: pointer; }
</style>"""

SCRIPT = """<script>(function(){
  var pop = document.getElementById('cpop'), body = document.getElementById('cpop-body');
  function openM(id){ var s = document.getElementById(id); if(!s) return; body.innerHTML = s.outerHTML; pop.classList.add('open'); }
  function closeM(){ pop.classList.remove('open'); body.innerHTML = ''; }
  document.addEventListener('click', function(e){
    var a = e.target.closest ? e.target.closest('.mlink') : null;
    if(a){ var h = a.getAttribute('href')||''; if(h.indexOf('#m-')===0){ e.preventDefault(); openM('m-'+h.slice(3)); return; } }
    if(e.target === pop || (e.target.closest && e.target.closest('.cpop-x'))) closeM();
  });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeM(); });
})();</script>"""

block = (
    f"{START}\n"
    f"{STYLE}\n"
    f"{days_html}\n"
    f'  <div id="cmodals">\n{modals_html}\n  </div>\n'
    f'  <div class="cpop" id="cpop"><div class="cpop-card"><button class="cpop-x" type="button" aria-label="Cerrar">×</button><div id="cpop-body"></div></div></div>\n'
    f"{SCRIPT}\n"
    f"{END}"
)

# ---- SUSTITUIR el itinerario a mano por el generado ----------------
htmltext = open(DST, encoding="utf-8").read()
MARK = "<!-- ITIN:GEN (viaje.yaml genera el itinerario) -->"
# quitar cualquier bloque compilado previo
htmltext = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n*", "", htmltext, flags=re.S)
i_deseos = htmltext.index('<section data-tab="deseos">')
i_close = htmltext.rindex("</section>", 0, i_deseos)   # cierre de la sección itinerario
if MARK in htmltext:
    # re-run: reemplazar desde el marcador hasta el cierre de la sección
    i_mark = htmltext.index(MARK)
    htmltext = htmltext[:i_mark] + MARK + "\n" + block + "\n" + htmltext[i_close:]
    action = "regenerado (sustituye al de mano)"
else:
    # primera vez: conservar el intro (h2 + explicación), quitar los días a mano
    i_sec = htmltext.index('<section data-tab="itinerario">')
    i_day1 = htmltext.index('<div class="day"', i_sec)
    htmltext = htmltext[:i_day1] + MARK + "\n" + block + "\n" + htmltext[i_close:]
    action = "sustituido el itinerario a mano"

open(DST, "w", encoding="utf-8").write(htmltext)
print(f"[{action}] {len(ref_order)} modales, {len(data.get('days',[]))} día(s) -> {DST}")
print("refs:", ", ".join(ref_order))
