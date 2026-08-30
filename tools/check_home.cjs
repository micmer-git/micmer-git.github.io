/* Controlla che la home compili — cioe' che non sia bianca.
 *
 * `index.html` non e' una pagina statica: e' React scritto in JSX dentro un
 * <script type="text/babel">, che il BROWSER transpila al volo con
 * @babel/standalone preso da unpkg. Ha una proprieta' spiacevole: se il JSX non
 * compila, `#root` resta vuoto e **la pagina bianca risponde 200 con 80 KB**.
 * Nessun health check, nessuna Action, nessun `curl` se ne accorge.
 *
 * E' successo davvero. Il 2026-08-18 il commit 0938ccf ha scritto
 *
 *     desc: 'Le soste a Sorsi e Bocconi: ... e l'uscita che c'era prima.',
 *
 * — apostrofi dritti dentro una stringa fra apici singoli. Babel si e' fermato
 * su `Unexpected token, expected ","`, e Michele ha visto il sito giu' per due
 * giorni mentre ogni segnale restava verde.
 *
 * Qui la stessa transpilazione si fa PRIMA, sul file, senza browser e senza
 * rete: e' l'unica delle due strade possibili che funzioni senza un browser
 * (l'altra sarebbe cercare una stringa che compare solo dopo il render, ma il
 * DOM lo scrive il client, quindi quella stringa non esiste).
 *
 *   npm i --no-save @babel/standalone     # una volta, o in CI
 *   node tools/check_home.cjs             # 0 compila · 1 rotta · 2 saltato
 *
 * Esce 2 (saltato, non rotto) se @babel/standalone non c'e': su una macchina
 * senza npm install questo controllo non deve impedire di lavorare. In CI il
 * pacchetto si installa in un passo prima, quindi li' un 2 non puo' capitare.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PAGINE = process.argv.slice(2).length
  ? process.argv.slice(2)
  : [path.join(ROOT, "index.html")];

let babel;
try {
  babel = require("@babel/standalone");
} catch (e) {
  console.log("SALTATO: manca @babel/standalone.");
  console.log("  npm i --no-save @babel/standalone");
  process.exit(2);
}

/* Il blocco JSX con la riga a cui comincia nel file: senza quell'offset l'errore
   di Babel dice "riga 340" di un blocco che nessuno apre, invece della riga vera
   di index.html — che e' l'unica su cui si va a mettere le mani. */
function blocchi(html) {
  const out = [];
  const re = /<script([^>]*\btype=["']text\/babel["'][^>]*)>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    out.push({
      attrs: m[1].trim(),
      code: m[2],
      rigaIniziale: html.slice(0, m.index + m[0].indexOf(m[2])).split("\n").length,
      modulo: /data-type=["']module["']/.test(m[1]),
    });
  }
  return out;
}

let rotte = 0, compilati = 0;

for (const file of PAGINE) {
  const rel = path.relative(ROOT, file).replace(/\\/g, "/");
  if (!fs.existsSync(file)) {
    console.log(`ROTTA ${rel}: il file non esiste`);
    rotte++;
    continue;
  }
  const html = fs.readFileSync(file, "utf8");
  const bs = blocchi(html);

  if (rel === "index.html") {
    const sprite = path.join(ROOT, "assets", "illustrazioni-micmer.svg");
    const ids = ["michele", "bici", "valle", "corsa", "archivio", "libro", "app", "dati", "stampa", "viaggio", "risorse"];
    const emojiSegnaposto = /[📚🧭📊📰✈️📂]/u;
    if (!fs.existsSync(sprite)) {
      console.log("ROTTA index.html: manca lo sprite illustrato assets/illustrazioni-micmer.svg");
      rotte++;
    } else {
      const svg = fs.readFileSync(sprite, "utf8");
      const mancanti = ids.filter((id) => !svg.includes(`id="${id}"`) || !html.includes(`illustrazioni-micmer.svg#${id}`));
      if (mancanti.length) {
        console.log(`ROTTA index.html: illustrazioni mancanti o non usate — ${mancanti.join(", ")}`);
        rotte++;
      }
      if (!svg.includes("feTurbulence") || !svg.includes("feDisplacementMap")) {
        console.log("ROTTA index.html: lo sprite ha perso la grana ruvida della firma illustrata");
        rotte++;
      }
    }
    if (emojiSegnaposto.test(html)) {
      console.log("ROTTA index.html: sono tornate emoji segnaposto nelle card narrative");
      rotte++;
    }
  }

  if (!bs.length) {
    /* Una home che smette di essere JSX e' una notizia, non un successo
       silenzioso: se il blocco sparisce il controllo non protegge piu' niente
       e deve dirlo, invece di passare perche' non ha trovato nulla da fare. */
    console.log(`ROTTA ${rel}: nessun blocco <script type="text/babel"> — ` +
      `il controllo non sta piu' guardando niente`);
    rotte++;
    continue;
  }

  for (const b of bs) {
    try {
      babel.transform(b.code, {
        presets: ["react"],
        sourceType: b.modulo ? "module" : "script",
        filename: rel,
      });
      compilati++;
      const righe = b.code.split("\n").length;
      console.log(`ok   ${rel}: il blocco JSX compila (${righe} righe, ` +
        `dalla ${b.rigaIniziale})`);
    } catch (err) {
      rotte++;
      const loc = err.loc || {};
      const riga = loc.line ? b.rigaIniziale + loc.line - 1 : null;
      console.log(`ROTTA ${rel}: il blocco JSX NON compila — la pagina sarebbe bianca`);
      console.log(`  ${String(err.message).split("\n")[0]}`);
      if (riga) {
        console.log(`  ${rel}:${riga}${loc.column != null ? ":" + loc.column : ""}`);
        const testo = html.split("\n")[riga - 1];
        if (testo) console.log(`  > ${testo.trim().slice(0, 160)}`);
      }
    }
  }
}

console.log(rotte
  ? `\n${rotte} PAGINE ROTTE (${compilati} ok)`
  : `\ntutto a posto: ${compilati} blocchi compilano`);
process.exit(rotte ? 1 : 0);
