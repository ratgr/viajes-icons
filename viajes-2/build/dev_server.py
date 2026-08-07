# -*- coding: utf-8 -*-
"""dev_server.py — servidor local de desarrollo (solo 127.0.0.1).

Sirve el directorio PADRE del repo (para ver pages/ y el app viejo) con
Cache-Control: no-store, y expone la API del modo dev del mapa — editar
pasos del YAML directamente desde la página:

    GET  /api/step?trip=X&day=N&step=M     YAML del paso (para el editor)
    POST /api/step {trip, day, step, yaml} valida y escribe src/<trip>/viaje.yaml
                                           (SIN rebuild: se editan varios y luego…)
    GET  /api/entity?trip=X&key=K[&kind=]  YAML de la entidad referenciada
                                           (busca en places → transits → lines)
    POST /api/entity {trip,kind,key,yaml}  escribe la entidad en su catálogo
    POST /api/step-insert {trip,day,step,where}  inserta un paso nuevo
                                           antes/después de la fila dada
    POST /api/step-move {trip,day,step,dir}      mueve el paso una posición
                                           (dir=-1 sube, dir=1 baja)
    POST /api/rebuild {trip}               reconstruye pages/<trip>/

La fila dN-rMM del HTML ES el paso M del día N del YAML (proyección 1:1),
así que la identidad de la edición sale del id de la fila.

Uso: python build/dev_server.py [puerto]      (default 8791)
"""
import contextlib
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, dump_yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SERVE_DIR = os.path.dirname(ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8791
CATALOGS = ("places", "transits", "lines")

# ---------- compartir las dev-tools: OAuth device flow de GitHub ----------
# `--share` escucha en 0.0.0.0 (túnel/LAN). Desde localhost no se pide login;
# desde fuera, TODO /api/ exige sesión de un usuario del allowlist (device
# flow: el server habla con GitHub, el navegador solo enseña el código).
SHARE = "--share" in sys.argv
BIND = "0.0.0.0" if SHARE else "127.0.0.1"
ALLOW_USERS = set((os.environ.get("TF_DEV_ALLOW") or "ratgr").split(","))
# client_id público del GitHub CLI (device flow habilitado); cámbialo con
# TF_DEV_OAUTH_CLIENT si prefieres tu propia OAuth App
OAUTH_CLIENT = os.environ.get("TF_DEV_OAUTH_CLIENT", "178c6fc778ccc68e1d6a")
_SESSIONS = {}      # sid → login de GitHub
_LOGINS = {}        # handle → device_code en curso
# cada cambio guardado se COMMITEA solo; deploy = copiar pages/ al repo de
# Pages y push (rebuild con {"deploy": true} o el botón Deploy del cajón)
AUTO_COMMIT = True
PAGES_REPO = os.path.join(os.path.dirname(ROOT), "viajes-icons")
PAGES_SUBDIR = "viajes2"


def _github(url, data=None, token=None):
    import urllib.request
    hdrs = {"Accept": "application/json", "User-Agent": "viajes-2 dev"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, body, hdrs)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def git_commit(repo, paths, message):
    """commit silencioso (no falla el request si no hay nada que commitear)."""
    if not AUTO_COMMIT:
        return
    try:
        subprocess.run(["git", "-C", repo, "add"] + paths, check=True,
                       capture_output=True, timeout=30)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", message],
                       capture_output=True, timeout=30)
    except Exception as e:
        print("aviso git:", e)


