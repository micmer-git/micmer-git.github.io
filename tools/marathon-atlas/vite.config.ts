import {defineConfig} from 'vite';
export default defineConfig({
 base:'/marathons/',
 server:{host:'127.0.0.1',fs:{deny:['.env','.env.*','*.{crt,pem}','**/.git/**','**/.source/**','**/.cache/**']}},
});
