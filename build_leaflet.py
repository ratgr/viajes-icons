# -*- coding: utf-8 -*-
"""Genera leaflet-viaje.html — app de mapa autocontenida (Leaflet + OSM, sin key).
30 capas por día (lugares + rutas), paradas numeradas, restos por nivel, flechas."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SD = r"C:/Users/Ricardo/AppData/Local/Temp/claude/d--dev-tamper-finances/81928241-1549-48b6-9a85-7eac7bb94ebc/scratchpad"
DATA = open(SD + "/viaje-data.json", encoding="utf-8").read()

HTML = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Japón 2026 · mapa por día</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-polylinedecorator@1.6.0/dist/leaflet.polylineDecorator.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,sans-serif}
  #map{position:absolute;inset:0}
  .panel{position:absolute;z-index:1000;top:10px;left:10px;background:#fff;border-radius:10px;
    box-shadow:0 4px 18px rgba(0,0,0,.25);max-height:calc(100% - 20px);overflow:auto;width:230px}
  .panel h1{font-size:15px;margin:0;padding:12px 14px 8px}
  .panel .sub{font-size:11px;color:#666;padding:0 14px 8px}
  .daybtns{display:flex;flex-wrap:wrap;gap:4px;padding:0 10px 10px}
  .daybtns button{font-size:11px;border:1px solid #ccc;background:#f7f7f7;border-radius:6px;padding:3px 6px;cursor:pointer}
  .daybtns button.on{background:#b23a2a;color:#fff;border-color:#b23a2a}
  .daybtns .allbtn{background:#2c6ba0;color:#fff;border-color:#2c6ba0}
  .lyr{padding:2px 14px;font-size:12px;display:flex;align-items:center;gap:6px;border-top:1px solid #eee}
  .lyr label{display:flex;align-items:center;gap:5px;cursor:pointer;flex:1}
  .lyr .swatch{width:10px;height:10px;border-radius:50%}
  .num{background:#b23a2a;color:#fff;border-radius:50%;width:20px;height:20px;line-height:20px;
    text-align:center;font-size:11px;font-weight:700;box-shadow:0 1px 3px rgba(0,0,0,.4)}
  .dot{border-radius:50%;width:13px;height:13px;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)}
  .lp{font-size:13px}.lp b{font-size:14px}.lp a{color:#b23a2a;font-weight:700;text-decoration:none}
  .toggle{position:absolute;z-index:1001;top:10px;left:250px;background:#fff;border:none;border-radius:8px;
    padding:8px 10px;box-shadow:0 2px 8px rgba(0,0,0,.25);cursor:pointer;font-size:13px;display:none}
  @media(max-width:600px){.panel{width:200px}.toggle{left:220px}}
</style></head><body>
<div id="map"></div>
<div class="panel" id="panel">
  <h1>⛩️ Japón 2026</h1>
  <div class="sub">Toca un día para ver sus lugares y ruta. Cada día = 2 capas (📍 lugares · 🚇 rutas).</div>
  <div class="daybtns" id="daybtns"></div>
  <div id="lyrs"></div>
</div>
<script>
var DATA = __DATA__;
var map = L.map('map',{zoomControl:true}).setView([35.0,135.6],6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
  maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);

var TIER = {Take:'#4a7d3a', Ai:'#2c6ba0', Shu:'#b23a2a'};
function placeColor(p){
  if(p.kind==='site'||p.kind==='stop') return '#b23a2a';
  if(p.kind==='hotel') return '#f0a500';
  if(p.kind==='aero') return '#7b4fa6';
  return TIER[p.tier]||'#777';
}
function placeMarker(p){
  var m;
  if(p.kind==='stop' && p.order){
    m=L.marker([p.lat,p.lng],{icon:L.divIcon({className:'',html:'<div class="num">'+p.order+'</div>',iconSize:[20,20],iconAnchor:[10,10]})});
  } else {
    var c=placeColor(p);
    m=L.marker([p.lat,p.lng],{icon:L.divIcon({className:'',html:'<div class="dot" style="background:'+c+'"></div>',iconSize:[13,13],iconAnchor:[7,7]})});
  }
  var tier=p.tier?(' · '+p.tier):'';
  m.bindPopup('<div class="lp"><b>'+esc(p.name)+'</b>'+tier+'<br>'+(p.desc?esc(p.desc)+'<br>':'')+
    '<a href="'+p.maps+'" target="_blank">Abrir en Google Maps ↗</a></div>');
  return m;
}
function esc(s){return String(s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function segLayer(seg){
  var w = seg.mode==='walk'?3:(seg.mode==='train'?6:5);
  var dash = seg.mode==='walk'?'4 7':null;
  var pl=L.polyline(seg.coords,{color:seg.color,weight:w,opacity:.9,dashArray:dash});
  var dec=L.polylineDecorator(pl,{patterns:[{offset:'8%',repeat:'22%',
    symbol:L.Symbol.arrowHead({pixelSize:9,pathOptions:{color:seg.color,fillOpacity:.9,weight:0}})}]});
  var g=L.layerGroup([pl,dec]);
  pl.bindPopup('<div class="lp">'+esc(seg.name)+'</div>');
  return g;
}

// construir capas por día
var dayLayers=[]; // {key,label,places:LayerGroup,segs:LayerGroup}
DATA.days.forEach(function(d){
  var pg=L.layerGroup(d.places.map(placeMarker));
  var sg=L.layerGroup(d.segments.map(segLayer));
  dayLayers.push({key:d.key,label:d.label,places:pg,segs:sg});
});
// capa fija de hoteles/aeropuertos
var fixedG=L.layerGroup(DATA.fixed.map(placeMarker));

var lyrs=document.getElementById('lyrs'), daybtns=document.getElementById('daybtns');
function row(label,swatch,layer,on){
  var div=document.createElement('div');div.className='lyr';
  var id='c'+Math.random().toString(36).slice(2);
  div.innerHTML='<label><input type="checkbox" id="'+id+'" '+(on?'checked':'')+'>'+
    '<span class="swatch" style="background:'+swatch+'"></span>'+label+'</label>';
  lyrs.appendChild(div);
  var cb=div.querySelector('input');
  cb.addEventListener('change',function(){cb.checked?map.addLayer(layer):map.removeLayer(layer);});
  if(on)map.addLayer(layer);
  return cb;
}
// botones de día (encienden/apagan ambas capas del día y centran)
DATA.days.forEach(function(d,i){
  var b=document.createElement('button');b.textContent=d.key;
  b.addEventListener('click',function(){
    var L1=dayLayers[i].places, L2=dayLayers[i].segs;
    var on=!map.hasLayer(L1);
    on?map.addLayer(L1):map.removeLayer(L1);
    on?map.addLayer(L2):map.removeLayer(L2);
    b.classList.toggle('on',on);
    // sincronizar checkboxes
    cbPlaces[i].checked=on; cbSegs[i].checked=on;
    if(on){var all=[];dayLayers[i].places.eachLayer(function(m){all.push(m.getLatLng());});
      dayLayers[i].segs.eachLayer(function(g){g.eachLayer&&g.eachLayer(function(x){x.getLatLngs&&all.push.apply(all,x.getLatLngs());});});
      if(all.length)map.fitBounds(L.latLngBounds(all).pad(.15));}
  });
  daybtns.appendChild(b);
});
var allb=document.createElement('button');allb.className='allbtn';allb.textContent='Todos';
allb.addEventListener('click',function(){
  dayLayers.forEach(function(dl,i){map.addLayer(dl.places);map.addLayer(dl.segs);cbPlaces[i].checked=true;cbSegs[i].checked=true;});
  document.querySelectorAll('.daybtns button:not(.allbtn):not(.nonebtn)').forEach(function(b){b.classList.add('on');});
});
daybtns.appendChild(allb);
var noneb=document.createElement('button');noneb.className='nonebtn';noneb.textContent='Ninguno';
noneb.addEventListener('click',function(){
  dayLayers.forEach(function(dl,i){map.removeLayer(dl.places);map.removeLayer(dl.segs);cbPlaces[i].checked=false;cbSegs[i].checked=false;});
  document.querySelectorAll('.daybtns button:not(.allbtn):not(.nonebtn)').forEach(function(b){b.classList.remove('on');});
});
daybtns.appendChild(noneb);

// checkboxes finas (lugares/rutas por día) + fijos
var cbPlaces=[], cbSegs=[];
row('🏨 Hoteles y aeropuertos','#f0a500',fixedG,true);
dayLayers.forEach(function(dl,i){
  var on = i===0;
  cbPlaces.push(row('📍 '+dl.label,'#b23a2a',dl.places,on));
  cbSegs.push(row('🚇 '+dl.key+' rutas','#2c6ba0',dl.segs,on));
  if(on){var b=daybtns.children[i];b.classList.add('on');}
});
// centrar en día 1
(function(){var all=[];dayLayers[0].places.eachLayer(function(m){all.push(m.getLatLng());});if(all.length)map.fitBounds(L.latLngBounds(all).pad(.2));})();
</script></body></html>"""

open(SD + "/leaflet-viaje.html", "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
s = open(SD + "/leaflet-viaje.html", encoding="utf-8").read()
print("leaflet-viaje.html:", len(s) // 1024, "KB")
