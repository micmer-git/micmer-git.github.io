export type Point={d:number;t:number;pace:number|null;altitude:number|null;hr:number|null;cadence:number|null};
export type Race={id:string;providerId:string;name:string;event:string;city:string|null;date:string;distance:number;elapsed:number;avgPace:number|null;elevation:number|null;avgHr:number|null;maxHr:number|null;cadence:number|null;points:Point[];route:number[][];routeSource:string|null;split:{first:number|null;second:number|null;delta:number|null};evidence:string;source:string;gaps:string[]};
export const MARATHON:number;
export function windowPace(points:Point[],start:number,end:number):number|null;
export function pace5k(points:Point[],d:number):number|null;
export function after30k(points:Point[]):number|null;
export const CHECKPOINTS:number[];
export function atDistance(points:Point[],d:number,key?:keyof Point):number|null;
export function rollingPace(points:Point[],d:number):number|null;
export function lateFade(points:Point[]):number|null;
export function paceStability(points:Point[]):number|null;
export function meanAtDistance(points:Point[],start:number,end:number,key?:keyof Point,step?:number):number|null;
export function hrDrift(points:Point[]):number|null;
export function gapAt(a:Race,b:Race,d:number):number|null;

export function fiveKmMeans(points:Point[]):{start:number;end:number;pace:number|null;hr:number|null}[];
