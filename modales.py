# -*- coding: utf-8 -*-
"""Render de modales ricos (lugar / línea-ride) — self-contained, sirve para
el mapa (leaflet) y el itinerario. Colores concretos (no var()) para que se
vea igual sin depender del CSS del contenedor. Incluye MODAL_CSS para inyectar."""
import re, html

REF_RE = re.compile(r"@\[(.+?)\]\((.+?)\)")
VJP = {"tren": "電車", "bus": "バス", "barco": "船"}
VRO = {"tren": "densha", "bus": "basu", "barco": "fune"}

def md(s, refs=None):
    if s is None:
        return ""
    s = html.escape(str(s).strip(), quote=False)
    def _ref(m):
        if refs is not None:
            refs.add(m.group(2))
        return f'<a class="mlink" href="#m-{m.group(2)}">{m.group(1)}</a>'
    s = REF_RE.sub(_ref, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = s.replace("\n", "<br>")
    return s

def render_place_modal(key, pl, foto_base, plan_url=None):
    nombre = html.escape(pl.get("nombre", key))
    out = [f'<div class="cmodal" id="m-{key}"><h3>{nombre}</h3>']
    if pl.get("imagen"):
        _im = pl["imagen"]
        _src = _im if _im.startswith("http") else f"{foto_base}{_im}"   # URL absoluta tal cual
        out.append(f'<img src="{_src}" alt="{nombre}" loading="lazy" '
                   f'onerror="this.style.display=&#39;none&#39;">')
    if pl.get("descripcion"):
        out.append(f"<p>{md(pl['descripcion'])}</p>")
    if pl.get("informacion"):
        out.append(f'<p class="cmodal-info">{md(pl["informacion"])}</p>')
    btns = []
    if pl.get("maps"):
        btns.append(f'<a class="mbtn" href="{html.escape(pl["maps"])}" target="_blank" rel="noopener">Abrir en Maps ↗</a>')
    if plan_url:
        btns.append(f'<a class="mbtn" href="{html.escape(plan_url)}" target="_blank" rel="noopener">Ver en itinerario ↗</a>')
    if btns:
        out.append('<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">' + "".join(btns) + "</div>")
    out.append("</div>")
    return "".join(out)

def add_min(hhmm, mins):
    """'21:45' + 10 → '21:55' (sin depender de datetime)."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(hhmm or "").strip())
    if not m:
        return ""
    total = (int(m.group(1)) * 60 + int(m.group(2)) + int(mins or 0)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"

def render_line_modal(key, ident, ride=None, guia=None, horario=None, soft="#7a7268", box="#f2ede3"):
    color = ident.get("color", "#555")
    chip = ident.get("chip", "")
    jp = html.escape(ident.get("nombre_jp", ""))
    nombre = html.escape(ident.get("nombre", key))
    rng = ""
    if horario and horario.get("desde") and horario.get("hasta"):
        rng = f' <span style="font-weight:400;color:{soft}">· {html.escape(str(horario["desde"]))} – {html.escape(str(horario["hasta"]))}</span>'
    h = [f'<div class="cmodal" id="m-{key}"><h3>{nombre}{rng}</h3>']
    chiphtml = (f'<div style="margin-top:8px"><span style="display:inline-block;background:#fff;'
                f'color:{color};border-radius:50%;min-width:30px;height:30px;line-height:30px;'
                f'font-weight:800;font-size:15px;padding:0 3px">{html.escape(chip)}</span></div>') if chip else ""
    h.append(f'<div style="background:{color};color:#fff;border-radius:10px;padding:14px 12px;'
             f'text-align:center;margin-bottom:12px"><div style="font-size:26px;font-weight:700;'
             f'line-height:1.2">{jp}</div>{chiphtml}</div>')
    # renglón de horario: Sale {desde} · origen → destino · Llega {hasta}
    if horario and (horario.get("desde") or horario.get("hasta")):
        o = html.escape(str(horario.get("origen", "")))
        d = html.escape(str(horario.get("destino", "")))
        desde = html.escape(str(horario.get("desde", "")))
        hasta = html.escape(str(horario.get("hasta", "")))
        h.append(f'<div style="display:flex;justify-content:space-between;gap:8px;background:{box};'
                 f'border-radius:8px;padding:8px 12px;margin:0 0 12px;font-size:13px">'
                 f'<span>🟢 <b>Sale {desde}</b><br><span style="color:{soft}">{o}</span></span>'
                 f'<span style="align-self:center;color:{soft}">→</span>'
                 f'<span style="text-align:right">🔴 <b>Llega {hasta}</b><br><span style="color:{soft}">{d}</span></span></div>')
    if ride:
        anden = ride.get("anden", ["", ""])
        veh = ride.get("vehiculo", "tren")
        # terminología del punto de abordaje según el vehículo
        ic, lab, word = {"barco": ("🛳️", "Embarcadero correcto", "muelle"),
                         "bus": ("🚏", "Parada correcta", "lado")}.get(veh, ("🧭", "Andén correcto", "andén"))
        h.append(f'<p style="margin:0 0 8px">{ic} <b>{lab}:</b> letrero '
                 f'<b style="font-size:17px">{html.escape(str(anden[0]))}</b> — {html.escape(str(anden[1]))}</p>')
        if ride.get("reverso"):
            h.append(f'<p style="margin:0 0 10px">⚠️ Si la primera parada es '
                     f'<b>{html.escape(str(ride["reverso"]))}</b>, van al revés: bajarse y cruzar de {word}.</p>')
        est = ride.get("estaciones", [])
        if est:
            h.append(f'<div style="border-left:3px solid {color};padding-left:10px;margin:0 0 12px">')
            for i, st in enumerate(est):
                code, sjp, srom = (list(st) + ["", "", ""])[:3]
                tag = " 🟢 <small><b>SUBIR</b></small>" if i == 0 else (
                    " 🔴 <small><b>BAJAR</b></small>" if i == len(est) - 1 else "")
                dot = (f'<span class="lc" style="background:{color};min-width:26px;border-radius:9px">'
                       f'{html.escape(str(code))}</span> ') if code else "· "
                h.append(f'<div style="padding:3px 0">{dot}<b>{html.escape(str(sjp))}</b> '
                         f'<span style="color:#7a7268;font-size:12px">{html.escape(str(srom))}</span>{tag}</div>')
            h.append("</div>")
            dest = est[-1]
            djp, drom = html.escape(str(dest[1])), html.escape(str(dest[2]))
            veh = ride.get("vehiculo", "tren")
            eki = "駅" if (veh == "tren" and "駅" not in str(dest[1]) and "ターミナル" not in str(dest[1])) else ""
            h.append(f'<div style="background:#f2ede3;border-radius:10px;padding:10px 12px;margin:0 0 12px">'
                     f'<div style="font-size:19px;line-height:1.6">すみません、{djp}{eki}へ行きたいです。この{VJP.get(veh,"電車")}で合っていますか？</div>'
                     f'<div style="color:#7a7268;font-size:13px;margin-top:4px">Sumimasen, {drom}{"-eki" if eki else ""} e ikitai desu. Kono {VRO.get(veh,"densha")} de atte imasu ka?</div>'
                     f'<div style="font-size:12px;margin-top:4px">«Disculpe, quiero ir a {drom}. ¿Voy bien en este {veh}?» — muéstrale el teléfono a cualquier local o uniformado.</div></div>')
    reconoce = html.escape(ident.get("reconoce", ""))
    h.append(f'<b>Se reconoce:</b> {reconoce}{" — letra <b>"+html.escape(chip)+"</b>" if chip else ""}.')
    texto = guia or ident.get("extra", "")
    if texto:
        h.append(f"<br><br>{md(texto)}")
    h.append("</div>")
    return "".join(h)

# CSS self-contained para inyectar donde se muestren los modales (mapa).
MODAL_CSS = """
  .cmodal{font:14px/1.45 system-ui,sans-serif;color:#241f1c;max-width:300px}
  .cmodal h3{margin:0 0 8px;font-size:17px}
  .cmodal img{max-width:100%;border-radius:6px;margin:0 0 10px;display:block}
  .cmodal p{margin:0 0 8px}
  .cmodal-info{color:#7a7268;font-size:13px}
  .cmodal .lc{display:inline-block;color:#fff;text-align:center;font-weight:700;font-size:11px;padding:1px 4px;line-height:1.7}
  .cmodal .mbtn{display:inline-block;margin-top:4px;border:1px solid #e2dacc;background:#f6f2ea;color:#241f1c;border-radius:6px;padding:6px 14px;font:600 13px system-ui;text-decoration:none}
  .cmodal .mlink{color:#b23a2a;text-decoration:underline dotted}
"""
