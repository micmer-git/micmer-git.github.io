(()=>{
const D=window.VX, A=D.acts, byId=new Map(A.map(a=>[a.id,a]));
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=(n,d=0)=>n==null?'–':Number(n).toLocaleString('it-IT',{minimumFractionDigits:d,maximumFractionDigits:d});
const hms=s=>{if(!s)return'–';s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return h?`${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`:`${m}:${String(x).padStart(2,'0')}`};
const hm=s=>{if(!s)return'–';const h=Math.floor(s/3600),m=Math.round(s%3600/60);return h?`${h} h ${String(m).padStart(2,'0')}`:`${m} min`};
const pace=s=>s?`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}/km`:'–';
const MESI=['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre'];
const GIORNI=['domenica','lunedì','martedì','mercoledì','giovedì','venerdì','sabato'];
const dlong=d=>{const x=new Date(d+'T12:00:00');return `${GIORNI[x.getDay()]} ${x.getDate()} ${MESI[x.getMonth()]} ${x.getFullYear()}`};
const dshort=d=>{const [y,m,g]=d.split('-');return `${+g}/${+m}/${y}`};
// sport: gruppi e colori (gli slot della pagina Vita)
const GROUPS={ride:{l:'Bici',c:'var(--s1)',hex:'#4285f4',band:'#aecbfa'},run:{l:'Corsa',c:'var(--s2)',hex:'#ea4335',band:'#f6aea9'},
  swim:{l:'Nuoto',c:'var(--s4)',hex:'#8430ce',band:'#d7aefb'},hike:{l:'A piedi',c:'var(--s3)',hex:'#1e8e3e',band:'#a8dab5'},
  snow:{l:'Neve',c:'#5f6368',hex:'#5f6368',band:'#e8eaed'},other:{l:'Altro',c:'#9aa0a6',hex:'#9aa0a6',band:'#fdd663'}};
const SPORT_IT={'Ride':'Bici','Virtual Ride':'Bici virtuale','Gravel Ride':'Gravel','Mountain Bike Ride':'MTB','E-Bike Ride':'E-bike','E-Mountain Bike Ride':'E-MTB','Velomobile':'Velomobile','Handcycle':'Handbike',
  'Run':'Corsa','Trail Run':'Trail','Virtual Run':'Corsa virtuale','TrailRun':'Trail','VirtualRun':'Corsa virtuale','VirtualRide':'Bici virtuale','Swim':'Nuoto','Hike':'Escursione','Walk':'Camminata',
  'Backcountry Ski':'Scialpinismo','BackcountrySki':'Scialpinismo','Alpine Ski':'Sci','AlpineSki':'Sci','Nordic Ski':'Sci di fondo','NordicSki':'Sci di fondo','Snowshoe':'Ciaspole','Workout':'Allenamento',
  'Weight Training':'Pesi','WeightTraining':'Pesi','Yoga':'Yoga','Rowing':'Canottaggio','Kayaking':'Kayak','Canoeing':'Canoa','Rock Climbing':'Arrampicata','RockClimbing':'Arrampicata','Ice Skate':'Pattinaggio','Elliptical':'Ellittica','Stair Stepper':'Scale','Crossfit':'Crossfit','Golf':'Golf','Tennis':'Tennis','Soccer':'Calcio','Surfing':'Surf','Windsurf':'Windsurf','Kitesurf':'Kitesurf','Stand Up Paddling':'SUP','Sail':'Vela','Inline Skate':'Pattini','Snowboard':'Snowboard'};
const grp=s=>/Ride|Velomobile|Handcycle/.test(s)?'ride':/Run/.test(s)?'run':s==='Swim'?'swim':/Hike|Walk/.test(s)?'hike':/Ski|Snow/.test(s)?'snow':'other';
A.forEach(a=>{a.g=grp(a.sp);a.y=a.d.slice(0,4);a.spi=SPORT_IT[a.sp]||a.sp;
  a.hay=[a.n,a.ds,a.d,dshort(a.d),dlong(a.d),a.spi,a.sp,GROUPS[a.g].l,a.race?'gara race':'',a.mar?'maratona marathon '+a.mar.event+' '+a.mar.city:'',a.mard?'42 km':'',a.ct?'cicloviaggio viaggio bici':'',a.tv?'viaggio':'',a.gear||''].join(' ').toLowerCase();});
const TRIPS=new Map(D.trips.map(t=>[t.id,t])), TRAV=new Map(D.travel.map(t=>[t.id,t]));
A.forEach(a=>{if(a.tv){const t=TRAV.get(a.tv);if(t)a.hay+=' '+(t.city||'').toLowerCase()+' '+(t.country||'').toLowerCase()} if(a.ct){const t=TRIPS.get(a.ct);if(t&&t.city)a.hay+=' '+t.city.toLowerCase()}});
const YEARS=[...new Set(A.map(a=>a.y))].sort();
const ST={year:'all',sport:'all',q:'',view:'foto',sort:'d'};
// ---------- filtro e ricerca ----------
function parseQ(q){const f=[],w=[];q.toLowerCase().trim().split(/\s+/).filter(Boolean).forEach(t=>{
  let m=t.match(/^(km|d\+|dislivello|ore|h)\s*([<>]=?)\s*(\d+(?:[.,]\d+)?)$/);
  if(m){const k=m[1]==='km'?'km':(m[1]==='ore'||m[1]==='h')?'h':'up';f.push([k,m[2],parseFloat(m[3].replace(',','.'))]);return}
  m=t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); if(m){w.push(`${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`);return}
  w.push(t)});return{f,w}}
function sel(opts={}){const{f,w}=parseQ(ST.q);return A.filter(a=>{
  if(!opts.anyYear&&ST.year!=='all'&&a.y!==ST.year)return false;
  if(!opts.anySport&&ST.sport!=='all'&&a.g!==ST.sport)return false;
  for(const t of w)if(!a.hay.includes(t))return false;
  for(const[k,op,v]of f){const x=k==='km'?a.km:k==='h'?(a.mv||0)/3600:(a.up||0);if(op[0]==='>'?!(op[1]?x>=v:x>v):!(op[1]?x<=v:x<v))return false}
  return true})}
// ---------- grafici: barre con media del periodo ----------
function bars(data,{w=520,h=170,unit='',color='var(--s1)',dec=0,onclick=null,hi=null,avgLabel='media',stack=null}={}){
  const pad={l:38,r:8,t:16,b:22},iw=w-pad.l-pad.r,ih=h-pad.t-pad.b;
  const vals=data.map(d=>d.v),max=Math.max(1,...vals)*1.08,avg=vals.length?vals.reduce((s,x)=>s+x,0)/vals.length:0;
  const bw=iw/data.length,y=v=>pad.t+ih-(v/max)*ih;
  let s=`<svg class="plot" viewBox="0 0 ${w} ${h}" role="img">`;
  [0,.5,1].forEach(k=>{const v=max/1.08*k,yy=y(v);s+=`<line x1="${pad.l}" x2="${w-pad.r}" y1="${yy}" y2="${yy}" stroke="var(--grid)"/><text x="${pad.l-4}" y="${yy+3}" text-anchor="end" font-size="9" fill="var(--muted)" font-family="ui-monospace,Menlo,monospace">${fmt(v,v<10&&dec?1:0)}</text>`});
  data.forEach((d,i)=>{const x=pad.l+i*bw+bw*.14,bwi=bw*.72;
    if(stack&&d.parts){let acc=0;d.parts.forEach(p=>{if(!p.v)return;const y0=y(acc+p.v),hh=y(acc)-y0;s+=`<rect x="${x}" y="${y0}" width="${bwi}" height="${Math.max(0,hh)}" fill="${p.c}"><title>${esc(d.l)} · ${esc(p.l)}: ${fmt(p.v,dec)} ${unit}</title></rect>`;acc+=p.v})}
    else s+=`<rect x="${x}" y="${y(d.v)}" width="${bwi}" height="${Math.max(0,pad.t+ih-y(d.v))}" fill="${d.c||color}" opacity="${hi&&d.k!==hi?.35:1}"><title>${esc(d.l)}: ${fmt(d.v,dec)} ${unit}</title></rect>`;
    if(onclick)s+=`<rect x="${pad.l+i*bw}" y="${pad.t}" width="${bw}" height="${ih}" fill="transparent" style="cursor:pointer" data-k="${esc(d.k)}"><title>${esc(d.l)}: ${fmt(d.v,dec)} ${unit}</title></rect>`;
    if(data.length<=14||i%Math.ceil(data.length/12)===0)s+=`<text x="${pad.l+i*bw+bw/2}" y="${h-7}" text-anchor="middle" font-size="9.5" fill="var(--muted)" font-family="ui-monospace,Menlo,monospace">${esc(d.s??d.l)}</text>`});
  const ya=y(avg);
  s+=`<line x1="${pad.l}" x2="${w-pad.r}" y1="${ya}" y2="${ya}" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${w-pad.r}" y="${ya-4}" text-anchor="end" class="chart-avg" fill="var(--ink)">${avgLabel} ${fmt(avg,dec)} ${unit}</text>`;
  return s+'</svg>'}
function dots(data,{w=520,h=180,fmtV=v=>v,inv=false,avgLabel='media'}={}){ // per i tempi di maratona
  const pad={l:44,r:8,t:16,b:22},iw=w-pad.l-pad.r,ih=h-pad.t-pad.b,vals=data.map(d=>d.v);
  const mn=Math.min(...vals)*.98,mx=Math.max(...vals)*1.02,avg=vals.reduce((s,x)=>s+x,0)/vals.length;
  const y=v=>pad.t+((v-mn)/(mx-mn||1))*ih, x=i=>pad.l+(data.length<2?iw/2:i*iw/(data.length-1));
  let s=`<svg class="plot" viewBox="0 0 ${w} ${h}">`;
  [mn,(mn+mx)/2,mx].forEach(v=>s+=`<line x1="${pad.l}" x2="${w-pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${pad.l-4}" y="${y(v)+3}" text-anchor="end" font-size="9" fill="var(--muted)" font-family="ui-monospace,Menlo,monospace">${fmtV(v)}</text>`);
  s+=`<polyline fill="none" stroke="var(--s2)" stroke-width="1.5" points="${data.map((d,i)=>x(i)+','+y(d.v)).join(' ')}"/>`;
  data.forEach((d,i)=>s+=`<rect x="${x(i)-4}" y="${y(d.v)-4}" width="8" height="8" fill="var(--s2)" stroke="var(--ink)" style="cursor:pointer" data-id="${d.id}"><title>${esc(d.l)}: ${fmtV(d.v)}</title></rect><text x="${x(i)}" y="${h-7}" text-anchor="middle" font-size="9" fill="var(--muted)" font-family="ui-monospace,Menlo,monospace">${esc(d.s)}</text>`);
  s+=`<line x1="${pad.l}" x2="${w-pad.r}" y1="${y(avg)}" y2="${y(avg)}" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="5 4"/><text x="${w-pad.r}" y="${y(avg)-4}" text-anchor="end" class="chart-avg">${avgLabel} ${fmtV(avg)}</text>`;
  return s+'</svg>'}
const tile=(title,now,small,body,foot='',wide=false)=>`<div class="tile ${wide?'wide':''}"><div class="t-side"><div class="t-head"><span class="t-title">${title}</span></div><div class="t-now">${now}<small>${small}</small></div></div><div>${body}</div>${foot?`<div class="t-bottom"><div class="t-foot">${foot}</div></div>`:''}</div>`;
const actLi=a=>`<li data-id="${a.id}"><b>${esc(a.n||a.spi)}</b><em>${dshort(a.d)} · ${fmt(a.km,1)} km${a.up?` · ${fmt(a.up)} m`:''}${a.mv?` · ${hm(a.mv)}`:''}</em></li>`;
// ---------- testata ----------
function totals(list){const km=list.reduce((s,a)=>s+(a.km||0),0),h=list.reduce((s,a)=>s+(a.mv||0),0)/3600,up=list.reduce((s,a)=>s+(a.up||0),0);
  const cells=[[fmt(list.length),'attività'],[fmt(km),'km'],[fmt(h),'ore'],[fmt(up),'m dislivello'],[fmt(list.filter(a=>a.cv).length),'con foto'],[fmt(list.filter(a=>a.race).length),'gare']];
  $('#totals').innerHTML=cells.map(([n,l])=>`<div class="total"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');
  $('#tot-label').textContent=(ST.year==='all'?'2015 – oggi':ST.year)+(ST.sport!=='all'?' · '+GROUPS[ST.sport].l:'')+(ST.q?' · «'+ST.q+'»':'');}
$('#sub').textContent=`${fmt(A.length)} uscite dal ${dlong(A[A.length-1].d)} al ${dlong(A[0].d)}. Foto, percorsi e numeri di ogni attività, senza uscire dal sito.`;
$('#sports').innerHTML=[['all','Tutto'],...Object.entries(GROUPS).map(([k,v])=>[k,v.l])].map(([k,l])=>`<button data-s="${k}" aria-pressed="${k==='all'}">${l}</button>`).join('');
// ---------- barra degli anni ----------
function yearbar(){const list=sel({anyYear:true}),per=YEARS.map(y=>({k:y,v:list.filter(a=>a.y===y).reduce((s,a)=>s+(a.km||0),0)}));
  const W=1000,H=64,max=Math.max(1,...per.map(p=>p.v)),bw=W/per.length,avg=per.reduce((s,p)=>s+p.v,0)/per.length;
  let s='';per.forEach((p,i)=>{const hh=(p.v/max)*(H-16);s+=`<rect x="${i*bw+bw*.12}" y="${H-12-hh}" width="${bw*.76}" height="${hh}" fill="${ST.year===p.k?'#202124':'#aecbfa'}" stroke="#202124" stroke-width="${ST.year===p.k?0:1}" vector-effect="non-scaling-stroke"/><text x="${i*bw+bw/2}" y="${H-1}" text-anchor="middle" font-size="10" fill="#5f6368" font-family="ui-monospace,Menlo,monospace">${p.k}</text><rect data-y="${p.k}" x="${i*bw}" y="0" width="${bw}" height="${H}" fill="transparent"><title>${p.k}: ${fmt(p.v)} km</title></rect>`});
  const ya=H-12-(avg/max)*(H-16);s+=`<line x1="0" x2="${W}" y1="${ya}" y2="${ya}" stroke="#202124" stroke-dasharray="6 4" stroke-width="1.5" vector-effect="non-scaling-stroke"/><text x="${W-2}" y="${ya-3}" text-anchor="end" font-size="10" font-family="ui-monospace,Menlo,monospace">media ${fmt(avg)} km/anno</text>`;
  $('#yb-svg').innerHTML=s;$('#yb-label').textContent=ST.year==='all'?'Tutti gli anni':ST.year;
  $('#year').min=+YEARS[0]-1;$('#year').max=YEARS[YEARS.length-1];$('#year').value=ST.year==='all'?+YEARS[0]-1:ST.year;}
$('#yb-svg').addEventListener('click',e=>{const y=e.target.dataset.y;if(y)setYear(ST.year===y?'all':y)});
$('#year').addEventListener('input',e=>{const v=e.target.value;setYear(+v<+YEARS[0]?'all':String(v))});
function setYear(y){ST.year=y;render();if(ST.view==='foto')window.scrollTo({top:$('.yearbar').offsetTop-60,behavior:'smooth'})}
function ysum(list){const g={};list.forEach(a=>{g[a.g]=g[a.g]||{n:0,km:0};g[a.g].n++;g[a.g].km+=a.km||0});
  $('#ysum').innerHTML=Object.entries(GROUPS).filter(([k])=>g[k]).map(([k,v])=>`<i style="--c:${v.c}">${v.l} ${fmt(g[k].n)} · ${fmt(g[k].km)} km</i>`).join('')}
// ---------- tracce (file per anno, caricati a richiesta) ----------
window.VXT=window.VXT||{};const loading={};
function loadYear(y){if(VXT[y])return Promise.resolve(VXT[y]);if(loading[y])return loading[y];
  return loading[y]=new Promise((res,rej)=>{const s=document.createElement('script');s.src=`data/tracks/${y}.js`;s.onload=()=>res(VXT[y]||{});s.onerror=()=>res({});document.head.appendChild(s)})}
function decode(str){let i=0,lat=0,lng=0,out=[];while(i<str.length){let b,sh=0,r=0;do{b=str.charCodeAt(i++)-63;r|=(b&31)<<sh;sh+=5}while(b>=32);lat+=r&1?~(r>>1):r>>1;sh=0;r=0;do{b=str.charCodeAt(i++)-63;r|=(b&31)<<sh;sh+=5}while(b>=32);lng+=r&1?~(r>>1):r>>1;out.push([lat/1e5,lng/1e5])}return out}
const segsOf=a=>{const t=VXT[a.y]&&VXT[a.y][a.id];return t?t.map(decode):null};
function miniSvg(a){const segs=segsOf(a);if(!segs)return'';const all=segs.flat();let la0=1e9,la1=-1e9,lo0=1e9,lo1=-1e9;all.forEach(([la,lo])=>{la0=Math.min(la0,la);la1=Math.max(la1,la);lo0=Math.min(lo0,lo);lo1=Math.max(lo1,lo)});
  const k=Math.cos(la0*Math.PI/180),w=(lo1-lo0)*k||1e-4,h=(la1-la0)||1e-4,sc=100/Math.max(w,h),ox=(100-w*sc)/2,oy=(100-h*sc)/2;
  return `<svg viewBox="-4 -4 108 108" preserveAspectRatio="xMidYMid meet">${segs.map(s=>`<polyline fill="none" stroke="#202124" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" points="${s.map(([la,lo])=>((lo-lo0)*k*sc+ox).toFixed(1)+','+((la1-la)*sc+oy).toFixed(1)).join(' ')}"/>`).join('')}</svg>`}
// ---------- vista foto ----------
const GRID_STEP=360;let gridList=[],gridShown=0;
// lazy foto affidabile: le prime 24 subito, le altre con IntersectionObserver (fallback: tutte subito)
let eagerLeft=24;const lio='IntersectionObserver' in window?new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){const im=e.target;im.src=im.dataset.src;im.removeAttribute('data-src');lio.unobserve(im)}}),{rootMargin:'900px 0px'}):null;
function lazyImgs(root){root.querySelectorAll('img[data-src]').forEach(im=>{if(lio)lio.observe(im);else{im.src=im.dataset.src;im.removeAttribute('data-src')}})}
function card(a){const b=(a.race?'<i>gara</i>':'')+(a.mar?'<i class="m">42k</i>':'')+(a.ct?'<i class="t">viaggio</i>':'')+(a.dq?'<i class="q">!</i>':'');
  const cap=`<div class="cap"><b>${esc(a.n||a.spi)}</b><span>${dshort(a.d)} · ${a.km?fmt(a.km,1)+' km':a.spi}</span></div>`;
  if(a.cv)return `<button class="card" data-id="${a.id}">${eagerLeft-->0?`<img decoding="async" src="data/photos/t/${a.cv}.jpg" alt="${esc(a.n)}">`:`<img decoding="async" data-src="data/photos/t/${a.cv}.jpg" alt="${esc(a.n)}">`}${cap}<div class="bdg">${b}</div></button>`;
  return `<button class="card nophoto" data-id="${a.id}" data-y="${a.y}" style="--bandc:${GROUPS[a.g].band}"><span class="km">${a.km?fmt(a.km,a.km<10?1:0)+' km':esc(a.spi)}</span>${a.trk?`<span class="mini" data-mini="${a.id}"></span>`:''}${cap}<div class="bdg">${b}</div></button>`}
function renderFoto(list){gridList=list;gridShown=0;eagerLeft=24;$('#v-foto').innerHTML=list.length?'':'<p class="t-empty">Nessuna attività con questi filtri.</p>';moreFoto()}
function moreFoto(){const host=$('#v-foto');host.querySelector('.more')?.remove();const part=gridList.slice(gridShown,gridShown+GRID_STEP);gridShown+=part.length;
  const groups=new Map();part.forEach(a=>{const k=a.d.slice(0,7);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(a)});
  let html='';for(const[k,l]of groups){let g=host.querySelector(`.mgroup[data-m="${k}"] .grid`);
    if(g){g.insertAdjacentHTML('beforeend',l.map(card).join(''));continue}
    const all=gridList.filter(a=>a.d.startsWith(k)),km=all.reduce((s,a)=>s+(a.km||0),0);
    html+=`<div class="mgroup" data-m="${k}" data-y="${k.slice(0,4)}"><div class="mhead"><b>${MESI[+k.slice(5)-1]} ${k.slice(0,4)}</b><span>${all.length} attività · ${fmt(km)} km · ${fmt(all.filter(a=>a.cv).length)} con foto</span></div><div class="grid">${l.map(card).join('')}</div></div>`}
  host.insertAdjacentHTML('beforeend',html);
  if(gridShown<gridList.length)host.insertAdjacentHTML('beforeend',`<button class="btn more" id="more">Mostra altre ${fmt(Math.min(GRID_STEP,gridList.length-gridShown))} di ${fmt(gridList.length-gridShown)}</button>`);
  lazyImgs(host);minis();rail()}
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting&&e.target.id==='more')moreFoto()}),{rootMargin:'800px'});
const mo=new MutationObserver(()=>{const m=$('#more');if(m)io.observe(m)});mo.observe($('#v-foto'),{childList:true});
function minis(){const need=new Set([...document.querySelectorAll('[data-mini]:empty')].map(e=>e.closest('[data-y]').dataset.y));
  need.forEach(y=>loadYear(y).then(()=>document.querySelectorAll(`.card[data-y="${y}"] [data-mini]:empty`).forEach(e=>{const a=byId.get(e.dataset.mini);e.innerHTML=miniSvg(a)})))}
function rail(){const ys=[...new Set(gridList.map(a=>a.y))];const r=$('#rail');r.classList.toggle('show',ST.view==='foto'&&ys.length>1);
  r.innerHTML=ys.map(y=>`<button data-y="${y}">${y}</button>`).join('')}
$('#rail').addEventListener('click',e=>{const y=e.target.dataset?.y;if(!y)return;let g=document.querySelector(`.mgroup[data-y="${y}"]`);
  while(!g&&gridShown<gridList.length){moreFoto();g=document.querySelector(`.mgroup[data-y="${y}"]`)}g&&g.scrollIntoView({behavior:'smooth'})});
// ---------- vista mappa: globo (MapLibre) ----------
// Le tracce lontane c'erano già. La camera no: se il riquadro del mondo superava
// 12°×8°, la vista si chiudeva sulla mediana delle partenze (il mucchio delle
// uscite di tutti i giorni) e Giappone, Hong Kong, Nepal restavano fuori.
// Qui il globo parte sul mondo. I punti sono l'inizio della traccia già tagliata:
// niente segnaposto sul centro di una zona privata. Le uscite virtuali non
// finiscono sul globo: quel GPS è il simulatore, non un luogo.
const GLOBE_AT={center:[92,22],zoom:1.22};
const isVirt=a=>/virtual/i.test(a.sp||'');
const onGlobe=a=>!!(a.st&&a.trk&&!isVirt(a));
const fc=features=>({type:'FeatureCollection',features});
function clumpsOf(pts){const gs=[];pts.forEach(a=>{
  let g=gs.find(g=>Math.abs(g.la-a.st[0])<2.4&&Math.abs(g.lo-a.st[1])<3);
  if(!g){g={la:a.st[0],lo:a.st[1],n:0,sla:0,slo:0,names:[]};gs.push(g)}
  g.n++;g.sla+=a.st[0];g.slo+=a.st[1];g.names.push(a.n||'');g.la=g.sla/g.n;g.lo=g.slo/g.n});return gs}
let everyday=null;
function everydayClump(){if(everyday)return everyday;const gs=clumpsOf(A.filter(onGlobe)).sort((a,b)=>b.n-a.n);everyday=gs[0]&&gs[0].n>40?gs[0]:null;return everyday}
// Il nome è quello del viaggio, non di ogni tappa: «Kathmandu» passa anche da
// Baku. Se il viaggio ha più di un mucchio e i nomi di quel mucchio non dicono
// la città, l'etichetta si toglie — non se ne inventa un'altra. Quelle vicine
// al mucchio di tutti i giorni restano nascoste finché lo zoom non le stacca.
function fold(s){return String(s||'').toLowerCase().normalize('NFD').replace(/\p{M}/gu,'')}
function cityInNames(names,city){const raw=fold(names.join(' ')),c=fold(city);if(!c)return false;
  if(raw.includes(c))return true;
  if(c==='kathmandu'&&/katmandu|\bktm\b/.test(raw))return true;
  return false}
function placeFeatures(list){const home=everydayClump(),feats=[];
  (D.travel||[]).forEach(t=>{if(!t.city)return;const pts=list.filter(a=>a.tv===t.id&&onGlobe(a));
    const gs=clumpsOf(pts).filter(g=>!(home&&Math.abs(g.la-home.la)<8&&Math.abs(g.lo-home.lo)<10));
    const multi=gs.length>1;
    gs.forEach(g=>{
      if(multi&&!cityInNames(g.names,t.city))return;
      const near=home&&Math.abs(g.la-home.la)<16&&Math.abs(g.lo-home.lo)<18?1:0;
      feats.push({type:'Feature',geometry:{type:'Point',coordinates:[g.lo,g.la]},properties:{label:t.city,n:g.n,prio:-g.n,near}})})});
  return fc(feats)}
function pointFeatures(list){return fc(list.filter(onGlobe).map(a=>({type:'Feature',geometry:{type:'Point',coordinates:[a.st[1],a.st[0]]},properties:{id:String(a.id),color:GROUPS[a.g].hex}})))}
function spanOf(pts){if(!pts.length)return null;let s=90,n=-90,w=180,e=-180;
  pts.forEach(a=>{s=Math.min(s,a.st[0]);n=Math.max(n,a.st[0]);w=Math.min(w,a.st[1]);e=Math.max(e,a.st[1])});
  return {s,n,w,e,wide:(e-w)>40||(n-s)>28}}
function frameOf(list){const pts=list.filter(onGlobe),sp=spanOf(pts);if(!sp)return null;
  const focused=!!ST.q.trim()||pts.length<80;
  if(!(focused&&sp.wide))return sp;
  let best=null,bn=0;
  pts.forEach(a=>{const n=pts.filter(b=>Math.abs(b.st[0]-a.st[0])<4&&Math.abs(b.st[1]-a.st[1])<5).length;if(n>bn){bn=n;best=a}});
  if(best&&bn>=Math.max(3,pts.length*0.5))return spanOf(pts.filter(b=>Math.abs(b.st[0]-best.st[0])<4&&Math.abs(b.st[1]-best.st[1])<5));
  return sp}
let gmap=null,gReady=false,gPending=null,gWide=false,trackTok=0,trackTimer=0;
function refreshTracks(){if(!gmap||!gReady)return;const list=gmap.__list||[],src=gmap.getSource('tracks');if(!src)return;
  const z=gmap.getZoom();
  if(z<6.4){src.setData(fc([]));return}
  const b=gmap.getBounds(),pad=.35;
  let vis=list.filter(onGlobe);
  if(vis.length>50)vis=vis.filter(a=>{if(!a.bb)return false;const [s,w,n,e]=a.bb;return n>=b.getSouth()-pad&&s<=b.getNorth()+pad&&e>=b.getWest()-pad&&w<=b.getEast()+pad});
  vis=vis.slice(0,140);
  const tok=++trackTok,ys=[...new Set(vis.map(a=>a.y))];
  Promise.all(ys.map(loadYear)).then(()=>{if(tok!==trackTok)return;const features=[];
    vis.forEach(a=>{const segs=segsOf(a);if(!segs)return;segs.forEach(seg=>{if(seg.length<2)return;
      features.push({type:'Feature',properties:{id:String(a.id),color:GROUPS[a.g].hex},geometry:{type:'LineString',coordinates:seg.map(([la,lo])=>[lo,la])}})})});
    src.setData(fc(features))})}
function applyGlobe(list){gmap.__list=list;
  const ptsSrc=gmap.getSource('acts'),labSrc=gmap.getSource('places');
  if(ptsSrc)ptsSrc.setData(pointFeatures(list));
  if(labSrc)labSrc.setData(placeFeatures(list));
  const sp=frameOf(list),pts=list.filter(onGlobe);
  if(sp&&sp.wide){if(!gWide){gmap.jumpTo({center:GLOBE_AT.center,zoom:GLOBE_AT.zoom,bearing:0,pitch:0});gWide=true}}
  else if(sp){gWide=false;try{gmap.fitBounds([[sp.w,sp.s],[sp.e,sp.n]],{padding:48,maxZoom:12.5,duration:650})}catch(e){gmap.jumpTo({center:[(sp.w+sp.e)/2,(sp.s+sp.n)/2],zoom:8})}}
  const virt=list.filter(isVirt).length,noGps=list.filter(a=>!a.trk&&!isVirt(a)).length;
  $('#maphint').textContent=(pts.length?`${fmt(pts.length)} attività sul globo`:'Nessun punto sul globo')
    +(noGps?` · ${fmt(noGps)} senza traccia pubblicabile`:'')
    +(virt?` · ${fmt(virt)} virtuali non segnate: il GPS non è un luogo`:'')
    +' · tocca un punto per aprirla, avvicina lo zoom per la traccia';
  $('#maplegend').innerHTML=Object.entries(GROUPS).map(([k,v])=>`<span><i style="background:${v.hex}"></i>${v.l}</span>`).join('');
  clearTimeout(trackTimer);trackTimer=setTimeout(refreshTracks,160)}
function renderMappa(list){if(!window.maplibregl){$('#maphint').textContent='Mappa non caricata (serve la rete).';return}
  gPending=list;
  if(!gmap){gmap=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/positron',
    center:GLOBE_AT.center,zoom:GLOBE_AT.zoom,attributionControl:true,canvasContextAttributes:{antialias:true},
    cooperativeGestures:matchMedia('(max-width:760px)').matches});
    window.VXMAP=gmap;
    gmap.addControl(new maplibregl.NavigationControl({showCompass:false,visualizePitch:false}),'top-right');
    gmap.on('style.load',()=>{gmap.setProjection({type:'globe'});
      gmap.addSource('tracks',{type:'geojson',data:fc([])});
      gmap.addSource('acts',{type:'geojson',data:fc([]),cluster:true,clusterRadius:42,clusterMaxZoom:8});
      gmap.addSource('places',{type:'geojson',data:fc([])});
      gmap.addLayer({id:'tracks',type:'line',source:'tracks',paint:{'line-color':['get','color'],'line-width':['interpolate',['linear'],['zoom'],6,1.4,13,3.2],'line-opacity':.9}});
      gmap.addLayer({id:'clusters',type:'circle',source:'acts',filter:['has','point_count'],paint:{
        'circle-color':'#202124','circle-stroke-width':2,'circle-stroke-color':'#fbbc04',
        'circle-radius':['step',['get','point_count'],12,10,16,50,20,200,26,800,32]}});
      // Il numero sta DENTRO il cerchio. Non entra nella collisione delle etichette:
      // «Tokyo» sotto il cerchio nascondeva il 7, mentre il 2.4k (senza etichetta
      // sopra, a questo zoom) restava. Le città continuano a non sovrapporsi fra loro.
      gmap.addLayer({id:'cluster-count',type:'symbol',source:'acts',filter:['has','point_count'],layout:{
        'text-field':['get','point_count_abbreviated'],'text-font':['Noto Sans Bold'],'text-size':11,
        'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'#ffffff'}});
      gmap.addLayer({id:'points',type:'circle',source:'acts',filter:['!',['has','point_count']],paint:{
        'circle-color':['get','color'],'circle-radius':6,'circle-stroke-width':2,'circle-stroke-color':'#202124'}});
      const placeLayout={'text-field':['get','label'],'text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.05],'text-anchor':'top',
        'text-allow-overlap':false,'text-ignore-placement':false,'text-padding':8,'symbol-sort-key':['get','prio']};
      const placePaint={'text-color':'#202124','text-halo-color':'#ffffff','text-halo-width':1.6};
      gmap.addLayer({id:'places',type:'symbol',source:'places',maxzoom:6.2,filter:['==',['get','near'],0],layout:placeLayout,paint:placePaint});
      gmap.addLayer({id:'places-near',type:'symbol',source:'places',minzoom:3.4,maxzoom:6.2,filter:['==',['get','near'],1],layout:placeLayout,paint:placePaint});
      gmap.on('click','clusters',e=>{const f=e.features&&e.features[0];if(!f)return;const id=f.properties.cluster_id;
        Promise.resolve(gmap.getSource('acts').getClusterExpansionZoom(id)).then(z=>{gmap.easeTo({center:f.geometry.coordinates,zoom:z})})});
      gmap.on('click','points',e=>{const id=e.features&&e.features[0]&&e.features[0].properties.id;if(id)openDetail(String(id))});
      gmap.on('click','tracks',e=>{const id=e.features&&e.features[0]&&e.features[0].properties.id;if(id)openDetail(String(id))});
      ['clusters','points','tracks'].forEach(id=>{gmap.on('mouseenter',id,()=>{gmap.getCanvas().style.cursor='pointer'});gmap.on('mouseleave',id,()=>{gmap.getCanvas().style.cursor=''})});
      gmap.on('moveend',()=>{clearTimeout(trackTimer);trackTimer=setTimeout(refreshTracks,120)});
      gReady=true;if(gPending)applyGlobe(gPending);gmap.resize()});
  }
  setTimeout(()=>{if(gmap)gmap.resize()},60);
  if(gReady)applyGlobe(list)}
// ---------- vista elenco ----------
const COLS=[['d','Data'],['n','Nome'],['spi','Sport'],['km','km'],['up','D+ m'],['mv','Tempo'],['kmh','km/h'],['hr','FC']];
function renderElenco(list){const k=ST.sort.replace('-',''),dir=ST.sort[0]==='-'?1:-1;
  const l=[...list].sort((a,b)=>{const x=a[k]??'',y=b[k]??'';return(x>y?1:x<y?-1:0)*dir});
  $('#v-elenco').innerHTML=`<div class="listwrap"><table class="list"><thead><tr>${COLS.map(([c,t])=>`<th data-k="${c}">${t}${k===c?(dir<0?' ▾':' ▴'):''}</th>`).join('')}</tr></thead><tbody>${l.slice(0,600).map(a=>`<tr data-id="${a.id}"><td>${dshort(a.d)}</td><td>${esc(a.n)}${a.race?' 🏁':''}${a.dq?' ⚠︎':''}</td><td>${esc(a.spi)}</td><td>${fmt(a.km,1)}</td><td>${fmt(a.up)}</td><td>${hms(a.mv)}</td><td>${a.kmh?fmt(a.kmh,1):'–'}</td><td>${a.hr||'–'}</td></tr>`).join('')}</tbody></table></div>${l.length>600?`<p class="hint">Prime 600 di ${fmt(l.length)}: restringi con la ricerca.</p>`:''}`}
$('#v-elenco').addEventListener('click',e=>{const th=e.target.closest('th');if(th){const k=th.dataset.k;ST.sort=ST.sort===k?'-'+k:k;renderElenco(sel());}});
// ---------- sezioni ----------
function sections(){const list=sel({anyYear:true}),inY=sel();
  // anno per anno
  const per=YEARS.map(y=>{const l=list.filter(a=>a.y===y);return{k:y,l:y,s:"'"+y.slice(2),v:l.reduce((s,a)=>s+(a.km||0),0),h:l.reduce((s,a)=>s+(a.mv||0),0)/3600,up:l.reduce((s,a)=>s+(a.up||0),0),n:l.length,
    parts:Object.entries(GROUPS).map(([g,G])=>({l:G.l,c:G.hex,v:l.filter(a=>a.g===g).reduce((s,a)=>s+(a.km||0),0)}))}});
  let h=tile('km per anno',fmt(per.reduce((s,p)=>s+p.v,0)),'km in totale',bars(per,{unit:'km',stack:true,onclick:1,avgLabel:'media annua'}),'colori = sport (blu bici, rosso corsa, viola nuoto, verde a piedi) · tocca un anno per filtrare',true);
  h+=tile('ore per anno',fmt(per.reduce((s,p)=>s+p.h,0)),'ore in movimento',bars(per.map(p=>({...p,v:p.h})),{unit:'h',color:'var(--s3)',onclick:1,hi:ST.year!=='all'?ST.year:null,avgLabel:'media annua'}));
  h+=tile('dislivello per anno',fmt(per.reduce((s,p)=>s+p.up,0)),'m in salita',bars(per.map(p=>({...p,v:p.up})),{unit:'m',color:'var(--s4)',onclick:1,hi:ST.year!=='all'?ST.year:null,avgLabel:'media annua'}));
  const yy=ST.year==='all'?null:ST.year;
  const mon=MESI.map((m,i)=>{const mm=String(i+1).padStart(2,'0');const l=(yy?list.filter(a=>a.y===yy):list).filter(a=>a.d.slice(5,7)===mm);return{k:mm,l:m,s:m.slice(0,3),v:yy?l.reduce((s,a)=>s+(a.km||0),0):l.reduce((s,a)=>s+(a.km||0),0)/YEARS.length}});
  h+=tile(yy?`mesi del ${yy}`:'mese tipo',fmt(mon.reduce((s,p)=>s+p.v,0)),yy?'km nell\'anno':'km/anno medi',bars(mon,{unit:'km',color:'var(--s1)',avgLabel:'media mensile'}),yy?'':'media di ogni mese su tutti gli anni');
  const hrs=[...Array(24)].map((_,i)=>({k:i,l:i+':00',s:i%3?'':String(i),v:inY.filter(a=>+a.t.slice(0,2)===i).length}));
  h+=tile('a che ora parto',fmt(inY.length),'attività nel periodo',bars(hrs,{unit:'att.',color:'var(--s2)',avgLabel:'media oraria'}),'ora locale di partenza');
  $('#p-anni').innerHTML=h;
  // record
  const pick=(f,arr=list)=>arr.filter(f);
  const best=(arr,k)=>arr.reduce((m,a)=>(a[k]||0)>((m&&m[k])||0)?a:m,null);
  const ok=a=>!a.dq;
  const rides=pick(a=>a.g==='ride'&&a.sp!=='Virtual Ride'&&ok(a)),runs=pick(a=>a.g==='run'&&ok(a)),swims=pick(a=>a.g==='swim'&&ok(a)),all=pick(ok);
  const mars=list.filter(a=>a.mar&&a.mv);const fm=mars.reduce((m,a)=>!m||a.mv<m.mv?a:m,null);
  const R=[['Giro in bici più lungo',best(rides,'km'),a=>fmt(a.km,1)+' km'],['Corsa più lunga',best(runs,'km'),a=>fmt(a.km,1)+' km'],['Più dislivello in un giorno',best(all,'up'),a=>fmt(a.up)+' m'],
    ['Più ore in movimento',best(all,'mv'),a=>hm(a.mv)],['Maratona più veloce (tempo in movimento)',fm,a=>hms(a.mv)],['Nuotata più lunga',best(swims,'km'),a=>fmt(a.km,2)+' km'],
    ['Più calorie',best(all,'cal'),a=>fmt(a.cal)+' kcal'],['Bici: media più alta (> 80 km)',best(rides.filter(a=>a.km>80),'kmh'),a=>fmt(a.kmh,1)+' km/h'],['Più foto in un\'uscita',best(all.map(a=>({...a,np:(a.ph||[]).length})),'np'),a=>a.np+' foto']];
  $('#p-record').innerHTML=R.filter(r=>r[1]).map(([l,a,f])=>`<button data-id="${a.id}"><div class="l">${l}</div><div class="v">${f(a)}</div><div class="n">${esc(a.n)} · ${dshort(a.d)}</div></button>`).join('')+
    `<p class="hint" style="grid-column:1/-1">I record escludono le attività con dati da controllare (vedi in fondo). Filtri attivi: ${ST.sport==='all'?'tutti gli sport':GROUPS[ST.sport].l}${ST.q?', «'+esc(ST.q)+'»':''}.</p>`;
  // lunghe (rispetta l'anno)
  const top=(arr,n=12)=>[...arr].sort((a,b)=>b.km-a.km).slice(0,n);
  const yr=a=>ST.year==='all'||a.y===ST.year;
  const tr=top(rides.filter(yr)),tn=top(runs.filter(yr));
  $('#p-lunghe').innerHTML=tile('bici',tr[0]?fmt(tr[0].km,1):'–','km la più lunga',`<ul class="acts">${tr.map(actLi).join('')}</ul>`,'',false).replace('class="tile ','class="tile block ')+
    tile('corsa',tn[0]?fmt(tn[0].km,1):'–','km la più lunga',`<ul class="acts">${tn.map(actLi).join('')}</ul>`,'',false).replace('class="tile ','class="tile block ');
  // maratone
  const M=[...list.filter(a=>a.mar)].sort((a,b)=>a.d<b.d?-1:1);
  const MD=list.filter(a=>a.mard&&!a.mar).sort((a,b)=>a.d<b.d?1:-1);
  const tv=a=>a.mar.official_s||a.mv;
  $('#p-maratone').innerHTML=(M.length?tile('le maratone ufficiali',M.length,'gare da 42,195 km',dots(M.map(a=>({id:a.id,v:tv(a),l:a.mar.event,s:a.mar.city.slice(0,5)})),{fmtV:v=>hms(v),avgLabel:'media'}),'tempo ufficiale quando c\'è (marathons/data/races.json), altrimenti tempo in movimento · più in basso = più veloce',true):'')+
    `<div class="tile block"><span class="t-title">Maratone</span><ul class="acts">${[...M].reverse().map(a=>`<li data-id="${a.id}"><b>${esc(a.mar.event)}</b><em>${dshort(a.d)} · ${hms(tv(a))}${a.mar.official_s?' ufficiale':' in movimento'}</em></li>`).join('')}</ul></div>`+
    `<div class="tile block"><span class="t-title">Altre corse da 42 km</span><ul class="acts">${MD.map(actLi).join('')||'<li>–</li>'}</ul></div>`;
  // gare
  const G=list.filter(a=>a.race).sort((a,b)=>a.d<b.d?1:-1),gy=YEARS.map(y=>({k:y,l:y,s:"'"+y.slice(2),v:G.filter(a=>a.y===y).length}));
  $('#p-gare').innerHTML=tile('gare per anno',G.length,'gare riconosciute',bars(gy,{unit:'gare',color:'var(--s2)',onclick:1,avgLabel:'media annua'}),'gara = maratona ufficiale, flag «race» di Intervals o nome dell\'evento (es. Granfondo, Trail, Half Marathon): elenco approssimato',true)+
    `<div class="tile block wide"><span class="t-title">Tutte le gare</span><ul class="acts" style="columns:2 320px;column-gap:24px">${G.filter(yr).map(actLi).join('')}</ul></div>`;
  // cicloviaggi
  const T=D.trips.filter(t=>t.n);const tc=[...T].reverse().map(t=>({k:t.id,l:t.start,s:t.start.slice(2,7).replace('-','/'),v:t.km}));
  $('#p-viaggi-chart').innerHTML=tile('cicloviaggi',T.length,'viaggi in bici di più giorni',bars(tc,{unit:'km',color:'var(--s3)',dec:0,avgLabel:'media per viaggio'}),'giorni consecutivi con uscite in bici lunghe e lontano da casa (stessa regola di activities.json)',true);
  $('#p-viaggi').innerHTML=T.map(t=>`<button class="trip" data-trip="${t.id}"><div class="ph" style="${t.cv?`background-image:url(data/photos/t/${t.cv}.jpg)`:''}"></div><div class="tx"><b>${esc(tripName(t))}</b><span>${dshort(t.start)} → ${dshort(t.end)} · ${t.days} giorni · ${fmt(t.km)} km · ${fmt(t.up)} m D+</span></div></button>`).join('');
  // qualità
  const Q=A.filter(a=>a.dq).sort((a,b)=>a.d<b.d?1:-1);
  $('#p-qualita').innerHTML=`<div class="tile block wide"><span class="t-title">${Q.length} attività segnalate</span><ul class="acts">${Q.map(a=>`<li data-id="${a.id}"><b>${esc(a.n)} · ${dshort(a.d)}</b><em>${esc(a.dq.join(' · '))}</em></li>`).join('')}</ul></div>`;
  $('#foot').innerHTML=`Fonti: export Strava (${fmt(A.filter(a=>a.src==='strava').length)} attività) e Intervals.icu (${fmt(A.filter(a=>a.src!=='strava').length)} in più, non presenti su Strava).<br>${esc(D.note)}<br>Dati generati il ${esc(D.generated)}.`;}
function tripName(t){const n=(t.names||[]).find(n=>!/^(Morning|Afternoon|Lunch|Evening|Night) Ride$/.test(n));return n?(t.city?`${t.city} · `:'')+n.replace(/\s*\/\s*\d+$/,''):(t.city||'Cicloviaggio')+' '+t.start.slice(0,4)}
// ---------- dettaglio ----------
let dmap,cur=null;
function openDetail(id,push=true){const a=byId.get(id);if(!a)return;cur=a;
  const t=a.ct&&TRIPS.get(a.ct),tv=a.tv&&TRAV.get(a.tv);
  const kv=[['Distanza',a.km?fmt(a.km,2)+' km':'–'],['In movimento',hms(a.mv)],['Tempo totale',hms(a.el)],['Dislivello',a.up!=null?fmt(a.up)+' m':'–'],
    a.pace?['Passo',pace(a.pace)]:['Velocità media',a.kmh?fmt(a.kmh,1)+' km/h':'–'],['FC media',a.hr?a.hr+' bpm':'–'],['FC max',a.mhr?a.mhr+' bpm':'–'],['Potenza media',a.w?a.w+' W':'–'],['Calorie',a.cal?fmt(a.cal)+' kcal':'–'],['Attrezzatura',a.gear||'–']].filter(x=>x[1]!=='–'||['Distanza','In movimento'].includes(x[0]));
  const bd=[a.race?`<span class="race">Gara</span>`:'',a.mar?`<span class="mar">Maratona · ${esc(a.mar.event)}</span>`:'',a.mard&&!a.mar?`<span>42 km</span>`:'',t?`<button class="trip" data-trip="${t.id}">Cicloviaggio · ${esc(tripName(t))}</button>`:'',tv?`<span>Viaggio · ${esc(tv.city||'')}${tv.country?' ('+esc(tv.country)+')':''}</span>`:'',a.cm?'<span>Pendolarismo</span>':''].join('');
  const list=sel(),i=list.findIndex(x=>x.id===a.id);
  $('#sheet-in').innerHTML=`<button class="sheet-x" aria-label="Chiudi">×</button><div class="sheet-hd"><div class="when">${dlong(a.d)} · ${a.t} · ${esc(a.spi)}</div><h3>${esc(a.n||a.spi)}</h3></div>
   <div class="dbdg">${bd}</div>
   ${a.dq?`<div class="dq"><b>Dato da controllare:</b> ${esc(a.dq.join(' · '))}</div>`:''}
   ${a.trk?`<h4>Percorso</h4><div id="dmap"></div><p class="hint">Inizio e fine vicino a casa, al lavoro e ai luoghi di partenza abituali sono tagliati per privacy.</p>`:a.gps_iv?'<h4>Percorso</h4><p class="t-empty">Traccia GPS solo su Intervals: non ancora importata.</p>':''}
   <h4>Numeri</h4><div class="kv">${kv.map(([l,v])=>`<div><b>${v}</b><span>${l}</span></div>`).join('')}</div>
   ${a.ph?`<h4>Foto (${a.ph.length}${a.nv?` + ${a.nv} video non mostrati`:''})</h4><div class="gal">${a.ph.map((p,j)=>`<img decoding="async" src="data/photos/t/${p}.jpg" data-p="${p}" alt="foto ${j+1}">`).join('')}</div>`:''}
   ${a.ds?`<h4>Descrizione</h4><p class="desc">${esc(a.ds)}</p>`:''}
   ${t?`<h4>Le tappe del viaggio</h4><ul class="acts">${t.ids.map(x=>byId.get(x)).filter(Boolean).map(actLi).join('')}</ul>`:''}
   <p class="hint" style="text-align:left;margin-top:14px">Fonte: ${a.src==='strava'?'export Strava':'Intervals.icu ('+esc(a.src.replace('intervals_',''))+')'}${a.iv?' · Intervals '+esc(a.iv):''}</p>
   <div class="dnav"><button data-nav="${i>0?list[i-1].id:''}" ${i>0?'':'disabled'}>← più recente</button><button data-nav="${i>=0&&i<list.length-1?list[i+1].id:''}" ${i>=0&&i<list.length-1?'':'disabled'}>più vecchia →</button></div>`;
  $('#sheet').classList.add('on');document.body.style.overflow='hidden';$('#sheet').scrollTop=0;
  if(push)history.replaceState(null,'','#a='+a.id);
  if(a.trk&&window.L)loadYear(a.y).then(()=>{if(cur!==a)return;const segs=segsOf(a);if(!segs)return;if(dmap){dmap.remove();dmap=null}
    dmap=L.map('dmap',{scrollWheelZoom:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(dmap);
    dmap.fitBounds(L.latLngBounds(segs.flat()).pad(.08));
    const g=L.featureGroup(segs.map(s=>L.polyline(s,{color:GROUPS[a.g].hex,weight:4,opacity:.9}))).addTo(dmap);
    segs.forEach(s=>{L.circleMarker(s[0],{radius:4,color:'#202124',fillColor:'#34a853',fillOpacity:1,weight:2}).addTo(dmap)});
    const last=segs[segs.length-1];L.circleMarker(last[last.length-1],{radius:4,color:'#202124',fillColor:'#ea4335',fillOpacity:1,weight:2}).addTo(dmap);
    setTimeout(()=>dmap&&dmap.invalidateSize(),60)})}
function closeDetail(){$('#sheet').classList.remove('on');document.body.style.overflow='';history.replaceState(null,'',location.pathname+location.search);if(dmap){dmap.remove();dmap=null}}
$('#sheet').addEventListener('click',e=>{if(e.target.id==='sheet'||e.target.closest('.sheet-x'))return closeDetail();
  const n=e.target.closest('[data-nav]');if(n&&n.dataset.nav)return openDetail(n.dataset.nav);
  const im=e.target.closest('.gal img');if(im){const p=im.dataset.p;$('#lb-img').src=`data/photos/t/${p}.jpg`;$('#lb').classList.add('on');return}
  const li=e.target.closest('[data-id]');if(li)return openDetail(li.dataset.id);
  const tr=e.target.closest('[data-trip]');if(tr)openTrip(tr.dataset.trip)});
$('#lb').addEventListener('click',()=>$('#lb').classList.remove('on'));
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if($('#lb').classList.contains('on'))$('#lb').classList.remove('on');else closeDetail()}
  if($('#sheet').classList.contains('on')&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){const b=document.querySelectorAll('[data-nav]')[e.key==='ArrowLeft'?0:1];b&&b.dataset.nav&&openDetail(b.dataset.nav)}});
function openTrip(id){const t=TRIPS.get(id);if(!t)return;closeDetail();ST.q='';$('#q').value='';ST.year=t.start.slice(0,4);ST.sport='ride';
  ST.view='mappa';render();ST.q='';const list=t.ids.map(x=>byId.get(x)).filter(Boolean);setView('mappa',list);window.scrollTo({top:$('#controls').offsetTop,behavior:'smooth'})}
document.addEventListener('click',e=>{if(e.target.closest('#sheet'))return;
  const c=e.target.closest('[data-id]');if(c&&!e.target.closest('svg rect[data-k]')){openDetail(c.dataset.id);return}
  const k=e.target.closest('rect[data-k]');if(k&&/^\d{4}$/.test(k.dataset.k)){setYear(ST.year===k.dataset.k?'all':k.dataset.k);return}
  const tr=e.target.closest('[data-trip]');if(tr){openTrip(tr.dataset.trip);return}
  const s=e.target.closest('#sports button');if(s){ST.sport=s.dataset.s;document.querySelectorAll('#sports button').forEach(b=>b.setAttribute('aria-pressed',b===s));render();return}
  const v=e.target.closest('#views button');if(v){setView(v.dataset.v);return}});
function setView(v,custom){ST.view=v;document.querySelectorAll('#views button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===v));
  ['foto','mappa','elenco'].forEach(x=>$('#v-'+x).hidden=x!==v);const list=custom||sel();
  if(v==='foto')renderFoto(list);if(v==='mappa')renderMappa(list);if(v==='elenco')renderElenco(list);rail()}
let qt;$('#q').addEventListener('input',e=>{clearTimeout(qt);qt=setTimeout(()=>{ST.q=e.target.value;render()},180)});
function render(){const list=sel();totals(list);yearbar();ysum(list);setView(ST.view);sections()}
render();
const m=location.hash.match(/a=([\w-]+)/);if(m)openDetail(m[1],false);
window.VXAPP={openDetail,setView,setYear,ST,render};
})();

// altezza reale della barra sticky (su mobile va a capo)
(()=>{const f=()=>{const c=document.getElementById('controls');if(c)document.documentElement.style.setProperty('--bar-h',c.offsetHeight+'px')};f();addEventListener('resize',f);addEventListener('load',f)})();