def deploy_pages(trip):
    """pages/<trip>/ → viajes-icons/viajes2/ + commit + push (Pages publica)."""
    src = os.path.join(ROOT, "pages", trip)
    dst = os.path.join(PAGES_REPO, PAGES_SUBDIR)
    if not os.path.isdir(src) or not os.path.isdir(PAGES_REPO):
        raise ValueError("no encuentro pages/ o el repo de Pages")
    import shutil
    shutil.copytree(src, dst, dirs_exist_ok=True)
    git_commit(PAGES_REPO, [PAGES_SUBDIR], f"viajes2: deploy desde dev ({trip})")
    r = subprocess.run(["git", "-C", PAGES_REPO, "push", "-q"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ValueError("push falló: " + (r.stderr or "").strip()[-200:])
    return "desplegado"


def yaml_path(trip):
    p = os.path.abspath(os.path.join(ROOT, "src", trip, "viaje.yaml"))
    # separador final: sin él, '../srcotra' pasaba el filtro de prefijo
    if not p.startswith(os.path.join(ROOT, "src", "")):
        raise ValueError(f"viaje inválido: {trip}")
    return p


# el servidor es multihilo: el candado debe cubrir CADA secuencia completa
# leer-modificar-guardar (no solo la lectura y la escritura por separado —
# dos POST simultáneos se pisaban la edición en silencio). RLock: load/save
# también se usan solos.
_YAML_LOCK = threading.RLock()


def load(trip):
    with _YAML_LOCK:
        return yaml.safe_load(open(yaml_path(trip), encoding="utf-8"))


def save(trip, data):
    """escritura atómica: tmp + replace, bajo el lock."""
    path = yaml_path(trip)
    tmp = path + ".tmp"
    with _YAML_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(dump_yaml(data))
        os.replace(tmp, path)


@contextlib.contextmanager
def edit(trip):
    """leer-modificar-guardar ATÓMICO: candado sostenido todo el trayecto."""
    with _YAML_LOCK:
        Y = load(trip)
        yield Y
        save(trip, Y)


def steps_of(Y, day):
    """lista de pasos del día 1-based — con validación de rango (el indexado
    negativo de Python convertía day=0 en 'el último día' sin error)."""
    d = int(day)
    if not 1 <= d <= len(Y.get("days", [])):
        raise ValueError(f"día fuera de rango: {day}")
    return Y["days"][d - 1]["steps"]


def step_at(Y, day, step):
    steps = steps_of(Y, day)
    s = int(step)
    if not 1 <= s <= len(steps):
        raise ValueError(f"paso fuera de rango: {step}")
    return steps, s - 1


# ---------- edición de YAML por TEXTO CRUDO ----------
# El editor manda/recibe el texto TAL CUAL está en el archivo (desindentado
# al nivel superior): los comentarios y el formato del usuario sobreviven.
# yaml.compose() da los marks de línea para ubicar el span de cada paso.

def _seq_item_span(seq, idx, n_lines):
    """(línea_inicio, línea_fin_exclusiva, columna_del_guion) del item idx."""
    item = seq.value[idx]
    start = item.start_mark.line
    if idx + 1 < len(seq.value):
        end = seq.value[idx + 1].start_mark.line
    else:
        # último item: el end_mark del ITEM (el de la secuencia se pasa de
        # largo hacia la estructura de AFUERA en listas anidadas)
        em = item.end_mark
        end = em.line + (1 if em.column > 0 else 0)
    return start, min(end, n_lines), item.start_mark.column - 2


def _map_get(node, key):
    for k, v in node.value:
        if k.value == key:
            return v
    raise ValueError(f"clave '{key}' no encontrada")


def _resolve_step_seq(root, day, step, sub=""):
    """navega hasta la SECUENCIA que contiene el paso y su índice; sub es un
    sufijo de id tipo '-g1-s2' (plan) o '-g1-o2-s3' (opción de tier)."""
    days = _map_get(root, "days")
    d = int(day)
    if not 1 <= d <= len(days.value):
        raise ValueError(f"día fuera de rango: {day}")
    seq = _map_get(days.value[d - 1], "steps")
    s = int(step)
    if not 1 <= s <= len(seq.value):
        raise ValueError(f"paso fuera de rango: {step}")
    idx = s - 1
    for part in [p for p in (sub or "").split("-") if p]:
        kind, n = part[0], int(part[1:]) - 1
        node = seq.value[idx]
        if kind == "g":
            seq = _map_get(node, "options")
        elif kind == "o":
            seq = _map_get(node, "options")
        elif kind == "s":
            seq = _map_get(node, "steps")
        else:
            raise ValueError(f"sub-ruta inválida: {sub}")
        if not 0 <= n < len(seq.value):
            raise ValueError(f"sub-índice fuera de rango: {part}")
        idx = n
    return seq, idx


def _dedent_line(ln, col):
    """quita col espacios preservando las líneas EN BLANCO (antes se comían
    su salto de línea y desaparecían del texto)."""
    if not ln.strip():
        return "\n" if ln.endswith("\n") else ln
    return ln[col:] if ln[:col].strip() == "" else ln.lstrip()


def raw_step(trip, day, step, sub=""):
    """texto CRUDO del paso, desindentado (sin el '- ' del item)."""
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    seq, idx = _resolve_step_seq(yaml.compose(text), day, step, sub)
    start, end, col = _seq_item_span(seq, idx, len(lines))
    out = []
    for i, ln in enumerate(lines[start:end]):
        if i == 0:
            out.append(ln[col + 2:] if ln[:col + 2].strip() in ("-",) else ln.lstrip())
        else:
            out.append(_dedent_line(ln, col + 2))
    return "".join(out)


def _reindent(raw, col):
    """texto del editor → bloque de item de lista con guion en la columna col
    (las líneas en blanco — incluidas las del final — se preservan)."""
    pad = " " * (col + 2)
    out = []
    for i, ln in enumerate(raw.splitlines(keepends=True)):
        body = ln.rstrip("\n")
        if i == 0:
            out.append(" " * col + "- " + body + "\n")
        elif body.strip():
            out.append(pad + body + "\n")
        else:
            out.append("\n")
    return "".join(out)


def _splice(trip, start, end, block):
    """reemplaza lines[start:end] por block (texto) — atómico, bajo el lock."""
    path = yaml_path(trip)
    with _YAML_LOCK:
        lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
        new = "".join(lines[:start]) + block + "".join(lines[end:])
        yaml.safe_load(new)          # el archivo COMPLETO debe seguir siendo válido
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, path)


def save_step_raw(trip, day, step, raw, sub=""):
    obj = yaml.safe_load(raw)
    if not isinstance(obj, dict):
        raise ValueError("el YAML debe ser un mapeo (un paso)")
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        seq, idx = _resolve_step_seq(yaml.compose(text), day, step, sub)
        start, end, col = _seq_item_span(seq, idx, len(lines))
        _splice(trip, start, end, _reindent(raw, col))


def insert_step_raw(trip, day, step, where, sub=""):
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        seq, idx = _resolve_step_seq(yaml.compose(text), day, step, sub)
        start, end, col = _seq_item_span(seq, idx, len(lines))
        at = start if where == "before" else end
        _splice(trip, at, at, " " * col + "- title: (nuevo paso)\n")
        return idx + 1 if where == "before" else idx + 2


def move_step_raw(trip, day, step, direction, sub=""):
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        seq, idx = _resolve_step_seq(yaml.compose(text), day, step, sub)
        j = idx + int(direction)
        if not (0 <= j < len(seq.value) and j != idx):
            raise ValueError("movimiento fuera de rango")
        a0, a1, _ = _seq_item_span(seq, idx, len(lines))
        b0, b1, _ = _seq_item_span(seq, j, len(lines))
        blk_a = "".join(lines[a0:a1])
        blk_b = "".join(lines[b0:b1])
        if idx < j:
            new = "".join(lines[:a0]) + blk_b + blk_a + "".join(lines[b1:])
        else:
            new = "".join(lines[:b0]) + blk_a + blk_b + "".join(lines[a1:])
        yaml.safe_load(new)
        path = yaml_path(trip)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, path)
        return j + 1


