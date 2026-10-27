import React from 'react';
import type {Race} from './v2-types';
const Route=React.memo(function Route({race}:{race:Race}){
 if(!race.route.length)return <div className="missing-route">Course unavailable</div>;
 const lat=race.route.map(p=>p[0]),lng=race.route.map(p=>p[1]),factor=Math.cos(lat[0]*Math.PI/180),x0=Math.min(...lng),y0=Math.min(...lat),ymax=Math.max(...lat),w=(Math.max(...lng)-x0)*factor,h=Math.max(...lat)-y0,yMax=Math.max(...lat),scale=100/(Math.max(w,h)||1);
 const path=race.route.map((p,i)=>(i?'L':'M')+(10+(120-w*scale)/2+(p[1]-x0)*factor*scale).toFixed(2)+','+(10+(100-h*scale)/2+(ymax-p[0])*scale).toFixed(2)).join(' ');
 return <svg className="route" viewBox="0 0 140 120" role="img" aria-label={race.city+' recorded GPS route'}><path d={path} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>
});

export default Route;
