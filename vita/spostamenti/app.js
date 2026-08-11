const IT = new Intl.NumberFormat("it-IT");
const shortDate = new Intl.DateTimeFormat("it-IT", { day:"numeric", month:"short", year:"numeric" });
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let DATA, WORLD, projection, path, globeSvg, land, activeTrip, observer;
let navLockUntil = 0;
const prefersReduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

Promise.all([
  fetch("data/travel.json?v=20260811b").then(r => r.json()),
  fetch("data/countries-110m.json?v=20260811b").then(r => r.json())
]).then(([data, world]) => {
  DATA = data; WORLD = world;
  renderTotals(); renderTrips(); renderYearRail(); renderHeatmap(); renderBars();
  initGlobe(); observeTrips();
  const linked = location.hash ? document.getElementById(location.hash.slice(1)) : null;
  if(linked) navLockUntil = Date.now() + 1600;
  activate(linked || document.querySelector(".trip:not([hidden])"));
  if(linked) linked.scrollIntoView({block:"center"});
}).catch(err => {
  console.error(err);
  $("#map-place").textContent = "Dati non disponibili";
});

function renderTotals(){
  const t = DATA.totals;
  const items = [
    [IT.format(t.trips),"viaggi riconosciuti"], [IT.format(t.countries),"paesi esteri"],
    [IT.format(t.flightLegs),"tratte aeree"], [IT.format(t.flightKm),"km in volo"],
    [t.transportCo2T.toLocaleString("it-IT",{minimumFractionDigits:1,maximumFractionDigits:1})+" t","CO₂e voli + auto"],
    [IT.format(t.cities),"luoghi distinti"]
  ];
  $("#totals").innerHTML = items.map(([n,l]) => `<div class="total"><b>${n}</b><span>${l}</span></div>`).join("");
  $("#source-note").textContent = `Copertura Timeline: ${date(DATA.meta.from)} → ${date(DATA.meta.to)} · ${DATA.meta.privacy}`;
  $("#half-total").textContent = IT.format(t.halfMarathons);
  $("#car-total").textContent = IT.format(t.carKm);
  $("#car-co2-total").textContent = t.carCo2T.toLocaleString("it-IT",{minimumFractionDigits:1,maximumFractionDigits:1});
  $("#sorsi-total").textContent = IT.format(t.sorsi);
  $("#co2-source").href = DATA.method.co2Source;
}

function date(s){ return shortDate.format(new Date(s + "T12:00:00")); }
function spanDate(t){ return t.start === t.end ? date(t.start) : `${date(t.start)} — ${date(t.end)}`; }

function renderTrips(){
  $("#trip-list").innerHTML = DATA.trips.map((t,i) => {
    const places = (t.places || []).slice(0,8);
    const numbers = t.mode === "volo"
      ? `<div><b>${IT.format(t.flightKm)} km</b><span>in volo osservati</span></div><div><b>${IT.format(t.co2Kg)} kg</b><span>CO₂e stimata</span></div>`
      : `<div><b>${IT.format(t.distanceFromHomeKm)} km</b><span>raggio del viaggio</span></div>`;
    const placeList = places.length ? `<div class="trip-places"><b>Luoghi osservati</b><ul>${places.map(p => `<li><span>${escapeHtml(p.city)}</span><small>${escapeHtml(p.country)}${p.visits ? ` · ${IT.format(p.visits)} ${p.visits===1?"visita":"visite"}` : ""}</small></li>`).join("")}</ul></div>` : "";
    return `<article class="trip" id="trip-${t.id}" data-trip-id="${escapeHtml(t.id)}" data-i="${i}" data-mode="${t.mode}" data-year="${t.year}" tabindex="-1">
      <div class="trip-top"><span class="trip-year">${t.year}</span><span class="trip-mode">${t.mode}</span></div>
      <h3>${escapeHtml(t.city)}</h3><div class="trip-country">${escapeHtml(t.country)}</div>
      <p class="trip-date">${spanDate(t)}</p>
      ${placeList}
      <div class="trip-numbers">${numbers}</div>
    </article>`;
  }).join("");
  $$(".filters button").forEach(b => b.addEventListener("click", () => {
    setFilter(b.dataset.filter);
  }));
}

