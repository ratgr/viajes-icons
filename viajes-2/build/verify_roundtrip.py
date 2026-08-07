# -*- coding: utf-8 -*-
"""verify_roundtrip.py — comprueba que itinerario.html es una proyección 1:1
de viaje.yaml: parsea el HTML generado, reconstruye días/pasos (invirtiendo el
markdown: <b>↔**, <i>↔*, <br>↔\\n, a.modal-link↔@[alt](clave)) y los compara
contra el YAML campo por campo.

Alcance: días (titulo/note/ancla/date) y pasos (location/transit/mode/time/
fixed/duration/title/note/solo_seleccion/hidden-summary/options anidadas).
Fuera de alcance (solo-mapa o derivado): coords/color de transits, y los
bloques data-derived de los modales (horario, frase, SUBIR/BAJAR, icono).
"""
import os
import sys
from html.parser import HTMLParser

import yaml

import contract
from common import resolve_trip, trip_paths

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
VOID = {"br", "img", "meta", "link", "input", "hr"}


class Node:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def cls(self):
        return (self.attrs.get("class") or "").split()


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def nodes(children, tag=None, klass=None):
    for c in children:
        if isinstance(c, Node) and (tag is None or c.tag == tag) and (klass is None or klass in c.cls()):
            yield c


def first(children, tag=None, klass=None):
    return next(nodes(children, tag, klass), None)


def text_of(node):
    out = []
    for c in node.children:
        out.append(c if isinstance(c, str) else text_of(c))
    return "".join(out)


def text_plain(node):
    """texto sin lo derivado ni separadores presentacionales (.sep)."""
    out = []
    for c in node.children:
        if isinstance(c, str):
            out.append(c)
        elif "data-derived" in c.attrs or "sep" in c.cls():
            continue
        else:
            out.append(text_plain(c))
    return "".join(out)


def to_md(children):
    """HTML renderizado → texto fuente (markdown + @[refs]); salta lo derivado."""
    out = []
    for c in children:
        if isinstance(c, str):
            out.append(c)
        elif "data-derived" in c.attrs:
            continue
        elif c.tag == "br":
            out.append("\n")
        elif c.tag == "i" and "line-chip" in c.cls():
            continue
        elif c.tag == "a" and "modal-link" in c.cls():
            key = contract.modal_key(c.attrs.get("href")) or ""
            out.append(f"@[{to_md(c.children)}]({key})")
        elif c.tag == "b":
            out.append("**" + to_md(c.children) + "**")
        elif c.tag == "i":
            out.append("*" + to_md(c.children) + "*")
        else:
            out.append(to_md(c.children))
    return "".join(out)


