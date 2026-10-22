'use strict';
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
const fmt=(n,digits=0)=>n==null?'—':Number(n).toLocaleString('it-IT',{maximumFractionDigits:digits});
const node=(tag,attrs={},text)=>{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;return e};
const label=(svg,x,y,text,attrs={})=>svg.append(node('text',{x,y,class:'chart-label',...attrs},text));
const pct=n=>fmt(n,1)+'%';
function heatColor(value){return [Math.round(239-203*value/100),Math.round(244-153*value/100),Math.round(251-74*value/100)]}
function heatText(value){const rgb=heatColor(value).map(n=>{const c=n/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4});const lum=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];return lum>=.179?'#000':'#fff'}
function svgRoot(width,height,description){const svg=node('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':description});return svg}
function title(el,text){el.append(node('title',{},text));return el}
function lineSegments(rows,valid,xy){const paths=[];let current=[];for(const r of rows){if(valid(r))current.push(xy(r));else{if(current.length)paths.push(current);current=[]}}if(current.length)paths.push(current);return paths}
const pointsPath=points=>points.map((p,i)=>(i?'L':'M')+p.join(',')).join(' ');
function init(data){
 $('content').hidden=false;
 const byYear=new Map(data.years.map(r=>[+r.period,r]));
 const first=Math.min(...data.years.map(r=>+r.period)),last=Math.max(...data.years.map(r=>+r.period));
 const years=Array.from({length:last-first+1},(_,i)=>first+i),rows=years.map(y=>byYear.get(y)||{period:String(y),entries:0});
 const W=Math.max(420,Math.round($('tone-chart').clientWidth)),compact=W<700,L=compact?42:70,R=compact?8:25,step=(W-L-R)/years.length,x=year=>L+step*(year-first+.5),barWidth=Math.min(32,step*.60);
 $('corpus').textContent=fmt(data.audit.analysedWords)+' parole lette · '+fmt(data.audit.analysedPassages)+' passaggi';
 $('span-label').textContent=first+'–'+last+' · tutti gli anni';
 document.querySelectorAll('.first-year').forEach(e=>e.textContent=first);document.querySelectorAll('.last-year').forEach(e=>e.textContent=last);
 $('model-note').textContent=data.model+'. L’analisi è eseguita in locale, senza inviare i testi a un servizio esterno.';
 $('coverage-note').textContent=`${data.audit.documents} documenti Word e un PDF di ${data.audit.pdfPages} pagine, ${data.audit.entries} sezioni conservate e ${fmt(data.audit.analysedWords)} parole analizzate. ${fmt(data.audit.undatedWords)} parole non hanno un anno affidabile. ${data.audit.documentsWithoutText} Word non contiene testo estraibile; il PDF integra ${data.audit.pdfAddedSections} sezioni e ne esclude ${data.audit.pdfDuplicateSections} già rappresentate nei Word.`;
 $('method-id').textContent=data.method+' · '+data.generated;
 const yTone=v=>165-v*105;
 const chart=svgRoot(W,440,'Tono contestuale annuale, variabilità fra i passaggi e quantità di testo. Anni mancanti lasciati vuoti.');
 chart.setAttribute('role','group');
 chart.append(node('rect',{x:L,y:60,width:W-L-R,height:105,fill:'#f4f8fd'}));
 chart.append(node('rect',{x:L,y:165,width:W-L-R,height:105,fill:'#fff8f3'}));
 for(const v of [-1,-.5,0,.5,1]){const y=yTone(v);chart.append(node('line',{x1:L,x2:W-R,y1:y,y2:y,class:'axis-line','stroke-dasharray':v===0?'0':'3 5'}));label(chart,L-14,y+4,v>0?'+'+fmt(v,1):fmt(v,1),{'text-anchor':'end'})}
 label(chart,L,28,'PIÙ PIACEVOLE',{'font-size':10});label(chart,L,292,'PIÙ SPIACEVOLE',{'font-size':10});
 const valid=r=>r.valence!=null;
 for(const seg of lineSegments(rows,valid,r=>[x(+r.period),r.valenceRange])){if(seg.length<2)continue;const upper=seg.map(([xx,range])=>[xx,yTone(range[1])]),lower=seg.map(([xx,range])=>[xx,yTone(range[0])]).reverse();chart.append(node('path',{d:pointsPath([...upper,...lower])+'Z',fill:'#dbe7fa',opacity:.9}))}
 for(const seg of lineSegments(rows,valid,r=>[x(+r.period),yTone(r.valence)])){if(seg.length>1)chart.append(node('path',{d:pointsPath(seg),fill:'none',stroke:'#245bb1','stroke-width':3,'stroke-linejoin':'round'}))}
 const maxWords=Math.max(...data.years.map(r=>r.words));
 const guide=node('line',{x1:0,x2:0,y1:45,y2:390,stroke:'#245bb1','stroke-dasharray':'3 5',opacity:.55,visibility:'hidden'});chart.append(guide);
 label(chart,L,332,'TESTO ANALIZZATO · PAROLE',{'font-size':10});
 for(const r of rows){const xx=x(+r.period);if(r.entries){const height=45*r.words/maxWords;chart.append(title(node('rect',{x:xx-barWidth/2,y:387-height,width:barWidth,height,fill:'#c6cbd2'}),`${r.period}: ${fmt(r.words)} parole, ${r.entries} sezioni`));if(valid(r))chart.append(title(node('circle',{cx:xx,cy:yTone(r.valence),r:compact?3.5:5.5,fill:'#245bb1',class:'point'}),`${r.period}: tono ${fmt(r.valence,2)}`))}else{chart.append(node('line',{x1:xx,y1:65,x2:xx,y2:385,stroke:'#b8bec7','stroke-dasharray':'3 6'}));label(chart,xx,318,'nessun dato',{'text-anchor':'middle','font-size':9})}label(chart,xx,413,r.period,{'text-anchor':compact?'end':'middle',class:'chart-label strong',style:`font-size:${compact?12:14}px`,transform:compact?`rotate(-45 ${xx} 413)`:'rotate(0)'});const hit=node('rect',{x:xx-step/2+2,y:45,width:step-4,height:378,class:'year-hit',tabindex:0,role:'button','aria-label':`Leggi ${r.period}: ${r.entries||0} sezioni`});const show=()=>readout(r);hit.addEventListener('pointerenter',show);hit.addEventListener('focus',show);hit.addEventListener('click',show);hit.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show()}});chart.append(hit)}
 $('tone-chart').replaceChildren(chart);
 function readout(r){guide.setAttribute('x1',x(+r.period));guide.setAttribute('x2',x(+r.period));guide.setAttribute('visibility','visible');$('year-readout').replaceChildren();const strong=document.createElement('strong');strong.textContent=r.period;$('year-readout').append(strong,document.createTextNode(' '));const content=document.createElement('span');content.textContent=r.entries?`${r.entries} sezioni · ${fmt(r.words)} parole · tono ${fmt(r.valence,2)} · temi: ${Object.entries(r.topics).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([t,v])=>t+' '+pct(v)).join(', ')}`:'Nessun gruppo di testi databile con copertura sufficiente. Il vuoto non indica tono neutro.';$('year-readout').append(content)}
 function heatmap(labels,key,target){const HW=1100,left=185,cell=(HW-left-25)/years.length,h=labels.length*39+48;const svg=svgRoot(HW,h,'Presenza annuale: '+labels.join(', '));labels.forEach((name,i)=>{label(svg,left-13,42+i*39,name,{'text-anchor':'end',class:'chart-label strong'});years.forEach((year,j)=>{const r=byYear.get(year),v=r?r[key][name]:null;const cx=left+j*cell,cy=20+i*39;const rect=node('rect',{x:cx+3,y:cy,width:cell-6,height:31,rx:2,fill:v==null?'#f5f5f5':`rgb(${Math.round(239-(239-36)*v/100)},${Math.round(244-(244-91)*v/100)},${Math.round(251-(251-177)*v/100)})`,stroke:v==null?'#bbb':'none','stroke-dasharray':v==null?'3 3':'0'});title(rect,`${year} · ${name}: ${v==null?'nessun dato':pct(v)}`);svg.append(rect);if(v!=null&&v>=10)label(svg,cx+cell/2,cy+20,fmt(v),{'text-anchor':'middle',style:`fill:${heatText(v)};font-size:14px`})})});years.forEach((year,j)=>label(svg,left+(j+.5)*cell,h-6,year,{'text-anchor':'middle'}));$(target).replaceChildren(svg)}
 heatmap(data.topics,'topics','topic-chart');heatmap(data.emotions,'emotions','emotion-chart');
 const top=Object.entries(data.overall.topics).sort((a,b)=>b[1]-a[1]).slice(0,3);$('topic-summary').textContent='Nel corpus completo: '+top.map(([name,v])=>name.toLowerCase()+' '+pct(v)).join(' · ')+'.';
 const concepts=Object.entries(data.overall.keywords);
 const literal=Object.entries(data.literalWords||{}).sort((a,b)=>b[1].count-a[1].count);
 for(const [word,info] of literal.slice(0,12)){
  const tr=document.createElement('tr'),name=document.createElement('td'),value=document.createElement('td'),plot=document.createElement('td');
  name.textContent=word;value.textContent=fmt(info.count);value.title=fmt(info.per1000,2)+' per 1.000 parole nel corpus';plot.className='spark';
  const svg=svgRoot(300,40,`Frequenza per 1.000 parole di ${word} dal ${first} al ${last}`),sx=y=>12+(y-first)/(last-first||1)*276;
  const maximum=Math.max(.1,...data.years.map(r=>r.literalWords?.[word]?.per1000||0));
  svg.append(node('line',{x1:10,y1:36,x2:290,y2:36,stroke:'#e5e7eb'}));
  for(const seg of lineSegments(rows,r=>!!r.entries,r=>[sx(+r.period),36-30*(r.literalWords?.[word]?.per1000||0)/maximum])){
   if(seg.length>1)svg.append(node('path',{d:pointsPath(seg),fill:'none',stroke:'#245bb1','stroke-width':1.8}));
  }
  for(const r of data.years)svg.append(title(node('circle',{cx:sx(+r.period),cy:36-30*(r.literalWords?.[word]?.per1000||0)/maximum,r:2.3,fill:'#245bb1'}),`${r.period}: ${fmt(r.literalWords?.[word]?.per1000||0,2)} per 1.000 parole`));
  plot.append(svg);tr.append(name,value,plot);$('word-trends').append(tr);
 }
 for(const [word,share] of concepts){const span=document.createElement('span');span.textContent=word;span.style.fontSize=(12+share*.18)+'px';span.title=pct(share)+' delle sezioni';$('word-field').append(span)}
 const positive=new Set(['Gioia','Serenità','Gratitudine','Curiosità','Motivazione']);
 for(const [name,share] of Object.entries(data.overall.emotions).sort((a,b)=>b[1]-a[1])){const row=document.createElement('div');row.className='emotion-row';const labelEl=document.createElement('span');labelEl.textContent=name;const track=document.createElement('div');track.className='track';const fill=document.createElement('span');fill.style.width=share+'%';fill.style.background=positive.has(name)?'#167347':'#ae6531';track.append(fill);const value=document.createElement('span');value.className='value';value.textContent=pct(share);row.append(labelEl,track,value);$('emotions').append(row)}
 const body=svgRoot(W,280,'Ore di sport e quota di sezioni con stanchezza, sullo stesso asse degli anni.');
 label(body,L,22,'SPORT REGISTRATO · ORE / ANNO',{'font-size':10});label(body,L,142,'STANCHEZZA NEI TESTI · % SEZIONI',{'font-size':10});
 const sports=data.sportYears||{},maxSport=Math.max(1,...Object.values(sports).map(r=>r.hours));
 for(const year of years){const xx=x(year),sport=sports[year],r=byYear.get(year);if(sport){const height=70*sport.hours/maxSport;body.append(title(node('rect',{x:xx-barWidth/2,y:108-height,width:barWidth,height,fill:'#167347'}),`${year}: ${fmt(sport.hours)} ore registrate`));label(body,xx,124,fmt(sport.hours),{'text-anchor':'middle',style:`font-size:${compact?10:14}px`})}else label(body,xx,100,'—',{'text-anchor':'middle'});if(r){const value=r.emotions.Stanchezza,height=65*value/100;body.append(title(node('rect',{x:xx-barWidth/2,y:224-height,width:barWidth,height,fill:'#b36c2d'}),`${year}: stanchezza in ${pct(value)} delle sezioni`));label(body,xx,239,pct(value),{'text-anchor':'middle',style:`font-size:${compact?10:14}px`})}else label(body,xx,210,'—',{'text-anchor':'middle'});label(body,xx,258,year,{'text-anchor':compact?'end':'middle',class:'chart-label strong',style:`font-size:${compact?12:14}px`,transform:compact?`rotate(-45 ${xx} 258)`:'rotate(0)'})}
 $('body-chart').replaceChildren(body);
 for(const r of rows){const tr=document.createElement('tr');for(const v of [r.period,fmt(r.entries),fmt(r.passages),fmt(r.words),fmt(r.valence,2),fmt(r.activation,2)]){const td=document.createElement('td');td.textContent=v;tr.append(td)}$('annual-table').append(tr)}
 $('status').hidden=true;$('content').hidden=false;
}
fetch('data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Dati non disponibili');return r.json()}).then(data=>{if(data.method!=='contextual-it-v2'||!data.years?.length||!data.audit.pdfPages||data.months)throw Error('La nuova lettura contestuale è ancora in corso.');init(data)}).catch(error=>{$('status').className='error';$('status').textContent=error.message+' Ricarica la pagina tra poco.'});