function setFilter(filter){
  $$(".filters button").forEach(x => x.classList.toggle("active", x.dataset.filter === filter));
  $$(".trip").forEach(card => card.hidden = filter !== "tutti" && card.dataset.mode !== filter);
  observeTrips();
}

function goToTrip(id){
  setFilter("tutti");
  const card = $$(".trip").find(x => x.dataset.tripId === id);
  if(!card) return;
  navLockUntil = Date.now() + 1600;
  history.replaceState(null,"",`#${card.id}`);
  activate(card);
  card.focus({preventScroll:true});
  card.scrollIntoView({behavior:prefersReduced?"auto":"smooth",block:"center"});
}

function renderYearRail(){
  const years = [...new Set(DATA.trips.map(t => t.year))].sort((a,b) => b-a);
  $("#year-rail").insertAdjacentHTML("beforeend", years.map(y => `<button data-year="${y}" aria-label="Vai al ${y}">${y}</button>`).join(""));
  $$("#year-rail button").forEach(b => b.addEventListener("click", () => {
    const card = document.querySelector(`.trip[data-year="${b.dataset.year}"]:not([hidden])`);
    if(card) card.scrollIntoView({behavior:prefersReduced?"auto":"smooth",block:"center"});
  }));
}

function observeTrips(){
  if(observer) observer.disconnect();
  observer = new IntersectionObserver(entries => {
    if(Date.now() < navLockUntil) return;
    const visible = entries.filter(e => e.isIntersecting).sort((a,b) => b.intersectionRatio-a.intersectionRatio)[0];
    if(visible) activate(visible.target);
  }, {rootMargin:"-32% 0px -46% 0px",threshold:[0,.15,.4,.7]});
  $$(".trip:not([hidden])").forEach(x => observer.observe(x));
}

function activate(card){
  if(!card || !DATA) return;
  $$(".trip").forEach(x => x.classList.toggle("active",x===card));
  activeTrip = DATA.trips[+card.dataset.i];
  $("#map-place").textContent = activeTrip.city;
  $("#map-date").textContent = spanDate(activeTrip);
  $$("#year-rail button").forEach(x => x.classList.toggle("active",+x.dataset.year===activeTrip.year));
  drawGlobe(activeTrip);
}

function initGlobe(){
  globeSvg = d3.select("#globe"); land = topojson.feature(WORLD, WORLD.objects.countries);
  const resize = () => {
    const node = globeSvg.node(), box = node.getBoundingClientRect();
    const w = Math.max(280,box.width), h = Math.max(280,box.height);
    globeSvg.attr("viewBox",`0 0 ${w} ${h}`);
    projection = d3.geoOrthographic().translate([w/2,h/2]).scale(Math.min(w,h)*.43).clipAngle(90).precision(.5);
    path = d3.geoPath(projection); drawGlobe(activeTrip || DATA.trips[0], true);
  };
  new ResizeObserver(resize).observe(globeSvg.node()); resize();
}

function arcLine(a,b){
  const interp = d3.geoInterpolate(a,b), n=50;
  return {type:"LineString",coordinates:d3.range(n+1).map(i=>interp(i/n))};
}

