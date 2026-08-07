/* mapa.js — cromo del mapa sobre el markup del itinerario:
   mapa base Leaflet + barra lateral (casillas por fila, maestro e
   interruptor de colapso por día, chips de día exclusivos).
   Las capas (marcadores/rutas) se conectarán aquí en la siguiente fase. */
(function () {
  'use strict';

  // ---------- mapa base (tiles Positron, como el mapa viejo) ----------
  // acento del tema RESUELTO (light-dark) para halos/marcadores del mapa
  var SHU = (getComputedStyle(document.documentElement).getPropertyValue('--shu') || '').trim() || '#b23a2a';
  var map = null;
  if (window.L && document.getElementById('map')) {
    map = L.map('map', { zoomControl: true }).setView([35.0, 135.6], 6);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 20, subdomains: 'abcd', attribution: '© OpenStreetMap © CARTO'
    }).addTo(map);
  }

  // ---------- barra lateral ----------
  var days = Array.prototype.slice.call(document.querySelectorAll('section.day'));
  var activeDay = -1;    // índice del día ACTIVO (visible en el mapa); lo
                         // mueven goDay/stGoTo/restore — no los clicks sueltos

  // INVARIANTE del maestro del día: todo prendido = ✔ · algo prendido = ▬
  // (tercer estado) · nada = vacío. Se recalcula tras CUALQUIER cambio,
  // venga de un click o de código (stepper de día, hash, restauración).
  function updateMaster(day) {
    var m = day.querySelector('.ck-day');
    if (!m) return;
    var cks = Array.prototype.slice.call(day.querySelectorAll('.ck:not(.ck-day)'));
    var on = cks.filter(function (c) { return c.checked; }).length;
    m.checked = on === cks.length && on > 0;
    m.indeterminate = on > 0 && on < cks.length;
  }

  // abrir SOLO ese día (exclusivo): los demás se pliegan
  function openOnly(day) {
    days.forEach(function (d) { d.classList.toggle('open', d === day); });
  }

  // casilla .ck al frente de una fila (prender/apagar su capa)
  function addCk(li) {
    var ck = document.createElement('input');
    ck.type = 'checkbox';
    ck.className = 'ck';
    li.insertBefore(ck, li.firstChild);
    return ck;
  }
  // caret plegable ▼: se inserta en host antes de before; su click corre
  // onClick y NO burbujea (plegar no elige ni selecciona)
  function makeCaret(cls, host, before, onClick) {
    var c = document.createElement('span');
    c.className = cls;
    c.textContent = '▼';
    host.insertBefore(c, before);
    c.addEventListener('click', function (e) {
      e.stopPropagation();
      onClick();
    });
    return c;
  }

  days.forEach(function (day) {
    var head = day.querySelector('.day-head');
    var rows = Array.prototype.slice.call(
      day.querySelectorAll(':scope > ul.steps > li'));   // incluye los solo-mapa

    // casilla por fila (prender/apagar su capa cuando existan capas)
    rows.forEach(addCk);

    // cabecera: maestro + caret
    var master = document.createElement('input');
    master.type = 'checkbox';
    master.className = 'ck ck-day';
    var caret = document.createElement('span');
    caret.className = 'caret';
    caret.textContent = '▶';
    head.insertBefore(caret, head.firstChild);
    head.insertBefore(master, head.firstChild);

    head.addEventListener('click', function (e) {
      if (e.target === master) return;
      // abrir un día también lo ENCUADRA (toda su geometría, sin dibujarla)
      if (day.classList.toggle('open')) focusKeys(keysUnder(day));
    });
    // el maestro prende TODO el día, incluidos los sub-pasos de las opciones
    // (aunque estén ocultas/plegadas: su geometría también cuenta)
    master.addEventListener('change', function () {
      // setDayChecked recalcula el maestro: deja indeterminate en falso
      setDayChecked(day, master.checked);
      if (master.checked) day.classList.add('open');
    });
    // tri-estado ante CUALQUIER cambio de casilla dentro del día
    day.addEventListener('change', function (e) {
      if (e.target === master || !e.target.classList.contains('ck')) return;
      updateMaster(day);
    });
  });

  // arranque: primer día abierto
  if (days.length) days[0].classList.add('open');

  // ---------- divisor arrastrable (persistente) ----------
  var panel = document.querySelector('.panel');
  var splitter = document.getElementById('splitter');
  if (panel && splitter) {
    var saved = localStorage.getItem('mapa-panel-w');
    if (saved) panel.style.width = saved + 'px';
    var dragging = false;
    splitter.addEventListener('pointerdown', function (e) {
      dragging = true;
      splitter.classList.add('dragging');
      splitter.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    splitter.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var w = Math.max(260, Math.min(e.clientX, window.innerWidth * 0.7));
      panel.style.width = w + 'px';
      if (map) map.invalidateSize();
    });
    splitter.addEventListener('pointerup', function () {
      dragging = false;
      splitter.classList.remove('dragging');
      localStorage.setItem('mapa-panel-w', parseInt(panel.style.width || '380', 10));
    });
    splitter.addEventListener('dblclick', function () {
      panel.style.width = '380px';
      localStorage.removeItem('mapa-panel-w');
      if (map) map.invalidateSize();
    });
  }

  // ---------- selección de fila + tarjeta como popup EN el mapa ----------
  var GEO = { locations: {}, transits: {} };
  try {
    GEO = JSON.parse(document.getElementById('geo').textContent);
  } catch (e) { /* sin geometría: los links caen al dialog */ }
  // vista inicial = caja del viaje completo (viene del build; el setView de
  // arriba queda de respaldo para GEO vacío)
  if (map && GEO.bbox) {
    map.fitBounds([[GEO.bbox[0], GEO.bbox[1]], [GEO.bbox[2], GEO.bbox[3]]],
      { padding: [40, 40] });
  }

  // ---------- primitivas GEO ----------
  // geometría de una clave: lugar (loc) y/o transporte (tr); tr solo llega
  // si trae coords NO vacías — el par de lookups + chequeo vive aquí una vez
  function geoOf(key) {
    var tr = GEO.transits[key];
    return {
      loc: GEO.locations[key],
      tr: tr && tr.coords.length ? tr : null
    };
  }
  // encuadre de una clave: punto o traza → L.latLngBounds (null sin geometría)
  function keyBounds(key) {
    var g = geoOf(key);
    if (g.loc) return L.latLngBounds([g.loc]);
    if (g.tr) return L.latLngBounds(g.tr.coords);
    return null;
  }
  // estilo de línea de un transporte: caminata = fina y punteada, resto sólida
  function lineStyle(tr) {
    var walk = tr && tr.mode === 'walk';
    return {
      color: tr && tr.color,
      weight: walk ? 3 : 5,
      dashArray: walk ? '4 7' : null
    };
  }
  // encuadre de una capa Leaflet (con o sin getBounds)
  function layerBounds(l) {
    return l.getBounds ? l.getBounds() : L.latLngBounds([l.getLatLng()]);
  }
  // unión de encuadres: toBounds(item) → L.latLngBounds|null por elemento
  function boundsUnion(items, toBounds) {
    var bounds = null;
    items.forEach(function (it) {
      var b = toBounds(it);
      if (b) bounds = bounds ? bounds.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast());
    });
    return bounds;
  }
  // rumbo de pantalla a→b en grados CSS (horario, 0° = este)
  function segAngle(a, b) {
    var dx = (b[1] - a[1]) * Math.cos(a[0] * Math.PI / 180);
    var dy = a[0] - b[0];   // pantalla: y crece hacia el sur
    return Math.atan2(dy, dx) * 180 / Math.PI;
  }
  // punto y rumbo a una fracción del largo total de la línea
  function pointAlong(coords, frac) {
    var d = [0], total = 0;
    for (var i = 1; i < coords.length; i++) {
      var dx = (coords[i][1] - coords[i - 1][1]) * Math.cos(coords[i][0] * Math.PI / 180);
      var dy = coords[i][0] - coords[i - 1][0];
      total += Math.sqrt(dx * dx + dy * dy);
      d.push(total);
    }
    if (!total) return null;
    var goal = total * frac;
    for (var j = 1; j < coords.length; j++) {
      if (d[j] >= goal) {
        var t = (goal - d[j - 1]) / (d[j] - d[j - 1] || 1);
        var a = coords[j - 1], b = coords[j];
        return { p: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], ang: segAngle(a, b) };
      }
    }
    return null;
  }
  // flechas de dirección sobre la línea (¼, ½, ¾ del recorrido)
  function chevronMarkers(coords, color) {
    var out = [];
    [.25, .5, .75].forEach(function (f) {
      var pa = pointAlong(coords, f);
      if (!pa) return;
      out.push(L.marker(pa.p, {
        interactive: false, keyboard: false,
        icon: L.divIcon({
          className: 'chev', iconSize: [16, 16],
          html: '<span style="transform:rotate(' + Math.round(pa.ang) + 'deg);color:' + color + '">❯</span>'
        })
      }));
    });
    return out;
  }
  // línea de transporte: polilínea + flechas + (si las estaciones calzan con
  // los vértices, como en los rieles) un punto con nombre por estación
  function transitGroup(key, tr, coords, inert) {
    // inert = capa de EXHIBICIÓN (la temporal del popup): sin interacción,
    // para que los clicks caigan a la capa viva de abajo — la temporal
    // encima de lo ya elegido se tragaba el click y el popup no reabría
    var g = L.featureGroup();
    var s = lineStyle(tr);
    var line = L.polyline(coords, {
      color: s.color, weight: s.weight, opacity: .85, dashArray: s.dashArray,
      interactive: !inert
    });
    // línea de IMPACTO invisible y gorda: las punteadas casi no se atinan
    if (!inert) {
      g.addLayer(L.polyline(coords, { weight: 16, opacity: 0.001, interactive: true }));
    }
    g.addLayer(line);
    g._line = line;
    g._decos = chevronMarkers(coords, tr.color);
    g._dots = [];
    // puntos de estación: de tr.stops (trazo denso OSM) o, si no hay, de los
    // vértices cuando calzan 1 a 1 con la lista de estaciones
    var stopPts = (tr.stops && tr.stations && tr.stops.length === tr.stations.length)
      ? tr.stops
      : (tr.stations && tr.stations.length === coords.length ? coords : null);
    if (stopPts) {
      stopPts.forEach(function (c, i) {
        var dot = L.circleMarker(c, { radius: 3.5, color: tr.color, weight: 2, fillColor: '#fff', fillOpacity: 1, interactive: !inert });
        if (tr.stations[i]) dot.bindTooltip(tr.stations[i], { direction: 'top', offset: [0, -4] });
        g._dots.push(dot);
      });
    }
    g._decos.concat(g._dots).forEach(function (d) { g.addLayer(d); });
    return g;
  }
  // insignia numerada de un lugar (seqLabels vive en la sección de capas)
  function locIcon(key, ghost) {
    var label = seqLabels[key] || '';
    var w = label.length > 2 ? 10 + label.length * 8 : 22;
    return L.divIcon({
      className: 'seq-badge' + (ghost ? ' ghost' : '') + (label ? '' : ' plain'),
      html: label, iconSize: label ? [w, 22] : [16, 16]
    });
  }

  var store = document.getElementById('modal-store').content;
  var selRow = null;
  var tempLayer = null;   // geometría resaltada de la selección (transit)

  function modalHtml(key) {
    var src = store.getElementById('m-' + key);
    return src ? src.outerHTML : '';
  }
  // un LUGAR puede aparecer en varios días (las rutas son únicas): la tarjeta
  // lleva una pieza por día, colapsada a «día + una línea»; la del día
  // seleccionado (sección abierta) o la fila clickeada llega expandida
  function dayPieces(key, activeRowId) {
    var rows = document.querySelectorAll('.panel .steps > li[data-location="' + key + '"]');
    if (!rows.length) return '';
    var out = ['<div class="uses">'];
    rows.forEach(function (li) {
      var day = li.closest('section.day');
      var label = day ? (day.querySelector('h3').textContent.split('·')[0].trim()) : '';
      var time = li.querySelector('time');
      var title = li.querySelector('.title');
      var note = li.querySelector('.note');
      var open = (day && day.classList.contains('open')) || li.id === activeRowId;
      out.push('<details class="use"' + (open ? ' open' : '') + '>' +
        '<summary><b>' + label + '</b><span class="use-line">' +
        (time ? time.textContent + ' · ' : '') + (title ? title.textContent : '') +
        '</span></summary>' +
        (note ? '<div class="use-note">' + note.innerHTML + '</div>' : '') +
        '</details>');
    });
    out.push('</div>');
    return out.join('');
  }
  function selectRow(li) {
    if (selRow) selRow.classList.remove('sel');
    selRow = li;
    if (li) li.classList.add('sel');
  }
  // el DÓNDE ESTAMOS vive en el hash (#m-clave@fila · #@fila · #dN) para que
  // una recarga (p.ej. tras rebuild) vuelva al mismo punto; la visibilidad
  // de casillas NO se codifica (recarga = default)
  function updateHash(mKey, rowId) {
    var h = (mKey ? 'm-' + mKey : '') + (rowId ? '@' + rowId : '');
    if (h) history.replaceState(null, '', '#' + h);
  }
  function openDayOf(li) {
    var day = li.closest('section.day');
    if (day) openOnly(day);
  }
  function clearTemp() {
    if (tempLayer && map) { map.removeLayer(tempLayer); tempLayer = null; }
  }

  // halo de SELECCIÓN: resalta en el mapa la geometría de lo elegido en la
  // barra (línea gorda translúcida / disco brillante), debajo de las capas
  var haloLayer = null;
  function clearHalo() {
    if (haloLayer && map) { map.removeLayer(haloLayer); haloLayer = null; }
  }
  function boundsForKeys(keys) {
    return boundsUnion(keys, keyBounds);
  }
  function focusKeys(keys) {
    if (!map || !keys.length) return;
    var b = boundsForKeys(keys);
    if (b && b.isValid()) map.flyToBounds(b.pad(.2), { duration: .5 });
  }
  function haloFor(keys) {
    clearHalo();
    if (!map) return;
    var parts = [];
    keys.forEach(function (key) {
      var g = geoOf(key);
      if (g.loc) {
        parts.push(L.circleMarker(g.loc, {
          radius: 14, color: SHU, weight: 0, fillColor: SHU,
          fillOpacity: .3, interactive: false
        }));
      } else if (g.tr) {
        parts.push(L.polyline(g.tr.coords, {
          color: g.tr.color, weight: 13, opacity: .35,
          lineCap: 'round', lineJoin: 'round', interactive: false
        }));
      }
    });
    if (parts.length) {
      haloLayer = L.layerGroup(parts).addTo(map);
      parts.forEach(function (p) { if (p.bringToBack) p.bringToBack(); });
    }
  }

  // ---------- modelo de rutas elegidas (choice-path) ----------
  // cada ul.options es un conjunto de ELECCIÓN (radios mutuamente excluyentes,
  // anidables); aquí vive todo lo que razona sobre qué rama está elegida
  var SEL_CHOICE = '.option-choice, .group-choice';
  var SEL_CHOICE_ON = '.option-choice:checked, .group-choice:checked';
  // itera los conjuntos .options ANCESTROS de el, de adentro hacia afuera;
  // fn(set, node) recibe el conjunto y el nodo interior por el que llegamos;
  // si fn devuelve false se corta el recorrido (y eachChoiceSet devuelve false)
  function eachChoiceSet(el, fn) {
    var node = el;
    for (var set = node.closest('.options'); set;
         set = set.parentElement && set.parentElement.closest('.options')) {
      if (fn(set, node) === false) return false;
      node = set;
    }
    return true;
  }
  // contenedor (opción u li de grupo) DENTRO de set del que cuelga node:
  // primero por la marca data-opt del renderer (el ancestro marcado más
  // cercano que pertenezca a ESTE conjunto); el recorrido DOM de siempre
  // queda de respaldo para markup sin la marca
  function chosenContainer(set, node) {
    for (var c = node.closest('[data-opt]'); c;
         c = c.parentElement && c.parentElement.closest('[data-opt]')) {
      if (c.closest('.options') === set) return c;
    }
    var opt = node.closest('.option');
    if (opt && opt.closest('.options') === set) return opt;
    var li = node;
    while (li && li.parentElement !== set) li = li.parentElement;
    return li;
  }
  // ¿el está en la RUTA elegida? (todas sus elecciones ancestras lo contienen)
  function onChosenPath(el) {
    return eachChoiceSet(el, function (set, node) {
      var chosen = set.querySelector(SEL_CHOICE_ON);
      if (chosen) {
        var cont = chosenContainer(set, node);
        if (!cont || !cont.contains(chosen)) return false;
      }
    });
  }
  // ¿el2 está en la MISMA rama de opciones que el? Un paso dentro de una
  // opción NO es vecino de los pasos de OTRA opción del mismo conjunto: su
  // ruta automática debe brincar al siguiente paso real, no a la opción de
  // al lado. (el2 fuera de todo conjunto siempre es válido.)
  function sameBranch(el, el2) {
    return eachChoiceSet(el2, function (set, node) {
      if (!set.contains(el)) return false;                    // otra opción/conjunto
      if (chosenContainer(set, el) !== chosenContainer(set, node)) return false;
    });
  }
  // estado fantasma: elemento marcado dentro de una opción NO elegida —
  // con 👁 su geometría se dibuja atenuada; con 🙈 va en línea GORDA tenue
  // (sigue visible: distinta, no borrada). Recorre TODOS los conjuntos
  // ancestros (vía eachChoiceSet, como onChosenPath/sameBranch): en
  // elecciones anidadas manda el peor estado de cualquier nivel.
  function ghostState(el) {
    var worst = 'full';
    eachChoiceSet(el, function (set, node) {
      var chosen = set.querySelector(SEL_CHOICE_ON);
      if (chosen) {
        var cont = chosenContainer(set, node);
        if (cont && !cont.contains(chosen)) {
          if (set.classList.contains('eye-hide')) { worst = 'hidden'; return false; }
          if (set.classList.contains('eye-ghost')) worst = 'ghost';
        }
      }
    });
    return worst;
  }
  // clave de un link a modal: href '#m-clave' → 'clave' (o null si no aplica)
  function modalKey(a) {
    var h = a.getAttribute('href') || '';
    return h.indexOf('#m-') === 0 ? h.slice(3) : null;
  }
  // FOCO genérico: cualquier nivel de la barra (fila, elección, grupo, día)
  // encuadra TODA la geometría contenida en su subárbol; con withLinks también
  // cuentan las claves solo REFERENCIADAS por links a modal (grupos de options)
  function keysUnder(el, withLinks) {
    var keys = [];
    var own = el.dataset && (el.dataset.location || el.dataset.transit);
    if (own) keys.push(own);
    el.querySelectorAll('[data-location],[data-transit]').forEach(function (e2) {
      var k = e2.dataset.location || e2.dataset.transit;
      if (k && keys.indexOf(k) < 0) keys.push(k);
    });
    if (withLinks) {
      el.querySelectorAll('a.modal-link').forEach(function (a) {
        var k = modalKey(a);
        if (k && keys.indexOf(k) < 0) keys.push(k);
      });
    }
    return keys;
  }

  // ---------- grupos de options: colapsables y seleccionables ----------
  // elegir un grupo (plan o tier) enciende TODA su geometría de un golpe
  var selGroupEl = null;
  function showGroupGeometry(g) {
    if (!map) return;
    clearTemp();
    var keys = keysUnder(g, true);
    haloFor(keys);
    var layers = [];
    keys.forEach(function (key) {
      var geo = geoOf(key);
      if (geo.loc) {
        layers.push(L.circleMarker(geo.loc, {
          radius: 7, color: '#fff', weight: 2, fillColor: SHU, fillOpacity: 1
        }).bindTooltip(key));
      } else if (geo.tr) {
        var s = lineStyle(geo.tr);
        layers.push(L.polyline(geo.tr.coords, {
          color: s.color, weight: s.weight, opacity: .9, dashArray: s.dashArray
        }));
      }
    });
    if (!layers.length) return;
    tempLayer = L.layerGroup(layers).addTo(map);
    map.flyToBounds(boundsUnion(layers, layerBounds).pad(.2), { duration: .5 });
  }
  function selectGroup(g) {
    if (selGroupEl) selGroupEl.classList.remove('sel-group');
    selGroupEl = g;
    g.classList.add('sel-group');
    showGroupGeometry(g);
  }
  // la FILA principal de una elección también se pliega: su caret colapsa
  // el conjunto de options completo
  document.querySelectorAll('.panel .steps > li').forEach(function (li) {
    var opts = li.querySelector(':scope > .body > ul.options');
    var title = li.querySelector('.title');
    if (!opts || !title) return;
    makeCaret('group-caret row-caret', title, title.firstChild, function () {
      li.classList.toggle('opts-closed');
    });
  });

  // cada ul.options es un CONJUNTO DE ELECCIÓN: sus grupos llevan radio
  // (mutuamente excluyentes); elegir uno marca la opción y enciende su geometría
  document.querySelectorAll('.panel .options').forEach(function (set, si) {
    // ojo del conjunto: 👁 = fantasma de los no elegidos · 🙈 = solo el elegido
    // (vive en la FILA padre, no dentro de las opciones)
    var eye = document.createElement('button');
    eye.type = 'button';
    eye.className = 'eye-toggle';
    eye.textContent = '👁';
    eye.title = 'Los no elegidos: fantasma (👁) u ocultos (🙈)';
    set.classList.add('eye-ghost');
    var host = set.closest('li') || set;
    host.appendChild(eye);
    eye.addEventListener('click', function (e) {
      e.stopPropagation();
      var hide = set.classList.toggle('eye-hide');
      set.classList.toggle('eye-ghost', !hide);
      eye.textContent = hide ? '🙈' : '👁';
    });
    // sub-filas de planes: casilla propia, individualmente seleccionables
    set.querySelectorAll('.steps > li').forEach(function (li) {
      if (li.querySelector(':scope > .ck')) return;
      addCk(li);
    });
    set.querySelectorAll(':scope > li').forEach(function (g) {
      var label = g.querySelector(':scope > b');
      if (!label) return;
      var caret = makeCaret('group-caret', label, label.firstChild, function () {
        g.classList.toggle('closed');          // colapsar NO elige
      });
      // el renderer declara la topología (data-kind); la forma DOM es respaldo
      var isPlan = g.dataset.kind ? g.dataset.kind === 'plan' : !!g.querySelector(':scope > ul.steps');
      if (isPlan) {
        // plan: la elección es el GRUPO (sus sub-pasos son su itinerario)
        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'choice-' + si;
        radio.className = 'group-choice';
        label.insertBefore(radio, caret);
        label.addEventListener('click', function (e) {
          e.stopPropagation();
          radio.checked = true;
          selectGroup(g);
          closePanelIfNarrow();
        });
      } else {
        // elección anidada (tiers): la elección real es CADA opción de abajo —
        // el radio va en el nivel inferior, compartido por TODO el conjunto
        label.addEventListener('click', function (e) {
          e.stopPropagation();
          selectGroup(g);             // ver la geometría del tier completo
          closePanelIfNarrow();
        });
        g.querySelectorAll(':scope > .option').forEach(function (opt) {
          var r = document.createElement('input');
          r.type = 'radio';
          r.name = 'choice-' + si;
          r.className = 'option-choice';
          opt.insertBefore(r, opt.firstChild);
          r.addEventListener('change', function () {
            var a = opt.querySelector('a.modal-link');
            var key = a && modalKey(a);
            if (key) showOnMap(key, a.textContent);
          });
          // pliegue propio de la opción: colapsa sus sub-pasos (ida/lugar/regreso)
          var sub = opt.querySelector(':scope > ul.steps');
          if (sub) {
            makeCaret('group-caret option-caret', opt, r.nextSibling, function () {
              opt.classList.toggle('closed');
            });
            opt.classList.add('closed');   // plegada por defecto
          }
        });
      }
    });
    // por defecto la PRIMERA opción del conjunto queda elegida (sin volar ahí)
    if (!set.querySelector(SEL_CHOICE_ON)) {
      var first = set.querySelector(SEL_CHOICE);
      if (first) first.checked = true;
    }
  });
  // popup con la tarjeta COMPLETA (en teléfono es la única vista); si es alta
  // se colapsa tras «Ver más» y expandida scrollea con tope de 40% de pantalla
  function openCardPopup(latlng, content) {
    // autoPan APAGADO: cada apertura viene con su propio vuelo explícito y
    // el paneo automático del popup peleaba con la animación en curso
    var pop = L.popup({ maxWidth: 320, autoPan: false })
      .setLatLng(latlng)
      .setContent('<div class="popup-card">' + content + '</div>')
      .openOn(map);
    // OJO: nada de pop.update() tras mutar el DOM — re-renderiza el contenido
    // desde el string original y borra la clase y el botón
    var root = pop.getElement ? pop.getElement() : null;
    var el = root && root.querySelector('.popup-card');
    var card = el && el.querySelector('.modal');
    if (card && card.scrollHeight > window.innerHeight * 0.4) {
      el.classList.add('collapsed');
      var btn = document.createElement('button');
      btn.className = 'see-more';
      btn.textContent = 'Ver más ↓';
      btn.addEventListener('click', function () {
        var collapsed = el.classList.toggle('collapsed');
        btn.textContent = collapsed ? 'Ver más ↓' : 'Ver menos ↑';
      });
      el.appendChild(btn);
    }
    return pop;
  }
  var lastShownKey = null;   // repetir click en lo YA elegido acerca el zoom
  // el caminador encuadra la GEOMETRÍA COMPLETA del paso con un tope de
  // acercamiento (regla del usuario: nada de promedios de zoom)
  var ST_MAX_ZOOM = 16;
  function showOnMap(key, fallbackTitle, activeRowId, fit) {
    if (!map) return false;
    var content = modalHtml(key) ||
      '<div class="modal"><h3>' + (fallbackTitle || key) + '</h3></div>';
    var g = geoOf(key);
    var loc = g.loc, tr = g.tr;
    var repeat = key === lastShownKey && !fit;
    lastShownKey = key;
    clearTemp();
    haloFor([key]);
    if (loc) {
      // repetido: acercar SIEMPRE por encima del nivel normal de lugar —
      // si venimos de un encuadre lejano, +2 podía quedar MÁS lejos que 15
      var z = repeat ? Math.min(19, Math.max(map.getZoom() + 2, 16))
                     : fit ? ST_MAX_ZOOM : Math.max(map.getZoom(), 15);
      map.flyTo(loc, z, { duration: .5 });
      openCardPopup(loc, content + dayPieces(key, activeRowId));
      return true;
    }
    if (tr) {
      tempLayer = transitGroup(key, tr, tr.coords, true).addTo(map);
      if (repeat) {
        map.flyToBounds(tempLayer.getBounds().pad(.02), { duration: .5 });
      } else {
        map.flyToBounds(tempLayer.getBounds().pad(.25),
          { duration: .5, maxZoom: fit ? ST_MAX_ZOOM : 18 });
      }
      openCardPopup(tr.coords[Math.floor(tr.coords.length / 2)], content);
      return true;
    }
    return false;
  }
  function rowOf(el) {
    var li = el.closest('li');
    while (li && !(li.parentElement && li.parentElement.classList.contains('steps'))) {
      li = li.parentElement ? li.parentElement.closest('li') : null;
    }
    return li;
  }

  // ---------- capas vivas: la CASILLA manda ----------
  // solo las filas/sub-filas MARCADAS dibujan su geometría (el maestro del
  // día marca todo el día); abrir/plegar solo organiza la barra
  var liveLayers = {};    // clave → capa Leaflet
  var autoLayers = {};    // id de fila → conector automático (transit sin geometría)
  var seqLabels = {};     // clave de lugar → '1' / '2·5' (cronología del día)

  // tabla de estilos por estado: opacidad de línea (line) y de marcadores
  // (mark), y cuánto ENGORDAR la línea oculta (widen) — sigue visible: distinta
  var STYLE = {
    full:   { line: .85, mark: 1,   widen: 0 },
    ghost:  { line: .25, mark: .25, widen: 0 },
    hidden: { line: .12, mark: .12, widen: 7 }
  };
  // misma estructura para los conectores automáticos (sus propios números)
  var AUTO_STYLE = {
    full:   { line: .7, mark: .8, weight: 2.5 },
    ghost:  { line: .2, mark: .2, weight: 2.5 },
    hidden: { line: .1, mark: .1, weight: 9 }
  };

  function makeLayer(key) {
    var g = geoOf(key);
    var loc = g.loc, tr = g.tr;
    var ly = null;
    if (loc) {
      ly = L.marker(loc, { icon: locIcon(key, false) });
    } else if (tr) {
      ly = transitGroup(key, tr, tr.coords);
    }
    if (ly) {
      // click en la geometría: SIEMPRE (re)abre su tarjeta — aun ya
      // seleccionada — y selecciona la fila correspondiente en la barra
      ly.on('click', function () {
        var content = modalHtml(key) || '<div class="modal"><h3>' + key + '</h3></div>';
        if (loc) content += dayPieces(key, null);
        openCardPopup(loc || tr.coords[Math.floor(tr.coords.length / 2)], content);
        // segundo click en lo ya elegido = acercar el zoom
        if (key === lastShownKey && map) {
          if (loc) map.flyTo(loc, Math.min(19, map.getZoom() + 2), { duration: .4 });
          else map.flyToBounds(L.latLngBounds(tr.coords).pad(.02), { duration: .4 });
        }
        lastShownKey = key;
        selectByKey(key);
      });
    }
    return ly;
  }
  // geometría → barra: seleccionar la fila del elemento clickeado en el mapa
  // (si la clave se repite, gana la de un día abierto)
  function selectByKey(key) {
    var idx = -1;
    for (var j = 0; j < stEls.length; j++) {
      if ((stEls[j].dataset.location || stEls[j].dataset.transit) !== key) continue;
      var day = stEls[j].closest('section.day');
      if (day && day.classList.contains('open')) { idx = j; break; }
      if (idx < 0) idx = j;
    }
    if (idx < 0) return;
    var li = rowOf(stEls[idx]) || stEls[idx];
    openDayOf(li);
    selectRow(li);
    if (li.id) updateHash(null, li.id);
    li.scrollIntoView({ block: 'center' });
    stCur = idx;
    stMode = null;
    stRender();
  }
  var ST_RANK = { full: 3, ghost: 2, hidden: 1 };
  function applyLayerState(key, st) {
    var ly = liveLayers[key];
    if (!ly) return;
    var s = STYLE[st];
    if (ly._line) {                       // grupo de transporte
      var w = lineStyle(GEO.transits[key]).weight;
      ly._line.setStyle({ opacity: s.line, weight: w + s.widen });
      ly._decos.forEach(function (d) { d.setOpacity(s.mark); });
      ly._dots.forEach(function (d) { d.setStyle({ opacity: s.mark, fillOpacity: s.mark }); });
    } else if (ly.setIcon) {              // marcador de lugar (insignia numerada)
      ly.setIcon(locIcon(key, st !== 'full'));
    }
  }
  // punto de anclaje de una fila con geometría: lugar → su gps;
  // transporte → su último/primer vértice (según sea el previo o el siguiente)
  function anchorPoint(el, end) {
    var key = el.dataset.location || el.dataset.transit;
    var g = geoOf(key);
    if (g.loc) return g.loc;
    if (g.tr) return end ? g.tr.coords[g.tr.coords.length - 1] : g.tr.coords[0];
    return null;
  }
  // anclas VECINAS de list[i] dentro de su misma rama: prev = último punto del
  // paso previo con geometría, next = primer punto del siguiente; con
  // sameDayOnly el rastreo se corta al cruzar de día (conectores automáticos)
  function neighborAnchors(list, i, sameDayOnly) {
    var el = list[i];
    var day = sameDayOnly ? el.closest('section.day') : null;
    var prev = null, next = null, j;
    for (j = i - 1; j >= 0 && !prev; j--) {
      if (sameDayOnly && list[j].closest('section.day') !== day) break;
      if (!sameBranch(el, list[j])) continue;      // no anclar en OTRA opción
      prev = anchorPoint(list[j], true);
    }
    for (j = i + 1; j < list.length && !next; j++) {
      if (sameDayOnly && list[j].closest('section.day') !== day) break;
      if (!sameBranch(el, list[j])) continue;
      next = anchorPoint(list[j], false);
    }
    return { prev: prev, next: next };
  }
  // anclas de una fila: primero las PRECALCULADAS del build (GEO.anchors,
  // por id de fila — misma regla de rama/día, resuelta en Python); si el id
  // no está, el rastreo en vivo de neighborAnchors de siempre
  function anchorsFor(el, list, i, sameDayOnly) {
    var pre = GEO.anchors && el.id && GEO.anchors[el.id];
    return pre || neighborAnchors(list, i, sameDayOnly);
  }
  function syncLayers() {
    if (!map) return;
    var want = {};      // clave → 'full' | 'ghost'
    var autos = {};     // id de conector → {a, b, st}
    var els = Array.prototype.slice.call(
      document.querySelectorAll('.panel [data-location], .panel [data-transit]'));
    var states = els.map(function (el) {
      var ck = el.querySelector(':scope > .ck');
      if (!ck || !ck.checked) return null;
      return ghostState(el);
    });
    els.forEach(function (el, i) {
      var st = states[i];
      if (!st) return;
      var key = el.dataset.location || el.dataset.transit;
      if (GEO.locations[key] || (GEO.transits[key] && GEO.transits[key].coords.length)) {
        if (!want[key] || ST_RANK[st] > ST_RANK[want[key]]) want[key] = st;
        return;
      }
      if (!el.dataset.transit) return;
      // transporte SIN geometría (referencia sin cumplir) = conector automático:
      // une el punto previo con el siguiente dentro del mismo día
      var na = anchorsFor(el, els, i, true);
      if (na.prev && na.next) autos['auto-' + i + '-' + key] = { a: na.prev, b: na.next, st: st };
    });
    // cronología del día: numerar los LUGARES plenos en orden del documento
    seqLabels = {};
    days.forEach(function (day) {
      var n = 0;
      els.forEach(function (el, i) {
        if (states[i] !== 'full' || !el.dataset.location) return;
        if (el.closest('section.day') !== day) return;
        var key = el.dataset.location;
        if (!GEO.locations[key]) return;
        n += 1;
        seqLabels[key] = seqLabels[key] ? seqLabels[key] + '·' + n : String(n);
      });
    });
    Object.keys(liveLayers).forEach(function (k) {
      if (!want[k]) {
        map.removeLayer(liveLayers[k]);
        delete liveLayers[k];
      }
    });
    Object.keys(want).forEach(function (k) {
      if (!liveLayers[k]) {
        var ly = makeLayer(k);
        if (ly) {
          liveLayers[k] = ly;
          ly.addTo(map);
        }
      }
      applyLayerState(k, want[k]);
    });
    // conectores automáticos: punteado recto gris, una flecha al centro
    Object.keys(autoLayers).forEach(function (id) {
      if (!autos[id]) {
        map.removeLayer(autoLayers[id]);
        delete autoLayers[id];
      }
    });
    Object.keys(autos).forEach(function (id) {
      var sp = autos[id];
      if (!autoLayers[id]) {
        var g = L.featureGroup();
        var line = L.polyline([sp.a, sp.b], { color: '#8a8073', weight: 2.5, opacity: .7, dashArray: '2 8' });
        g.addLayer(line);
        g._line = line;
        g._decos = chevronMarkers([sp.a, sp.b], '#8a8073').slice(1, 2);   // solo la del centro
        g._decos.forEach(function (d) { g.addLayer(d); });
        autoLayers[id] = g.addTo(map);
      }
      var s = AUTO_STYLE[sp.st];
      autoLayers[id]._line.setStyle({ opacity: s.line, weight: s.weight });
      autoLayers[id]._decos.forEach(function (d) { d.setOpacity(s.mark); });
    });
  }
  function fitToLayers() {
    var bounds = boundsUnion(Object.keys(liveLayers), function (k) {
      return layerBounds(liveLayers[k]);
    });
    if (bounds && bounds.isValid()) map.flyToBounds(bounds.pad(.15), { duration: .5 });
  }
  var syncT = null;
  function schedSync() {
    clearTimeout(syncT);
    syncT = setTimeout(syncLayers, 120);
  }
  panel.addEventListener('click', schedSync);
  panel.addEventListener('change', schedSync);
  // chip de día = día EXCLUSIVO: abre ese y colapsa los demás; después del
  // cambio, sincronizar capas y encuadrar el día
  document.querySelectorAll('.day-nav a[href^="#d"]').forEach(function (a) {
    a.addEventListener('click', function () {
      var sec = document.getElementById((a.getAttribute('href') || '').slice(1));
      openOnly(sec);
      clearHalo();
      setTimeout(function () {
        syncLayers();
        if (sec) focusKeys(keysUnder(sec)); else fitToLayers();
      }, 60);
    });
  });
  // arranque: si restore() ya posicionó la cámara (hash), NO re-encuadrar —
  // el fitToLayers de arranque cancelaba el vuelo del restore a media animación
  var restoredView = false;
  setTimeout(function () {
    syncLayers();
    if (!restoredView) fitToLayers();
  }, 150);

  // ---------- STEPPER: recorrido paso a paso (navegación principal en teléfono) ----------
  // ‹ / › recorren los pasos CONCRETOS (con lugar o transporte) siguiendo la
  // opción ELEGIDA de cada choice; cuando el siguiente paso entra a un choice
  // se muestran sus opciones para elegir a cuál saltar (anidados: columnas
  // plegables por grupo — se elige la opción de abajo, no el grupo); dentro
  // de una opción el «saltar a» sigue visible (plegable) y saltar a otra
  // opción arranca en su primer paso
  var stEls = Array.prototype.slice.call(
    document.querySelectorAll('.panel [data-location], .panel [data-transit]'));
  var stCur = stEls.length ? 0 : -1;
  var stMode = null;        // conjunto .options mostrando elección, o null
  var stJumpOpen = true;

  function nextConcrete(i, dir) {
    for (var j = i + dir; j >= 0 && j < stEls.length; j += dir) {
      if (onChosenPath(stEls[j])) return j;
    }
    return -1;
  }
  // texto plano de una etiqueta: espacios colapsados; con stripCaret también
  // se quita el caret de plegado de la barra si vino dentro del elemento
  function labelText(s, stripCaret) {
    s = s.replace(/\s+/g, ' ');
    if (stripCaret) s = s.replace(/^[▼▾▸▶ ]+/, '');
    return s.trim();
  }
  function stTitle(el) {
    var t = el.querySelector('.title') || el.querySelector('a.modal-link');
    return labelText(t ? t.textContent : (el.dataset.location || el.dataset.transit));
  }
  function optLabel(cont) {
    var a = cont.querySelector('a.modal-link');
    var b = cont.querySelector('b');
    var s = (a && a.textContent) || (b && b.textContent) || cont.textContent;
    return labelText(s, true).slice(0, 42);
  }

  var stBar = document.createElement('div');
  stBar.className = 'stepper';
  stBar.innerHTML =
    '<div class="st-row">' +
    '<button class="st-prev" type="button">‹</button>' +
    '<div class="st-center"></div>' +
    '<button class="st-next" type="button">›</button></div>' +
    '<div class="st-jump" hidden>' +
    '<button class="st-jump-toggle" type="button">saltar a ▾</button>' +
    '<div class="st-jump-body"></div></div>';
  document.getElementById('map').appendChild(stBar);
  // parar TODO lo de ratón: un click en una barra que burbujee hasta Leaflet
  // CIERRA el popup recién abierto por ese mismo click
  function swallowEvents(el) {
    ['pointerdown', 'mousedown', 'mouseup', 'click', 'touchstart', 'dblclick', 'wheel'].forEach(function (ev) {
      el.addEventListener(ev, function (e) { e.stopPropagation(); });
    });
  }
  swallowEvents(stBar);

  function stGoTo(i) {
    // cruzar de día con el caminador — como sea que pase (‹ ›, día ‹ ›,
    // saltar a opción) — OCULTA el día ACTIVO (no el del stepper: pueden
    // diferir si el usuario clickeó una fila de otro día) y ACTIVA el nuevo
    var newDi = dayIndexOf(stEls[i]);
    if (newDi >= 0 && newDi !== activeDay) {
      if (activeDay >= 0) setDayChecked(days[activeDay], false);
      setDayChecked(days[newDi], true);
      activeDay = newDi;
      syncLayers();
    }
    stCur = i;
    stMode = null;
    var el = stEls[i];
    var li = rowOf(el) || el;
    openDayOf(li);
    selectRow(li);
    if (li.id) updateHash(null, li.id);   // el hash sigue al caminador
    li.scrollIntoView({ block: 'center' });
    var key = el.dataset.location || el.dataset.transit;
    if (!showOnMap(key, stTitle(el), li.id, true)) {
      // sin geometría (conector automático): encuadrar sus puntos vecinos
      // COMPLETOS (con el mismo tope de acercamiento) y abrir su tarjeta
      var na = anchorsFor(el, stEls, i, false);
      var pts = [];
      if (na.prev) pts.push(na.prev);
      if (na.next) pts.push(na.next);
      if (pts.length && map) {
        var b = L.latLngBounds(pts);
        map.flyToBounds(b.pad(.25), { duration: .5, maxZoom: ST_MAX_ZOOM });
        openCardPopup(b.getCenter(), modalHtml(key) ||
          '<div class="modal"><h3>' + stTitle(el) + '</h3></div>');
      }
    }
    stRender();
  }
  function enterOption(cont) {
    var r = cont.querySelector(SEL_CHOICE);
    if (r && !r.checked) { r.checked = true; syncLayers(); }
    for (var j = 0; j < stEls.length; j++) {
      if (cont.contains(stEls[j])) { stGoTo(j); return; }
    }
    // opción PLANA (sin sub-pasos concretos): mostrarla en el mapa vía su
    // referencia — antes el click marcaba el radio y no pasaba nada más
    var a = cont.querySelector('a.modal-link');
    var key = a && modalKey(a);
    if (key) showOnMap(key, a.textContent);
    stMode = null;
    stRender();
  }
  // botones de opciones de un conjunto: planes = un botón por li; tiers = las
  // opciones de abajo agrupadas en columnas plegables por grupo
  function renderChoices(set, box) {
    box.innerHTML = '';
    var curEl = stEls[stCur];
    [].slice.call(set.children).forEach(function (li) {
      if (li.tagName !== 'LI') return;
      var opts = [].slice.call(li.querySelectorAll('.option')).filter(function (o) {
        return o.closest('.options') === set;
      });
      function mkBtn(cont, label) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'st-opt';
        b.textContent = label;
        if (li.dataset.tier) b.dataset.tier = li.dataset.tier;   // color del tier
        if (curEl && cont.contains(curEl)) b.classList.add('on');
        var r = cont.querySelector(SEL_CHOICE);
        if (r && r.checked) b.classList.add('chosen');
        b.addEventListener('click', function () { enterOption(cont); });
        return b;
      }
      if (opts.length) {
        // columna por grupo con su etiqueta fija (solo el «saltar a» se pliega)
        var col = document.createElement('div');
        col.className = 'st-col';
        var head = li.querySelector('b');
        if (head) {
          var hs = document.createElement('span');
          hs.className = 'st-col-head';
          if (li.dataset.tier) hs.dataset.tier = li.dataset.tier;
          hs.textContent = labelText(head.textContent, true);
          col.appendChild(hs);
        }
        opts.forEach(function (o) { col.appendChild(mkBtn(o, optLabel(o))); });
        box.appendChild(col);
      } else {
        box.appendChild(mkBtn(li, optLabel(li)));
      }
    });
  }
  function stRender() {
    var el = stEls[stCur];
    var center = stBar.querySelector('.st-center');
    var nextB = stBar.querySelector('.st-next');
    var jump = stBar.querySelector('.st-jump');
    // en modo elección ‹ es CANCELAR: siempre disponible aunque no haya
    // paso anterior (antes quedaba deshabilitado y no había salida)
    stBar.querySelector('.st-prev').disabled = !stMode && nextConcrete(stCur, -1) < 0;
    if (stMode) {                       // eligiendo a qué opción entrar
      center.innerHTML = '';
      renderChoices(stMode, center);
      nextB.hidden = true;
    } else {
      center.innerHTML = '<span class="st-cur"></span>';
      center.querySelector('.st-cur').textContent = el ? stTitle(el) : '—';
      var nx = nextConcrete(stCur, 1);
      nextB.hidden = false;
      nextB.disabled = nx < 0;
    }
    // dentro de una opción: «saltar a» con TODAS las opciones del conjunto
    var set = el ? el.closest('.options') : null;
    if (set && !stMode) {
      jump.hidden = false;
      var body = jump.querySelector('.st-jump-body');
      body.hidden = !stJumpOpen;
      jump.querySelector('.st-jump-toggle').textContent = stJumpOpen ? 'saltar a ▾' : 'saltar a ▸';
      if (stJumpOpen) renderChoices(set, body); else body.innerHTML = '';
    } else {
      jump.hidden = true;
    }
    if (dayBar) dsRender();
  }
  stBar.querySelector('.st-prev').addEventListener('click', function () {
    var p = nextConcrete(stCur, -1);
    if (stMode) { stMode = null; stRender(); return; }   // cancelar elección
    if (p >= 0) stGoTo(p);
  });
  stBar.querySelector('.st-next').addEventListener('click', function () {
    var nx = nextConcrete(stCur, 1);
    if (nx < 0) return;
    var curSet = stEls[stCur] ? stEls[stCur].closest('.options') : null;
    var nxSet = stEls[nx].closest('.options');
    if (nxSet && nxSet !== curSet) { stMode = nxSet; stRender(); return; }
    stGoTo(nx);
  });
  stBar.querySelector('.st-jump-toggle').addEventListener('click', function () {
    stJumpOpen = !stJumpOpen;
    stRender();
  });
  // click en una fila de la barra → el stepper se posiciona ahí
  function stSyncTo(li) {
    for (var j = 0; j < stEls.length; j++) {
      if (stEls[j] === li || li.contains(stEls[j])) { stCur = j; stMode = null; stRender(); return; }
    }
  }

  // ---------- STEPPER DE DÍA (barra inferior) ----------
  // ‹ día / día › saltan al PRIMER paso concreto del día vecino: apagan y
  // pliegan el día actual, prenden y muestran el nuevo completo
  var dayBar = document.createElement('div');
  dayBar.className = 'day-stepper';
  dayBar.innerHTML =
    '<button class="ds-prev" type="button">‹ día</button>' +
    '<span class="ds-cur"></span>' +
    '<button class="ds-next" type="button">día ›</button>';
  document.getElementById('map').appendChild(dayBar);
  swallowEvents(dayBar);
  function dayIndexOf(el) {
    return el ? days.indexOf(el.closest('section.day')) : -1;
  }
  // día "actual" del stepper de día: el ACTIVO si lo hay; si no, el del paso
  function curDayIdx() {
    return activeDay >= 0 ? activeDay : dayIndexOf(stEls[stCur]);
  }
  function setDayChecked(day, on) {
    Array.prototype.forEach.call(day.querySelectorAll('.ck:not(.ck-day)'), function (c) {
      c.checked = on;
    });
    updateMaster(day);
  }
  function firstConcreteOfDay(di) {
    for (var j = 0; j < stEls.length; j++) {
      if (stEls[j].closest('section.day') === days[di] && onChosenPath(stEls[j])) return j;
    }
    return -1;
  }
  // el día ACTIVO (visible en el mapa) es la fuente de verdad del stepper de
  // día — NO el día del paso actual: pueden divergir si el usuario clickea
  // filas de otros días sin activarlos
  function goDay(di) {
    if (di < 0 || di >= days.length) return;
    if (activeDay >= 0 && activeDay !== di) setDayChecked(days[activeDay], false);
    setDayChecked(days[di], true);
    activeDay = di;
    openOnly(days[di]);
    syncLayers();
    var j = firstConcreteOfDay(di);
    if (j >= 0) {
      stGoTo(j);
    } else {
      // día sin pasos concretos: igual queda activo y navegable (antes el
      // stepper de día se atoraba aquí para siempre)
      history.replaceState(null, '', '#' + days[di].id);
      stRender();
    }
  }
  function dsRender() {
    var di = curDayIdx();
    var h3 = di >= 0 ? days[di].querySelector('h3') : null;
    dayBar.querySelector('.ds-cur').textContent =
      h3 ? labelText(h3.textContent) : '—';
    dayBar.querySelector('.ds-prev').disabled = di <= 0;
    dayBar.querySelector('.ds-next').disabled = di < 0 || di >= days.length - 1;
  }
  dayBar.querySelector('.ds-prev').addEventListener('click', function () {
    goDay(curDayIdx() - 1);
  });
  dayBar.querySelector('.ds-next').addEventListener('click', function () {
    goDay(curDayIdx() + 1);
  });
  stRender();

  // teléfono: el panel es un sobrepuesto que abre el botón ☰; al elegir algo
  // se cierra solo para dejar ver el popup
  var narrow = window.matchMedia('(max-width: 820px)');
  var toggle = document.createElement('button');
  toggle.className = 'panel-toggle';
  toggle.type = 'button';
  toggle.textContent = '☰';
  toggle.title = 'Días';
  document.body.appendChild(toggle);
  toggle.addEventListener('click', function () {
    document.body.classList.toggle('panel-open');
  });
  function closePanelIfNarrow() {
    if (narrow.matches) document.body.classList.remove('panel-open');
  }

  // toggle ⏳: ver el tiempo LIBRE entre pasos (huecos calculados, data-free)
  var freeBtn = document.createElement('button');
  freeBtn.className = 'free-toggle';
  freeBtn.type = 'button';
  freeBtn.textContent = '⏳';
  freeBtn.title = 'Ver tiempo libre entre pasos';
  document.body.appendChild(freeBtn);
  if (localStorage.getItem('mapa-free') === '1') {
    document.body.classList.add('show-free');
    freeBtn.classList.add('on');
  }
  freeBtn.addEventListener('click', function () {
    var on = document.body.classList.toggle('show-free');
    localStorage.setItem('mapa-free', on ? '1' : '0');
    freeBtn.classList.toggle('on', on);
  });

  // links a modal: si la clave tiene geometría, la tarjeta va al popup del
  // mapa (captura, para ganarle al dialog de itinerario.js); si no, dialog
  document.addEventListener('click', function (e) {
    var link = e.target.closest('.modal-link');
    if (!link || !e.target.closest('.panel')) return;
    if (devMode) {                        // en modo dev la fila se EDITA
      var liDev = rowOf(link);
      if (liDev) {
        e.preventDefault();
        e.stopPropagation();
        selectRow(liDev);
        openDevEditor(liDev);
      }
      return;
    }
    var key = modalKey(link);
    if (!key) return;
    var linkRow = rowOf(link);
    if (showOnMap(key, link.textContent, linkRow && linkRow.id)) {
      e.preventDefault();
      e.stopPropagation();
      selectRow(linkRow);
      updateHash(key, linkRow && linkRow.id);
      closePanelIfNarrow();
    }
  }, true);

  // click en la fila (fuera de casillas/links): seleccionar y mostrar su clave
  panel.addEventListener('click', function (e) {
    if (e.target.closest('input') || e.target.closest('.modal-link') ||
        e.target.closest('.day-head') || e.target.closest('.day-nav')) return;
    var li = rowOf(e.target);
    if (!li) return;
    selectRow(li);
    stSyncTo(li);
    if (devMode) { updateHash(null, li.id); openDevEditor(li); return; }
    var key = li.dataset.location || li.dataset.transit;
    if (key) {
      var title = li.querySelector('.title');
      if (showOnMap(key, title ? title.textContent : key, li.id)) {
        updateHash(key, li.id);
        closePanelIfNarrow();
      }
    } else {
      updateHash(null, li.id);
      var ks = keysUnder(li);          // fila-contenedor: enfocar TODO lo suyo
      if (ks.length) {
        haloFor(ks);
        focusKeys(ks);
      }
    }
  });

  // ---------- modo dev (solo localhost): click en fila = editar su paso YAML;
  // guardar hace POST al dev_server, que reescribe src/<viaje>/viaje.yaml y
  // reconstruye — la fila dN-rMM ES days[N-1].steps[M-1] (proyección 1:1)
  var TRIP = (GEO && GEO.trip) || location.pathname.split('/').slice(-2, -1)[0] || '';
  // llamada al dev_server: sin body = GET tal cual; con body = POST JSON con
  // trip incluido — siempre devuelve la promesa del JSON de respuesta
  function api(path, body) {
    if (body === undefined) {
      return fetch(path).then(function (r) { return r.json(); });
    }
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ trip: TRIP }, body))
    }).then(function (r) { return r.json(); });
  }
  var devMode = false;
  var drawer = null;
  var devAuth = 'ok';   // 'ok' | 'required' — lo dice el ping del dev server
  // el modo dev aparece cuando la página la SIRVE el dev server (localhost o
  // túnel compartido): la sonda /api/ping decide, no el hostname — en Pages
  // no hay server y el botón nunca existe
  fetch('/api/ping').then(function (r) { return r.json(); }).then(function (p) {
    if (!p || !p.ok) return;
    devAuth = p.auth;
    var devBtn = document.createElement('button');
    devBtn.className = 'dev-toggle';
    devBtn.type = 'button';
    devBtn.textContent = '🛠';
    devBtn.title = p.auth === 'ok'
      ? 'Modo dev: click en una fila = editar su YAML'
      : 'Modo dev (pide iniciar sesión con GitHub)';
    document.body.appendChild(devBtn);
    devMode = p.auth === 'ok' && localStorage.getItem('mapa-dev') === '1';
    devBtn.classList.toggle('on', devMode);
    devBtn.addEventListener('click', function () {
      if (devAuth !== 'ok') { devLogin(devBtn); return; }
      devMode = !devMode;
      localStorage.setItem('mapa-dev', devMode ? '1' : '0');
      devBtn.classList.toggle('on', devMode);
      if (!devMode) closeDrawer();
    });
  }).catch(function () { /* sin dev server (Pages): nada que hacer */ });
  // login por DEVICE FLOW: el server habla con GitHub; aquí solo se enseña el
  // código y se sondea hasta que la sesión queda puesta (cookie)
  function devLogin(devBtn) {
    api('/api/login/start', {}).then(function (d) {
      if (!d.ok) { alert('login: ' + d.error); return; }
      window.open(d.verification_uri, '_blank');
      var box = document.createElement('div');
      box.className = 'dev-login';
      box.innerHTML = 'GitHub → <b>' + d.user_code + '</b> en ' +
        '<a href="' + d.verification_uri + '" target="_blank" rel="noopener">' +
        d.verification_uri + '</a> <span class="dev-login-state">esperando…</span>';
      document.body.appendChild(box);
      var iv = setInterval(function () {
        api('/api/login/poll', { handle: d.handle }).then(function (p) {
          if (p.pending) return;
          clearInterval(iv);
          if (p.ok) {
            devAuth = 'ok';
            box.querySelector('.dev-login-state').textContent = '✓ ' + p.user;
            setTimeout(function () { box.remove(); }, 1500);
            devBtn.title = 'Modo dev: click en una fila = editar su YAML';
          } else {
            box.querySelector('.dev-login-state').textContent = '✗ ' + (p.error || 'falló');
          }
        }).catch(function () { clearInterval(iv); box.remove(); });
      }, (d.interval || 5) * 1000);
    }).catch(function (e) { alert('login: ' + e); });
  }
  function closeDrawer() {
    stopGeomEdit();
    if (drawer) { drawer.remove(); drawer = null; }
  }

  // ---------- editor de GEOMETRÍA de un segmento (modo dev) ----------
  // arrastra los vértices · click en un punto medio inserta uno · click
  // derecho sobre un vértice lo borra · «Ajustar a calle» pega la línea a la
  // vialidad más cercana (OSRM público) — cada cambio reescribe la línea
  // coords: del YAML de la entidad en el cajón; Guardar referencia persiste
  var geomEd = null;   // {key, coords, group, ta, msg}
  function stopGeomEdit() {
    if (geomEd) {
      if (map) map.removeLayer(geomEd.group);
      geomEd = null;
    }
  }
  // largo del camino y tiempo A PIE — espejo EXACTO de walk_calc/round_walk
  // del build (4 km/h; techo a múltiplo de 5 hasta 45, luego de 15)
  function pathMeters(coords) {
    var m = 0;
    for (var i = 1; i < coords.length; i++) {
      var dy = (coords[i][0] - coords[i - 1][0]) * 111000;
      var dx = (coords[i][1] - coords[i - 1][1]) * 111000 *
               Math.cos(coords[i - 1][0] * Math.PI / 180);
      m += Math.sqrt(dx * dx + dy * dy);
    }
    return m;
  }
  function walkMins(coords) {
    var mins = pathMeters(coords) / (4000 / 60);
    var m5 = Math.max(5, Math.ceil(mins / 5) * 5);
    return m5 <= 45 ? m5 : Math.ceil(mins / 15) * 15;
  }
  // '· 750 m ≈ ~15 min a pie' para los mensajes del editor (solo caminatas)
  function walkNote(coords, isWalk) {
    if (!isWalk || coords.length < 2) return '';
    return ' · ' + Math.round(pathMeters(coords)) + ' m ≈ ~' + walkMins(coords) + ' min a pie';
  }

  // reescribe la línea coords: del textarea de entidad y refleja en GEO —
  // lo usan el editor de geometría, el snap y el trazado Geo auto
  function setCoordsIn(ta, key, coords) {
    var s = coords.map(function (c) {
      return c[0].toFixed(6) + ',' + c[1].toFixed(6);
    }).join(' ');
    // OJO: la escalar larga puede venir PLEGADA en varias líneas (más
    // indentadas): reemplazar el bloque completo, no solo la primera
    var re = /^([ \t]*)coords:[^\n]*(?:\n\1[ \t]+[^\n]*)*/m;
    if (re.test(ta.value)) {
      ta.value = ta.value.replace(re, '$1coords: ' + s);
    } else {
      ta.value = ta.value.replace(/\s*$/, '\n') + '  coords: ' + s + '\n';
    }
    GEO.transits[key] = GEO.transits[key] || { color: '#7a6f63', mode: 'walk' };
    GEO.transits[key].coords = coords;
  }
  function geomToYaml() {
    if (!geomEd) return;
    setCoordsIn(geomEd.ta, geomEd.key, geomEd.coords);
  }
  function startGeomEdit(key, ta, msg) {
    stopGeomEdit();
    if (!map) return;
    var tr = GEO.transits[key];
    var coords = tr && tr.coords.length
      ? tr.coords.map(function (c) { return [c[0], c[1]]; })
      : (function () {
        // transit NUEVO sin geometría: sembrar la línea entre el último punto
        // del paso previo y el primero del siguiente (donde se referencia)
        for (var j = 0; j < stEls.length; j++) {
          if (stEls[j].dataset.transit !== key) continue;
          var na = neighborAnchors(stEls, j, false);
          if (na.prev && na.next) {
            return [[na.prev[0], na.prev[1]], [na.next[0], na.next[1]]];
          }
          break;
        }
        var c = map.getCenter(), d = 0.002;
        return [[c.lat, c.lng - d], [c.lat, c.lng + d]];
      })();
    var group = L.featureGroup().addTo(map);
    geomEd = { key: key, coords: coords, group: group, ta: ta, msg: msg };
    function redraw() {
      group.clearLayers();
      var line = L.polyline(coords, { color: '#d4a017', weight: 4, opacity: .9, dashArray: '1 7' });
      group.addLayer(line);
      coords.forEach(function (c, i) {
        var h = L.marker(c, {
          draggable: true,
          icon: L.divIcon({ className: 'geo-pt', iconSize: [12, 12] })
        });
        h.on('drag', function (e) {
          var ll = e.target.getLatLng();
          coords[i] = [ll.lat, ll.lng];
          line.setLatLngs(coords);
        });
        h.on('dragend', function () { redraw(); geomToYaml(); });
        h.on('contextmenu', function () {
          if (coords.length > 2) { coords.splice(i, 1); redraw(); geomToYaml(); }
        });
        group.addLayer(h);
      });
      for (var i = 0; i + 1 < coords.length; i++) {
        (function (i) {
          var mid = [(coords[i][0] + coords[i + 1][0]) / 2, (coords[i][1] + coords[i + 1][1]) / 2];
          var m = L.marker(mid, { icon: L.divIcon({ className: 'geo-mid', iconSize: [10, 10] }) });
          m.on('click', function () {
            coords.splice(i + 1, 0, mid);
            redraw();
            geomToYaml();
          });
          group.addLayer(m);
        })(i);
      }
    }
    redraw();
    map.flyToBounds(L.latLngBounds(coords).pad(.3), { duration: .4 });
  }
  function snapGeomToRoads() {
    if (!geomEd) return;
    var msg = geomEd.msg;
    msg.textContent = 'ajustando a calles…';
    // punto por punto contra /nearest (el /match del OSRM público rechaza
    // trazas largas con TooBig); caminatas van al perfil PEATONAL de FOSSGIS
    // (incluye calles peatonales), lo demás al de auto
    var tr0 = GEO.transits[geomEd.key];
    var base = (!tr0 || tr0.mode === 'walk')
      ? 'https://routing.openstreetmap.de/routed-foot/nearest/v1/foot/'
      : 'https://router.project-osrm.org/nearest/v1/driving/';
    var reqs = geomEd.coords.map(function (c) {
      return fetch(base + c[1].toFixed(6) + ',' + c[0].toFixed(6))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var w = d.code === 'Ok' && d.waypoints && d.waypoints[0];
          return w && w.location ? [w.location[1], w.location[0]] : null;
        })
        .catch(function () { return null; });
    });
    // capturar la edición que originó el snap: si al llegar las respuestas ya
    // se editaba OTRO segmento, tirarlas (escribían índice a índice en él)
    var mine = geomEd;
    Promise.all(reqs).then(function (snapped) {
      if (geomEd !== mine) return;
      var moved = 0;
      snapped.forEach(function (p, i) {
        if (p) { geomEd.coords[i] = p; moved += 1; }
      });
      geomToYaml();                                        // persistir en GEO + textarea
      startGeomEdit(geomEd.key, geomEd.ta, geomEd.msg);    // redibujar con lo ajustado
      var trSnap = GEO.transits[geomEd.key];
      geomEd.msg.textContent = 'snap ✓ (' + moved + '/' + snapped.length + ' puntos' +
        walkNote(geomEd.coords, trSnap && trSnap.mode === 'walk') + ')';
    });
  }
  function openDevEditor(li) {
    // id extendido: dN-rMM[-gG[-oO]-sS] — los sub-pasos de options también
    // se editan; el sufijo viaja como `sub` y el server navega el YAML
    var m = /^d(\d+)-r(\d+)((?:-[gos]\d+)*)$/.exec(li.id || '');
    if (!m) return;
    var sub = m[3] || '';
    closeDrawer();
    // «todo» de la fila: identidad, claves, horario visible y conflicto
    var facts = ['fila ' + li.id + '  (days[' + (m[1] - 1) + '].steps[' + (m[2] - 1) + ']' +
                 (sub ? ' ' + sub : '') + ')'];
    ['location', 'transit', 'mode'].forEach(function (k) {
      if (li.dataset[k]) facts.push(k + ': ' + li.dataset[k]);
    });
    var t = li.querySelector('time');
    if (t) facts.push('horario: ' + labelText(t.textContent));
    var w = li.querySelector('.warn');
    if (w) facts.push('⚠️ ' + (w.getAttribute('title') || ''));
    drawer = document.createElement('div');
    drawer.className = 'dev-drawer';
    drawer.innerHTML = '<div class="dev-info"></div>' +
      '<textarea class="dev-step" spellcheck="false">cargando…</textarea>' +
      '<div class="dev-btns"><button class="dev-save" type="button">Guardar</button>' +
      '<button class="dev-rebuild" type="button">Rebuild</button>' +
      '<button class="dev-deploy" type="button" ' +
      'title="Rebuild + copiar a viajes-icons/viajes2 + push (Pages publica)">Deploy 🚀</button>' +
      '<button class="dev-close" type="button">Cancelar</button><span class="dev-msg"></span></div>' +
      '<div class="dev-btns dev-step-ops">' +
      '<button class="dev-add-before" type="button" title="Insertar un paso nuevo ANTES de esta fila">+ antes</button>' +
      '<button class="dev-add-after" type="button" title="Insertar un paso nuevo DESPUÉS de esta fila">+ después</button>' +
      '<button class="dev-move-up" type="button" title="Subir esta fila un lugar">▲ subir</button>' +
      '<button class="dev-move-down" type="button" title="Bajar esta fila un lugar">▼ bajar</button></div>' +
      '<div class="dev-refs"></div>' +
      '<div class="dev-btns dev-newref-row">' +
      '<input class="dev-newref" spellcheck="false" placeholder="nueva-clave">' +
      '<button class="dev-addref" type="button" ' +
      'title="Crear una referencia aún sin catálogo (queda pendiente de geometría)">➕ ref</button></div>' +
      '<div class="dev-btns dev-tpl" hidden><span class="dev-tpl-label">plantilla:</span>' +
      '<button type="button" data-tpl="lugar">lugar</button>' +
      '<button type="button" data-tpl="walk">caminata</button>' +
      '<button type="button" data-tpl="train">tren</button>' +
      '<button type="button" data-tpl="bus">bus</button>' +
      '<button type="button" data-tpl="ferry">ferry</button></div>' +
      '<textarea class="dev-entity" spellcheck="false" hidden></textarea>' +
      '<div class="dev-btns dev-entity-btns" hidden>' +
      '<button class="dev-save-entity" type="button">Guardar referencia</button>' +
      '<button class="dev-geom" type="button" hidden ' +
      'title="Arrastra vértices · click en punto medio inserta · click derecho borra">Geometría</button>' +
      '<button class="dev-snap" type="button" hidden>Ajustar a calle</button>' +
      '<button class="dev-autogeo" type="button" hidden ' +
      'title="Trazar coords por ruta OSRM entre las anclas vecinas del paso">Geo auto</button>' +
      '<span class="dev-entity-name"></span></div>';
    drawer.querySelector('.dev-info').textContent = facts.join('\n');
    document.body.appendChild(drawer);
    var ta = drawer.querySelector('.dev-step');
    var msg = drawer.querySelector('.dev-msg');
    // rebuild compartido: reconstruye y, si salió bien, corre onOk (el botón
    // recarga; mover/insertar pasos recoloca el hash antes de recargar)
    function doRebuild(onOk) {
      api('/api/rebuild', {})
        .then(function (d) {
          if (d.ok) onOk();
          else msg.textContent = 'error: ' + d.error;
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    }

    // lo REFERENCIADO por la fila (location/transit + @refs de los textos):
    // un botón por clave carga su YAML del catálogo para editarlo también
    var refKeys = [];
    if (li.dataset.location) refKeys.push(li.dataset.location);
    if (li.dataset.transit) refKeys.push(li.dataset.transit);
    li.querySelectorAll('.modal-link').forEach(function (a) {
      var k = modalKey(a);
      if (k && refKeys.indexOf(k) < 0) refKeys.push(k);
    });
    var refsBox = drawer.querySelector('.dev-refs');
    var entTa = drawer.querySelector('.dev-entity');
    var entBtns = drawer.querySelector('.dev-entity-btns');
    var entName = drawer.querySelector('.dev-entity-name');
    var geomBtn = drawer.querySelector('.dev-geom');
    var snapBtn = drawer.querySelector('.dev-snap');
    var entCur = null;    // {kind, key} de la entidad cargada
    geomBtn.addEventListener('click', function () {
      if (geomEd) {
        var doneCoords = geomEd.coords;
        var doneTr = GEO.transits[geomEd.key];
        stopGeomEdit();
        geomBtn.textContent = 'Geometría';
        snapBtn.hidden = true;
        msg.textContent = 'edición de geometría terminada' +
          walkNote(doneCoords, doneTr && doneTr.mode === 'walk');
        return;
      }
      if (!entCur) { msg.textContent = 'carga primero una referencia'; return; }
      try {
        startGeomEdit(entCur.key, entTa, msg);
      } catch (err) {
        msg.textContent = 'geometría error: ' + (err && err.message || err);
        return;
      }
      geomBtn.textContent = 'Terminar geometría';
      snapBtn.hidden = false;
    });
    snapBtn.addEventListener('click', snapGeomToRoads);
    var autogeoBtn = drawer.querySelector('.dev-autogeo');
    var tplRow = drawer.querySelector('.dev-tpl');
    // plantillas para referencias NUEVAS (aún sin catálogo)
    var TPL = {
      lugar: { kind: 'places', body: "name: \ngps: \ndescription: ''" },
      walk: { kind: 'transits', body: "mode: walk\ncolor: '#7a6f63'" },
      train: { kind: 'transits', body: "mode: train\nline: \ncolor: '#0d6bb7'\nchip: ''\nplatform: []\nreverse: ''\nstations: []" },
      bus: { kind: 'transits', body: "mode: bus\nline: \ncolor: '#8a6d3b'" },
      ferry: { kind: 'transits', body: "mode: ferry\ncolor: '#005caf'" }
    };
    function showEntity(kind, key, yamlText, isNew) {
      entCur = { kind: kind, key: key };
      entName.textContent = (kind || '¿tipo?') + ' · ' + key + (isNew ? ' (NUEVA)' : '');
      entTa.value = yamlText;
      entTa.hidden = false;
      entBtns.hidden = false;
      tplRow.hidden = !isNew;
      stopGeomEdit();
      geomBtn.hidden = kind !== 'transits';
      geomBtn.textContent = 'Geometría';
      snapBtn.hidden = true;
      autogeoBtn.hidden = kind !== 'transits';
    }
    var entReq = 0;    // generación: gana el ÚLTIMO click, no la respuesta más lenta
    function loadRef(key) {
      msg.textContent = '';
      var myReq = ++entReq;
      api('/api/entity?trip=' + encodeURIComponent(TRIP) + '&key=' + encodeURIComponent(key))
        .then(function (d) {
          if (myReq !== entReq) return;   // ya se pidió otra referencia
          if (d.ok) {
            showEntity(d.kind, key, d.yaml, false);
          } else {
            // no existe: modo CREAR — elegir plantilla y Guardar referencia
            showEntity(null, key, key + ':\n  # referencia nueva — elige una plantilla arriba\n', true);
            msg.textContent = 'referencia sin catálogo: elige plantilla y guarda';
          }
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    }
    refKeys.forEach(function (key) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = key;
      b.addEventListener('click', function () { loadRef(key); });
      refsBox.appendChild(b);
    });
    // crear una referencia SIN CUMPLIR desde cero (clave nueva escrita a mano)
    drawer.querySelector('.dev-addref').addEventListener('click', function () {
      var key = drawer.querySelector('.dev-newref').value.trim();
      if (!/^[a-z0-9][a-z0-9-]*$/.test(key)) {
        msg.textContent = 'clave inválida (minúsculas, dígitos y guiones)';
        return;
      }
      loadRef(key);
    });
    tplRow.addEventListener('click', function (e) {
      var tpl = e.target.dataset && TPL[e.target.dataset.tpl];
      if (!tpl || !entCur) return;
      var body = tpl.body.split('\n').map(function (l) { return '  ' + l; }).join('\n');
      showEntity(tpl.kind, entCur.key, entCur.key + ':\n' + body + '\n', true);
      tplRow.hidden = false;   // se puede cambiar de plantilla antes de guardar
      msg.textContent = 'plantilla ' + e.target.dataset.tpl + ' — edita y Guardar referencia';
    });
    // GEO AUTO: trazar coords por ruta OSRM entre las anclas vecinas del paso
    autogeoBtn.addEventListener('click', function () {
      if (!entCur) return;
      var a = (GEO.anchors || {})[li.id] || {};
      var prev = a.prev, next = a.next;
      if (!prev || !next) {
        var idx = stEls.indexOf(li);
        if (idx >= 0) {
          var na = neighborAnchors(stEls, idx, false);
          prev = prev || na.prev;
          next = next || na.next;
        }
      }
      if (!prev || !next) { msg.textContent = 'sin anclas vecinas para trazar'; return; }
      var walk = /mode:\s*walk/.test(entTa.value);
      var base = walk
        ? 'https://routing.openstreetmap.de/routed-foot/route/v1/foot/'
        : 'https://router.project-osrm.org/route/v1/driving/';
      msg.textContent = 'trazando ruta (' + (walk ? 'peatonal' : 'auto') + ')…';
      fetch(base + prev[1] + ',' + prev[0] + ';' + next[1] + ',' + next[0] +
            '?overview=full&geometries=geojson')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var cs = d.routes && d.routes[0] && d.routes[0].geometry.coordinates;
          if (!cs || !cs.length) { msg.textContent = 'ruta no encontrada (' + (d.code || '?') + ')'; return; }
          var pts = cs.map(function (c) { return [c[1], c[0]]; });
          setCoordsIn(entTa, entCur.key, pts);
          if (geomEd && geomEd.key === entCur.key) startGeomEdit(entCur.key, entTa, msg);
          msg.textContent = 'geo auto ✓ (' + pts.length + ' pts' + walkNote(pts, walk) +
            ') — Guardar referencia para persistir';
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    });
    drawer.querySelector('.dev-save-entity').addEventListener('click', function () {
      if (!entCur) return;
      if (!entCur.kind) { msg.textContent = 'elige una plantilla primero (fija el catálogo)'; return; }
      msg.textContent = 'guardando referencia…';
      api('/api/entity', { kind: entCur.kind, key: entCur.key, yaml: entTa.value })
        .then(function (d) {
          if (!d.ok) { msg.textContent = 'error: ' + d.error; return; }
          msg.textContent = 'referencia guardada ✓ (pendiente rebuild)';
          tplRow.hidden = true;
          entName.textContent = entCur.kind + ' · ' + entCur.key;
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    });
    api('/api/step?trip=' + encodeURIComponent(TRIP) + '&day=' + m[1] + '&step=' + m[2] +
        '&sub=' + encodeURIComponent(sub))
      .then(function (d) { ta.value = d.ok ? d.yaml : 'error: ' + d.error; })
      .catch(function (e) { ta.value = 'error: ' + e; });
    drawer.querySelector('.dev-close').addEventListener('click', closeDrawer);
    // Guardar SOLO escribe el YAML (se pueden editar varias filas); Rebuild
    // reconstruye una vez y recarga — el hash #@fila nos regresa aquí mismo
    drawer.querySelector('.dev-save').addEventListener('click', function () {
      msg.textContent = 'guardando…';
      api('/api/step', { day: +m[1], step: +m[2], sub: sub, yaml: ta.value })
        .then(function (d) {
          msg.textContent = d.ok ? 'guardado ✓ (pendiente rebuild)' : 'error: ' + d.error;
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    });
    drawer.querySelector('.dev-deploy').addEventListener('click', function () {
      msg.textContent = 'rebuild + deploy…';
      api('/api/rebuild', { deploy: true })
        .then(function (d) {
          if (!d.ok) { msg.textContent = 'error: ' + d.error; return; }
          msg.textContent = 'desplegado ✓ — recargando…';
          setTimeout(function () { location.reload(); }, 600);
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    });
    drawer.querySelector('.dev-rebuild').addEventListener('click', function () {
      msg.textContent = 'rebuild…';
      doRebuild(function () {
        msg.textContent = 'rebuild ok — recargando…';
        setTimeout(function () { location.reload(); }, 400);
      });
    });
    // insertar / mover pasos: el server reescribe days[].steps[] y al aceptar
    // se pregunta si recalcular (rebuild + recarga posicionada en el paso)
    function stepOp(path, body) {
      msg.textContent = '…';
      api(path, Object.assign({ day: +m[1], step: +m[2], sub: sub }, body))
        .then(function (d) {
          if (!d.ok) { msg.textContent = 'error: ' + d.error; return; }
          // el paso EDITADO cambió de número: re-apuntar el cajón YA — si no,
          // el siguiente Guardar/mover escribiría sobre la fila equivocada.
          // El índice que cambia es el ÚLTIMO segmento (sN del sub, o el rMM)
          var mine = sub ? +(/(\d+)$/.exec(sub) || [0, 0])[1] : +m[2];
          if (path === '/api/step-insert') {
            if (body.where === 'before') mine += 1;      // me recorrí un lugar
          } else {
            mine = d.step;                               // move: soy el movido
          }
          var newId;
          if (sub) {
            sub = sub.replace(/\d+$/, String(mine));
            newId = 'd' + m[1] + '-r' + String(+m[2]).padStart(2, '0') + sub;
          } else {
            m[2] = String(mine);
            newId = 'd' + m[1] + '-r' + String(mine).padStart(2, '0');
          }
          drawer.querySelector('.dev-info').textContent =
            'fila ' + newId + '  — tras ' + path.slice(5);
          var targetN = sub ? sub.replace(/\d+$/, String(d.step)) : null;
          var target = sub
            ? 'd' + m[1] + '-r' + String(+m[2]).padStart(2, '0') + targetN
            : 'd' + m[1] + '-r' + String(d.step).padStart(2, '0');
          if (window.confirm('Guardado. ¿Recalcular (rebuild) ahora?')) {
            doRebuild(function () {
              location.hash = '#@' + target;
              location.reload();
            });
          } else {
            msg.textContent = 'guardado ✓ (pendiente rebuild; este cajón ya apunta a ' +
              newId + ')';
          }
        })
        .catch(function (e) { msg.textContent = 'error: ' + e; });
    }
    drawer.querySelector('.dev-add-before').addEventListener('click', function () {
      stepOp('/api/step-insert', { where: 'before' });
    });
    drawer.querySelector('.dev-add-after').addEventListener('click', function () {
      stepOp('/api/step-insert', { where: 'after' });
    });
    drawer.querySelector('.dev-move-up').addEventListener('click', function () {
      stepOp('/api/step-move', { dir: -1 });
    });
    drawer.querySelector('.dev-move-down').addEventListener('click', function () {
      stepOp('/api/step-move', { dir: 1 });
    });
  }

  // ---------- llegada: restaurar el DÓNDE ESTAMOS desde el hash ----------
  // #dN = día exclusivo · #@fila = fila seleccionada · #m-clave@fila = popup;
  // en modo dev la fila reabre su editor. itinerario.js pudo abrir su dialog
  // con el mismo hash: aquí manda el mapa, se cierra.
  (function restore() {
    var overlayEl = document.getElementById('overlay');
    var m = /^#(?:m-([^@]+))?(?:@(.+))?$/.exec(location.hash || '');
    var dm = /^#(d\d+)$/.exec(location.hash || '');
    function applyDefault() {
      // día 1 completo seleccionado, stepper en su primer paso concreto
      // (sin volar: el encuadre inicial ya lo hace)
      if (!days.length) return;
      setDayChecked(days[0], true);
      activeDay = 0;
      openOnly(days[0]);
      var j0 = firstConcreteOfDay(0);
      if (j0 >= 0) { stCur = j0; stRender(); }
      schedSync();
    }
    if (dm) {
      // #dN: ese día completo seleccionado y el stepper en su primer paso;
      // día inexistente (hash viejo) → estado por defecto, no página en blanco
      var sec = document.getElementById(dm[1]);
      if (sec) { goDay(days.indexOf(sec)); restoredView = true; } else applyDefault();
      return;
    }
    if (!m || (!m[1] && !m[2])) {
      applyDefault();
      return;
    }
    if (overlayEl && overlayEl.open) overlayEl.close();
    var li = m[2] ? document.getElementById(m[2]) : null;
    if (li) {
      openDayOf(li);
      // el día de la fila del hash llega ACTIVO (visible en el mapa)
      var liDay = li.closest('section.day');
      if (liDay) {
        setDayChecked(liDay, true);
        activeDay = days.indexOf(liDay);
      }
      selectRow(li);
      stSyncTo(li);
      li.scrollIntoView({ block: 'center' });
      schedSync();
    } else if (!m[1]) {
      // fila del hash ya no existe (ids renumerados) y no hay modal → defecto
      applyDefault();
      return;
    }
    if (devMode && li) {
      openDevEditor(li);
    } else if (m[1]) {
      var title = li && li.querySelector('.title');
      if (showOnMap(m[1], title ? title.textContent : m[1], li && li.id)) {
        restoredView = true;   // que el encuadre de arranque no pise este vuelo
      }
    }
  })();
})();
