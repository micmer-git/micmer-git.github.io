import {fiveKmMeans} from './races.mjs';
export function meanDomain(races,metric){
 const values=races.flatMap(r=>fiveKmMeans(r.points).map(b=>b[metric])).filter(v=>Number.isFinite(v));
 const step=metric==='pace'?15:5;
 if(!values.length)return metric==='pace'?[210,300]:[130,190];
 const min=Math.min(...values),max=Math.max(...values),pad=Math.max(step*.5,(max-min)*.08);
 return [Math.floor((min-pad)/step)*step,Math.ceil((max+pad)/step)*step];
}
export function metresPerBeat(pace,hr){return pace>0&&hr>0?60000/(pace*hr):null;}
export function axisTicks([lo,hi],metric){
 const options=metric==='pace'?[5,10,15,30,60,120]:[1,2,5,10,20,50];
 const step=options.find(s=>s>=(hi-lo)/4)||options.at(-1),values=[];
 for(let v=Math.ceil(lo/step)*step;v<=hi;v+=step)values.push(v);
 return values;
}