function drawGlobe(trip, immediate=false){
  if(!projection || !trip) return;
  const target = [-trip.lon,-trip.lat,0], start = projection.rotate();
  const duration = immediate || prefersReduced ? 0 : 700;
  const render = rot => {
    projection.rotate(rot); globeSvg.selectAll("*").remove();
    globeSvg.append("path").datum({type:"Sphere"}).attr("class","sphere").attr("d",path);
    globeSvg.append("path").datum(d3.geoGraticule10()).attr("class","graticule").attr("d",path);
    globeSvg.append("path").datum(land).attr("class","land").attr("d",path);
    drawLocationHeat();
    trip.routes.forEach(r => globeSvg.append("path").datum(arcLine(r.a,r.b))
      .attr("class",`route-path ${trip.mode==="terra"?"land-route":""}`).attr("d",path));
    (trip.places || []).forEach(p => {
      if(!visibleOnGlobe([p.lon,p.lat])) return;
      const pp=projection([p.lon,p.lat]);
      globeSvg.append("circle").attr("class","trip-place-point")
        .attr("cx",pp[0]).attr("cy",pp[1]).attr("r",3.5)
        .append("title").text(`${p.city} · ${p.country}`);
    });
    const hp=projection([9.67,45.70]), cp=projection([trip.lon,trip.lat]);
    if(hp) globeSvg.append("circle").attr("class","home-point").attr("cx",hp[0]).attr("cy",hp[1]).attr("r",3.2);
    if(cp) globeSvg.append("circle").attr("class","city-point").attr("cx",cp[0]).attr("cy",cp[1]).attr("r",5);
  };
  if(!duration){render(target);return;}
  d3.select({}).transition().duration(duration).ease(d3.easeCubicInOut).tween("rotate",()=>{
    const r=d3.interpolate(start,target); return t=>render(r(t));
  });
}

function visibleOnGlobe(point){
  const rot=projection.rotate(), center=[-rot[0],-rot[1]];
  return d3.geoDistance(point,center) < Math.PI/2;
}

function drawLocationHeat(){
  const max=d3.max(DATA.heatmap,d=>d.trips) || 1;
  const radius=d3.scaleSqrt().domain([1,max]).range([3.8,10]);
  DATA.heatmap.forEach(h => {
    if(!visibleOnGlobe([h.lon,h.lat])) return;
    const pp=projection([h.lon,h.lat]), r=radius(h.trips);
    const g=globeSvg.append("g").datum(h).attr("class","heat-location")
      .attr("transform",`translate(${pp[0]},${pp[1]})`).attr("role","button")
      .attr("tabindex",0).attr("aria-label",`${h.city}, ${h.trips} viaggi. Vai al viaggio più recente.`)
      .on("click",()=>goToTrip(h.latestTripId))
      .on("keydown",event=>{if(event.key==="Enter" || event.key===" "){event.preventDefault();goToTrip(h.latestTripId)}});
    g.append("circle").attr("class","heat-halo").attr("r",r*2.1);
    g.append("circle").attr("class","heat-dot").attr("r",r);
    g.append("title").text(`${h.city} · ${h.country} · ${h.trips} ${h.trips===1?"viaggio":"viaggi"} · clicca per aprire`);
  });
}

function renderHeatmap(){
  const rows = new Map();
  DATA.halfMarathons.monthly.forEach(x => {
    const [y,m]=x.month.split("-").map(Number); if(!rows.has(y)) rows.set(y,Array(12).fill(0)); rows.get(y)[m-1]=x.count;
  });
  const months=["g","f","m","a","m","g","l","a","s","o","n","d"];
  $("#half-heatmap").innerHTML = `<table class="heatmap"><thead><tr><th></th>${months.map(x=>`<th>${x}</th>`).join("")}</tr></thead><tbody>${[...rows].map(([y,v])=>`<tr><td>${y}</td>${v.map((n,m)=>`<td class="heat-cell ${n>=5?"hot":""}" data-v="${Math.min(n,4)}" title="${monthName(m)} ${y}: ${n}">${n||""}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function monthName(i){return ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"][i]}
function renderBars(){
  bars("#car-bars",DATA.carByYear,"km");
  bars("#sorsi-bars",DATA.specialPlaces[0].years,"count");
}
function bars(sel,rows,key){
  const max=Math.max(...rows.map(x=>x[key]));
  $(sel).innerHTML=rows.map(x=>`<div class="year-bar" title="${x.year}: ${IT.format(x[key])}"><i style="height:${Math.max(2,x[key]/max*100)}%"></i><span>${String(x.year).slice(2)}</span></div>`).join("");
}
function escapeHtml(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
