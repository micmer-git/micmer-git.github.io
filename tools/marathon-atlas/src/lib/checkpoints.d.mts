import type {Point} from './races.mjs';
import type {Race} from '../v2-types';
export const SPLIT_DISTANCES:number[];
export function stepsUntil(points:Point[],distance:number):number|null;
export function checkpointStats(race:Race,distance:number):{distance:number;elapsed:number|null;steps:number|null};
