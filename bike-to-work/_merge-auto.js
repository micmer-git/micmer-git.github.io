/* Merge GPS-confirmed additions without changing the reviewed historical archive. */
(function mergeCommutes(){
  if(typeof AUTO_SYNC==='undefined')return;
  for(const record of AUTO_SYNC.records){
    const list=record.sport==='Run'?RUNS:DAYS, row=record.day;
    if(list.some(day=>(day.acts||[]).includes(record.id)))continue;
    const existing=list.find(day=>day.d===row.d);
    if(!existing)list.push(JSON.parse(JSON.stringify(row)));
    else{
      for(const direction of ['tw','th']){
        const next=row.legs[direction],old=existing.legs[direction];
        if(next&&(!old||(direction==='tw'?next.c0<old.c0:next.c1>old.c1)))existing.legs[direction]={...next};
      }
      existing.acts.push(record.id);
      if(row.missingCalories)existing.missingCalories=true;
      existing.cal+=row.cal;existing.km=Math.round((existing.km+row.km)*10)/10;existing.gain+=row.gain;
      if(row.name!==existing.name)existing.name+=' / '+row.name;
    }
    TRACKS[record.id]=record.track;
  }
  for(const list of [DAYS,RUNS]){
    list.sort((a,b)=>a.d.localeCompare(b.d));
    for(const row of list){
      if(!row.acts.some(id=>AUTO_SYNC.records.some(r=>r.id===id)))continue;
      const {tw,th}=row.legs;
      if(tw&&th&&th.c0>=tw.c1)row.dwell=th.c0-tw.c1;
    }
  }
  addEventListener('DOMContentLoaded',()=>{
    const note=document.createElement('p');note.className='auto-sync-note';
    note.textContent='Controllo automatico Intervals.icu: '+AUTO_SYNC.checkedThrough+' · nuove tratte riconosciute via GPS casa/lavoro (raggio '+AUTO_SYNC.radiusM+' m).';
    const missing=AUTO_SYNC.records.filter(r=>r.day.missingCalories).length;
    if(missing)note.textContent+=' Calorie e equivalenti alimentari parziali: '+missing+' attività senza calorie registrate.';
    const target=document.querySelector('footer')||document.querySelector('main')||document.body;target.appendChild(note);
  });
})();
