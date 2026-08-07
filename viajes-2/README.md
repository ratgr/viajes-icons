# viajes-2 — itinerario + mapa desde un solo YAML

Formato reutilizable para diseñar viajes: **`src/<viaje>/viaje.yaml` es la única
fuente de verdad** y de ahí se generan dos páginas estáticas autocontenidas —
el itinerario legible y el mapa interactivo (Leaflet vendorizado, sin CDN).
El HTML es una **proyección 1:1 verificada** del YAML: `verify_roundtrip.py`
invierte el render en cada build y compara contra la fuente; todo lo calculado
(horarios encadenados, duraciones de caminata, avisos) va marcado
`data-derived` y queda fuera de la comparación.

**En vivo:** <https://ratgr.github.io/viajes-icons/viajes2/mapa.html> ·
<https://ratgr.github.io/viajes-icons/viajes2/itinerario.html>

## Estructura

```
viajes-2/
  src/2026-Japon/       viaje.yaml (fuente) · plantillas · config.yaml
  build/                pipeline: render.py + build_*.py + verify_roundtrip.py
                        contract.py (vocabulario renderer↔verificador)
                        dev_server.py (edición local opcional)
                        assets/ (css/js/vendor copiados al release)
  pages/2026-Japon/     release generado (NO editar a mano)
  scratch/              herramientas fuera del pipeline (migraciones, OSM…)
../viajes2/             copia publicada por la Action (lo que sirve Pages)
```

## Flujo de edición EN LÍNEA (sin server)

1. Edita `viajes-2/src/2026-Japon/viaje.yaml` — desde el editor web de GitHub,
   el móvil, o por API (contents). Necesitas ser colaborador del repo; para la
   API basta un **PAT fine-grained** con `contents: read/write` SOLO de este
   repo (uno por persona).
2. Al hacer commit, la Action **`build viajes2`** corre sola: construye ambas
   páginas, verifica el round-trip y publica `/viajes2`. Ediciones rápidas se
   cancelan entre sí (solo se construye el último estado).
3. GitHub Pages sirve el resultado ~90 s después del commit.

Los diagnósticos del build (horarios incompletos, caminatas que no cuadran,
teletransportes 🌀) salen en el log de la Action — y como ⚠️/🌀 en las filas
del mapa.

## Flujo LOCAL (opcional, preview instantáneo)

```
python build/dev_server.py 8791          # sirve todo con no-store + API dev
python build/dev_server.py 8791 --share  # 0.0.0.0 para túnel/LAN
```

En el mapa aparece el botón **🛠** (solo cuando la página la sirve el dev
server): click en cualquier fila —también los pasos dentro de options— abre su
YAML **tal cual está en el archivo** (los comentarios sobreviven: la edición es
por empalme de texto). Desde el cajón:

- **Guardar / Rebuild / Deploy 🚀** — guardar escribe (y auto-commitea);
  rebuild reconstruye local; deploy además copia a `/viajes2` y hace push.
- **+ antes / + después / ▲ / ▼** — insertar y mover pasos.
- **Referencias** — cada clave referenciada se edita ahí mismo; una clave que
  no existe (o el input **➕ ref**) abre modo CREAR con plantillas
  (lugar/caminata/tren/bus/ferry) = referencias sin cumplir.
- **Geometría** — editor de vértices (arrastrar/insertar/borrar),
  **Ajustar a calle** (OSRM peatonal para caminatas), **Geo auto** (traza la
  ruta entre las anclas vecinas del paso). Toda edición reporta
  `N m ≈ ~X min a pie` con la misma regla del build (4 km/h, techos de 5/15).

En modo `--share`, los visitantes remotos inician sesión con **GitHub device
flow** y deben estar en el allowlist (`TF_DEV_ALLOW`, default `ratgr`).

## Esquema (lo esencial)

- `days[].steps[]`: cada paso puede llevar `location:`/`transit:` (claves de
  catálogo), `time-from`/`time-to`/`fixed`, `duration:` (o `flex`,
  `flex(min-max)`…), `title`/`note` con markdown mínimo y refs `@[texto](clave)`,
  variantes `*-show` (mostrar algo distinto sin perder el dato),
  `hidden-summary` (solo geometría del mapa) y `options:` (planes con `steps:`
  o tiers con `options:`).
- Catálogos `places:` (`gps: "lat,lng"`), `transits:` (`mode`, `color`,
  `coords: "lat,lng lat,lng …"`, `stations`, y `stops:` cuando coords es un
  trazo denso), `lines:`.
- Horario por **snap**: cada paso debe cerrar con 2 de {inicio, duración, fin};
  lo que falte se encadena a los vecinos y se pinta gris (~). Verde = explícito,
  rojo = fijo.
- Un `transit` declarado **sin coords** es una referencia pendiente: el mapa lo
  dibuja como conector punteado entre sus anclas vecinas hasta que tenga
  geometría (el editor la traza en un click).

## Para un segundo viaje

`src/<nuevo>/` con su `viaje.yaml` + plantillas + `config.yaml`
(`photo_base`), y correr los builds con el nombre del viaje. Los estilos de
tiers tienen respaldo posicional (no dependen de llamarse Take/Ai/Shu).
