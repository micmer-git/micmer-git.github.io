import React,{useMemo,useRef,useState,useEffect,useId} from 'react';
import {atDistance,fiveKmMeans,MARATHON} from './lib/races.mjs';
import {meanDomain,metresPerBeat,axisTicks} from './lib/charts.mjs';
import type {Race} from './v2-types';
export type Metric='pace'|'hr'|'relationship';
export const raceColors=['#a64e36','#526c78','#997427','#677348','#6b647e','#ad583e','#7d6a51','#356b60','#385e94'];
export const formatPace=(n:number|null)=>n==null?'—':Math.floor(Math.round(n)/60)+':'+String(Math.round(n)%60).padStart(2,'0');
const sampleDistances=[...Array.from({length:169},(_,i)=>i*250),MARATHON];
const finite=(v:number|null):v is number=>v!==null&&Number.isFinite(v);
const activeBin=(start:number,end:number,d:number)=>d>=start&&(d<end||end===MARATHON);
type Props={races:Race[];allRaces:Race[];selected:string;distance:number;setDistance:(d:number)=>void;metric?:Metric;dual?:boolean;focus:boolean;raw:boolean};
export function EffortChart({races,allRaces,selected,distance,setDistance,metric='pace',dual=false,focus,raw}:Props){
 const ref=useRef<SVGSVGElement>(null),[width,setWidth]=useState(360),id=useId().replace(/:/g,'');
 useEffect(()=>{const observer=new ResizeObserver(()=>setWidth(ref.current?.getBoundingClientRect().width||360));if(ref.current)observer.observe(ref.current);return()=>observer.disconnect()},[]);
 const bins=useMemo(()=>races.map(race=>({race,means:fiveKmMeans(race.points)})),[races]);
 const selectedRace=allRaces.find(r=>r.id===selected)||races[0];
 const [paceRange,hrRange]=useMemo(()=>{const scale=focus?[selectedRace]:allRaces;return [meanDomain(scale,'pace'),meanDomain(scale,'hr')]},[focus,selectedRace,allRaces]);
 const left=42,right=dual?42:16,top=38,bottom=260,plotW=Math.max(1,width-left-right);
 const X=(d:number)=>left+d/MARATHON*plotW;
 const Y=(v:number,key:'pace'|'hr')=>{const [lo,hi]=key==='pace'?paceRange:hrRange;const frac=(v-lo)/(hi-lo);return key==='pace'?top+frac*(bottom-top):bottom-frac*(bottom-top)};
 const fmt=(v:number,key:'pace'|'hr')=>key==='pace'?formatPace(v):Math.round(v).toString();
 const ordered=[...bins].sort((a,b)=>Number(a.race.id===selected)-Number(b.race.id===selected));
 const keys:('pace'|'hr')[]=dual?['pace','hr']:[metric==='hr'?'hr':'pace'];
 const color=(race:Race,key:'pace'|'hr')=>dual?(key==='pace'?'#385e94':'#a64e36'):raceColors[allRaces.findIndex(r=>r.id===race.id)%raceColors.length];
 const path=(race:Race,key:'pace'|'hr')=>{let pen=false;return sampleDistances.map(d=>{const v=atDistance(race.points,d,key);if(!finite(v)){pen=false;return ''}const cmd=pen?'L':'M';pen=true;return `${cmd}${X(d)},${Y(v,key)}`}).join(' ')};
 const change=(e:React.PointerEvent<SVGSVGElement>)=>{const box=e.currentTarget.getBoundingClientRect();setDistance(Math.max(0,Math.min(MARATHON,(e.clientX-box.left-left)/plotW*MARATHON)))};
 const labels:{x:number;y:number;value:string;color:string}[]=[];
 for(const key of keys){const row=bins.find(b=>b.race.id===selected);row?.means.forEach((b,i)=>{const v=b[key];if(!finite(v))return;const x=(X(b.start)+X(b.end))/2;let y=Y(v,key)+(key==='hr'?16:-9);if(i===8)y=Y(v,key)+16;y=Math.max(top-12,Math.min(bottom+18,y));if(labels.some(l=>Math.abs(l.x-x)<27&&Math.abs(l.y-y)<13))y=Y(v,key)-18;labels.push({x,y,value:fmt(v,key),color:color(row.race,key)})})}
 return <div className="effort-visual"><div className="axis-heading"><span style={{color:dual?'#385e94':undefined}}>{metric==='hr'&&!dual?'BPM':'Pace · /km'}{dual?' · solid':''}</span>{dual?<span style={{color:'#a64e36'}}>BPM · dashed</span>:<span>5 km means</span>}</div>
 <svg className="effort-chart" ref={ref} viewBox={`0 0 ${width} 300`} role="img" aria-label={dual?'Pace and heart rate with separate axes':metric==='hr'?'Heart rate comparison':'Pace comparison'} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);change(e)}} onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))change(e)}}>
 <defs><clipPath id={id}><rect x={left} y={top-2} width={plotW} height={bottom-top+4}/></clipPath></defs>
 {[0,10000,20000,30000,40000].map(d=><g key={d}><line x1={X(d)} x2={X(d)} y1={top} y2={bottom} className="gridline"/><text x={X(d)} y="289" textAnchor="middle">{d/1000}</text></g>)}
 {keys.map((key,k)=>{const range=key==='pace'?paceRange:hrRange;return axisTicks(range,key).map(v=><g key={key+v}><text x={k===1?width-right+7:left-7} y={Y(v,key)+3} textAnchor={k===1?'start':'end'} style={{fill:dual?color(races[0],key):undefined}}>{fmt(v,key)}</text>{k===0&&<line x1={left} x2={width-right} y1={Y(v,key)} y2={Y(v,key)} className="gridline"/>}</g>)})}
 <g clipPath={`url(#${id})`}>{raw&&ordered.map(({race})=>keys.map(key=><path key={race.id+key} data-raw-trace={key} d={path(race,key)} fill="none" stroke={color(race,key)} opacity={race.id===selected ? .18 : .045} strokeWidth="1.1"/>))}
 {ordered.map(({race,means})=><g key={race.id} data-race-line={race.id}>{keys.map(key=>means.map((b,i)=>{const v=b[key];if(!finite(v))return null;const isSelected=race.id===selected;return <line key={key+i} data-mean-segment={key} x1={X(b.start)+1.5} x2={X(b.end)-1.5} y1={Y(v,key)} y2={Y(v,key)} stroke={color(race,key)} strokeWidth={isSelected?2.8:1.2} strokeDasharray={dual&&key==='hr'?'5 3':undefined} opacity={isSelected?1:.28}><title>{race.city}: {b.start/1000}–{b.end/1000} km, {fmt(v,key)} {key==='hr'?'bpm':'/km'}</title></line>}))}</g>)}
 </g>
 {labels.map((l,i)=><text key={i} className="mean-value" x={l.x} y={l.y} textAnchor="middle" style={{fill:l.color}}>{l.value}</text>)}
 <line x1={X(distance)} x2={X(distance)} y1={top-8} y2={bottom+4} className="crosshair"/>
 {!bins.some(b=>b.means.some(v=>keys.some(key=>finite(v[key]))))&&<text x={width/2} y="150" textAnchor="middle">Recording unavailable</text>}
 </svg><p className="chart-note">Distance · km. {focus?'Scale focused on selected race; other traces may be clipped.':'Shared scales across all races.'} {raw?'Faint recordings behind 5 km means; spikes outside the scale are clipped.':''}{dual?' Axes are independent; crossings do not imply equal values.':''}</p></div>;
}
export function RelationshipChart({races,allRaces,selected,distance,setDistance,focus,raw}:Props){
 const ref=useRef<SVGSVGElement>(null),[width,setWidth]=useState(360),id=useId().replace(/:/g,'');
 useEffect(()=>{const ro=new ResizeObserver(()=>setWidth(ref.current?.getBoundingClientRect().width||360));if(ref.current)ro.observe(ref.current);return()=>ro.disconnect()},[]);
 const rows=useMemo(()=>races.map(race=>({race,bins:fiveKmMeans(race.points)})),[races]);
 const [[p0,p1],[h0,h1]]=useMemo(()=>{const scale=focus?races.filter(r=>r.id===selected):allRaces;return [meanDomain(scale,'pace'),meanDomain(scale,'hr')]},[focus,selected,races,allRaces]);
 const X=(h:number)=>46+(h-h0)/(h1-h0)*(width-68),Y=(p:number)=>28+(p-p0)/(p1-p0)*224;
 const active=rows.find(r=>r.race.id===selected)?.bins.find(b=>activeBin(b.start,b.end,distance));
 return <div className="effort-visual"><div className="axis-heading"><span>Pace · /km ↑ faster</span><span>One dot = one 5 km segment</span></div><svg className="effort-chart relation-chart" ref={ref} viewBox={`0 0 ${width} 300`} role="group" aria-label="Pace versus heart rate by 5 km segment">
 <defs><clipPath id={id}><rect x="44" y="26" width={width-64} height="228"/></clipPath></defs>
 {axisTicks([h0,h1],'hr').map(v=><g key={'h'+v}><line x1={X(v)} x2={X(v)} y1="28" y2="252" className="gridline"/><text x={X(v)} y="272" textAnchor="middle">{v}</text></g>)}
 {axisTicks([p0,p1],'pace').map(v=><g key={'p'+v}><line x1="46" x2={width-22} y1={Y(v)} y2={Y(v)} className="gridline"/><text x="39" y={Y(v)+4} textAnchor="end">{formatPace(v)}</text></g>)}
 <text x={width/2} y="296" textAnchor="middle">Heart rate · bpm →</text>
 <g clipPath={`url(#${id})`}>{[...rows].sort((a,b)=>Number(a.race.id===selected)-Number(b.race.id===selected)).map(({race,bins})=>{const c=raceColors[allRaces.indexOf(race)%raceColors.length],on=race.id===selected;return <g key={race.id} data-efficiency-race={race.id}>
 {raw&&on&&sampleDistances.map(d=>{const p=atDistance(race.points,d,'pace'),h=atDistance(race.points,d,'hr');return finite(p)&&finite(h)?<circle key={d} cx={X(h)} cy={Y(p)} r="1.7" fill={c} opacity=".12"/>:null})}
 {bins.map((b,i)=>{if(!finite(b.pace)||!finite(b.hr))return null;const current=on&&activeBin(b.start,b.end,distance);return <g key={i}><circle data-efficiency-point={on?'selected':'other'} cx={X(b.hr)} cy={Y(b.pace)} r={current?6:on?4:2.8} fill={c} opacity={on?1:.22} stroke={current?'var(--paper,#f3f0e7)':'none'} strokeWidth="2"/><circle cx={X(b.hr)} cy={Y(b.pace)} r="12" fill="transparent" role={on?"button":undefined} pointerEvents={on?"auto":"none"} tabIndex={on?0:-1} aria-label={`${race.city}, ${b.start/1000} to ${b.end/1000} km, ${formatPace(b.pace)} per km, ${Math.round(b.hr)} bpm`} onClick={()=>setDistance(b.start)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setDistance(b.start)}}}><title>{race.city} · {b.start/1000}–{b.end/1000} km · {formatPace(b.pace)} /km · {Math.round(b.hr)} bpm</title></circle>{current&&<text x={Math.max(65,Math.min(width-55,X(b.hr)))} y={Math.max(17,Y(b.pace)-12)} textAnchor="middle" className="mean-value">{b.start/1000}–{b.end/1000} km</text>}</g>})}</g>})}</g>
 </svg><div className="relationship-readout"><span>{active?`${active.start/1000}–${active.end/1000} km`:'No segment'}</span><strong>{formatPace(active?.pace??null)} <small>/km</small></strong><strong>{active?.hr==null?'—':Math.round(active.hr)} <small>bpm</small></strong><span>{metresPerBeat(active?.pace??null,active?.hr??null)?.toFixed(2)??'—'} m/beat</span></div><p className="chart-note">Higher = faster at the same BPM. Tap a selected-race dot to inspect a segment. Metres/beat = speed ÷ HR; descriptive, affected by course, temperature and sensor quality. {focus?'Focused axes may clip other races.':'Axes stay fixed across races.'}</p></div>;
}
export function ChartControls({focus,setFocus,raw,setRaw}:{focus:boolean;setFocus:(v:boolean)=>void;raw:boolean;setRaw:(v:boolean)=>void}){
 return <div className="chart-controls"><div className="scale-switch" aria-label="Chart scale"><button aria-pressed={!focus} onClick={()=>setFocus(false)}>Shared scale</button><button aria-pressed={focus} onClick={()=>setFocus(true)}>Focus race</button></div><label><input type="checkbox" checked={raw} onChange={e=>setRaw(e.target.checked)}/> Faint recording</label></div>;
}
