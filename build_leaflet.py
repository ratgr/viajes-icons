# -*- coding: utf-8 -*-
"""leaflet-viaje.html — mapa autocontenido (Leaflet + Positron, sin key).
Itinerario por día con casillas integradas; rutas INTERCALADAS con sus lugares
en orden (cada ruta va antes del lugar al que lleva). Hoteles/aeropuertos viven
en los días donde se usan. Popup limpio: nombre (link al plan) · hora · tiempo,
foto, descripción, 🏛️ historia, Maps. Escritorio: panel acoplado; móvil: overlay."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = os.path.dirname(os.path.abspath(__file__))
DATA = open(SD + "/viaje-data.json", encoding="utf-8").read()
from modales import MODAL_CSS

HTML = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Japón 2026 · mapa por día</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-polylinedecorator@1.6.0/dist/leaflet.polylineDecorator.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,sans-serif;color:#241f1c}
  #map{position:absolute;inset:0}
  .panel{position:absolute;z-index:1000;top:10px;left:10px;background:#fff;border-radius:10px;
    box-shadow:0 4px 18px rgba(0,0,0,.28);max-height:calc(100% - 20px);display:flex;flex-direction:column;width:300px}
  .phead{padding:9px 12px 4px}
  .phead h1{font-size:15px;margin:0}
  .phead .sub{font-size:10.5px;color:#777;margin-top:2px}
  .daybtns{display:flex;flex-wrap:wrap;gap:4px;padding:6px 10px 8px;border-bottom:1px solid #eee}
  .daybtns button{font-size:11px;border:1px solid #ccc;background:#f7f7f7;border-radius:6px;padding:3px 6px;cursor:pointer}
  .daybtns button.on{background:#b23a2a;color:#fff;border-color:#b23a2a}
  .daybtns .allbtn{background:#2c6ba0;color:#fff;border-color:#2c6ba0}
  .daybtns .nonebtn{background:#777;color:#fff;border-color:#777}
  .tree{overflow:auto;padding:2px 0 12px}
  .dayg{border-top:1px solid #eee}
  .dhead{display:flex;align-items:center;gap:7px;padding:6px 10px;cursor:pointer;user-select:none}
  .dhead:hover{background:#faf7f3}
  .dhead .caret{width:11px;color:#999;font-size:11px;transition:transform .15s}
  .dhead.open .caret{transform:rotate(90deg)}
  .dhead .dname{font-size:12.5px;font-weight:700;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dhead .dtime{font-size:10.5px;color:#b23a2a;background:#f6ebe8;border-radius:5px;padding:1px 5px;flex:0 0 auto}
  .dbody{display:none;padding:0 0 6px 4px}
  .dbody.open{display:block}
  .sublbl{font-size:10.5px;color:#8a8078;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:6px 10px 1px}
  .it{display:flex;gap:7px;align-items:flex-start;padding:3px 10px 3px 8px;border-left:3px solid transparent}
  .it:hover{background:#f4f7fa;border-left-color:#2c6ba0}
  .it.sel{background:#fdeee9;border-left-color:#b23a2a;box-shadow:inset 0 0 0 1px rgba(178,58,42,.25)}
  .selmark{filter:drop-shadow(0 0 5px rgba(178,58,42,.9)) drop-shadow(0 0 2px rgba(178,58,42,.9));z-index:900!important}
  .it.rt{padding-top:1px;padding-bottom:1px}
  .it .ck{margin:2px 0 0;flex:0 0 auto}
  .it .pin{width:12px;height:12px;border-radius:50%;flex:0 0 auto;margin-top:2px;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.15)}
  .it .npin{background:#b23a2a;color:#fff;border-radius:50%;width:18px;height:18px;line-height:18px;text-align:center;font-size:10.5px;font-weight:700;flex:0 0 auto;margin-top:0}
  .it .ln{width:16px;height:0;border-top:3px solid;flex:0 0 auto;margin-top:8px}
  .it.walk .ln{border-top-style:dotted;border-top-width:3px}
  .it .bd{min-width:0;flex:1;cursor:pointer}
  .it .nm{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .it.rt .nm{font-weight:500;font-size:11.5px;color:#6a625a}
  .it .ds{font-size:10.5px;color:#7a7268;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .it .tm{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;flex:0 0 auto;padding-top:1px;white-space:nowrap}
  .tm.fix{color:#b23a2a}.tm.est{color:#9a9188}
  .tm.warn{color:#fff;background:#c0392b;border-radius:5px;padding:0 4px}
  .it.conflict{background:#fdecea}
  .lp{font-size:13px;max-width:270px}
  .lp .tt{font-weight:700;font-size:14px}.lp .tt a{color:inherit;text-decoration:none;border-bottom:1px dotted #b23a2a}
  .lp .meta{color:#8a7f72;font-weight:600;font-size:12px}
  .lp .pf{width:100%;max-height:150px;object-fit:cover;border-radius:8px;margin:7px 0;display:block;background:#eee}
  .lp .dsc{margin:5px 0;font-size:12.5px}
  .lp .ph{font-size:11.5px;color:#6a625a;margin:6px 0;line-height:1.35}
  .lp a.gm{color:#b23a2a;font-weight:700;text-decoration:none}
  .num{background:#b23a2a;color:#fff;border-radius:50%;width:20px;height:20px;line-height:20px;text-align:center;font-size:11px;font-weight:700;box-shadow:0 1px 3px rgba(0,0,0,.4)}
  .dot{border-radius:50%;width:13px;height:13px;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)}
  .fold{position:absolute;z-index:1001;top:10px;right:10px;background:#fff;border:none;border-radius:8px;width:36px;height:36px;box-shadow:0 2px 8px rgba(0,0,0,.25);cursor:pointer;font-size:17px;display:none}
  @media(min-width:821px){
    body{overflow:hidden}
    .panel{position:absolute;top:0;left:0;height:100%;max-height:100%;width:380px;border-radius:0;box-shadow:2px 0 12px rgba(0,0,0,.12)}
    #map{left:380px}
    .it .nm,.it .ds{white-space:normal}
  }
  /* modo móvil: barras de recorrido paso a paso */
  .mbar{position:absolute;left:8px;right:8px;z-index:1002;display:flex;gap:6px;align-items:center;pointer-events:none}
  .mbar>*{pointer-events:auto}
  .mbar.mtop{top:8px}.mbar.mbot{bottom:8px}
  /* escritorio (no móvil): barras a la derecha del panel, nunca lo tapan */
  body:not(.mob) .mbar{left:392px;right:14px}
  body:not(.mob) .mbar.mtop{top:12px}
  body:not(.mob) .mbar.mbot{bottom:12px}
  /* grupo de comida colapsable + ruta a cada opción */
  .mealh{cursor:pointer;display:flex;align-items:center;gap:5px}
  .mealh .mcar{margin-left:auto;color:#b23a2a;font-size:11px;transition:transform .15s}
  .mealh.closed .mcar{transform:rotate(-90deg)}
  .mealc{padding-left:16px;border-left:2px solid #efe6e0;margin-left:8px}
  .mealc.closed{display:none}
  .optgrp{margin:2px 0 7px;border-left:2px solid #d8cfc7;padding-left:6px}
  .planh{font-weight:700;font-size:11.5px;color:#b23a2a;padding:3px 0 1px}
  .dimmed{opacity:.4} /* marcador de alternativa (no elegida) */
  .it.dimrow .nm,.it.dimrow .ds{opacity:.55}
  .mbar .nav{width:40px;height:40px;border-radius:10px;border:none;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.28);font-size:22px;line-height:1;cursor:pointer;flex:0 0 auto}
  .mbar .nav:disabled{opacity:.4}
  .mbar .cur{flex:1;background:#fff;border:none;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.28);padding:9px 10px;font-size:13px;font-weight:700;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mbar .cur .stp{font-size:10px;color:#8a7f72;font-weight:600}
  .mbar .mopts{flex:1;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
  .mbar .mopts::-webkit-scrollbar{display:none}
  .mbar .opt{flex:0 0 auto;background:#fff;border:1px solid #ccc;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.22);padding:7px 10px;font-size:12px;font-weight:600;cursor:pointer;max-width:130px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mbar .opt.on{background:#b23a2a;color:#fff;border-color:#b23a2a}
  .daymenu{position:absolute;inset:0;z-index:1004;background:rgba(0,0,0,.4);display:flex;flex-direction:column;justify-content:center;gap:6px;padding:18px}
  .daymenu button{background:#fff;border:none;border-radius:9px;padding:12px;font-size:14px;font-weight:600;cursor:pointer;text-align:left}
  .daymenu button.on{background:#b23a2a;color:#fff}
  body.mob .panel{display:none}
  body.mob .fold{display:none}
  body.mob .mbar{display:flex}
  /* que las barras no tapen los controles del mapa (zoom, capas, atribución) */
  .leaflet-top{top:58px}.leaflet-bottom{bottom:58px}
  /* herramienta: dibujar ruta a mano y copiar coordenadas */
  #drawbox{position:absolute;z-index:1500;right:12px;bottom:72px;width:250px;background:#fff;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.32);padding:10px;font-size:12px}
  #drawbox .dbhd{font-weight:700;margin-bottom:6px;font-size:11.5px;line-height:1.3}
  #drawbox textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,monospace;font-size:11px;resize:vertical;border:1px solid #ccc;border-radius:6px;padding:5px}
  #drawbox .dbcount{font-size:10.5px;color:#888;margin:3px 0}
  #drawbox .dbbtns{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
  #drawbox .dbbtns button{font-size:11px;border:1px solid #ccc;background:#f7f7f7;border-radius:6px;padding:4px 7px;cursor:pointer}
  #drawbox .dbbtns #dbcopy{background:#e6007e;color:#fff;border-color:#e6007e}
  .leaflet-bar a.drawon{background:#e6007e;color:#fff}
  .dbtip{background:#e6007e;color:#fff;border:none;box-shadow:none;font-size:10px;font-weight:700;padding:0 3px;border-radius:4px}
  .dbtip::before{display:none}
</style></head><body>
<div id="map"></div>
<button class="fold" id="fold">☰</button>
<div class="mbar mtop" id="mtop"></div>
<div class="mbar mbot" id="mbot"></div>
<div class="panel" id="panel">
  <div class="phead"><h1>⛩️ Japón 2026 · mapa por día</h1>
    <div class="sub">Casilla = prender/apagar. Toca el nombre para volar ahí. Rojo = hora fija · gris = estimada.</div></div>
  <div class="daybtns" id="daybtns"></div>
  <div class="tree" id="tree"></div>
</div>
<script>
var DATA = __DATA__;
var APP='https://ratgr.github.io/viajes-icons/app/japon.html';
var map = L.map('map',{zoomControl:true}).setView([35.0,135.6],6);
var bases={
  'Claro (Positron)':L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:20,subdomains:'abcd',attribution:'© OpenStreetMap © CARTO'}),
  'Sin etiquetas':L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',{maxZoom:20,subdomains:'abcd',attribution:'© OpenStreetMap © CARTO'}),
  'Color (Voyager)':L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{maxZoom:20,subdomains:'abcd',attribution:'© OpenStreetMap © CARTO'}),
  'Satélite':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'© Esri'})
};
bases['Claro (Positron)'].addTo(map);
L.control.layers(bases,null,{position:'topright'}).addTo(map);

var TIER={Take:'#4a7d3a',Ai:'#2c6ba0',Shu:'#b23a2a'};
function esc(s){return String(s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function pColor(kind,tier){if(kind==='site'||kind==='stop')return '#b23a2a';if(kind==='hotel')return '#f0a500';if(kind==='aero')return '#7b4fa6';return TIER[tier]||'#777';}
function norm(s){return String(s||'').replace(/^[\s⭐🍜🏨✈️📍·]+/,'').replace(/\s*\(d\d+\)\s*$/,'').replace(/^\d+\.\s*/,'').replace(/\d\d:\d\d\s*·?\s*/,'').trim().toLowerCase();}
function stopTime(name){var m=/(\d\d:\d\d)/.exec(name);return m?m[1]:'';}
function stopClean(name){return name.replace(/^\d+\.\s*/,'').replace(/\d\d:\d\d\s*·?\s*/,'').replace(/\s*\(d\d+\)\s*$/,'').trim();}
function segEnds(name){var m=name.split(':').pop().split('⇒')[0];var a=m.split('→');return a.length>=2?{a:a[0].trim(),b:a[1].trim()}:null;}
function segTarget(name){var i=name.indexOf('⇒');return i>=0?norm(name.slice(i+1)):'';}
function fmtMin(m){if(!m)return '';if(m<60)return '~'+m+' min';var h=(m/60|0),mm=m%60;return '~'+h+' h'+(mm?(' '+mm+' min'):'');}

function placeMarker(it){
  var m;
  if(it.num){m=L.marker(it.ll,{icon:L.divIcon({className:'',html:'<div class="num">'+it.num+'</div>',iconSize:[20,20],iconAnchor:[10,10]})});}
  else{m=L.marker(it.ll,{icon:L.divIcon({className:'',html:'<div class="dot" style="background:'+it.color+'"></div>',iconSize:[13,13],iconAnchor:[7,7]})});}
  var meta=[];if(it.tier)meta.push(it.tier);if(it.time)meta.push(it.time);if(it.incTxt)meta.push(it.incTxt);
  var metaHtml=meta.length?(' <span class="meta">· '+esc(meta.join(' · '))+'</span>'):'';
  var img=it.foto?('<img class="pf" src="'+it.foto+'" loading="lazy" onerror="this.style.display=\'none\'">'):'';
  var desc=it.desc?('<div class="dsc">'+esc(it.desc)+'</div>'):'';
  var hist=it.hist?('<div class="ph">🏛️ '+esc(it.hist)+'</div>'):'';
  var html='<div class="lp"><div class="tt"><a href="'+APP+'" target="_blank" title="Ver el plan">'+esc(it.title)+'</a>'+metaHtml+'</div>'+
    img+desc+hist+(it.maps?'<a class="gm" href="'+it.maps+'" target="_blank">Abrir en Google Maps ↗</a>':'')+'</div>';
  m.bindPopup(it.pop||html,{maxWidth:it.pop?320:285});
  m.on('click',function(){if(typeof selectStep==='function')selectStep(it,false);});
  return m;
}
function segLayer(seg){
  var w=seg.mode==='walk'?3:(seg.mode==='train'?6:5),dash=seg.mode==='walk'?'4 7':null;
  var pl=L.polyline(seg.coords,{color:seg.color,weight:w,opacity:.9,dashArray:dash});
  var hit=L.polyline(seg.coords,{color:seg.color,weight:16,opacity:0});
  var dec=L.polylineDecorator(pl,{patterns:[{offset:'10%',repeat:'25%',symbol:L.Symbol.arrowHead({pixelSize:9,pathOptions:{color:seg.color,fillOpacity:.95,weight:0}})}]});
  var a=seg.coords[0],b=seg.coords[seg.coords.length-1],e=segEnds(seg.name)||{a:'inicio',b:'fin'};
  var start=L.circleMarker(a,{radius:5,color:seg.color,weight:2,fillColor:'#fff',fillOpacity:1}).bindPopup('<div class="lp">Sale de <b>'+esc(e.a)+'</b></div>');
  var end=L.circleMarker(b,{radius:5,color:'#fff',weight:2,fillColor:seg.color,fillOpacity:1}).bindPopup('<div class="lp">Llega a <b>'+esc(e.b)+'</b></div>');
  var det=[seg.durTxt,seg.distTxt].filter(Boolean).join(' · ');
  var pop=seg.pop||('<div class="lp">'+esc(seg.name)+(det?(' · <b>'+esc(det)+'</b>'):'')+'</div>');var pw=seg.pop?320:300;pl.bindPopup(pop,{maxWidth:pw});hit.bindPopup(pop,{maxWidth:pw});
  var parts=[hit,pl,dec];
  if(seg.mode!=='walk'){for(var i=1;i<seg.coords.length-1;i++){parts.push(L.circleMarker(seg.coords[i],{radius:3.5,color:seg.color,weight:1.5,fillColor:'#fff',fillOpacity:1,interactive:false}));}}
  parts.push(start,end);
  var g=L.layerGroup(parts);g._pts=[L.latLng(a[0],a[1]),L.latLng(b[0],b[1])];g._pop=pl;g._hit=hit;g._mid=pl.getBounds().getCenter();
  return g;
}

// ---- modelo por día: paradas absorben sitios; rutas intercaladas por su ⇒destino ----
var days=[];
DATA.days.forEach(function(d){
  var stops=d.places.filter(function(p){return p.kind==='stop';})
    .map(function(p){return {kind:'stop',num:p.order,seqi:p.seqi,title:stopClean(p.name),time:stopTime(p.name),trange:p.trange,
      desc:'',tier:'',maps:'https://www.google.com/maps/search/?api=1&query='+p.lat+','+p.lng,foto:'',hist:'',
      color:'#b23a2a',ll:L.latLng(p.lat,p.lng),inc:0,fixTime:p.fixTime};})
    .sort(function(a,b){return a.num-b.num;});
  var byNorm={};stops.forEach(function(s){byNorm[norm(s.title)]=s;});
  var hoteles=[],restos=[];
  d.places.filter(function(p){return p.kind!=='stop';}).forEach(function(p){
    var s=byNorm[norm(p.name)];
    if(s&&p.kind==='site'){s.desc=p.desc;s.maps=p.maps;s.foto=p.foto;s.hist=p.hist;s.pop=p.pop;return;}
    var it={kind:p.kind,num:0,seqi:p.seqi,title:p.name,time:p.time||'',trange:p.trange,fixTime:p.time||'',desc:p.desc,tier:p.tier,foto:p.foto,hist:p.hist,key:p.key||'',
      pop:p.pop,maps:p.maps,color:pColor(p.kind,p.tier),ll:L.latLng(p.lat,p.lng)};
    (p.kind==='hotel'||p.kind==='aero')?hoteles.push(it):restos.push(it);
  });
  var segs=d.segments.map(function(s){var e=segEnds(s.name),cd=s.coords;return {seg:true,layer:segLayer(s),
    name:s.name,title:(e?(e.a+' → '+e.b):s.name),color:s.color,durTxt:s.durTxt,distTxt:s.distTxt,dur:s.dur||0,mode:s.mode,coordsLL:cd,
    off:!!s.off,trange:s.trange,pop:s.pop,seqi:s.seqi,fix:s.fix,
    ord:parseInt((/·(\d+)/.exec(s.name)||[0,'999'])[1],10),end:L.latLng(cd[cd.length-1][0],cd[cd.length-1][1])};});
  segs.sort(function(a,b){return a.ord-b.ord;});
  segs.forEach(function(it){[it.layer._hit,it.layer._pop].forEach(function(ln){if(ln)ln.on('click',function(){selectStep(it,false);});});}); // clic en ruta = seleccionarla
  // (orden estricto por seqi más abajo; el acumulado de traslado se calcula al recorrer seq)
  // comidas: cada una es un grupo de opciones (marcadores propios)
  var meals=(d.meals||[]).map(function(me){
    if(me.plan){return {meal:true,plan:true,seqi:me.seqi,time:me.time,trange:me.trange,fix:me.fix,options:me.options,chosen:0};} // planes en paralelo
    var opts=me.opts.map(function(o){var it={kind:'resto',num:0,title:o.name,time:me.time||'',desc:o.desc,tier:o.tier,foto:o.foto,hist:'',
      key:o.key,mealt:me.time,pop:o.pop,maps:o.maps,ida:o.ida,reg:o.reg,price:o.price,nogeo:!!o.nogeo,color:pColor('resto',o.tier),
      ll:o.nogeo?null:L.latLng(o.lat,o.lng)};return it;});
    return {meal:true,seqi:me.seqi,time:me.time,trange:me.trange,fix:me.fix,options:opts,chosen:0};
  });
  var mkeys={};meals.forEach(function(me){me.options.forEach(function(o){if(o.key)mkeys[o.key]=1;});});
  restos=restos.filter(function(r){return !(r.key&&mkeys[r.key]);}); // los que ya son opción de comida salen de "sueltos"
  // marcadores (tras calcular inc, para el meta del popup)
  var opall=[];meals.forEach(function(me){opall=opall.concat(me.options);});
  stops.concat(hoteles,restos,opall).forEach(function(it){it.layer=it.nogeo?null:placeMarker(it);});
  // trayectos SIN geometría (vuelo, monorriel interno, trámite): fila de panel, ubicados por seqi
  var infos=(d.infoTransits||[]).map(function(t){return {seg:true,info:true,seqi:t.seqi,title:t.title,durTxt:t.durTxt,trange:t.trange,fix:t.fix,mode:t.mode,color:t.color,time:t.time,coordsLL:t.coordsLL||null};});
  // SECUENCIA: TODO ordenado estrictamente por seqi (nunca por geografía ni por hora)
  function _si(x){return (x&&x.seqi!=null)?x.seqi:99999;}
  var seq=segs.concat(stops,hoteles,restos,meals,infos).filter(Boolean).sort(function(a,b){return _si(a)-_si(b);});
  // traslado acumulado hasta cada parada (recorriendo la secuencia)
  var acc=0;seq.forEach(function(it){if(it.seg&&!it.meal&&!it.info){acc+=it.dur||0;}else if(it.kind==='stop'){it.inc=acc;it.incTxt=fmtMin(acc);acc=0;}});
  function wkm(m){return m<1000?(Math.round(m/10)*10+' m'):((m/1000).toFixed(1)+' km');}
  function wmin(m){return Math.max(5,Math.round(m/66.7/5)*5);} // 4 km/h (66.7 m/min)
  function lineDist(cs){var d=0;for(var i=1;i<cs.length;i++){d+=L.latLng(cs[i-1][0],cs[i-1][1]).distanceTo(L.latLng(cs[i][0],cs[i][1]));}return d;}
  var mroutes=[]; // ida/regreso como elementos separados
  meals.forEach(function(me){
    if(me.plan){ // grupo de PLANES en paralelo: cada opción = una ruta seleccionable
      me.options.forEach(function(o){
        o.parts=[]; o.ll=null;
        (o.elems||[]).forEach(function(el){
          var pop=el.pop||('<div class="lp">'+esc(el.name||'')+'</div>'), lyr, coordsLL=null;
          if(el.line){var w=el.mode==='walk'?3:5,dash=el.mode==='walk'?'4 7':null;
            lyr=L.polyline(el.line,{color:el.color,weight:w,opacity:.9,dashArray:dash});
            coordsLL=el.line; if(!o.ll)o.ll=L.latLng(el.line[0][0],el.line[0][1]);}
          else{lyr=L.circleMarker(el.pt,{radius:6,color:'#fff',weight:2,fillColor:el.color,fillOpacity:1});
            if(!o.ll)o.ll=L.latLng(el.pt[0],el.pt[1]);}
          lyr.bindPopup(pop,{maxWidth:el.pop?320:220});
          var part={seg:!!el.line,layer:lyr,optRef:o,title:el.name||'',color:el.color,mode:el.mode||'walk',coordsLL:coordsLL,mealt:me.time};
          o.parts.push(part);mroutes.push(part);lyr.on('click',function(){selectStep(part,false);});
        });
      });
      return;
    }
    // la comida ya está posicionada por seqi; sus vecinos dan el punto de ida/regreso
    var idx=seq.indexOf(me);
    var fromLL=null;for(var j=idx-1;j>=0;j--){var pv=seq[j];if(pv&&!pv.meal&&pv.ll){fromLL=pv.ll;break;}}
    var toLL=null;for(var j2=idx+1;j2<seq.length;j2++){var nx=seq[j2];if(nx&&!nx.meal){if(nx.ll){toLL=nx.ll;break;}if(nx.seg&&!nx.off&&nx.coordsLL){toLL=L.latLng(nx.coordsLL[0][0],nx.coordsLL[0][1]);break;}}}
    me.fromLL=fromLL;me.toLL=toLL;
    me.options.forEach(function(o){
      o.parts=[];
      if(o.nogeo){o.parts.push(o);return;} // genérica sin lugar → solo fila de panel, sin ruta ni marcador
      // ida real (o.ida = ruta OSRM del punto anterior al resto) o recta como fallback
      var idaC=o.ida||(fromLL?[[fromLL.lat,fromLL.lng],[o.ll.lat,o.ll.lng]]:null);
      if(idaC){var mi=lineDist(idaC),pl=L.polyline(idaC,{color:'#b23a2a',weight:3,opacity:.9,dashArray:'3 7'});
        pl.bindPopup('<div class="lp">🚶 Ida a <b>'+esc(o.title)+'</b> · '+wkm(mi)+' · ~'+wmin(mi)+' min</div>');
        var ida={seg:true,layer:pl,optRef:o,title:'ida → '+o.title,color:'#b23a2a',mode:'walk',durTxt:'~'+wmin(mi)+' min',distTxt:wkm(mi),mealt:me.time,coordsLL:idaC};
        o.ida=ida;o.parts.push(ida);mroutes.push(ida);pl.on('click',function(){selectStep(ida,false);});}
      o.parts.push(o);
      // regreso real (o.reg = ruta OSRM del resto al SIGUIENTE punto) o recta como fallback
      var regC=o.reg||(toLL?[[o.ll.lat,o.ll.lng],[toLL.lat,toLL.lng]]:null);
      if(regC){var mv=lineDist(regC),pl2=L.polyline(regC,{color:'#c8791f',weight:3,opacity:.9,dashArray:'1 6'});
        pl2.bindPopup('<div class="lp">🚶 Al siguiente punto · '+wkm(mv)+' · ~'+wmin(mv)+' min</div>');
        var reg={seg:true,layer:pl2,optRef:o,title:'regreso → siguiente',color:'#c8791f',mode:'walk',durTxt:'~'+wmin(mv)+' min',distTxt:wkm(mv),mealt:me.time,coordsLL:regC};
        o.reg=reg;o.parts.push(reg);mroutes.push(reg);pl2.on('click',function(){selectStep(reg,false);});}
    });
  });
  days.push({key:d.key,label:d.label,travelTxt:d.travelTxt,startTime:d.startTime||'',seq:seq,restos:restos,meals:meals,all:stops.concat(hoteles,restos,segs,opall,mroutes)});
});
days.forEach(function(d){d.steps=buildStepsFor(d);});
// hotel/aeropuerto de SALIDA: si está posicionado antes de un lugar con hora menor, su hora nombrada es la de regreso
// nocturno; corregir a la hora de inicio del día (te levantas y sales del hotel)
days.forEach(function(d){d.seq.forEach(function(it,idx){
  if((it.kind==='hotel'||it.kind==='aero')&&idx<=1&&/^\d\d:\d\d$/.test(it.time||'')){ // solo hotel de salida (arranque del día)
    for(var j=idx+1;j<d.seq.length;j++){var nx=d.seq[j];if(!nx||nx.meal||nx.seg)continue;
      if(/^\d\d:\d\d$/.test(nx.time||'')&&nx.time<it.time){if(d.startTime){it.time=d.startTime;it.fixTime=d.startTime;}break;}}
  }});});
// contradicciones: dentro de un día las horas deben ir en aumento; si una es menor que la previa, se marca
var CONFLICTS=[];
days.forEach(function(d){var last=null,lastIt=null;d.seq.forEach(function(it){
  if(it.meal)return; // la comida se ubica por cercanía, no por hora → no participa del chequeo
  var t=(it.time&&/^\d\d:\d\d$/.test(it.time))?it.time:'';
  if(!/^\d\d:\d\d$/.test(t))return;
  if(last!==null&&t<last){it.conflict=true;
    CONFLICTS.push(d.key+': '+it.title+' '+t+' va DESPUÉS de '+(lastIt?lastIt.title:'?')+' '+last);}
  last=t;lastIt=it;});});
if(window.console)CONFLICTS.forEach(function(c){console.warn('⚠️ '+c);});
window.CONFLICTS=CONFLICTS;
var _cd=document.createElement('div');_cd.id='conflicts';_cd.style.display='none';_cd.textContent=CONFLICTS.length?CONFLICTS.join(' || '):'sin contradicciones';document.body.appendChild(_cd);

function itemSet(it,on){if(it.layer){if(on){if(!map.hasLayer(it.layer))map.addLayer(it.layer);}else{if(map.hasLayer(it.layer))map.removeLayer(it.layer);}}if(it.cb)it.cb.checked=on;}
function dimItem(it,dim){ // alternativas de comida con transparencia
  if(it.seg&&it.layer&&it.layer.setStyle)it.layer.setStyle({opacity:dim?.3:.9});
  else if(it.layer&&it.layer._icon)it.layer._icon.classList.toggle('dimmed',dim);
  if(it._row)it._row.classList.toggle('dimrow',dim);}
function dayPts(day){var pts=[];day.all.forEach(function(it){if(it.off||!it.layer)return;if(it.layer.getLatLng)pts.push(it.layer.getLatLng());else if(it.layer._pts)pts.push.apply(pts,it.layer._pts);});return pts;}
function zoomDay(day){var pts=dayPts(day);if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.15));}
function volar(it){selectStep(it,true);}

var tree=document.getElementById('tree'),daybtns=document.getElementById('daybtns'),dayEls=[];
function mkRow(it){
  var row=document.createElement('div');row.className='it'+(it.seg?(' rt'+(it.mode==='walk'?' walk':'')):'');
  var cb=document.createElement('input');cb.type='checkbox';cb.className='ck';it.cb=cb;
  var vis;
  if(it.seg){vis='<span class="ln" style="border-top-color:'+it.color+'"></span>';}
  else if(it.num){vis='<span class="npin">'+it.num+'</span>';}
  else{vis='<span class="pin" style="background:'+it.color+'"></span>';}
  var ds=it.seg?[it.durTxt,it.distTxt].filter(Boolean).join(' · '):[it.tier,it.rtxt,it.desc].filter(Boolean).join(' · ');
  // badge de tiempo = inicio–fin SIEMPRE (nunca duración): rojo si obligatorio (reserva/fixed), gris si flexible
  var tlabel=it.trange||it.time;
  var tm='';
  if(tlabel){var cls=it.conflict?'warn':((it.fix||it.fixTime)?'fix':'est');tm='<span class="tm '+cls+'">'+(it.conflict?'⚠️ ':'')+esc(tlabel)+'</span>';}
  if(it.info)cb.style.visibility='hidden';
  row.appendChild(cb);
  row.insertAdjacentHTML('beforeend',vis+'<div class="bd"><div class="nm">'+esc(it.title)+'</div>'+(ds?'<div class="ds">'+esc(ds)+'</div>':'')+'</div>'+tm);
  cb.addEventListener('change',function(){itemSet(it,cb.checked);syncMasters();});
  if(!it.info){row.querySelector('.bd').addEventListener('click',function(){volar(it);});}
  else if(it.coordsLL){ // sin-geo con geometría solo-seleccionable (vuelo): dibuja al elegir
    row.querySelector('.bd').addEventListener('click',function(){clearSel();setSel(it);map.fitBounds(L.latLngBounds(it.coordsLL).pad(.2));});
  }
  it._row=row;
  return row;
}
// ---- resaltar el seleccionado (halo en ruta, glow en lugar, fila marcada) ----
var selGlow=L.polyline([],{weight:13,opacity:.35,lineCap:'round',lineJoin:'round'});
var selItem=null,selRow=null;
function clearSel(){
  if(selRow){selRow.classList.remove('sel');selRow=null;}
  if(map.hasLayer(selGlow))map.removeLayer(selGlow);
  if(selItem&&!selItem.seg&&selItem.layer&&selItem.layer._icon)selItem.layer._icon.classList.remove('selmark');
  selItem=null;
}
function setSel(it){
  clearSel();selItem=it;selRow=it._row||null;
  if(selRow){selRow.classList.add('sel');if(selRow.scrollIntoView)selRow.scrollIntoView({block:'nearest'});}
  if(it.seg){if(it.coordsLL){selGlow.setLatLngs(it.coordsLL).setStyle({color:it.color});selGlow.addTo(map).bringToBack();}}
  else if(it.layer&&it.layer._icon){it.layer._icon.classList.add('selmark');}
}
function mealLabel(t){if(!t)return 'Comer';var h=parseInt(String(t).slice(0,2),10);return h<11?'Desayuno':(h<16?'Comida':'Cena');}
function mkDay(day,open){
  var g=document.createElement('div');g.className='dayg';
  var head=document.createElement('div');head.className='dhead'+(open?' open':'');
  var tt=day.travelTxt?('<span class="dtime">🕐 '+esc(day.travelTxt)+'</span>'):'';
  head.innerHTML='<input type="checkbox" class="dm"><span class="caret">▶</span><span class="dname">'+esc(day.label)+'</span>'+tt;
  var body=document.createElement('div');body.className='dbody'+(open?' open':'');
  day.seq.forEach(function(it){
    if(it.meal){
      var mh=document.createElement('div');mh.className='sublbl mealh';
      var mlbl=it.plan?('🧭 Elige tu plan'):('🍴 '+mealLabel(it.time));
      mh.innerHTML=mlbl+((it.trange||it.time)?(' · '+esc(it.trange||it.time)):'')+' — elige <span class="mcar">▼</span>';
      var mc=document.createElement('div');mc.className='mealc';
      it.options.forEach(function(o){var og=document.createElement('div');og.className='optgrp';
        if(it.plan&&o.name){var ph=document.createElement('div');ph.className='planh';ph.textContent=o.name;og.appendChild(ph);}
        (o.parts||[o]).forEach(function(p){og.appendChild(mkRow(p));});mc.appendChild(og);});
      mh.addEventListener('click',function(){mh.classList.toggle('closed');mc.classList.toggle('closed');});
      body.appendChild(mh);body.appendChild(mc);
    } else body.appendChild(mkRow(it));
  });
  var dm=head.querySelector('.dm');
  head.addEventListener('click',function(e){if(e.target===dm)return;head.classList.toggle('open');body.classList.toggle('open');});
  dm.addEventListener('click',function(e){e.stopPropagation();});
  dm.addEventListener('change',function(){day.all.forEach(function(it){itemSet(it,dm.checked);});if(dm.checked){head.classList.add('open');body.classList.add('open');zoomDay(day);}syncMasters();});
  g.appendChild(head);g.appendChild(body);
  dayEls.push({day:day,head:head,body:body,dm:dm,chip:null});return g;
}
function syncMasters(){dayEls.forEach(function(de){var items=de.day.all,on=items.filter(function(it){return it.cb&&it.cb.checked;}).length;de.dm.checked=on===items.length&&on>0;de.dm.indeterminate=on>0&&on<items.length;if(de.chip)de.chip.classList.toggle('on',on>0);});}

days.forEach(function(d,i){tree.appendChild(mkDay(d,i===0));});
// mostrar TODA la geometría de un día: alternativas de comida atenuadas, elegida sólida
function showDay(d){
  d.all.forEach(function(it){itemSet(it,true);dimItem(it,false);});
  (d.meals||[]).forEach(function(me){me.options.forEach(function(o,k){(o.parts||[o]).forEach(function(p){itemSet(p,true);dimItem(p,k!==me.chosen);});});});
}
// cambio de día EXCLUSIVO: apaga los demás días, enciende todo el nuevo, abre sólo su árbol y hace zoom
function selectDay(i){
  days.forEach(function(dd){dd.all.forEach(function(it){itemSet(it,false);});});
  showDay(days[i]);
  dayEls.forEach(function(de,k){de.head.classList.toggle('open',k===i);de.body.classList.toggle('open',k===i);});
  zoomDay(days[i]);syncMasters();
}
days.forEach(function(d,i){
  var b=document.createElement('button');b.textContent=d.key;
  b.addEventListener('click',function(){selectDay(i);});
  daybtns.appendChild(b);dayEls[i].chip=b;
});
var allb=document.createElement('button');allb.className='allbtn';allb.textContent='Todos';
allb.addEventListener('click',function(){days.forEach(function(d){d.all.forEach(function(it){itemSet(it,true);});});syncMasters();});
daybtns.appendChild(allb);
var noneb=document.createElement('button');noneb.className='nonebtn';noneb.textContent='Ninguno';
noneb.addEventListener('click',function(){days.forEach(function(d){d.all.forEach(function(it){itemSet(it,false);});});syncMasters();});
daybtns.appendChild(noneb);

selectDay(0); // carga inicial: día 1 exclusivo con toda su geometría
document.getElementById('fold').addEventListener('click',function(){document.getElementById('panel').classList.toggle('hidden');});

// ================= RECORRIDO PASO A PASO (barra arriba pasos, abajo día) =================
function isResto(it){return it&&!it.seg&&it.kind!=='stop'&&it.kind!=='hotel'&&it.kind!=='aero';}
function buildStepsFor(day){
  var steps=[],i=0,seq=day.seq;
  while(i<seq.length){
    if(seq[i].meal){var me=seq[i];steps.push({type:'opt',items:me.options,title:'🍴 '+mealLabel(me.time)+(me.time?(' · '+me.time):''),chosen:me.chosen,meal:me});i++;}
    else if(isResto(seq[i])){var opts=[];while(i<seq.length&&isResto(seq[i])){opts.push(seq[i]);i++;}
      steps.push({type:'opt',items:opts,title:'🍴 Comer',chosen:0});}
    else{steps.push({type:'one',items:[seq[i]],title:seq[i].title,seg:!!seq[i].seg});i++;}
  }
  var lastLL=null;
  steps.forEach(function(s){
    if(s.type==='one'&&s.items[0].ll)lastLL=s.items[0].ll;
    else if(s.type==='opt'&&lastLL){var best=0,bd=1e12;s.items.forEach(function(o,k){if(o.ll){var d=lastLL.distanceTo(o.ll);if(d<bd){bd=d;best=k;}}});s.chosen=best;s.fromLL=lastLL;if(s.meal)s.meal.chosen=best;}
  });
  return steps;
}
function isMob(){return document.body.classList.contains('mob');}
var mDay=0,mStep=0;
function dSteps(){return days[mDay].steps;}
function mCur(){var s=dSteps()[mStep];return s.type==='one'?s.items[0]:s.items[s.chosen];}
function openPop(it){var L2=it&&it.layer;if(!L2)return;if(L2._popup)L2.openPopup();else if(L2._pop)L2._pop.openPopup(L2._mid);} // grupo (ruta) no tiene popup propio → abre el de su línea
// límites del TRAZO del paso actual (tramo: su polilínea; comida: ida+lugar+regreso). null si es solo un punto.
function stepBounds(cur){
  var pts=[],hasLine=false;
  function add(c){if(c&&c.length){hasLine=true;for(var i=0;i<c.length;i++)pts.push(c[i]);}}
  if(cur.coordsLL)add(cur.coordsLL);
  if(cur.parts)cur.parts.forEach(function(p){if(p.coordsLL)add(p.coordsLL);});
  if(cur.ll)pts.push([cur.ll.lat,cur.ll.lng]);
  return hasLine?L.latLngBounds(pts):null;
}
// centrado de un LUGAR (sin trazo propio): círculo centrado en el lugar cuyo radio depende de los
// tramos vecinos — d1/d2 = distancia del lugar al extremo lejano del tramo anterior/siguiente;
// radio = máx( media geométrica de los dos, el más chico duplicado ). Encuadra ese círculo.
function placeCircleBounds(cur,seq){
  if(!cur.ll)return null;
  var idx=seq.indexOf(cur);if(idx<0)return null;
  var pv=null,nx=null,it,c;
  for(var i=idx-1;i>=0;i--){it=seq[i];if(it&&it.seg&&!it.info&&it.coordsLL&&it.coordsLL.length){c=it.coordsLL;pv=L.latLng(c[0][0],c[0][1]);break;}}
  for(var j=idx+1;j<seq.length;j++){it=seq[j];if(it&&it.seg&&!it.info&&it.coordsLL&&it.coordsLL.length){c=it.coordsLL;nx=L.latLng(c[c.length-1][0],c[c.length-1][1]);break;}}
  var d1=pv?cur.ll.distanceTo(pv):null,d2=nx?cur.ll.distanceTo(nx):null,R;
  if(d1!=null&&d2!=null)R=Math.max(Math.sqrt(d1*d2),2*Math.min(d1,d2));
  else if(d1!=null)R=2*d1;else if(d2!=null)R=2*d2;else return null;
  R=Math.max(R,90); // piso para no acercar de más en lugares muy pegados a sus tramos
  return cur.ll.toBounds(2*R); // caja de lado 2R (±R alrededor del lugar)
}
function mApply(fly){
  var day=days[mDay],s=dSteps()[mStep];
  map.closePopup(); // cerrar el popup anterior al movernos
  if(isMob()){ // móvil: recorrido progresivo (enciende hasta el paso, apaga lo demás)
    day.all.forEach(function(it){itemSet(it,false);});
    for(var k=0;k<=mStep;k++){var sk=day.steps[k];if(sk.type==='opt'){var ch=sk.items[sk.chosen];(ch.parts||[ch]).forEach(function(p){itemSet(p,true);dimItem(p,false);});}else itemSet(sk.items[0],true);}
  } else if(s.type!=='opt'){ itemSet(mCur(),true); }
  // comida: elegida a full, alternativas con transparencia (elementos separados: ida/lugar/regreso)
  if(s.type==='opt'){s.items.forEach(function(o,k){(o.parts||[o]).forEach(function(p){itemSet(p,true);dimItem(p,k!==s.chosen);});});}
  syncMasters();
  var cur=mCur(),ll=cur.ll||(cur.layer&&cur.layer._pts&&cur.layer._pts[0]);
  setSel(cur); // resaltar la ruta/lugar actual
  if(fly!==false){
    var b=stepBounds(cur)||placeCircleBounds(cur,day.seq); // trazo del paso, o círculo del lugar según tramos vecinos
    if(b&&b.isValid())map.flyToBounds(b,{padding:[60,72],maxZoom:16,duration:.5});
    else if(ll)map.flyTo(ll,16,{duration:.5}); // sin trazo ni vecinos → centra el punto
    setTimeout(function(){openPop(cur);},520);
  } else openPop(cur); // abrir popup también en click (lugares y rutas)
  mRender();
}
function mRender(){
  var day=days[mDay],st=dSteps(),s=st[mStep];
  var top=document.getElementById('mtop'),bot=document.getElementById('mbot');
  var mid;
  if(s.type==='opt'){mid='<div class="mopts">'+s.items.map(function(o,k){return '<button class="opt'+(k===s.chosen?' on':'')+'" data-k="'+k+'">'+esc(o.title)+'</button>';}).join('')+'</div>';}
  else{mid='<div class="cur"><div class="stp">Paso '+(mStep+1)+'/'+st.length+'</div>'+(s.seg?'🚇 ':'')+esc(s.title)+'</div>';}
  top.innerHTML='<button class="nav" id="mprev" '+(mStep<=0?'disabled':'')+'>‹</button>'+mid+'<button class="nav" id="mnext" '+(mStep>=st.length-1?'disabled':'')+'>›</button>';
  document.getElementById('mprev').onclick=function(){if(mStep>0){mStep--;mApply();}};
  document.getElementById('mnext').onclick=function(){if(mStep<st.length-1){mStep++;mApply();}};
  if(s.type==='opt')top.querySelectorAll('.opt').forEach(function(b){b.onclick=function(){s.chosen=+b.getAttribute('data-k');mApply();};});
  bot.innerHTML='<button class="nav" id="dprev" '+(mDay<=0?'disabled':'')+'>‹</button><button class="cur" id="dsel">'+esc(day.label)+' ▾</button><button class="nav" id="dnext" '+(mDay>=days.length-1?'disabled':'')+'>›</button>';
  document.getElementById('dprev').onclick=function(){if(mDay>0)setDay(mDay-1);};
  document.getElementById('dnext').onclick=function(){if(mDay<days.length-1)setDay(mDay+1);};
  document.getElementById('dsel').onclick=dayPicker;
}
function setDay(i){mDay=i;mStep=0;if(isMob())days.forEach(function(d,k){if(k!==i)d.all.forEach(function(it){itemSet(it,false);});});mApply();}
function findStep(it){for(var di=0;di<days.length;di++){var st=days[di].steps;for(var si=0;si<st.length;si++){var s=st[si];if(s.type==='one'&&s.items[0]===it)return [di,si,0];if(s.type==='opt'){var k=s.items.indexOf(it);if(k>=0)return [di,si,k];}}}return null;}
function selectStep(it,fly){
  // ida/regreso de comida = tramos seleccionables por sí solos (elemento suelto)
  var f=it&&it.optRef?null:findStep(it);
  if(!f){ // elemento suelto: enciende, resalta y vuela sin cambiar de paso
    itemSet(it,true);setSel(it);map.closePopup();var ll=it.ll||(it.coordsLL&&L.latLng(it.coordsLL[0][0],it.coordsLL[0][1]));
    if(fly!==false){var b=stepBounds(it);if(b&&b.isValid())map.flyToBounds(b,{padding:[60,72],maxZoom:16,duration:.5});else if(ll)map.flyTo(ll,15,{duration:.5});setTimeout(function(){openPop(it);},520);}else openPop(it);return;}
  mDay=f[0];mStep=f[1];var s=dSteps()[mStep];if(s.type==='opt')s.chosen=f[2];if(isMob())days.forEach(function(d,k){if(k!==mDay)d.all.forEach(function(x){itemSet(x,false);});});mApply(fly);}
function dayPicker(){
  var menu=document.createElement('div');menu.className='daymenu';
  menu.innerHTML=days.map(function(d,k){return '<button data-k="'+k+'"'+(k===mDay?' class="on"':'')+'>'+esc(d.label)+(d.travelTxt?(' · 🕐 '+esc(d.travelTxt)):'')+'</button>';}).join('');
  document.body.appendChild(menu);
  menu.querySelectorAll('button').forEach(function(b){b.onclick=function(e){e.stopPropagation();setDay(+b.getAttribute('data-k'));document.body.removeChild(menu);};});
  menu.onclick=function(){document.body.removeChild(menu);};
}
mRender(); // barras visibles también en escritorio
function checkMobile(){document.body.classList.toggle('mob',window.innerWidth<=820);setTimeout(function(){map.invalidateSize();},60);}
window.addEventListener('resize',checkMobile);checkMobile();
setTimeout(function(){map.invalidateSize();},200);

// ================= DIBUJAR RUTA A MANO (clic = punto) Y COPIAR COORDENADAS =================
var drawMode=false, drawPts=[], drawLine=L.polyline([],{color:'#e6007e',weight:4,opacity:.95,dashArray:'5 5'}), drawDots=L.layerGroup();
var drawCtl=L.control({position:'topleft'});
drawCtl.onAdd=function(){var b=L.DomUtil.create('div','leaflet-bar');b.innerHTML='<a href="#" id="drawtgl" title="Dibujar ruta a mano">✏️</a>';L.DomEvent.disableClickPropagation(b);
  b.querySelector('#drawtgl').addEventListener('click',function(e){e.preventDefault();toggleDraw();});return b;};
drawCtl.addTo(map);
// puntos de anclaje = extremos de rutas + marcadores (para empatar continuidad)
var SNAP=[];days.forEach(function(d){d.all.forEach(function(it){
  if(it.ll)SNAP.push(it.ll);
  else if(it.coordsLL&&it.coordsLL.length){var c=it.coordsLL;SNAP.push(L.latLng(c[0][0],c[0][1]));SNAP.push(L.latLng(c[c.length-1][0],c[c.length-1][1]));}
});});
function drawSnap(latlng){var pt=map.latLngToContainerPoint(latlng),best=null,bd=15;
  SNAP.forEach(function(s){var d=pt.distanceTo(map.latLngToContainerPoint(s));if(d<bd){bd=d;best=s;}});return best||latlng;}
var drawBox=document.createElement('div');drawBox.id='drawbox';drawBox.style.display='none';
drawBox.innerHTML='<div class="dbhd">✏️ Ruta a mano — clic en orden. Los clics cerca del fin de otra ruta o de un punto se PEGAN ahí (continuidad).</div>'
  +'<textarea id="dbtxt" readonly rows="6" placeholder="lat, lng por línea…"></textarea>'
  +'<div class="dbcount" id="dbcount">0 puntos</div>'
  +'<div class="dbbtns"><button id="dbundo">↶ Deshacer</button><button id="dbclear">🗑 Borrar</button><button id="dbcopy">📋 Copiar</button><button id="dbclose">✕ Cerrar</button></div>';
document.body.appendChild(drawBox);
function drawRender(){
  drawLine.setLatLngs(drawPts);drawDots.clearLayers();
  drawPts.forEach(function(p,i){var m=L.circleMarker(p,{radius:5,color:'#e6007e',fillColor:'#fff',fillOpacity:1,weight:2});m.bindTooltip(String(i+1),{permanent:true,direction:'top',className:'dbtip'});m.addTo(drawDots);});
  document.getElementById('dbtxt').value=drawPts.map(function(p){return p.lat.toFixed(6)+', '+p.lng.toFixed(6);}).join('\n');
  document.getElementById('dbcount').textContent=drawPts.length+' puntos';
}
function toggleDraw(){
  drawMode=!drawMode;
  var a=document.getElementById('drawtgl');if(a)a.classList.toggle('drawon',drawMode);
  drawBox.style.display=drawMode?'block':'none';
  map.getContainer().style.cursor=drawMode?'crosshair':'';
  if(drawMode){drawLine.addTo(map);drawDots.addTo(map);}
}
map.on('click',function(e){if(drawMode){drawPts.push(drawSnap(e.latlng));drawRender();}});
document.getElementById('dbundo').addEventListener('click',function(){drawPts.pop();drawRender();});
document.getElementById('dbclear').addEventListener('click',function(){drawPts=[];drawRender();});
document.getElementById('dbclose').addEventListener('click',function(){toggleDraw();});
document.getElementById('dbcopy').addEventListener('click',function(){var t=document.getElementById('dbtxt');t.select();t.setSelectionRange(0,99999);
  var done=function(){var b=document.getElementById('dbcopy');b.textContent='✓ Copiado';setTimeout(function(){b.textContent='📋 Copiar';},1300);};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t.value).then(done,function(){document.execCommand('copy');done();});}
  else{document.execCommand('copy');done();}});
</script></body></html>"""

out = HTML.replace("__DATA__", DATA).replace("</style>", MODAL_CSS + "\n</style>", 1)
open(SD + "/leaflet-viaje.html", "w", encoding="utf-8").write(out)
s = open(SD + "/leaflet-viaje.html", encoding="utf-8").read()
print("leaflet-viaje.html:", len(s) // 1024, "KB")
