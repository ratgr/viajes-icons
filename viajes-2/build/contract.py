# -*- coding: utf-8 -*-
"""contract.py — el vocabulario compartido renderer ↔ verificador.

Cada literal que ambos lados deben acordar (prefijos, separadores,
normalizaciones) vive aquí UNA sola vez: render.py lo emite y
verify_roundtrip.py lo invierte con el mismo dato."""
import re

# prefijo de los modales: href = '#' + MODAL_PREFIX + clave (e id del div)
MODAL_PREFIX = "m-"

# duraciones que cuentan como ausencia de dato (no se emiten)
SKIP_DUR = (None, 0, "0")

# separador visual entre campos de la fila (vive dentro de span.sep)
SEP = " - "
SEP_STRIP_RE = re.compile(r"^\s*" + re.escape(SEP.strip()) + r"\s")

# etiqueta del ancla del día en el header
ANCHOR_LABEL = "Ancla: "
ANCHOR_STRIP_RE = re.compile(r"^" + re.escape(ANCHOR_LABEL.strip()) + r"\s*")

# guion del rango horario ('–hasta') dentro de <time>
TIME_TO_DASH = "–"

_FLEX_NORM_RE = re.compile(r"[\s()]")


def modal_key(href):
    """'#m-xxx' → 'xxx' — None si el href no es de un modal."""
    h = str(href or "")
    prefix = "#" + MODAL_PREFIX
    return h[len(prefix):] if h.startswith(prefix) else None


def norm_flex(spec_str):
    """LA normalización canónica del spec flex: sin espacios ni paréntesis
    ('( 30 - 60 )' ≡ '30-60')."""
    return _FLEX_NORM_RE.sub("", str(spec_str))


def clean_title(s, strip=True):
    """título sin asteriscos (defensa; migrate_yaml ya los quita)."""
    s = str(s).replace("*", "")
    return s.strip() if strip else s
