import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {checkpointStats,SPLIT_DISTANCES} from './src/lib/checkpoints.mjs';
const data=JSON.parse(await readFile('public/data/races.json','utf8'));
const fmt=n=>{const s=Math.round(n);return `${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`};
const url=process.env.QA_URL||'http://127.0.0.1:5195/marathons/';
await mkdir('artifacts',{recursive:true});const browser=await chromium.launch({channel:'msedge',headless:true});
try{for(const width of [320,390,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url+'#splits');await page.locator('.splits-table').waitFor();assert.equal(await page.locator('[data-checkpoint-race]').count(),9);
 for(const r of data.races){const row=page.locator(`[data-checkpoint-race="${r.id}"]`);for(const [i,d] of SPLIT_DISTANCES.entries()){const stat=checkpointStats(r,d);assert.equal(await row.locator('td strong').nth(i).innerText(),fmt(stat.elapsed));assert.equal(await row.locator('.split-steps').nth(i).innerText(),`≈ ${(Math.round(stat.steps/10)*10).toLocaleString('en-GB')} steps`);}}
 for(const [i,label] of ['10K','HM','30K','35K'].entries()){await page.locator('.split-sort').getByRole('button',{name:label,exact:true}).click();const fastest=[...data.races].sort((a,b)=>checkpointStats(a,SPLIT_DISTANCES[i]).elapsed-checkpointStats(b,SPLIT_DISTANCES[i]).elapsed)[0];assert.equal(await page.locator('[data-checkpoint-race]').first().getAttribute('data-checkpoint-race'),fastest.id);}
 await page.locator('.split-sort').getByRole('button',{name:'10K',exact:true}).click();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`artifacts/splits-${width}.png`,fullPage:true});
 if(width<700){await page.locator('.split-sort').getByRole('button',{name:'35K',exact:true}).click();assert.equal(await page.locator('.splits-table thead th:visible').count(),2);await page.screenshot({path:`artifacts/splits-35k-${width}.png`});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.locator('[data-checkpoint-race="i190801543"] th button').click();assert.match(await page.locator('.split-selection').innerText(),/Berlin/);await page.getByRole('button',{name:'races',exact:true}).click();assert.equal(await page.locator('.race-hero h1').innerText(),'Berlin');
 await page.goBack();await page.locator('.splits-table').waitFor();await page.reload();await page.locator('.splits-table').waitFor();assert.deepEqual(errors,[]);console.log(width,'PASS all 36 split times/steps, four rankings, responsive checkpoint columns, shared selection, hash navigation/reload');await page.close();
}}finally{await browser.close();}