# ---------------------------------------------------------------- HTML → pasos
def parse_step(li):
    d = {}
    if "data-location" in li.attrs:
        d["location"] = li.attrs["data-location"]
    if "data-transit" in li.attrs:
        d["transit"] = li.attrs["data-transit"]
    if "data-mode" in li.attrs:
        d["mode"] = li.attrs["data-mode"]
    if "data-select-only" in li.attrs:
        d["select-only"] = True
    if "data-flex" in li.attrs:
        spec = li.attrs.get("data-flex") or ""
        d["duration"] = f"flex({spec})" if spec else "flex"
    if "hidden-summary" in li.cls():
        d["hidden-summary"] = True
    t = first(li.children, "time")
    if t is not None:
        # texto directo = time-from explícito (los spans from/to no cuentan)
        tt = "".join(c for c in t.children if isinstance(c, str)).strip()
        if tt:
            d["time-from"] = tt
        to = first(t.children, "span", "to")
        if to is not None and "data-derived" not in to.attrs:
            d["time-to"] = text_of(to).lstrip(contract.TIME_TO_DASH).strip()
        if "fixed" in t.cls():
            d["fixed"] = True
    body = first(li.children, "div", "body")
    inner = body.children if body else []
    wrap = first(inner, "span", "transit")
    if wrap is not None:
        inner = wrap.children + [c for c in inner if c is not wrap]
    for c in nodes(inner):
        if "data-derived" in c.attrs:      # duración inferida etc.: no es dato
            continue
        if c.tag == "b" and "title" in c.cls():
            if "data-value" in c.attrs:    # convención *-show: base en data-value
                d["title"] = c.attrs["data-value"]
                d["title-show"] = to_md(c.children).strip()
            else:
                d["title"] = to_md(c.children).strip()
        elif c.tag == "span" and "duration" in c.cls():
            if "data-value" in c.attrs:
                dur = c.attrs["data-value"]
                if dur.startswith("flex"):
                    spec = contract.norm_flex(dur[4:])
                    dur = f"flex({spec})" if spec else "flex"
                d["duration"] = dur
                d["duration-show"] = text_plain(c).strip()
            else:
                d["duration"] = text_plain(c).strip()
        elif c.tag == "span" and "note" in c.cls():
            note_md = contract.SEP_STRIP_RE.sub("", to_md(c.children)).strip()
            if "data-value" in c.attrs:
                d["note"] = c.attrs["data-value"]
                d["note-show"] = note_md
            else:
                d["note"] = note_md
        elif c.tag == "ul" and "options" in c.cls():
            d["options"] = [parse_opt(o) for o in nodes(c.children, "li")]
    return d


def parse_option_span(c):
    """span.option → plana {location, price} o enriquecida {title, price, steps}."""
    ul = first(c.children, "ul", "steps")
    price_el = first(c.children, "span", "price")
    e = {}
    if ul is not None:
        inline = [x for x in c.children
                  if x is not ul and not (isinstance(x, Node) and "price" in x.cls())]
        e["title"] = to_md(inline).strip()
        if price_el is not None:
            e["price"] = text_of(price_el).strip()
        e["steps"] = [parse_step(x) for x in nodes(ul.children, "li")]
    else:
        a = first(c.children, "a", "modal-link")
        e["location"] = (contract.modal_key(a.attrs.get("href")) or "") if a else ""
        if price_el is not None:
            e["price"] = text_of(price_el).strip()
    return e


def parse_opt(li):
    sub = first(li.children, "ul", "steps")
    b = first(li.children, "b")
    title = to_md(b.children).strip() if b else ""
    if sub is not None:
        d = {"title": title, "steps": [parse_step(x) for x in nodes(sub.children, "li")]}
    else:
        d = {"title": title,
             "options": [parse_option_span(c) for c in nodes(li.children, "span", "option")]}
    if li.attrs.get("class"):
        d["class"] = li.attrs["class"]
    return d


def parse_days(html_text):
    tb = TreeBuilder()
    tb.feed(html_text)

    def walk(n, out):
        for c in n.children:
            if isinstance(c, Node):
                if c.tag == "section" and "day" in c.cls():
                    out.append(c)
                walk(c, out)

    sections, days = [], []
    walk(tb.root, sections)
    for s in sections:
        head = first(s.children, "header")
        h3 = first(head.children, "h3")
        note = first(head.children, "span", "note")
        ancla = first(head.children, "span", "anchor")
        steps_ul = first(s.children, "ul", "steps")
        days.append({
            "title": text_of(h3).strip() if h3 else "",
            "note": text_of(note).strip() if note else "",
            "anchor": contract.ANCHOR_STRIP_RE.sub("", text_of(ancla).strip()) if ancla else "",
            "date": s.attrs.get("data-fecha", ""),
            "steps": [parse_step(li) for li in nodes(steps_ul.children, "li")],
        })
    return days


