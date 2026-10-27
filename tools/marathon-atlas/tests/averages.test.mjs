import test from 'node:test';
import assert from 'node:assert/strict';
import {fiveKmMeans,MARATHON} from '../src/lib/races.mjs';
const points=Array.from({length:86},(_,i)=>({d:i*500,t:i*120,hr:140+i,pace:240}));
test('pace uses elapsed/distance and HR integrates time, including final partial bin',()=>{const bins=fiveKmMeans(points);assert.equal(bins.length,9);assert.equal(bins[0].pace,240);assert.equal(bins[0].hr,145);assert.equal(bins[8].end,MARATHON);assert.ok(Math.abs(bins[8].pace-240)<1e-9);assert.ok(Math.abs(bins[8].hr-222.195)<1e-9);});
test('missing channels and recording gaps are not invented',()=>{assert.equal(fiveKmMeans(points.map(p=>({...p,hr:null})))[0].hr,null);const gapped=points.filter(p=>p.d<2000||p.d>4000);assert.equal(fiveKmMeans(gapped)[0].pace,null);assert.equal(fiveKmMeans(gapped)[0].hr,null);assert.equal(fiveKmMeans([])[0].pace,null);});
