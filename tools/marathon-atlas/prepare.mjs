import {mkdir,copyFile} from 'node:fs/promises';
await mkdir(new URL('./public/data/',import.meta.url),{recursive:true});
await copyFile(new URL('../../marathons/data/races.json',import.meta.url),new URL('./public/data/races.json',import.meta.url));
