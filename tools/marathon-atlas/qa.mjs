import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'msedge',headless:true});
for(const width of [390,1440]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.QA_URL||'http://127.0.0.1:5194/marathons/');await page.locator('.mean-panel').first().waitFor();
 assert.equal(await page.locator('.race-rail button').count(),9);
 console.log(width,await page.locator('.race-hero h1').innerText());
 assert.equal(await page.locator('[data-mean-segment="pace"]').count(),9);assert.equal(await page.locator('[data-mean-segment="hr"]').count(),9);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('.race-effort').scrollIntoViewIfNeeded();await page.screenshot({path:`artifacts/effort-${width}.png`});
 await page.getByRole('button',{name:'overlay',exact:true}).click();assert.equal(await page.locator('[data-race-line]').count(),9);
 await page.locator('.live-legend button').filter({hasText:'Boston'}).click();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:`artifacts/overlay-${width}.png`});
 await page.getByRole('button',{name:'ghost',exact:true}).click();await page.locator('.ghost-readout').waitFor();assert.deepEqual(errors,[]);console.log('PASS selection, 9 races, means, overlay, ghost, no overflow/errors');await page.close();
}
await browser.close();
