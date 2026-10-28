const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.join(__dirname,'../bike-to-work');const context=vm.createContext({addEventListener:()=>{}});
vm.runInContext(fs.readFileSync(path.join(dir,'_data.js'),'utf8')+';globalThis.baseline=JSON.stringify({days:DAYS,runs:RUNS});',context);
vm.runInContext(fs.readFileSync(path.join(dir,'_auto.js'),'utf8'),context);
const merge=fs.readFileSync(path.join(dir,'_merge-auto.js'),'utf8');vm.runInContext(merge,context);
const capture=()=>vm.runInContext('JSON.stringify({days:DAYS,runs:RUNS,tracks:TRACKS})',context);
const snapshot=capture(),data=JSON.parse(snapshot),base=JSON.parse(context.baseline);
for(const [list,old] of [[data.days,base.days],[data.runs,base.runs]]){
 assert.equal(new Set(list.map(d=>d.d)).size,list.length,'unique days');
 assert.deepEqual(list.map(d=>d.d),list.map(d=>d.d).sort(),'chronological');
 for(const d of old){const found=list.find(x=>x.d===d.d);assert(found);for(const id of d.acts)assert(found.acts.includes(id),'preserve historical activity');}
 for(const d of list)for(const leg of Object.values(d.legs)){assert(leg.elapsed>0&&leg.moving>=0&&leg.moving<=leg.elapsed);assert(leg.c1>=leg.c0);}
}
vm.runInContext(merge,context);assert.equal(capture(),snapshot,'replay is idempotent');
console.log(`Bike to Work OK: ${data.days.length} bike days, ${data.runs.length} run days; unique, ordered, historical IDs retained, replay unchanged.`);
