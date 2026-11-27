/* Lac Léman at blue hour. One canvas pixel is one brush mark. */
(() => {
  'use strict';

  const round = Math.round;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const mix = (a, b, t) => a + (b - a) * t;
  const hash = (a, b) => {
    let n = Math.imul(a ^ 0x4a39b70d, 1597334677) ^ Math.imul(b ^ 0x26d564b5, 3812015801);
    n = Math.imul(n ^ (n >>> 16), 2246822519);
    return ((n ^ (n >>> 13)) >>> 0) / 4294967296;
  };
  const noise = (x, seed) => mix(hash(Math.floor(x), seed), hash(Math.floor(x) + 1, seed), x - Math.floor(x));
  const choose = (list, fraction) => list[Math.floor(fraction * list.length)];
  const lineColor = (a, b, t) => {
    const n = parseInt(a, 16), m = parseInt(b, 16);
    const c = shift => round(mix((n >> shift) & 255, (m >> shift) & 255, t));
    return 'rgb(' + [c(16), c(8), c(0)].join(',') + ')';
  };

  function rect(c, color, x, y, w = 1, h = 1) {
    c.fillStyle = color;
    c.fillRect(round(x), round(y), Math.max(1, round(w)), Math.max(1, round(h)));
  }

  // Rasterise on whole pixels, including the diagonals of rooflines and Alpine ridges.
  function polygon(c, color, pts) {
    let min = Infinity, max = -Infinity;
    for (const p of pts) { min = Math.min(min, p[1]); max = Math.max(max, p[1]); }
    c.fillStyle = color;
    for (let y = Math.ceil(min); y < max; y++) {
      const cuts = [];
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const a = pts[i], b = pts[j], scan = y + .5;
        if ((a[1] > scan) !== (b[1] > scan)) cuts.push(a[0] + (scan - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
      }
      cuts.sort((a, b) => a - b);
      for (let i = 0; i < cuts.length - 1; i += 2) {
        const left = round(cuts[i]);
        c.fillRect(left, y, round(cuts[i + 1]) - left, 1);
      }
    }
  }

  function curve(points, x) {
    for (let i = 1; i < points.length; i++) {
      if (x <= points[i][0]) return mix(points[i - 1][1], points[i][1], (x - points[i - 1][0]) / (points[i][0] - points[i - 1][0]));
    }
    return points[points.length - 1][1];
  }

  function sheet(w, h, painter) {
    const layer = document.createElement('canvas');
    layer.width = w; layer.height = h;
    const c = layer.getContext('2d');
    c.imageSmoothingEnabled = false;
    painter(c);
    return layer;
  }

  function sky(c, w, h) {
    const bands = [[0,'10132d'],[.22,'232948'],[.39,'514962'],[.54,'aa7785'],[.67,'df9687'],[.8,'f4c5a0'],[1,'bd91a0']];
    let index = 1;
    for (let y = 0; y < h; y++) {
      while (index < bands.length - 1 && y/h > bands[index][0]) index++;
      const a = bands[index - 1], b = bands[index];
      rect(c, lineColor(a[1], b[1], (y/h - a[0])/(b[0] - a[0])), 0, y, w);
    }
    for (let i = 0; i < w * .31; i++) {
      const x = hash(i, 1) * w, y = Math.pow(hash(i, 2), 1.25) * h * .53;
      if (hash(i, 3) < y/h) continue;
      rect(c, choose(['#6e718f','#777992','#aba9b2','#d6c8bf'], hash(i, 4)), x, y);
      if (i % 45 === 1 && y < h * .32) {
        rect(c, '#7c7a94', x-1, y, 3); rect(c, '#7c7a94', x, y-1, 1, 3); rect(c, '#eee3d4', x, y);
      }
    }
    // Fragments of high cirrus open onto the moon and leave the type area quiet.
    for (let i = 0; i < 13; i++) {
      const cx = hash(i, 7) * w, cy = (.28 + hash(i, 8) * .28) * h;
      const breadth = (10 + hash(i, 10) * 50) * w / 560;
      for (let j = 0; j < 7; j++) {
        const dx = (hash(i*11+j, 63) - .5) * breadth * 1.9;
        const tone = cy < .41*h ? 'rgba(186,149,161,.19)' : 'rgba(247,186,166,.28)';
        rect(c,tone,cx + dx,cy + j + Math.abs(dx / breadth) * 3,breadth * (.2 + hash(i*11+j, 68) * .9));
      }
    }

    const moonX = round(w * .779), moonY = round(h * (w/h < 1 ? .335 : .276));
    const radius = round(Math.min(w * .102, h * .076));
    // A slight, ordered dither softens the halo while the disc retains a hard pixel edge.
    for (let y = -radius*1.55|0; y <= radius*1.55; y++) for (let x = -radius*1.55|0; x <= radius*1.55; x++) {
      const d = Math.hypot(x,y) / radius;
      if (d > 1 && d < 1.5 && hash(x+radius*2,y+radius*2)<.38) {
        c.fillStyle = 'rgba(255,189,145,' + (.14 * (1.5-d)/.5) + ')'; c.fillRect(moonX+x,moonY+y,1,1);
      }
      if (d > 1) continue;
      let tint = y < radius*.25 ? '#ffe2ac' : y < radius*.64 ? '#ffd29c' : '#f9bc91';
      const mottle = noise(x / 4 + 19, Math.floor((y + radius) / 3) + 12);
      if (mottle > .75 && y > -radius*.69 && x > -radius*.6) tint = y > radius*.28 ? '#f8bf92' : '#f8d29f';
      if (d > .94 && x-y > 0) tint = '#f6c69b';
      c.fillStyle = tint; c.fillRect(moonX+x,moonY+y,1,1);
    }
    rect(c,'#b08b96',moonX+radius*.4,moonY+radius*.65,radius*1.08);
    rect(c,'#bd949b',moonX+radius*.73,moonY+radius*.65+1,radius*1.22);
  }

  function horizon(c,w,h,points,base,color,seed,detail=1) {
    c.fillStyle = color;
    for (let x = 0; x < w; x++) {
      const y = round(curve(points,x/w)*h + (noise(x/4,seed)-.5)*3*detail + (noise(x/16,seed+2)-.5)*6*detail);
      c.fillRect(x,y,1,Math.max(1,round(h*base)-y));
    }
  }

  function massif(c,w,h,left,top,right,peakY,base,seed,tones) {
    const l = round(left*w), p = round(top*w), r = round(right*w);
    const foot = round(base*h), topY = round(peakY*h), tall = foot - topY;
    const width = r-l;
    const crag = sheet(width + 1,tall+6, g => {
      const summit = p-l;
      const rim = [];
      const anchors = [[0,.95],[.12,.77],[.22,.75],[.41,.48],[.48,.5],[.63,.31],[.68,.32],[.81,.17],[.91,.13],[1,0]];
      for (let x=0;x<=width;x++) {
        const onWest=x<=summit, t=onWest ? x/summit : (width-x)/(width-summit);
        const jag=(noise(x/3,seed)-.5)*.047 + (noise(x/10,seed+1)-.5)*.09;
        const shape=onWest ? curve(anchors,t) : 1-t+(Math.sin(t*15)+Math.sin(t*25))*.032*Math.sin(t*Math.PI);
        rim.push(round((shape+jag*Math.sin(t*Math.PI))*tall)+1);
        rect(g,tones[0],x,rim[x],1,tall+5-rim[x]);
      }
      g.globalCompositeOperation='source-atop';
      const point=(x,y)=>[x*width,y*tall];
      // Directional rock faces fold away from the summit towards the water.
      polygon(g,tones[1],[[summit,0],[summit-2,tall*.13],[summit+width*.058,tall*.31],[summit+width*.025,tall*.38],
        [summit+width*.095,tall*.59],[summit+width*.063,tall*.73],[summit+width*.1,tall+5],[width,tall+5],[width,-3]]);
      for (let i=0;i<11;i++) {
        const x=round(width*(.095+hash(i,seed+18)*.79));
        const depth=.22+hash(i,seed+54)*.56;
        const side=x<summit?-1:1, spread=width*(.025+hash(i,seed+27)*.045);
        const y=rim[x]+round(tall*(i%3===0?.16:.06));
        polygon(g, i%4===1?tones[2]:tones[1],
          [[x,y],[x+side*spread*.5,y+tall*depth*.39],[x+side*spread*.34,y+tall*depth*.45],[x+side*spread*1.8,y+tall*depth],
          [x+side*spread*.3,y+tall*depth*.62],[x+side*spread*.2,y+tall*depth*.5]]);
      }
      // The snow follows the crest and fractures into tapering gullies.
      for (let x=0;x<=width;x++) {
        const height=rim[x]/tall;
        if(height>.61)continue;
        const snow=Math.max(0,(.62-height)*tall*(.10 + noise(x/5,seed+7)*.28));
        if (snow>=1) rect(g,x<summit ? tones[3] : tones[2],x,rim[x],1,snow);
      }
      for(let i=0;i<13;i++) {
        const x=clamp(round(summit+(hash(i,seed+39)-.5)*width*.52),0,width);
        const y=rim[x], side=x<summit?-1:1, t=(.11+hash(i,seed+13)*.21)*tall;
        const dx=width*(.021+hash(i,seed+40)*.042)*side;
        polygon(g,x<summit?tones[3]:tones[2],[[x,y],[x+dx*.6,y+t*.4],[x+dx*.36,y+t*.47],
          [x+dx*1.35,y+t],[x+dx*.19,y+t*.52],[x+dx*.27,y+t*.4]]);
      }
      for (let i=0;i<width*2;i++) {
        const x=clamp(round(hash(i,seed+74)*width),0,width);
        const y=rim[x]+Math.pow(hash(i,seed+75),2)*tall*.63;
        if(y>tall*.82)continue;
        const light=x<summit && i%4===0;
        const col=light?'rgba(255,205,172,.43)':'rgba(53,58,91,.23)';
        rect(g,col,x,y,1+hash(i,seed+76)*1.9);
        if(i%3===0)rect(g,col,x+(x<summit?-1:1),y+1);
      }
      polygon(g,'rgba(78,70,111,.20)',[point(0,.73),point(.28,.77),point(.5,.64),point(.75,.79),point(1,.67),point(1,1.1),point(0,1.1)]);
    });
    c.drawImage(crag,l,topY);
  }

  function alpine(c,w,h) {
    const distant=['#bd95a1','#90829d','#cfa4a8','#ebbaa8'];
    const near=['#ab8496','#706d90','#c9a2ab','#ffbca3'];
    for (const m of [[-.22,.053,.21,.538,.745,126],[.063,.26,.43,.574,.74,143],[.18,.387,.56,.514,.735,154],
      [.40,.524,.695,.471,.74,165],[.64,.785,.94,.474,.735,182],[.794,.984,1.165,.444,.735,151]]) {
      massif(c,w,h,...m,distant);
    }
    for (const m of [[-.16,.02,.207,.596,.75,215],[.035,.19,.35,.626,.75,222],[.16,.329,.48,.579,.744,233],
      [.30,.474,.596,.545,.744,241],[.412,.607,.77,.432,.739,252],[.584,.711,.856,.523,.746,261],
      [.722,.855,1.025,.461,.751,273],[.892,1.012,1.135,.536,.745,286]]) {
      massif(c,w,h,...m,near);
    }
  }

  const hillPoints = [[0,.757],[.23,.745],[.39,.725],[.49,.719],[.57,.713],[.62,.689],[.69,.684],[.745,.656],[.8,.654],[.87,.627],[.94,.638],[1,.608]];
  function town(c,w,h) {
    const ground=x=>curve(hillPoints,x/w)*h;
    const bottom=.761*h;
    horizon(c,w,h,hillPoints,.757,'#454566',318,.28);
    for(let i=0;i<w*.63;i++) {
      const x=hash(i,88)*w, y=ground(x)+hash(i,89)*(.753*h-ground(x));
      rect(c,choose(['#484969','#4c4a68','#53506b','#57516c','#3e4265'], hash(i,90)),x,y,2+hash(i,91)*9);
    }
    const count=round(w*.29);
    for(let i=0;i<count;i++) {
      const x=hash(i,301)*w; if(x<w*.27 && i%5)continue;
      const depth=hash(i,302), y=ground(x)+depth*(bottom-ground(x))*.94;
      const scale=.44+depth*.45+Math.max(0,x/w-.5)*.3;
      const width=Math.max(2,round((2+hash(i,303)*5)*scale));
      const ht=Math.max(2,round((3+hash(i,304)*6)*scale));
      rect(c,choose(['#655b74','#6c6178','#78687c','#817080'],hash(i,305)),x,y-ht,width,ht);
      rect(c,'#55516b',x+width*.6,y-ht,Math.max(1,width*.35),ht);
      polygon(c,choose(['#514a65','#665369','#72566e'],hash(i,306)),[[x-1,y-ht+1],[x+width*.35,y-ht-2],[x+width+1,y-ht+1]]);
      if(width>=3 && i%4) rect(c,choose(['#f2b67e','#d79779','#ce9d8b','#ffe0a2'],hash(i,307)),x+1,y-ht+2);
      if(width>=5 && i%3) rect(c,'#b8948c',x+width-2,y-2);
    }

    // Notre-Dame's long nave, lantern tower and Gothic belfry above the old town.
    const unit=clamp(Math.min(w/535,h/300),.63,1.48);
    const cx=round(w*.837), cy=round(ground(cx)+2);
    c.save(); c.translate(cx,cy);
    const R=(col,x,y,a,b)=>rect(c,col,x*unit,y*unit,a*unit,b*unit);
    const P=(col,pts)=>polygon(c,col,pts.map(([x,y])=>[x*unit,y*unit]));
    const limestone='#ba9b9a', ashlar='#87788b', dusk='#5c5978', light='#e9bc9f';
    R(ashlar,-23,-5,36,6); P('#4f536f',[[-25,-5],[-18,-11],[4,-11],[11,-5]]);
    R(limestone,-9,-18,6,16); R(ashlar,-5,-17,3,15);
    P('#414c6d',[[-11,-18],[-6,-26],[-2,-18]]); R(dusk,-7,-28,1,4);
    R(ashlar,-22,-12,5,11); R(limestone,-22,-12,2,11);
    P(dusk,[[-24,-12],[-20,-18],[-16,-12]]);
    R(limestone,5,-20,7,21); R(ashlar,9,-20,4,21);
    R(dusk,4,-21,10,2); R(ashlar,6,-26,5,6); R('#dbb3a1',6,-25,1,6);
    P('#394661',[[4,-26],[7,-32],[8,-39],[9,-33],[13,-26]]); R('#293a59',8,-40,1,4);
    R(dusk,6,-17,1,4); R(dusk,9,-17,1,4); R(light,6,-9,1,3); R(light,10,-9,1,3);
    for(let x=-17;x<=1;x+=4){R(dusk,x,-4,1,4);R('#e6b394',x+1,-4,1,2);}
    c.restore();
    // Promenade lamps follow the lakeside and spill onto the dark embankment.
    for(let i=0;i<w*.19;i++) {
      const x=hash(i,321)*w, y=h*(.738+.014*Math.sin(x/w*8))+hash(i,322)*2;
      if(x<w*.35 && i%3)continue;
      rect(c,choose(['#e5af84','#c6897c','#efca96','#9e838a'],hash(i,323)),x,y,1+(i%7===0));
    }
  }

  function water(c,w,h) {
    const top=round(h*.751);
    const stops=[[0,'968498'],[.10,'686d90'],[.30,'4a6088'],[.62,'314e7b'],[1,'1c385b']];
    let k=1;
    for (let y=top;y<h;y++) {
      const t=(y-top)/(h-top-1);
      while(k<stops.length-1&&t>stops[k][0])k++;
      const a=stops[k-1],b=stops[k]; rect(c,lineColor(a[1],b[1],(t-a[0])/(b[0]-a[0])),0,y,w);
    }
    for(let i=0;i<w*1.6;i++) {
      const x=hash(i,351)*w,t=hash(i,352),y=top+(h-top)*t;
      const dark=i%4===0;
      const col=dark?'rgba(27,43,76,.28)':t<.45?'rgba(199,169,173,.28)':'rgba(154,163,192,.19)';
      rect(c,col,x,y,(1+hash(i,353)*6)*(1+t));
    }
    for(let i=0;i<w*.38;i++) {
      const x=hash(i,357)*w,dy=Math.pow(hash(i,358),2)*(.027+Math.max(0,x/w-.55)*.055)*h;
      if(x<w*.33 && i%3)continue;
      rect(c,i%5?'rgba(220,164,139,.5)':'rgba(252,204,152,.64)',x,top+dy,1+hash(i,359)*3);
    }
  }

  function steamer(c,w,h,x,y) {
    const s=clamp(Math.min(w/490,h/265),.64,1.42);
    c.save(); c.translate(round(x),round(y));
    const R=(col,a,b,d,e=1)=>rect(c,col,a*s,b*s,d*s,e*s);
    const P=(col,pts)=>polygon(c,col,pts.map(([a,b])=>[a*s,b*s]));
    R('rgba(17,36,66,.58)',-17,2,34); R('rgba(224,174,143,.38)',-11,3,20);
    P('#172a48',[[-22,-2],[21,-2],[18,1],[-16,2]]); R('#e6b99d',-21,-3,41);
    R('#b57270',-16,-1,33); R('#fbdab1',-16,-5,30,2);
    for(let a=-14;a<14;a+=4)R('#536079',a,-5,2);
    R('#d8a885',-18,-6,34); R('#ecccab',-9,-9,15,3);
    R('#4e536b',-7,-8,3); R('#4e536b',-2,-8,4); R('#796a77',-9,-10,16);
    R('#f1b078',1,-14,3,4); R('#3d425a',1,-15,3,2);
    R('#4e4863',-16,-13,1,10); R('#d1a391',-15,-13,3);
    R('#74617a',17,-9,1,6); R('#e38679',18,-9,3,2);
    c.restore();
  }

  function foreground(c,w,h) {
    const near='#182c43',front='#112538', lit='#33425a';
    const pine=(x,base,height,color,seed)=>{
      const crown=height*.16;
      rect(c,color,x-1,base-height*.9,Math.max(1,height*.043),height*.91);
      for(let layer=0;layer<6;layer++) {
        const top=base-height+layer*height*.124,wide=crown*(.22+layer*.165),dy=height*(.27+layer*.015);
        const pts=[[x,top],[x+wide*.28,top+dy*.36],[x+wide*.23,top+dy*.42],[x+wide*.65,top+dy*.69],
          [x+wide*.55,top+dy*.68],[x+wide,top+dy],[x+wide*.35,top+dy*.88],[x,top+dy*.98],
          [x-wide*.48,top+dy*.87],[x-wide*(.9+hash(layer,seed)*.2),top+dy],[x-wide*.48,top+dy*.62],
          [x-wide*.56,top+dy*.62],[x-wide*.23,top+dy*.38]];
        polygon(c,color,pts);
        if(height>30 && layer>1)rect(c,lit,x+wide*.62,top+dy*.85,Math.max(1,wide*.17));
      }
    };
    const shore=[[0,1.008],[.04,1],[.065,.992],[.099,.998],[.12,1.008],[.847,1.009],[.884,.993],[.918,.99],
      [.943,.966],[.961,.963],[.985,.946],[1,.941],[1.04,.94]];
    horizon(c,w,h,shore,1.03,front,397,.2);
    for(const [x,y,t,id] of [[.939,.993,.096,2],[.96,.983,.128,3],[.977,.973,.178,4],[.918,1,.058,5],[.051,1.012,.047,8],[.039,1.009,.073,9]]) {
      pine(x*w,y*h,t*h,id%2 ? near:front,id*23);
    }
  }

  function install(canvas) {
    const c=canvas.getContext('2d',{alpha:false});
    if(!c)return;
    if(!canvas.hasAttribute('aria-hidden')&&!canvas.hasAttribute('aria-label')){
      canvas.setAttribute('role','img'); canvas.setAttribute('aria-label','Pixel art of Lausanne and Lake Geneva at dusk. A paddle steamer crosses the lake beneath the moon.');
    }
    canvas.style.imageRendering='pixelated';
    const preference=window.matchMedia('(prefers-reduced-motion: reduce)');
    const moving=()=>document.documentElement.dataset.motion==='on'||(document.documentElement.dataset.motion!=='off'&&!preference.matches);
    let w=0,h=0,layers,g=0,view=true,anim=0,elapsed=0,previous=0,camera=0;
    function prepare(){
      const box=canvas.getBoundingClientRect(); if(!box.width||!box.height)return;
      const pixel=box.width<620 ? 1.9 : Math.max(2.15,box.width/720);
      const width=round(box.width/pixel),height=round(box.height/pixel);
      if(width===w && height===h && layers)return;
      w=canvas.width=width; h=canvas.height=height; c.imageSmoothingEnabled=false;
      g=round(w*.029)+3; const ww=w+g*2;
      layers=[
        sheet(ww,h,(a)=>sky(a,ww,h)),
        sheet(ww,h,(a)=>horizon(a,ww,h,[[0,.54],[.08,.5],[.16,.559],[.24,.517],[.31,.552],[.42,.461],[.47,.501],[.56,.447],[.64,.511],[.73,.454],[.85,.481],[.91,.427],[1,.47]],.77,'#a58aa0',28,1)),
        sheet(ww,h,(a)=>{
          const mountainWidth=Math.max(ww,h*1.36);
          a.translate(-round((mountainWidth-ww)*.61),0);
          alpine(a,mountainWidth,h);
        }),
        sheet(ww,h,(a)=>{
          horizon(a,ww,h,[[0,.631],[.075,.614],[.18,.657],[.25,.647],[.37,.681],[.455,.659],[.52,.678],[.64,.595],[.70,.611],[.78,.589],[.91,.662],[1,.6]],.766,'#666987',42,.68);
          horizon(a,ww,h,[[0,.674],[.07,.648],[.17,.698],[.29,.679],[.36,.704],[.43,.679],[.53,.69],[.63,.656],[.7,.679],[.81,.634],[.91,.642],[1,.653]],.767,'#515a7b',71,.47);
        }),
        sheet(ww,h,(a)=>town(a,ww,h)),sheet(ww,h,(a)=>water(a,ww,h)),sheet(ww,h,(a)=>foreground(a,ww,h))
      ];
      render();
    }
    function render(){
      if(!layers)return;
      const t=elapsed/1000,active=moving();
      if(active){
        const box=canvas.getBoundingClientRect();
        camera=clamp(-box.top/Math.max(1,box.height),0,1);
      }
      const dx=[0,.16,.32,.55,.76,.76,1],dy=[0,.018,.034,.045,.053,.053,-.014];
      for(let i=0;i<6;i++)c.drawImage(layers[i],-g-round(camera*g*dx[i]),-round(camera*h*dy[i]));
      // Extend the foreground water under the moving water plane on scroll.
      if(camera>.01)rect(c,'#1c385b',0,h-round(camera*h*.053),w,h*camera*.055);
      const waterTop=h*(.751-camera*.053);
      for(let i=0;i<87;i++){
        const depth=hash(i,444),phase=t*(.52+hash(i,445)*.75)+i*5.12;
        const flicker=(Math.sin(phase)+1)*.5;
        if(flicker<.27)continue;
        const span=w*(.008+depth*.095);
        const x=w*.79+(hash(i,446)-.5)*2*span-camera*g*.76+Math.sin(phase*.55)*1.4;
        const y=waterTop+2+depth*h*.226;
        rect(c,'rgba(248,189,150,'+((.18+.47*flicker)*(1-depth*.45))+')',x,y,(1+depth*7)*(.4+flicker));
      }
      const boatX=w*(.455+.11*Math.sin(t/69-.65))-camera*g*.96;
      const boatY=h*(.842-camera*.053)+.8*Math.sin(t*1.35);
      for(let i=0;i<14;i++){
        const tail=4+hash(i,463)*w*.092, swing=(Math.sin(t*1.1+i)+1)*.5;
        rect(c,'rgba(230,190,172,'+(.12+.20*swing)+')',boatX-19-tail,boatY+2+hash(i,464)*3,1+tail*.13);
      }
      steamer(c,w,h,boatX,boatY);
      c.drawImage(layers[6],-g-round(camera*g*dx[6]),-round(camera*h*dy[6]));
    }
    function tick(now) {
      anim=0;
      if(!view||document.hidden||!moving()){previous=0;return;}
      if(!previous||now-previous>=1000/16) {
        if(previous)elapsed+=Math.min(130,now-previous);
        previous=now;render();
      }
      anim=window.requestAnimationFrame(tick);
    }
    function resume() {
      if(anim)cancelAnimationFrame(anim);anim=0;previous=0;
      if(view&&!document.hidden){render();if(moving())anim=requestAnimationFrame(tick);}
    }
    prepare();resume();
    if('ResizeObserver' in window)new ResizeObserver(prepare).observe(canvas);
    else window.addEventListener('resize',prepare,{passive:true});
    if('IntersectionObserver' in window)new IntersectionObserver(([entry])=>{view=entry.isIntersecting;resume();}).observe(canvas);
    new MutationObserver(resume).observe(document.documentElement,{attributes:true,attributeFilter:['data-motion']});
    if(preference.addEventListener)preference.addEventListener('change',resume);
    document.addEventListener('visibilitychange',resume);
  }
  const start=()=>document.querySelectorAll('canvas[data-lake]').forEach(install);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
