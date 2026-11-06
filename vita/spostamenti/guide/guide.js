'use strict';
(() => {
 const data=JSON.parse(document.getElementById('guide-data').textContent),$=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
 const status=$('#map-status'),city=$('#city'),layers=[],routeLayers=new Map(),stopLayers=new Map();let map;
 const selectedCity=()=>city.value;
 const cityMatches=item=>selectedCity()==='all'||item.city===selectedCity();
 const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
 function popup(item,type){const n=document.createElement('div');n.append(el('b',item.name));if(type==='route')n.append(el('p',`${item.km.toFixed(2)} km · ${item.ascent_m} m ↑ · ${item.date}`));else n.append(el('p',item.when));const a=el('a',type==='route'?'Vedi il percorso':'Vedi la sosta');a.href='#'+type+'-'+item.id;n.append(a);return n;}
 function fit(){if(!map)return;const active=layers.filter(x=>map.hasLayer(x.layer));if(active.length)map.fitBounds(L.featureGroup(active.map(x=>x.layer)).getBounds(),{padding:[25,25],maxZoom:15});}
 function refresh(){
  all('.route-card,.stop-card').forEach(c=>c.hidden=selectedCity()!=='all'&&c.dataset.city!==selectedCity());
  if(!map)return;
  layers.forEach(x=>{const visible=cityMatches(x.item)&&$(x.type==='route'?'#show-routes':x.item.kind==='food'?'#show-food':'#show-places').checked;if(visible)x.layer.addTo(map);else map.removeLayer(x.layer);});fit();
  status.textContent=layers.filter(x=>map.hasLayer(x.layer)).length+' tracce e soste nella selezione.';
 }
 function focus(type,id){
  const item=(type==='route'?data.routes:data.stops).find(x=>x.id===id);if(!item)return;
  if(!cityMatches(item)){city.value=item.city;refresh();}
  $(type==='route'?'#show-routes':item.kind==='food'?'#show-food':'#show-places').checked=true;refresh();
  all('.selected').forEach(n=>n.classList.remove('selected'));$('#'+type+'-'+id).classList.add('selected');
  if(map){const l=(type==='route'?routeLayers:stopLayers).get(id);if(type==='route')map.fitBounds(l.getBounds(),{padding:[30,30],maxZoom:16});else map.setView(l.getLatLng(),16);l.openPopup();status.textContent=item.name+' · selezionato';}
  if(matchMedia('(max-width:900px)').matches)$('#atlas-title').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
 }
 if(window.L){
  map=L.map('route-map',{scrollWheelZoom:false});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  data.routes.forEach(r=>{const layer=L.polyline(r.points.map(p=>[p[1],p[0]]),{color:r.sport==='Swim'?'#1684a5':'#245bb1',weight:3,opacity:.8}).bindPopup(popup(r,'route'));layer.on('click',()=>{all('.route-card.selected').forEach(x=>x.classList.remove('selected'));$('#route-'+r.id).classList.add('selected');});layers.push({layer,item:r,type:'route'});routeLayers.set(r.id,layer);});
  data.stops.forEach(s=>{const icon=L.divIcon({className:'map-point '+(s.kind==='food'?'food':'place'),html:s.kind==='food'?'F':'<span>P</span>',iconSize:[24,24],iconAnchor:[12,12]});const layer=L.marker([s.lat,s.lon],{icon,title:s.name,alt:s.name}).bindPopup(popup(s,'stop'));layers.push({layer,item:s,type:'stop'});stopLayers.set(s.id,layer);});
 }else{const n=el('p','La mappa interattiva non è disponibile. Le anteprime dei percorsi, i GPX e i link Google Maps qui sotto sono utilizzabili.');n.className='map-fallback';$('#route-map').append(n);status.textContent='Mappa non disponibile: usa le tracce e i pin qui sotto.';}
 city.addEventListener('change',refresh);['#show-routes','#show-food','#show-places'].forEach(s=>$(s).addEventListener('change',refresh));$('#all-map').addEventListener('click',fit);
 all('[data-route]').forEach(b=>b.addEventListener('click',()=>focus('route',b.dataset.route)));all('[data-stop]').forEach(b=>b.addEventListener('click',()=>focus('stop',b.dataset.stop)));refresh();
})();
