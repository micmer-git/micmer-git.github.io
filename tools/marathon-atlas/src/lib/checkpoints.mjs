import {atDistance} from './races.mjs';
export const SPLIT_DISTANCES=[10000,21097.5,30000,35000];
// Cadence is Intervals rpm (one leg). Integrate 2*rpm over recorded seconds.
// The published samples are reduced and stop positions can be collapsed: estimates only.
export function stepsUntil(points,distance){
 const start=atDistance(points,0),end=atDistance(points,distance);
 if(start===null||end===null||end<start)return null;
 if(distance===0)return 0;
 let steps=0,covered=0;
 for(let i=1;i<points.length;i++){
  const a=points[i-1],b=points[i];
  const lo=Math.max(start,a.t),hi=Math.min(end,b.t);
  if(hi<=lo)continue;
  if(b.t-a.t>60||b.d-a.d>1000||a.cadence==null||b.cadence==null||!Number.isFinite(a.cadence)||!Number.isFinite(b.cadence)||a.cadence<0||b.cadence<0)return null;
  const c0=a.cadence+(b.cadence-a.cadence)*(lo-a.t)/(b.t-a.t);
  const c1=a.cadence+(b.cadence-a.cadence)*(hi-a.t)/(b.t-a.t);
  steps+=(c0+c1)*(hi-lo)/60;covered+=hi-lo;
 }
 return Math.abs(covered-(end-start))<.01?steps:null;
}
export function checkpointStats(race,distance){
 const start=atDistance(race.points,0),end=atDistance(race.points,distance);
 return {distance,elapsed:start===null||end===null?null:end-start,steps:stepsUntil(race.points,distance)};
}
