'use strict';
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
const fmt=(n,digits=0)=>n==null?'—':Number(n).toLocaleString('it-IT',{maximumFractionDigits:digits});
const node=(tag,attrs={},text)=>{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;return e};
const label=(svg,x,y,text,attrs={})=>svg.append(node('text',{x,y,class:'chart-label',...attrs},text));
const pct=n=>fmt(n,1)+'%';
function svgRoot(width,height,description){const svg=node('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':description});return svg}
function title(el,text){el.append(node('title',{},text));return el}
function lineSegments(rows,valid,xy){const paths=[];let current=[];for(const r of rows){if(valid(r))current.push(xy(r));else{if(current.length)paths.push(current);current=[]}}if(current.length)paths.push(current);return paths}
const pointsPath=points=>points.map((p,i)=>(i?'L':'M')+p.join(',')).join(' ');
function init(data){
 $('content').hidden=false;
 const byYear=new Map(data.years.map(r=>[+r.period,r]));
 const first=Math.min(...data.years.map(r=>+r.period)),last=Math.max(...data.years.map(r=>+r.period));
 const years=Array.from({length:last-first+1},(_,i)=>first+i),rows=years.map(y=>byYear.get(y)||{period:String(y),entries:0});
 const W=Math.max(240,Math.round($('tone-chart').clientWidth)),compact=W<700,L=compact?42:70,R=compact?8:25,step=(W-L-R)/years.length,x=year=>L+step*(year-first+.5),barWidth=Math.min(32,step*.60);
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
 // One card per series keeps every annual point visible on narrow screens.
 const series=(key,name)=>rows.map(r=>({year:+r.period,value:r.entries?(r[key]?.[name]??0):null}));
 const span=values=>{const present=values.filter(r=>r.value!=null);return present.length?Math.max(...present.map(r=>r.value))-Math.min(...present.map(r=>r.value)):0};
 function trendCard(name,values,target,{unit='%',color='#245bb1',ceiling=100}={}){
  const card=document.createElement('article');card.className='trend-card';
  const heading=document.createElement('h3');heading.textContent=name;card.append(heading);
  const present=values.filter(r=>r.value!=null),peak=present.reduce((a,b)=>b.value>a.value?b:a),low=present.reduce((a,b)=>b.value<a.value?b:a);
  const svg=svgRoot(360,146,`${name}, ${first}–${last}. ${unit==='%'?'Percentuale delle sezioni':'Occorrenze per 1.000 parole'}. Picco ${peak.year}: ${fmt(peak.value,1)} ${unit}.`);
  const left=27,right=12,top=15,bottom=112,max=Math.max(ceiling||0,.1,...present.map(r=>r.value)),sx=year=>left+(year-first)/(last-first||1)*(360-left-right),sy=value=>bottom-value/max*(bottom-top);
  for(const v of [0,max/2,max]){svg.append(node('line',{x1:left,x2:348,y1:sy(v),y2:sy(v),stroke:'#dfe2e6','stroke-dasharray':v===0?'0':'2 4'}));label(svg,left-5,sy(v)+3,fmt(v,max<10?1:0),{'text-anchor':'end',style:'font-size:11px'})}
  for(const seg of lineSegments(values,r=>r.value!=null,r=>[sx(r.year),sy(r.value)])){if(seg.length>1){svg.append(node('path',{d:pointsPath([...seg,[seg[seg.length-1][0],bottom],[seg[0][0],bottom]])+'Z',fill:color,opacity:.08}));svg.append(node('path',{d:pointsPath(seg),fill:'none',stroke:color,'stroke-width':2.4,'stroke-linejoin':'round'}))}}
  for(const r of values){if(r.value!=null)svg.append(title(node('circle',{cx:sx(r.year),cy:sy(r.value),r:r.year===peak.year?4:2.6,fill:color,stroke:'#fff','stroke-width':1}),`${r.year}: ${fmt(r.value,2)} ${unit}`));label(svg,sx(r.year),132,String(r.year).slice(2),{'text-anchor':'middle',style:'font-size:14px'})}
  card.append(svg);
  const note=document.createElement('div');note.className='trend-note';
  const range=document.createElement('span');range.textContent=`${fmt(low.value,1)}–${fmt(peak.value,1)}${unit==='%'?'%':' /1.000'}`;
  const high=document.createElement('span');high.textContent=`picco ${peak.year}`;note.append(range,high);card.append(note);$(target).append(card);
 }
 data.topics.forEach(name=>trendCard(name,series('topics',name),'topic-chart'));
 data.emotions.forEach(name=>trendCard(name,series('emotions',name),'emotion-chart',{color:'#a85c28'}));
 const concepts=Object.keys(data.overall.keywords).map(name=>({name,values:series('keywords',name)})).sort((a,b)=>span(b.values)-span(a.values));
 concepts.slice(0,8).forEach(r=>trendCard(r.name,r.values,'concept-trends'));
 const literal=Object.entries(data.literalWords||{}).filter(([,info])=>info.count>=10).map(([name])=>({name,values:rows.map(r=>({year:+r.period,value:r.entries?(r.literalWords?.[name]?.per1000??0):null}))})).sort((a,b)=>span(b.values)-span(a.values));
 literal.slice(0,8).forEach(r=>trendCard(r.name,r.values,'word-trends',{unit:'/1.000',ceiling:0,color:'#167347'}));
 // Numeric insights describe annual textual estimates, never wellbeing or causes.
 function insight(labelText,valueText,detailText){const item=document.createElement('article');item.className='insight';const h=document.createElement('h3');h.textContent=labelText;const value=document.createElement('p');value.className='insight-value';value.textContent=valueText;const detail=document.createElement('p');detail.textContent=detailText;item.append(h,value,detail);$('change-insights').append(item)}
 const changes=rows.slice(1).flatMap((r,i)=>r.valence!=null&&rows[i].valence!=null?[{from:rows[i],to:r,delta:r.valence-rows[i].valence}]:[]).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
 if(changes.length){const c=changes[0];insight('Il salto di tono nei testi più ampio',`${c.delta>0?'+':''}${fmt(c.delta,2)}`,`${c.from.period} → ${c.to.period} · scala −1 / +1`)}
 for(const [names,key,labelText] of [[data.topics,'topics','Il tema con più variazione'],[data.emotions,'emotions','L’emozione con più variazione']]){const all=names.map(name=>({name,values:series(key,name)})).sort((a,b)=>span(b.values)-span(a.values)),r=all[0],valid=r.values.filter(v=>v.value!=null),lo=valid.reduce((a,b)=>b.value<a.value?b:a),hi=valid.reduce((a,b)=>b.value>a.value?b:a);insight(labelText,r.name,`Min ${lo.year}: ${pct(lo.value)} · max ${hi.year}: ${pct(hi.value)} · escursione ${fmt(span(r.values),1)} punti %`)}
 const body=svgRoot(W,280,'Ore di sport e quota di sezioni con stanchezza, sullo stesso asse degli anni.');
 label(body,L,22,'SPORT REGISTRATO · ORE / ANNO',{'font-size':10});label(body,L,142,'STANCHEZZA NEI TESTI · % SEZIONI',{'font-size':10});
 const sports=data.sportYears||{},maxSport=Math.max(1,...Object.values(sports).map(r=>r.hours));
 for(const year of years){const xx=x(year),sport=sports[year],r=byYear.get(year);if(sport){const height=70*sport.hours/maxSport;body.append(title(node('rect',{x:xx-barWidth/2,y:108-height,width:barWidth,height,fill:'#167347'}),`${year}: ${fmt(sport.hours)} ore registrate`));if(W>=500)label(body,xx,124,fmt(sport.hours),{'text-anchor':'middle',style:`font-size:${compact?10:14}px`})}else label(body,xx,100,'—',{'text-anchor':'middle'});if(r){const value=r.emotions.Stanchezza,height=65*value/100;body.append(title(node('rect',{x:xx-barWidth/2,y:224-height,width:barWidth,height,fill:'#b36c2d'}),`${year}: stanchezza in ${pct(value)} delle sezioni`));if(W>=500)label(body,xx,239,pct(value),{'text-anchor':'middle',style:`font-size:${compact?10:14}px`})}else label(body,xx,210,'—',{'text-anchor':'middle'});label(body,xx,258,year,{'text-anchor':compact?'end':'middle',class:'chart-label strong',style:`font-size:${compact?12:14}px`,transform:compact?`rotate(-45 ${xx} 258)`:'rotate(0)'})}
 $('body-chart').replaceChildren(body);
 for(const r of rows){const tr=document.createElement('tr');for(const v of [r.period,fmt(r.entries),fmt(r.passages),fmt(r.words),fmt(r.valence,2),fmt(r.activation,2)]){const td=document.createElement('td');td.textContent=v;tr.append(td)}$('annual-table').append(tr)}
 $('status').hidden=true;$('content').hidden=false;
}
async function load(){
 $('status').className='loading';$('status').textContent='Caricamento dei grafici…';$('status').hidden=false;
 try{const response=await fetch('data.json',{cache:'no-store'});if(!response.ok)throw Error('http');const data=await response.json();if(data.method!=='contextual-it-v2'||!data.years?.length||!data.audit.pdfPages||data.months)throw Error('schema');init(data)}
 catch(error){$('content').hidden=true;$('status').className='error';$('status').replaceChildren(document.createTextNode('Impossibile caricare i dati dei grafici. Controlla la connessione e riprova. '));const retry=document.createElement('button');retry.type='button';retry.textContent='Riprova';retry.addEventListener('click',load);$('status').append(retry);if(['localhost','127.0.0.1'].includes(location.hostname)){const link=document.createElement('a');link.href='https://micmer-git.github.io/vita/come-sto/';link.textContent='Apri il sito online';$('status').append(document.createTextNode(' '),link)}}
}
load();
