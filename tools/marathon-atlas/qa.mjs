import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile} from 'node:fs/promises';
import {fiveKmMeans} from './src/lib/races.mjs';
const data=JSON.parse(await readFile('public/data/races.json','utf8'));
await mkdir('artifacts',{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
try{for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.QA_URL||'http://127.0.0.1:5195/marathons/');await page.locator('.effort-chart').first().waitFor();
 assert.equal(await page.locator('.race-rail button').count(),9);
 assert.match(await page.locator('.start-line').innerText(),/80.3/);assert.equal(await page.locator('.volume-bars>div').count(),8);
 assert.equal(await page.locator('[data-mean-segment="pace"]').count(),9);assert.equal(await page.locator('[data-mean-segment="hr"]').count(),9);
 assert.equal(await page.locator('[data-raw-trace]').count(),2);
 const noOverflow=async()=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await noOverflow();await page.screenshot({path:`artifacts/context-${width}.png`,fullPage:true});
 await page.locator('.race-effort').scrollIntoViewIfNeeded();await page.screenshot({path:`artifacts/effort-${width}.png`});
 await page.getByRole('button',{name:'Focus race',exact:true}).click();await page.screenshot({path:`artifacts/focus-${width}.png`});
 await page.getByRole('button',{name:'Shared scale',exact:true}).click();
 await page.getByRole('checkbox',{name:'Faint recording'}).uncheck();assert.equal(await page.locator('[data-raw-trace]').count(),0);await page.getByRole('checkbox',{name:'Faint recording'}).check();
 await page.getByRole('button',{name:'overlay',exact:true}).click();assert.equal(await page.locator('[data-race-line]').count(),9);
 await page.screenshot({path:`artifacts/overlay-${width}.png`});
 await page.getByRole('button',{name:'BPM',exact:true}).click();assert.equal(await page.locator('[data-race-line]').count(),9);
 for(const r of data.races){const b=fiveKmMeans(r.points)[6];assert.match(await page.locator('.live-legend button').filter({hasText:r.city}).locator('b').innerText(),new RegExp(String(Math.round(b.hr))));}
 const axes=await page.locator('.effort-chart>g>text').allTextContents();
 await page.locator('.live-legend button').filter({hasText:'Boston'}).click();assert.deepEqual(await page.locator('.effort-chart>g>text').allTextContents(),axes);await noOverflow();await page.screenshot({path:`artifacts/bpm-${width}.png`});
 await page.getByRole('button',{name:'Pace × BPM',exact:true}).click();assert.equal(await page.locator('[data-efficiency-race]').count(),9);assert.equal(await page.locator('[data-efficiency-point="selected"]').count(),9);
 const dot=page.locator('.relation-chart circle[tabindex="0"]').nth(2);await dot.focus();await page.keyboard.press('Enter');assert.equal(await page.locator('input[type=range]').inputValue(),'10000');
 await noOverflow();await page.screenshot({path:`artifacts/relationship-${width}.png`});
 await page.getByRole('button',{name:'ghost',exact:true}).click();await page.locator('.ghost-readout').waitFor();assert.deepEqual(errors,[]);console.log(width,'PASS context, dual axes, shared scales, BPM readouts, scatter keyboard, raw toggle, ghost, no overflow/errors');await page.close();
}}finally{await browser.close();}