def _entity_span(root, kinds, key, n_lines):
    """span de líneas del PAR completo 'clave: valor' en su catálogo (incluye
    la línea de la clave: el editor lo ve con encabezado, dedentado 2)."""
    for kind in kinds:
        try:
            cat = _map_get(root, kind)
        except ValueError:
            continue
        for i, (k, v) in enumerate(cat.value):
            if k.value != key:
                continue
            start = k.start_mark.line
            if i + 1 < len(cat.value):
                end = cat.value[i + 1][0].start_mark.line
            else:
                em = cat.end_mark
                end = em.line + (1 if em.column > 0 else 0)
            return kind, start, min(end, n_lines), k.start_mark.column
    raise ValueError(f"'{key}' no está en {'/'.join(kinds)}")


def raw_entity(trip, key, kind=None):
    kinds = [kind] if kind in CATALOGS else CATALOGS
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    k, start, end, col = _entity_span(yaml.compose(text), kinds, key, len(lines))
    out = [_dedent_line(ln, col) for ln in lines[start:end]]
    return k, "".join(out)


def save_entity_raw(trip, kind, key, raw):
    obj = yaml.safe_load(raw)
    if not isinstance(obj, dict) or list(obj.keys()) != [key]:
        raise ValueError(f"el YAML debe ser el bloque completo '{key}: …'")
    with _YAML_LOCK:
        text = open(yaml_path(trip), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        root = yaml.compose(text)
        try:
            _k, start, end, col = _entity_span(root, [kind], key, len(lines))
        except ValueError:
            # clave NUEVA: se crea al FINAL de su catálogo (referencia sin
            # cumplir → entra al mapa como conector pendiente hasta tener geo)
            cat = _map_get(root, kind)
            if not cat.value:
                raise ValueError(f"catálogo {kind} vacío: agrégala a mano")
            last_key = cat.value[-1][0].value
            _k, _s, end, col = _entity_span(root, [kind], last_key, len(lines))
            start = end
        pad = " " * col
        block = "".join((pad + ln if ln.strip() else ("\n" if ln.endswith("\n") else ln))
                        for ln in raw.splitlines(True))
        if not block.endswith("\n"):
            block += "\n"
        _splice(trip, start, end, block)


def rebuild(trip):
    # bajo el candado: un Guardar aterrizando entre los dos scripts producía
    # itinerario y mapa construidos de VERSIONES DISTINTAS del YAML
    with _YAML_LOCK:
        outs = []
        for script in ("build_itinerario.py", "build_mapa.py"):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "build", script), trip],
                               capture_output=True, text=True, encoding="utf-8")
            outs.append(r.stdout.strip() or r.stderr.strip())
        return "\n".join(outs)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8",
                      ".css": "text/css; charset=utf-8",
                      ".js": "text/javascript; charset=utf-8"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- sesión: localhost pasa directo; remoto exige login del allowlist ---
    def _is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _session_user(self):
        c = self.headers.get("Cookie") or ""
        for part in c.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "devsid" and v in _SESSIONS:
                return _SESSIONS[v]
        return None

    def _authed(self):
        return self._is_local() or self._session_user() is not None

    def do_GET(self):
        if not self.path.startswith("/api/"):
            return super().do_GET()
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/api/ping":
            # sonda del cliente: ¿hay dev server, y hace falta login?
            return self._json(200, {"ok": True, "auth": "ok" if self._authed() else "required",
                                    "user": self._session_user()})
        if not self._authed():
            return self._json(401, {"error": "inicia sesión (GitHub)"})
        try:
            if u.path == "/api/step":
                # TEXTO CRUDO del archivo (comentarios/formato del usuario
                # intactos), no un re-dump serializado
                self._json(200, {"ok": True,
                                 "yaml": raw_step(q["trip"], q["day"], q["step"],
                                                  q.get("sub", ""))})
            elif u.path == "/api/entity":
                kind, raw = raw_entity(q["trip"], q["key"], q.get("kind"))
                self._json(200, {"ok": True, "kind": kind, "yaml": raw})
            else:
                self._json(404, {"error": "endpoint desconocido"})
        except Exception as e:
            self._json(400, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            # login por device flow: lo ÚNICO abierto sin sesión
            if u.path == "/api/login/start":
                d = _github("https://github.com/login/device/code",
                            {"client_id": OAUTH_CLIENT, "scope": ""})
                handle = os.urandom(12).hex()
                _LOGINS[handle] = d["device_code"]
                return self._json(200, {"ok": True, "handle": handle,
                                        "user_code": d["user_code"],
                                        "verification_uri": d["verification_uri"],
                                        "interval": d.get("interval", 5)})
            if u.path == "/api/login/poll":
                dc = _LOGINS.get(req.get("handle"))
                if not dc:
                    return self._json(400, {"error": "login no iniciado"})
                t = _github("https://github.com/login/oauth/access_token",
                            {"client_id": OAUTH_CLIENT, "device_code": dc,
                             "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                if t.get("error") == "authorization_pending":
                    return self._json(200, {"ok": True, "pending": True})
                if "access_token" not in t:
                    return self._json(400, {"error": t.get("error", "login falló")})
                user = _github("https://api.github.com/user", token=t["access_token"])
                login = user.get("login", "")
                del _LOGINS[req["handle"]]
                if login not in ALLOW_USERS:
                    return self._json(403, {"error": f"'{login}' no está en el allowlist"})
                sid = os.urandom(16).hex()
                _SESSIONS[sid] = login
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie",
                                 f"devsid={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000")
                body = json.dumps({"ok": True, "user": login}).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if not self._authed():
                return self._json(401, {"error": "inicia sesión (GitHub)"})
            who = self._session_user() or "local"
            yml = os.path.relpath(yaml_path(req["trip"]), ROOT) if req.get("trip") else ""
            if u.path == "/api/step":
                save_step_raw(req["trip"], req["day"], req["step"], req["yaml"],
                              req.get("sub", ""))
                git_commit(ROOT, [yml], f"dev: paso d{req['day']}-r{req['step']}{req.get('sub','')} ({who})")
                self._json(200, {"ok": True})
            elif u.path == "/api/entity":
                if req.get("kind") not in CATALOGS:
                    return self._json(400, {"error": f"kind debe ser uno de {CATALOGS}"})
                save_entity_raw(req["trip"], req["kind"], req["key"], req["yaml"])
                git_commit(ROOT, [yml], f"dev: {req['kind']}.{req['key']} ({who})")
                self._json(200, {"ok": True})
            elif u.path == "/api/step-insert":
                pos = insert_step_raw(req["trip"], req["day"], req["step"],
                                      req.get("where"), req.get("sub", ""))
                git_commit(ROOT, [yml], f"dev: inserta paso en d{req['day']} ({who})")
                self._json(200, {"ok": True, "step": pos})
            elif u.path == "/api/step-move":
                pos = move_step_raw(req["trip"], req["day"], req["step"],
                                    req.get("dir", 0), req.get("sub", ""))
                git_commit(ROOT, [yml], f"dev: mueve paso en d{req['day']} ({who})")
                self._json(200, {"ok": True, "step": pos})
            elif u.path == "/api/rebuild":
                out = rebuild(req["trip"])
                extra = ""
                if req.get("deploy"):
                    git_commit(ROOT, ["pages"], f"dev: rebuild ({who})")
                    extra = " · " + deploy_pages(req["trip"])
                self._json(200, {"ok": True, "build": out + extra})
            else:
                self._json(404, {"error": "endpoint desconocido"})
        except Exception as e:
            self._json(400, {"error": str(e)})


if __name__ == "__main__":
    os.chdir(SERVE_DIR)
    modo = "COMPARTIDO (0.0.0.0 — túnel/LAN, login GitHub p/ remotos)" if SHARE else "local"
    print(f"dev server [{modo}] → http://127.0.0.1:{PORT}/viajes-2/pages/  · allowlist: {sorted(ALLOW_USERS)}")
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
