# Diferencias (conversión rica desde japon.html)

## Correcciones / notas
- **Orden por secuencia (fix)**: el mapa ahora ordena cada día ESTRICTAMENTE por `seqi` (índice del paso en el YAML), nunca por geografía ni por hora. `compile_mapa` emite `seqi` en cada ítem (paradas, tramos, comidas, info, hotel) y `build_leaflet` hace un solo `sort` por `seqi`. Antes las paradas se pegaban al tramo geográficamente más cercano → desorden (ej. lunes).
- **d5-9 "Hondori a pie de pasada" (fix de datos)**: sus coordenadas estaban en Osaka (`34.733…,135.50…`, copiadas de un tramo de Shin-Osaka) y saltaban fuera de Hiroshima. Corregidas a un caminito real a pie (OSRM foot, 779 m ≈ 11 min) del Parque Memorial a la parada del tranvía donde arranca `d5-10` (`34.393382,132.457008`), por la zona de Hondori.

- 2026-10-05: 5 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-06: 3 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-07: 4 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-08: 1 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-09: 2 planes anidados (Opción templo, Opción río)
- 2026-10-09: 9 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-10: 2 planes anidados (👘 Kimono en Arashiyama, Opción libre)
- 2026-10-10: 7 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-11: 3 planes anidados (Templeros, Vista, Libre)
- 2026-10-11: 8 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-12: 3 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-13: 3 planes anidados (Altura, Capibaras ☕, Calle)
- 2026-10-14: 3 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-15: 3 planes anidados (Animales ☕, Compras, Café)
- 2026-10-15: 3 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-16: 3 planes anidados (A · Kamakura 🌊, B · Fuji · Kawaguchiko 🗻, C · urbano 🏙️)
- 2026-10-16: 2 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-17: 2 planes anidados (Odaiba 🔘, Compras)
- 2026-10-17: 6 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)
- 2026-10-18: 2 tramos embebidos dibujados en mapa (hidden-summary, no en itinerario)