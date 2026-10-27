export const MARATHON = 42195;
export const CHECKPOINTS = [5000,10000,21097.5,30000,35000,40000];
export const number = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v)) ? Number(v) : null;
export function classify(a, overrides = {allow:{},deny:{}}) {
  const ids = [a.id,a.strava_id,a.intervals_id].filter(Boolean).map(String);
  const denied = ids.find(id=>overrides.deny[id]);
  if (denied) return {include:false,reason:overrides.deny[denied]};
  if ((a.sport_type || a.type) !== 'Run') return {include:false,reason:'Not a Run'};
  if (!(number(a.distance)>=41800 && number(a.distance)<=43000)) return {include:false,reason:'Outside 41.8–43.0 km'};
  if (!(number(a.elapsed_time)>0) || a.completed===false) return {include:false,reason:'No completed elapsed duration'};
  const allowed=ids.find(id=>overrides.allow[id]?.reason);
  if (allowed) return {include:true,reason:overrides.allow[allowed].reason,metadata:overrides.allow[allowed]};
  if (String(a.workout_type)==='1' || a.race===true || a.icu_race===true || String(a.category).toUpperCase()==='RACE' || String(a.sub_type).toUpperCase()==='RACE') return {include:true,reason:'Provider race flag'};
  if (a.race_metadata?.event && a.race_metadata?.completed===true) return {include:true,reason:'Explicit completed race metadata'};
  return {include:false,reason:'No verified race evidence; review manually'};
}
export function decodePolyline(encoded) {
  const points=[];let i=0,lat=0,lng=0;
  while(i<encoded.length){const values=[];for(let j=0;j<2;j++){let shift=0,result=0,b;do{if(i>=encoded.length||shift>30)return [];b=encoded.charCodeAt(i++)-63;if(b<0||b>63)return [];result|=(b&31)<<shift;shift+=5;}while(b>=32);values.push(result&1?~(result>>1):result>>1);}lat+=values[0];lng+=values[1];points.push([lat/1e5,lng/1e5]);}
  return points;
}
export function normalizeStreams(raw={}) {
  const streams=Array.isArray(raw)?Object.fromEntries(raw.map(s=>[s.type,s.type==='latlng'&&s.data2?s.data.map((lat,i)=>[lat,s.data2[i]]):s.data])):Object.fromEntries(Object.entries(raw).map(([k,v])=>[k,Array.isArray(v)?v:v?.data]));
  const distance=streams.distance||[],time=streams.time||[];
  const points=[];let previousD=-1,previousT=-1;
  for(let i=0;i<distance.length;i++){
    const d=number(distance[i]),t=number(time[i]);
    if(d===null||t===null||d<0||t<0||d<previousD||t<previousT)continue;
    const velocity=number((streams.velocity_smooth||streams.velocity||[])[i]);
    const p={d,t,pace:velocity>0?1000/velocity:null,altitude:number(streams.altitude?.[i]),hr:number(streams.heartrate?.[i]),cadence:number(streams.cadence?.[i])};
    // At a stopped GPS distance keep the latest elapsed timestamp, including the stop.
    if(d===previousD)points[points.length-1]=p;else points.push(p);
    previousD=d;previousT=t;
  }
  const route=(streams.latlng||[]).filter(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180);
  return {points,route};
}
export function atDistance(points,d,key='t') {
  if(!points?.length||d<points[0].d||d>points.at(-1).d)return null;
  let lo=0,hi=points.length-1;
  while(lo<hi){const mid=(lo+hi)>>1;if(points[mid].d<d)lo=mid+1;else hi=mid;}
  const b=points[lo];if(b.d===d)return number(b[key]);
  const a=points[lo-1];if(!a||b.d-a.d>1000)return null;
  const av=number(a[key]),bv=number(b[key]);return av===null||bv===null?null:av+(bv-av)*(d-a.d)/(b.d-a.d);
}
export function rollingPace(points,d) {
  if(d<5000||d>MARATHON)return null;
  const end=atDistance(points,d),start=atDistance(points,d-5000);
  if(end===null||start===null)return null;
  // An unobserved gap within the window must not silently become a smooth estimate.
  for(let i=1;i<points.length;i++)if(points[i].d>d-5000&&points[i-1].d<d&&points[i].d-points[i-1].d>1000)return null;
  return (end-start)/5;
}
export function lateFade(points) {
  const early=windowPace(points,5000,25000),late=windowPace(points,30000,40000);
  return early===null||late===null?null:late-early;
}
export function paceStability(points) {
  const splits=[];
  for(let d=5000;d<40000;d+=1000){
    const p=windowPace(points,d,d+1000);
    if(p!==null&&p>=150&&p<=500)splits.push(p);
  }
  if(splits.length<20)return null;
  const median=a=>{const s=[...a].sort((x,y)=>x-y),m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2};
  const med=median(splits);
  return median(splits.map(v=>Math.abs(v-med)));
}
export function meanAtDistance(points,start,end,key='hr',step=250) {
  const vals=[];
  for(let d=start;d<=end;d+=step){const v=atDistance(points,d,key);if(v!==null)vals.push(v);}
  return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
}
export function hrDrift(points) {
  const early=meanAtDistance(points,5000,25000,'hr'),late=meanAtDistance(points,30000,40000,'hr');
  return early===null||late===null?null:late-early;
}
export function windowPace(points, start, end) {
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) return null;
  const a = atDistance(points,start), b = atDistance(points,end);
  if (a === null || b === null) return null;
  // Do not bridge missing sections even when both window endpoints exist.
  if (points.some((p,i)=>i && p.d>start && points[i-1].d<end && p.d-points[i-1].d>1000)) return null;
  return (b-a)/((end-start)/1000);
}
export function pace5k(points,d) { return windowPace(points,Math.max(0,d-5000),d); }
export function after30k(points) {
  const early=windowPace(points,0,30000),late=windowPace(points,30000,MARATHON);
  return early===null||late===null?null:late-early;
}
export function halves(points){const start=atDistance(points,0),half=atDistance(points,MARATHON/2),end=atDistance(points,MARATHON);return {first:half!==null&&start!==null?half-start:null,second:end!==null&&half!==null?end-half:null,delta:start!==null&&half!==null&&end!==null?end-2*half+start:null};}
export function gapAt(a,b,d){const x=atDistance(a.points,d),y=atDistance(b.points,d);return x===null||y===null?null:x-y;}
export function normalizeRace(a,raw,decision,source){
  const {points,route}=normalizeStreams(raw);const summary=a.map?.summary_polyline||a.map?.polyline||'';
  const course=route.length?route:decodePolyline(summary);
  const distance=number(a.distance),elapsed=number(a.elapsed_time);
  return {id:String(a.strava_id||a.id),providerId:String(a.id),name:decision.metadata?.name||String(a.name||'Unnamed race').replace(/[^\p{L}\p{N}\s\-.,()]/gu,'').trim(),event:decision.metadata?.event||a.name,city:decision.metadata?.city||a.location_city||null,date:String(a.start_date_local||a.start_date||'').slice(0,10),distance,elapsed,officialTime:decision.metadata?.officialTime??null,avgPace:elapsed&&distance?elapsed/(distance/1000):null,elevation:number(a.total_elevation_gain),avgHr:number(a.average_heartrate),maxHr:number(a.max_heartrate),cadence:number(a.average_cadence),points,route:course,routeSource:route.length?'GPS stream':course.length?'Strava summary polyline':null,split:halves(points),evidence:decision.reason,source,gaps:[...(!points.length?['Distance streams unavailable']:[]),...(!course.length?['Course unavailable']:[])]};
}

// Non-overlapping distance bins; HR is a time-weighted trapezoidal mean.
// Missing endpoints or >1 km recording gaps stay unavailable.
export function fiveKmMeans(points) {
 return Array.from({length:9},(_,i)=>{
  const start=i*5000,end=Math.min(start+5000,MARATHON);
  const pace=windowPace(points,start,end);
  const a=atDistance(points,start),b=atDistance(points,end);
  let integral=0,duration=0,valid=a!==null&&b!==null;
  for(let j=1;j<points.length;j++){
   const left=points[j-1],right=points[j];
   const lo=Math.max(start,left.d),hi=Math.min(end,right.d);
   if(hi<=lo)continue;
   if(right.d-left.d>1000||left.hr==null||right.hr==null){valid=false;continue;}
   const t0=atDistance(points,lo),t1=atDistance(points,hi);
   const h0=atDistance(points,lo,'hr'),h1=atDistance(points,hi,'hr');
   if([t0,t1,h0,h1].some(v=>v===null)){valid=false;continue;}
   const dt=t1-t0;integral+=(h0+h1)/2*dt;duration+=dt;
  }
  return {start,end,pace,hr:valid&&duration>0?integral/duration:null};
 });
}
