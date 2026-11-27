(() => {
  'use strict';

  function startLab() {
    const canvas = document.querySelector('[data-lab]');
    if (!canvas) return;

    const machines = [...document.querySelectorAll('[data-machine]')];
    const caption = document.querySelector('[data-lab-caption]');
    const speedInput = document.querySelector('[data-speed]');
    const speedValue = document.querySelector('[data-speed-value]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const scenes = {
      motor: {
        caption: 'Oil jets strike the winding ends. Changing rotor speed alters how the oil spreads around the motor.',
        alt: 'Cutaway of an electric motor with two oil jets aimed at its copper end windings.'
      },
      gearbox: {
        caption: 'The lower gear dips into the sump. As it turns faster, it carries oil higher and throws it across the housing.',
        alt: 'Cutaway of two meshing gears lifting oil from a sump and throwing droplets into the gearbox.'
      }
    };
    const selected = machines.find(button => button.getAttribute('aria-pressed') === 'true');
    let machine = selected && scenes[selected.dataset.machine] ? selected.dataset.machine : 'gearbox';
    let speed = Math.max(1, Math.min(5, Number(speedInput?.value) || 3));
    let phase = 0.65;
    let visible = !('IntersectionObserver' in window);
    let frame = 0;
    let previous = null;
    const width = 360, height = 230;
    canvas.width = width;
    canvas.height = height;
    canvas.style.imageRendering = 'pixelated';
    canvas.setAttribute('role', 'img');
    const ctx = canvas.getContext('2d', {alpha:false});
    const tau = Math.PI * 2;
    const ink = {
      field:'#0a1c2c', grid:'#102b3d', cross:'#1f4054', shell:'#54798a', bevel:'#8aa5a5',
      edge:'#243f53', dark:'#122b40', iron:'#446679', steel:'#84a4ab', shine:'#bed2c9',
      shadow:'#203b4e', slot:'#152f40', water:'#36858d', waterDeep:'#235464',
      foam:'#98d8cb', glint:'#d3f2db', copper:'#d87857', hot:'#f1a878', orangeDark:'#8c5048'
    };

    function rect(x,y,w,h,color) {
      ctx.fillStyle=color;
      ctx.fillRect(Math.round(x),Math.round(y),w,h);
    }
    function line(x0,y0,x1,y1,color) {
      x0=Math.round(x0); y0=Math.round(y0); x1=Math.round(x1); y1=Math.round(y1);
      const dx=Math.abs(x1-x0), sx=x0<x1?1:-1, dy=-Math.abs(y1-y0), sy=y0<y1?1:-1;
      let err=dx+dy;
      ctx.fillStyle=color;
      while (true) {
        ctx.fillRect(x0,y0,1,1);
        if (x0===x1 && y0===y1) break;
        const doubled=2*err;
        if (doubled>=dy) {err+=dy; x0+=sx;}
        if (doubled<=dx) {err+=dx; y0+=sy;}
      }
    }
    function polygon(points, color) {
      const ys=points.map(p=>p[1]), top=Math.ceil(Math.min(...ys)), bottom=Math.floor(Math.max(...ys));
      ctx.fillStyle=color;
      for(let y=top;y<=bottom;y++){
        const nodes=[];
        for(let i=0,j=points.length-1;i<points.length;j=i++){
          const p=points[i], q=points[j];
          if((p[1]<=y && q[1]>y)||(q[1]<=y && p[1]>y)) nodes.push(p[0]+(y-p[1])*(q[0]-p[0])/(q[1]-p[1]));
        }
        nodes.sort((a,b)=>a-b);
        for(let n=0;n+1<nodes.length;n+=2){
          const left=Math.ceil(nodes[n]);
          ctx.fillRect(left,y,Math.floor(nodes[n+1])-left+1,1);
        }
      }
    }
    function disk(x,y,r,col) {
      ctx.fillStyle=col;
      for(let d=-r;d<=r;d++){
        const half=Math.floor(Math.sqrt(r*r-d*d));
        ctx.fillRect(Math.round(x)-half,Math.round(y)+d,2*half+1,1);
      }
    }
    function bolt(x,y) {
      disk(x,y,3,ink.dark); rect(x-1,y-2,3,1,ink.steel); line(x-1,y+1,x+1,y-1,ink.iron);
    }
    function casing(points) {
      polygon(points,ink.shell);
      const cx=180,cy=118;
      const middle=points.map(([x,y])=>[cx+(x-cx)*0.96,cy+(y-cy)*0.94]);
      const inside=points.map(([x,y])=>[cx+(x-cx)*0.92,cy+(y-cy)*0.89]);
      polygon(middle,ink.edge); polygon(inside,ink.dark);
      for(let n=0;n<points.length-1;n++){
        if(points[n][1]<=points[n+1][1]) line(...points[n],...points[n+1],ink.bevel);
      }
    }
    function gear(x,y,r,teeth,angle) {
      const pts=[];
      for(let i=0;i<teeth;i++){
        for(const [fraction,radius] of [[0,r-4],[0.13,r-4],[0.29,r+2],[0.56,r+2],[0.72,r-4]]){
          const a=angle+tau*(i+fraction)/teeth;
          pts.push([x+Math.cos(a)*radius,y+Math.sin(a)*radius]);
        }
      }
      polygon(pts.map(([a,b])=>[a+2,b+3]),ink.slot);
      polygon(pts,ink.steel);
      for(let i=0;i<teeth;i++){
        const q=i*5;
        line(...pts[q+1],...pts[q+2],ink.shine);
        line(...pts[q+3],...pts[q+4],ink.iron);
      }
      disk(x,y,r-7,ink.iron); disk(x,y,r-10,ink.steel); disk(x,y,r-12,ink.shadow);
      for(let i=0;i<6;i++){
        const a=angle+i*tau/6;
        const ux=Math.cos(a),uy=Math.sin(a), vx=-uy,vy=ux;
        const local=(v,w)=>[x+ux*v+vx*w,y+uy*v+vy*w];
        polygon([local(5,-3),local(r-11,-4),local(r-11,1),local(5,3)],ink.iron);
        line(...local(9,-3),...local(r-12,-3),ink.steel);
      }
      disk(x,y,9,ink.steel); disk(x,y,6,ink.iron); disk(x,y,3,ink.slot);
      line(x-2,y+1,x+1,y-2,ink.shine);
    }
    function backdrop() {
      rect(0,0,width,height,ink.field);
      for(let x=8;x<width;x+=16) rect(x,0,1,height,ink.grid);
      for(let y=8;y<height;y+=16) rect(0,y,width,1,ink.grid);
      for(let x=8;x<width;x+=64) for(let y=8;y<height;y+=64){
        rect(x-2,y,5,1,ink.cross); rect(x,y-2,1,5,ink.cross);
      }
    }
    const fractional = n => n-Math.floor(n);
    function splash(x,y,dir,reach,lift,offset,t) {
      const n=18+speed*3;
      for(let i=0;i<n;i++){
        const u=fractional(t*(0.44+0.03*(i%4)) + i*0.618+offset);
        const jitter=Math.sin(i*10.45);
        const dx=x+dir*u*(reach+5*jitter);
        const dy=y+u*(y<120?62:35)-(lift+7*jitter)*4*u*(1-u);
        const c=i%9===0?ink.hot:i%4===0?ink.glint:ink.foam;
        rect(dx,dy,i%3===0?3:2,i%4===0?2:1,c);
      }
    }
    function gearbox(t) {
      const hull=[[66,80],[88,58],[174,58],[190,44],[243,44],[282,79],[291,101],[291,153],[270,183],[243,193],[90,193],[63,166],[63,92]];
      casing(hull);
      for(let i=0;i<7;i++){
        line(70+i*5,87-i*5,78+i*5,87-i*5,ink.iron);
        line(249+i*4,58+i*4,249+i*4,63+i*4,ink.iron);
      }
      rect(57,108,19,23,ink.edge); rect(49,113,17,12,ink.shell); rect(48,115,20,2,ink.bevel);
      rect(284,98,17,22,ink.edge); rect(292,102,16,11,ink.shell); rect(293,104,15,2,ink.bevel);
      const angle=-t;
      gear(146,125,48,20,angle);
      gear(222,108,32,13,-angle*20/13+0.23);
      const surface=163;
      for(let x=75;x<=277;x++){
        const base=Math.min(184,169+(x-75),168+(277-x));
        const top=Math.round(surface+2*Math.sin(x*0.12+t*2)+Math.sin(x*0.35-t));
        rect(x,top,1,base-top+1,ink.waterDeep);
        rect(x,top,1,2,ink.water);
        if((x+Math.floor(t*4))%19<7) rect(x,top,1,1,ink.foam);
      }
      for(let i=0;i<39;i++){
        const x=88+((i*47+Math.floor(t*3))%175), y=171+(i*13%10);
        rect(x,y,2+i%4,1,i%5===0?ink.water:ink.edge);
      }
      splash(183,144,1,44+4*speed,16+5*speed,0.5,t);
      splash(132,82,-1,28+4*speed,7+2*speed,0,t);
      [[85,77],[100,64],[174,64],[244,53],[279,90],[280,149],[266,172],[96,184],[74,160]].forEach(([a,b])=>bolt(a,b));
      line(104,198,243,198,ink.cross); line(114,196,114,200,ink.shell); line(234,196,234,200,ink.shell);
    }
    function motor(t) {
      const hull=[[62,84],[88,58],[108,48],[248,48],[279,69],[294,91],[294,147],[278,170],[249,185],[97,185],[69,168],[57,143],[57,98]];
      casing(hull);
      for(let x=113;x<=237;x+=10){rect(x,41,3,8,ink.iron); rect(x,41,2,2,ink.bevel); rect(x,183,3,7,ink.iron);}
      for(const y of [82,143]){
        rect(92,y,156,10,ink.slot);
        for(let i=0;i<28;i++) {
          const x=95+i*5;
          rect(x,y,3,9,ink.iron); rect(x,y,3,2,ink.steel);
        }
      }
      for(const cx of [101,249]){
        for(const cy of [89,146]){
          for(let i=0;i<6;i++){
            const x=cx-11+i*4, yy=cy+(i===0||i===5?2:0);
            rect(x,yy-7,3,14,ink.orangeDark); rect(x,yy-7,2,11,ink.copper); rect(x,yy-7,2,3,ink.hot);
          }
        }
      }
      rect(45,109,266,17,ink.edge); rect(45,113,266,7,ink.steel); rect(45,113,266,2,ink.shine);
      polygon([[122,98],[135,93],[221,93],[235,101],[235,132],[220,139],[135,139],[122,132]],ink.iron);
      for(let i=0;i<18;i++){
        const x=136+i*5;
        rect(x,96,2,39,ink.shadow); rect(x,99,1,33,ink.shell);
      }
      for(let i=0;i<4;i++){
        const y=97+fractional(t*0.25+i/4)*37;
        line(137,y,218,y,ink.steel);
      }
      rect(75,108,12,20,ink.shell); rect(266,108,12,20,ink.shell);
      for(const [x,dir] of [[80,1],[271,-1]]){
        rect(x-4,56,8,14,ink.steel); rect(x-2,69,5,5,ink.shell);
        const dx=x+4*dir,dy=74;
        for(let j=0;j<13;j++){
          const u=fractional(t*0.74+j/13);
          for(const spread of [-1,1]){
            const px=dx+dir*(u*19+u*spread*3), py=dy+u*14;
            rect(px,py,2,1,j%4===0?ink.glint:ink.foam);
          }
        }
        splash(x+23*dir,91,-dir,14+speed*3,2+speed*2,0.2,t);
        for(let i=0;i<16;i++){
          const u=fractional(t*0.45+i*0.63);
          const px=x+dir*(18+6*Math.sin(i)*u);
          rect(px,95+u*65,2,2,ink.water);
        }
      }
      rect(107,168,139,4,ink.waterDeep); rect(122,167,109,1,ink.water);
      [[85,67],[103,54],[248,56],[281,83],[284,147],[254,174],[95,174],[69,147]].forEach(([a,b])=>bolt(a,b));
    }
    function draw() {
      if (!ctx) return;
      backdrop();
      if(machine==='motor') motor(phase); else gearbox(phase);
    }
    function settings() {
      for(const button of machines) button.setAttribute('aria-pressed',String(button.dataset.machine===machine));
      if(speedValue) speedValue.textContent=String(speed);
      if(caption) caption.textContent=scenes[machine].caption;
      canvas.setAttribute('aria-label',scenes[machine].alt);
      canvas.textContent=scenes[machine].alt;
      draw();
    }
    function tick(now) {
      if(previous===null) previous=now;
      if(now-previous>=48){
        phase += Math.min(now-previous,100)/1000*(0.36+speed*0.29);
        previous=now;
        draw();
      }
      frame=requestAnimationFrame(tick);
    }
    function sync() {
      const mode=document.documentElement.dataset.motion;
      const moving=ctx && visible && !document.hidden && (mode==='on' || (mode!=='off' && !reducedMotion.matches));
      if(!moving){
        if(frame) cancelAnimationFrame(frame);
        frame=0; previous=null;
      } else if(!frame){
        frame=requestAnimationFrame(tick);
      }
    }
    for(const button of machines) button.addEventListener('click',()=>{
      if(!scenes[button.dataset.machine]) return;
      machine=button.dataset.machine;
      settings();
    });
    speedInput?.addEventListener('input',()=>{
      speed=Math.max(1,Math.min(5,Number(speedInput.value)||3));
      settings();
    });
    if('IntersectionObserver' in window){
      new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();}).observe(canvas);
    }
    new MutationObserver(sync).observe(document.documentElement,{attributes:true,attributeFilter:['data-motion'],subtree:true});
    reducedMotion.addEventListener('change',sync);
    document.addEventListener('visibilitychange',sync);
    settings();
    sync();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',startLab,{once:true});
  else startLab();
})();
