// Prova viva della front page: browser vero, console e rendering.
const puppeteer = require('C:/Users/micme/Desktop/micmer/know-how/ff-assets/node_modules/puppeteer');

(async () => {
  const url = process.argv[2] || 'https://micmer-git.github.io/?v=' + process.pid;
  const b = await puppeteer.launch({ headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 420, height: 900 });
  const errori = [];
  p.on('pageerror', e => errori.push('js: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errori.push('console: ' + m.text().slice(0, 300)); });
  try {
    await p.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
  } catch (e) { errori.push('goto: ' + e.message); }
  await new Promise(r => setTimeout(r, 6000));
  const esito = await p.evaluate(() => {
    const root = document.getElementById('root');
    return {
      rootPresente: !!root,
      rootFigli: root ? root.children.length : -1,
      rootTesto: root ? root.innerText.slice(0, 200) : null,
      bodyTesto: document.body.innerText.slice(0, 200),
      titolo: document.title,
    };
  });
  console.log(JSON.stringify({ url, esito, errori }, null, 2));
  await b.close();
})();
