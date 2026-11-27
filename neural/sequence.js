/* The same particles move between deposited material, candidate designs and tool calls. */
(() => {
  'use strict';
  const W = 420, H = 320, tau = Math.PI * 2;
  const round = Math.round;
  const clamp = x => Math.max(0, Math.min(1, x));
  const mix = (a, b, t) => a + (b - a) * t;
  const smooth = x => { const t = clamp(x); return t*t*(3-2*t); };
  const random = (i, seed) => {
    let n = Math.imul(i + 1, 1597334677) ^ Math.imul(seed + 1, 3812015801);
    n = Math.imul(n ^ (n >>> 16), 2246822519);
    return ((n ^ (n >>> 13)) >>> 0) / 4294967296;
  };
  const palette = {
    field:'#0b1c2b', interior:'#10283a', grid:'#183547', line:'#305267', metal:'#506d7a',
    bevel:'#9bb5b2', dim:'#476171', mint:'#b2d9cd', amber:'#ffbd81', warm:'#d78365'
  };
  const materials = [
    ['#87495a','#ae535a','#cc605b','#e87a64','#f89973','#ffc190','#ffe1ad'],
    ['#31476c','#365d8c','#417cb0','#519bc5','#6bbbd6','#91d9e1','#caf3e9']
  ];
  function block(c,x,y,w,h,color) {
    c.fillStyle=color; c.fillRect(round(x),round(y),w,h);
  }
  function line(c, x0, y0, x1, y1, color) {
    x0=round(x0);y0=round(y0);x1=round(x1);y1=round(y1);
    c.fillStyle=color;
    const dx=Math.abs(x1-x0),dy=-Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1;
    let error=dx+dy;
    while(true){
      c.fillRect(x0,y0,1,1);
      if(x0===x1&&y0===y1)break;
      const e=2*error;
      if(e>=dy){error+=dy;x0+=sx;}
      if(e<=dx){error+=dx;y0+=sy;}
    }
  }
  function wire(c,points,color) {
    for(let n=1;n<points.length;n++)line(c,...points[n-1],...points[n],color);
  }
  function face(c,points,color) {
    const min=Math.ceil(Math.min(...points.map(p=>p[1]))),max=Math.ceil(Math.max(...points.map(p=>p[1])));
    for(let y=min;y<max;y++){
      const cuts=[];
      for(let i=0,j=points.length-1;i<points.length;j=i++){
        const a=points[i],b=points[j],scan=y+.5;
        if((a[1]>scan)!==(b[1]>scan))cuts.push(a[0]+(scan-a[1])*(b[0]-a[0])/(b[1]-a[1]));
      }
      cuts.sort((a,b)=>a-b);
      for(let k=0;k<cuts.length-1;k+=2)block(c,round(cuts[k]),y,round(cuts[k+1])-round(cuts[k]),1,color);
    }
  }
  function type(c,word,x,y,size,color,align='center') {
    c.font='bold '+size+'px monospace';c.fillStyle=color;c.textAlign=align;c.textBaseline='middle';
    c.fillText(word,x,y);
  }
  function frame(c,x,y,w,h,color) {
    block(c,x,y,w,1,color);block(c,x,y+h-1,w,1,color);
    block(c,x,y,1,h,color);block(c,x+w-1,y,1,h,color);
  }
  function panel(draw) {
    const layer=document.createElement('canvas');layer.width=W;layer.height=H;
    draw(layer.getContext('2d'));return layer;
  }
  function ground(c) {
    block(c,0,0,W,H,palette.field);
    for(let x=10;x<W;x+=12)for(let y=10;y<H;y+=12)block(c,x,y,1,1,palette.grid);
    for(const [x,y,dx,dy] of [[14,14,1,1],[405,14,-1,1],[14,305,1,-1],[405,305,-1,-1]]){
      line(c,x,y,x+dx*8,y,palette.line);line(c,x,y,x,y+dy*8,palette.line);
    }
  }
  function printer(c) {
    const plate=[[22,222],[237,137],[395,197],[179,284]];
    face(c,[[22,222],[179,284],[395,197],[395,204],[179,292],[22,229]],'#223e50');
    face(c,plate,'#132d40');
    for(let i=0;i<=12;i++){
      const t=i/12;
      line(c,mix(22,237,t),mix(222,137,t),mix(179,395,t),mix(284,197,t),'#214357');
    }
    for(let i=0;i<=9;i++){
      const t=i/9;
      line(c,mix(22,179,t),mix(222,284,t),mix(237,395,t),mix(137,197,t),'#214357');
    }
    wire(c,[...plate,plate[0]],'#5e8190');
    wire(c,[[22,229],[179,292],[395,204]],'#3b6072');
    for(let i=0;i<4;i++)line(c,39+i*7,232+i*3,42+i*7,233+i*3,'#8baaa8');
    // Separate feedstocks enter the print head before the toothed collar and brass tip.
    for(const [x,col,light] of [[277,'#a8555b','#ef9773'],[307,'#3d78a6','#80c4d6']]){
      block(c,x,0,9,39,col);block(c,x+1,0,2,39,light);
      for(let y=4;y<38;y+=6)block(c,x+5,y,4,2,'#354557');
    }
    face(c,[[256,36],[272,28],[322,28],[334,37],[320,45],[269,45]],'#a9b8b1');
    face(c,[[256,36],[269,45],[269,66],[256,59]],'#516d77');
    face(c,[[269,45],[320,45],[334,37],[334,59],[320,67],[269,67]],'#78929a');
    block(c,275,47,6,16,'#b6c9bd');block(c,282,47,21,16,'#8fa4a6');block(c,316,45,3,20,'#465e6e');
    block(c,278,65,34,29,'#4d6876');
    for(let j=0;j<4;j++){
      const y=65+j*7;
      face(c,[[269,y],[315,y],[321,y+3],[314,y+6],[269,y+6],[265,y+3]],j%2?'#708a90':'#829b9d');
      block(c,270,y,42,2,'#b7c8b9');block(c,269,y+4,43,2,'#38536a');
      block(c,275,y+1,8,2,'#d5d7bb');
    }
    face(c,[[271,94],[312,94],[319,99],[311,108],[278,109],[269,103]],'#b17a65');
    face(c,[[277,96],[304,96],[301,105],[278,107]],'#e6a378');
    block(c,278,97,6,8,'#ffd396');
    face(c,[[277,108],[310,108],[302,120],[295,127],[291,127],[285,120]],'#d28b65');
    face(c,[[277,108],[289,108],[293,126],[285,119]],'#ffd697');
    face(c,[[300,108],[310,108],[295,127]],'#916158');
    block(c,290,126,7,2,'#f8c48d');block(c,291,128,4,11,'#ce6960');block(c,294,128,2,11,'#76acc2');
    wire(c,[[247,82],[188,82],[177,71],[138,71]],'#4a6977');
    block(c,243,80,4,4,'#9bb8b4');
    type(c,'ROTATING NOZZLE',134,70,10,'#9db7b9','right');
  }
  const cx=[104,211,318],cy=[83,160,237];
  function study(c) {
    type(c,'PITCH',211,23,11,palette.mint);
    line(c,64,37,356,37,palette.line);line(c,64,34,64,40,palette.bevel);
    wire(c,[[351,34],[356,37],[351,40]],palette.bevel);
    line(c,40,58,40,260,palette.line);line(c,37,58,43,58,palette.bevel);
    wire(c,[[37,255],[40,260],[43,255]],palette.bevel);
    c.save(); c.translate(25,158); c.rotate(-Math.PI/2);
    type(c,'DIAMETER',0,0,10,palette.mint);c.restore();
    for(const y of cy)for(const x of cx){
      block(c,x-48,y-30,96,60,'#102437');
      frame(c,x-48,y-30,96,60,'#2c455b');
      block(c,x-48,y-30,8,1,'#658493'); block(c,x+39,y+29,9,1,'#658493');
      for(let d=-29;d<=28;d+=10)block(c,x+d,y+13,5,1,'#2a4052');
    }
  }
  const traces=[
    [[91,81],[112,81],[151,120],[151,134],[171,154]],
    [[91,160],[171,160]],
    [[91,239],[112,239],[151,200],[151,186],[171,166]],
    [[248,153],[263,153],[280,136],[305,136]],
    [[248,167],[263,167],[280,184],[305,184]]
  ];
  function network(c) {
    for(const points of traces){
      for(const dy of [-4,4])wire(c,points.map(([x,y])=>[x,y+dy]),'#25475b');
      wire(c,points,'#567887');
    }
    for(const y of [81,160,239]){
      block(c,24,y-22,67,44,'#142e41');frame(c,24,y-22,67,44,palette.metal);
      block(c,28,y-18,59,36,'#142737');frame(c,28,y-18,59,36,'#2c495d');
      block(c,89,y-7,5,14,'#718e90');
      for(let x=33;x<=44;x+=4)block(c,x,y+13,2,1,'#68888f');
    }
    wire(c,[[40,74],[46,80],[40,86]],palette.amber);
    block(c,50,85,9,2,palette.mint);
    wire(c,[[42,153],[49,153],[55,159],[63,159],[70,151]],palette.mint);
    wire(c,[[42,166],[49,166],[55,160],[63,160],[70,167]],'#75aaca');
    for(let n=0;n<5;n++)block(c,41+n*7,247-n*3,4,2+n*3,n%2?'#90c5c9':'#6b9db2');
    for(let x=183;x<=236;x+=7){
      block(c,x,118,3,9,'#67868d'); block(c,x,193,3,9,'#67868d');
    }
    for(let y=137;y<=183;y+=7){
      block(c,164,y,9,3,'#88a3a2'); block(c,246,y,9,3,'#88a3a2');
    }
    face(c,[[171,131],[177,125],[242,125],[248,131],[248,190],[242,196],[177,196],[171,190]],'#83a19e');
    face(c,[[174,133],[180,128],[240,128],[245,133],[245,188],[241,193],[179,193],[174,188]],'#2c4856');
    block(c,178,133,63,55,'#192e3b');frame(c,178,133,63,55,'#52707a');
    block(c,182,137,4,3,palette.amber);
    type(c,'MCP',210,158,22,'#d8e4d7');
    for(let i=0;i<12;i++)block(c,185+i*4,178,i%4===0?2:1,4,i%3?'#68828a':'#a4b7ad');
    block(c,304,113,91,96,'#263f50');frame(c,304,113,91,96,'#708c91');
    block(c,309,118,81,74,'#112738');frame(c,309,118,81,74,'#536e7a');
    const tray=[[319,166],[350,156],[381,165],[349,179]];
    face(c,tray,'#253e55');wire(c,[...tray,tray[0]],'#75979e');
    wire(c,[[319,143],[319,166],[349,179],[349,154],[319,143],[350,131],[381,142],[349,154]],'#4b7488');
    wire(c,[[381,142],[381,165]],'#4b7488');
    for(let j=0;j<5;j++)block(c,312+j*5,198,3,2,j<2?palette.amber:'#527383');
    block(c,367,198,14,3,'#799597');
    type(c,'AGENTS',58,277,12,palette.mint);
    type(c,'PARTICLEWORKS',349,228,10,palette.mint);
  }
  function locateTrace(points,t) {
    const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    let left=t*lengths.reduce((total,value)=>total+value,0);
    for(let i=0;i<lengths.length;i++){
      if(left<=lengths[i]||i===lengths.length-1){
        const f=clamp(left/lengths[i]);
        return [mix(points[i][0],points[i+1][0],f),mix(points[i][1],points[i+1][1],f)];
      }
      left-=lengths[i];
    }
  }
  function thread(t,s,material,x0,y0,x1,y1,turns,radius,thickness,grain) {
    const angle=t*turns*tau+material*Math.PI-.68;
    const depth=Math.sin(angle),cross=Math.cos(angle)*radius+s*thickness;
    const dx=x1-x0,dy=y1-y0,len=Math.hypot(dx,dy);
    const x=mix(x0,x1,t)-dy/len*cross+.19*depth*radius;
    const y=mix(y0,y1,t)+dx/len*cross-.20*depth*radius;
    const light=clamp(.43+.25*depth-.26*s+.11*(1-Math.abs(s))+(grain-.5)*.20);
    return [x,y,depth,round(light*6)];
  }
  function particles() {
    const result=[];
    for(let i=0;i<4400;i++){
      const material=i%2,t=random(i,1),s=random(i,2)*2-1,grain=random(i,3);
      const cell=Math.floor(i/2)%9,col=cell%3,row=Math.floor(cell/3);
      const a=thread(t,s,material,72,228,294,138,4.4,9.0,6.5,grain);
      const b=thread(t,s,material,cx[col]-33,cy[row]+8,cx[col]+33,cy[row]-8,
        4.2-col*1.17,3.5+row*1.8,2.35+row*.65,grain);
      const group=Math.floor(random(i,4)*7),slot=Math.floor(t*8);
      let x,y;
      if(group<5){
        const p=locateTrace(traces[group],(slot+.16+(t*8-slot)*.40)/8);
        x=p[0];y=p[1]+(material?1.25:-1.25)+s*.85;
      }else{
        // The receiving viewport contains two simulated material streams.
        const run=t*.96+.02;
        x=321+56*run; y=161+Math.sin(run*tau*1.14+material*2.1)*3.8+s*2.3-Math.sin(run*Math.PI)*6;
      }
      result.push({a,b,end:[x,y,0,round(2+grain*4)],material,grain,t,
        driftX:(random(i,8)-.5)*94,driftY:(random(i,9)-.5)*122,cell});
    }
    return result;
  }
  function start(){
    const canvas=document.querySelector('[data-sequence]');
    if(!canvas)return;
    const scene=canvas.closest('.sequence-sticky')||canvas.parentElement;
    const caption=scene.querySelector('[data-sequence-label]');
    const sections=['award','automation','agents'].map(id=>document.getElementById(id));
    if(sections.some(s=>!s))return;
    const c=canvas.getContext('2d',{alpha:false});if(!c)return;
    canvas.width=W;canvas.height=H;canvas.style.imageRendering='pixelated';c.imageSmoothingEnabled=false;
    const background=panel(ground),decor=[printer,study,network].map(panel),cloud=particles();
    const ordered=[...cloud].sort((p,q)=>p.a[2]-q.a[2]);
    const studyOrder=[...cloud].sort((p,q)=>p.b[2]-q.b[2]);
    const captions=['01 / Helical deposition','02 / Design exploration','03 / Agent orchestration'];
    const system=matchMedia('(prefers-reduced-motion: reduce)');
    const moving=()=>document.documentElement.dataset.motion==='on' ||
      (document.documentElement.dataset.motion!=='off'&&!system.matches);
    let active=-1,visible=true,frame=0,clock=0,last=0,position=0,dirty=true;
    function measure(){
      const vh=window.innerHeight;
      position=0;
      for(let i=1;i<3;i++)position+=smooth((vh*.74-sections[i].getBoundingClientRect().top)/(vh*.43));
      const index=round(position);
      if(active!==index){active=index;if(caption)caption.textContent=captions[index];}
      dirty=true;
    }
    function render(){
      const motion=moving(),p=motion?position:round(position);
      const step=Math.min(1,Math.floor(p)),f=p-step,bend=Math.sin(Math.PI*f);
      c.drawImage(background,0,0);
      c.globalAlpha=1-smooth(f/.74);c.drawImage(decor[step],0,0);
      c.globalAlpha=smooth((f-.26)/.74);c.drawImage(decor[step+1],0,0);c.globalAlpha=1;
      const drawingOrder=p<.55?ordered:studyOrder;
      for(const item of drawingOrder){
        const from=step===0?item.a:item.b,to=step===0?item.b:item.end;
        const q=clamp(f+(item.grain-.5)*bend*.28),arc=Math.sin(Math.PI*q);
        const x=mix(from[0],to[0],q)+item.driftX*arc;
        const y=mix(from[1],to[1],q)+item.driftY*arc;
        let shade=round(mix(from[3],to[3],q));
        if(p>1.84 && motion && Math.sin(item.t*tau*2-clock*2.4)>.89)shade=Math.min(6,shade+1);
        const size=p<.55&&item.grain>.56?3:2;
        block(c,x,y,size,size,materials[item.material][shade]);
      }
      if(motion&&p<.12){
        c.globalAlpha=(1-p/.12)*(.38+.45*(1+Math.sin(clock*2))/2);
        block(c,291,130,3,3,'#ffe2ac');c.globalAlpha=1;
      }
    }
    function tick(time){
      frame=0;
      if(document.hidden||!visible){last=0;return;}
      if(dirty||!last||time-last>=80){
        if(last&&moving())clock+=Math.min(140,time-last)/1000;
        last=time;dirty=false;render();
      }
      if(moving())frame=requestAnimationFrame(tick);
    }
    function schedule(){if(!frame&&visible&&!document.hidden)frame=requestAnimationFrame(tick);}
    function sync(){measure();schedule();}
    function visibility(){
      if(frame)cancelAnimationFrame(frame);frame=0;last=0;sync();
    }
    // Measure on the first frame as well as after the browser restores a deep-linked position.
    measure();render();schedule();
    if('IntersectionObserver'in window)new IntersectionObserver(([entry])=>{
      visible=entry.isIntersecting;visibility();
    }).observe(canvas);
    window.addEventListener('scroll',sync,{passive:true});
    window.addEventListener('resize',sync,{passive:true});window.addEventListener('pageshow',sync);
    window.addEventListener('hashchange',sync);window.addEventListener('load',sync,{once:true});
    if('ResizeObserver'in window)new ResizeObserver(sync).observe(sections[0].parentElement);
    document.addEventListener('visibilitychange',visibility);
    new MutationObserver(visibility).observe(document.documentElement,{attributes:true,attributeFilter:['data-motion']});
    if(system.addEventListener)system.addEventListener('change',visibility);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
