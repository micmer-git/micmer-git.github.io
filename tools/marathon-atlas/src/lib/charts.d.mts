import type {Race} from '../v2-types';
export function meanDomain(races:Race[],metric:'pace'|'hr'):[number,number];
export function metresPerBeat(pace:number|null,hr:number|null):number|null;
export function axisTicks(range:[number,number],metric:"pace"|"hr"):number[];