# ---------------------------------------------------------------- YAML → pasos
def norm_step(s):
    d = {}
    if s.get("location"):
        d["location"] = str(s["location"])
    if s.get("transit"):
        d["transit"] = str(s["transit"])
    if s.get("mode"):
        d["mode"] = str(s["mode"])
    if s.get("select-only"):
        d["select-only"] = True
    if s.get("hidden-summary"):
        d["hidden-summary"] = True
    if s.get("time-from") not in (None, ""):
        d["time-from"] = str(s["time-from"])
    if s.get("time-to") not in (None, ""):
        d["time-to"] = str(s["time-to"])
    if s.get("fixed"):
        d["fixed"] = True
    if s.get("duration") not in contract.SKIP_DUR:
        dur = str(s["duration"]).strip()
        if dur.startswith("flex"):
            spec = contract.norm_flex(dur[4:])   # flex( 30 - 60 ) ≡ flex(30-60)
            dur = f"flex({spec})" if spec else "flex"
        d["duration"] = dur
    if s.get("title"):
        d["title"] = contract.clean_title(s["title"])
    if s.get("note"):
        d["note"] = str(s["note"]).strip()
    # convención *-show (lo mostrado; el campo base sigue siendo el dato)
    if s.get("title-show"):
        d["title-show"] = contract.clean_title(s["title-show"])
    if s.get("note-show"):
        d["note-show"] = str(s["note-show"]).strip()
    if s.get("duration-show"):
        d["duration-show"] = str(s["duration-show"]).strip()
    if s.get("options"):
        d["options"] = [norm_opt(o) for o in s["options"] if isinstance(o, dict)]
    return d


def norm_opt(o):
    title = contract.clean_title(o.get("title", ""))
    if "steps" in o:
        d = {"title": title, "steps": [norm_step(x) for x in o["steps"] if isinstance(x, dict)]}
    else:
        opts = []
        for x in o.get("options", []):
            if not isinstance(x, dict):
                continue
            if "steps" in x or "title" in x:      # opción enriquecida
                e = {"title": str(x.get("title", "")).strip()}
                if x.get("price"):
                    e["price"] = str(x["price"]).strip()
                if x.get("steps"):
                    e["steps"] = [norm_step(s) for s in x["steps"] if isinstance(s, dict)]
            else:
                e = {"location": str(x.get("location") or "")}
                if x.get("price"):
                    e["price"] = str(x["price"]).strip()
            opts.append(e)
        d = {"title": title, "options": opts}
    if o.get("class"):
        d["class"] = str(o["class"])
    return d


def norm_day(day):
    date = day.get("date")
    return {
        "title": str(day.get("title", "")).strip(),
        "note": str(day.get("note", "")).strip(),
        "anchor": str(day.get("anchor", "")).strip(),
        "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
        "steps": [norm_step(s) for s in day.get("steps", []) if isinstance(s, dict)],
    }


# ---------------------------------------------------------------- comparación
def diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff(a.get(k), b.get(k), f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} vs {len(b)} elementos")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")


def main():
    trip = resolve_trip(sys.argv)
    page = sys.argv[2] if len(sys.argv) > 2 else "itinerario.html"
    src_dir, pages_dir, _ = trip_paths(trip)
    Y = yaml.safe_load(open(os.path.join(src_dir, "viaje.yaml"), encoding="utf-8"))
    html_days = parse_days(open(os.path.join(pages_dir, page), encoding="utf-8").read())
    yaml_days = [norm_day(d) for d in Y.get("days", [])]
    problems = []
    if len(html_days) != len(yaml_days):
        problems.append(f"días: {len(html_days)} en HTML vs {len(yaml_days)} en YAML")
    for i, (h, y) in enumerate(zip(html_days, yaml_days)):
        diff(y, h, f"d{i + 1}", problems)
    total = sum(len(d["steps"]) for d in yaml_days)
    if problems:
        print(f"round-trip: {len(problems)} diferencias ({total} pasos):")
        for p in problems[:40]:
            print("  ·", p)
        if len(problems) > 40:
            print(f"  … y {len(problems) - 40} más")
        return 1
    print(f"round-trip OK: {len(yaml_days)} días · {total} pasos — HTML ≡ YAML")
    return 0


if __name__ == "__main__":
    sys.exit(main())
