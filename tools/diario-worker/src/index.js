/**
 * vita-diario — il pezzo di /vita che sa scrivere.
 *
 * /vita e' un file statico su GitHub Pages: puo' mostrare una giornata, non puo'
 * registrarne una. Questo Worker e' la meta' mancante. La pagina gli manda le
 * annotazioni, lui le tiene in D1 e le riserve subito — cosi' quello che annoti dal
 * telefono lo vedi dal portatile, senza aspettare una build.
 *
 * Quello che NON e': una seconda verita' sul cibo. `tools/food/data/food_log.csv`
 * resta l'unico registro. Qui le operazioni restano `applied_at IS NULL` finche' la
 * Action oraria non le travasa nel CSV, e da quel momento la pagina le legge da li'.
 * Una casella di posta con un'ora di vita, non un archivio parallelo.
 *
 * Chiavi (segreti del Worker, mai nel repo e mai nella pagina):
 *   VITA_DIARY_KEY    header `X-Vita-Key`   — la usa il browser, la digita Michele
 *   VITA_DIARY_ADMIN  header `X-Vita-Admin` — la usa la GitHub Action per svuotare
 *                                             la casella. Separata apposta: la chiave
 *                                             del browser vive in un localStorage, e
 *                                             non deve poter marcare niente come
 *                                             gia' finito nel repo.
 */

const ALLOWED_ORIGINS = [
  "https://micmer-git.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

const KINDS = new Set(["add", "set", "del"]);
const MEALS = new Set(["colazione", "spuntino", "pranzo", "merenda", "cena",
                       "non_specificato"]);
const MAX_QTY = 5000;        // g/ml: oltre, e' un dito scivolato sulla tastiera
const MAX_NOTE = 300;

function cors(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Vita-Key, X-Vita-Admin",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

const json = (body, status, origin) => new Response(JSON.stringify(body), {
  status: status || 200,
  headers: { "Content-Type": "application/json; charset=utf-8", ...cors(origin) },
});

/* Confronto a tempo costante: su un segreto corto un confronto normale perde
   informazione dal tempo di risposta. Costa niente, e toglie la domanda.
 *
 * Il `trim()` non e' pigrizia: `echo chiave | wrangler secret put` ci attacca un
 * a capo (su Windows un CRLF), e il segreto memorizzato diventa lungo due caratteri
 * in piu' di quello che chiunque digiterebbe. Il risultato e' un 401 su una chiave
 * giusta, senza niente nei log che lo spieghi — ci e' costato un giro di collaudo
 * il 2026-08-13. Meglio normalizzare qui che fidarsi di come e' stato caricato. */
function sameSecret(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  a = a.trim(); b = b.trim();
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const isDay = s => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s)
  && !isNaN(Date.parse(s + "T00:00:00Z"));
/* gli id sono quelli di foods.csv/recipes.csv: minuscole, cifre, underscore, e il
   prefisso `recipe:`. Tutto il resto non e' un id e non deve entrare nel CSV. */
const isFoodId = s => typeof s === "string" && s.length <= 64
  && /^(recipe:)?[a-z0-9_]+$/.test(s);

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const url = new URL(request.url);
    const p = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(origin) });
    }

    /* La salute e' pubblica: e' il `verify:` del registry, e non dice niente di
       privato — quanti giorni toccati e quante operazioni ancora da travasare. */
    if (p === "/api/health") {
      try {
        const r = await env.DB.prepare(
          "SELECT COUNT(*) AS tot, SUM(applied_at IS NULL) AS pending, " +
          "COUNT(DISTINCT day) AS giorni FROM ops").first();
        return json({ ok: true, ops: r.tot || 0, pending: r.pending || 0,
                      giorni: r.giorni || 0 }, 200, origin);
      } catch (e) {
        return json({ ok: false, errore: String(e && e.message || e) }, 500, origin);
      }
    }

    const key = request.headers.get("X-Vita-Key") || "";
    const admin = request.headers.get("X-Vita-Admin") || "";
    const isUser = !!env.VITA_DIARY_KEY && sameSecret(key, env.VITA_DIARY_KEY);
    const isAdmin = !!env.VITA_DIARY_ADMIN && sameSecret(admin, env.VITA_DIARY_ADMIN);

    try {
      /* ---- la pagina: leggi il giorno ------------------------------------ */
      if (request.method === "GET" && p.startsWith("/api/day/")) {
        if (!isUser) return json({ errore: "chiave non valida" }, 401, origin);
        const day = p.slice("/api/day/".length);
        if (!isDay(day)) return json({ errore: "data non valida" }, 400, origin);
        const { results } = await env.DB.prepare(
          "SELECT id, kind, meal, food_id, qty, row_key, note, created_at " +
          "FROM ops WHERE day = ? AND applied_at IS NULL ORDER BY id").bind(day).all();
        return json({ day, ops: results || [] }, 200, origin);
      }

      /* ---- la pagina: annota --------------------------------------------- */
      if (request.method === "POST" && p === "/api/ops") {
        if (!isUser) return json({ errore: "chiave non valida" }, 401, origin);
        let b;
        try { b = await request.json(); } catch { return json({ errore: "corpo non JSON" }, 400, origin); }

        if (!isDay(b.day)) return json({ errore: "data non valida" }, 400, origin);
        if (!KINDS.has(b.kind)) return json({ errore: "tipo non valido" }, 400, origin);

        const meal = String(b.meal || "");
        const note = String(b.note || "").slice(0, MAX_NOTE);
        let qty = null, foodId = "", rowKey = null;

        if (b.kind === "add") {
          if (!isFoodId(b.food_id)) return json({ errore: "alimento non valido" }, 400, origin);
          if (!MEALS.has(meal)) return json({ errore: "pasto non valido" }, 400, origin);
          qty = Number(b.qty);
          if (!isFinite(qty) || qty <= 0 || qty > MAX_QTY)
            return json({ errore: "quantita' fuori scala" }, 400, origin);
          foodId = b.food_id;
        } else {
          /* set e del si appoggiano a una riga che esiste gia' nella build: senza
             row_key non c'e' niente da correggere, e la riga finirebbe orfana */
          if (typeof b.row_key !== "string" || !b.row_key || b.row_key.length > 128)
            return json({ errore: "row_key mancante" }, 400, origin);
          rowKey = b.row_key;
          foodId = isFoodId(b.food_id) ? b.food_id : "";
          if (b.kind === "set") {
            qty = Number(b.qty);
            if (!isFinite(qty) || qty < 0 || qty > MAX_QTY)
              return json({ errore: "quantita' fuori scala" }, 400, origin);
          }
        }

        /* set/del: l'ultima parola vince. Senza questo, correggere tre volte la
           stessa riga lascerebbe tre correzioni pendenti e la Action applicherebbe
           quella sbagliata — e sarebbe anche l'unico modo di violare l'indice
           unico qui sotto. Le `add` invece si accumulano: due banane sono due. */
        const stmts = [];
        if (rowKey) {
          stmts.push(env.DB.prepare(
            "DELETE FROM ops WHERE day = ? AND row_key = ? AND applied_at IS NULL")
            .bind(b.day, rowKey));
        }
        stmts.push(env.DB.prepare(
          "INSERT INTO ops (day, kind, meal, food_id, qty, row_key, note, created_at) " +
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(b.day, b.kind, meal, foodId, qty, rowKey, note, new Date().toISOString()));
        await env.DB.batch(stmts);

        const row = await env.DB.prepare(
          "SELECT id, kind, meal, food_id, qty, row_key, note, created_at FROM ops " +
          "WHERE day = ? AND applied_at IS NULL ORDER BY id DESC LIMIT 1").bind(b.day).first();
        return json({ ok: true, op: row }, 201, origin);
      }

      /* ---- la pagina: disfa un'annotazione ancora pendente ---------------- */
      if (request.method === "DELETE" && p.startsWith("/api/ops/")) {
        if (!isUser) return json({ errore: "chiave non valida" }, 401, origin);
        const id = Number(p.slice("/api/ops/".length));
        if (!Number.isInteger(id) || id <= 0) return json({ errore: "id non valido" }, 400, origin);
        /* solo se ancora pendente: una volta nel CSV si corregge nel repo, non qui */
        const r = await env.DB.prepare(
          "DELETE FROM ops WHERE id = ? AND applied_at IS NULL").bind(id).run();
        const n = (r.meta && r.meta.changes) || 0;
        return n ? json({ ok: true }, 200, origin)
                 : json({ errore: "gia' travasata nel repo, o inesistente" }, 409, origin);
      }

      /* ---- la pipeline: cosa c'e' da travasare ---------------------------- */
      if (request.method === "GET" && p === "/api/pending") {
        if (!isAdmin) return json({ errore: "chiave admin non valida" }, 401, origin);
        const { results } = await env.DB.prepare(
          "SELECT id, day, kind, meal, food_id, qty, row_key, note, created_at " +
          "FROM ops WHERE applied_at IS NULL ORDER BY day, id").all();
        return json({ ops: results || [] }, 200, origin);
      }

      /* ---- la pipeline: fatto, sono nel repo ------------------------------ */
      if (request.method === "POST" && p === "/api/applied") {
        if (!isAdmin) return json({ errore: "chiave admin non valida" }, 401, origin);
        let b;
        try { b = await request.json(); } catch { return json({ errore: "corpo non JSON" }, 400, origin); }
        const ids = (Array.isArray(b.ids) ? b.ids : [])
          .map(Number).filter(n => Number.isInteger(n) && n > 0);
        if (!ids.length) return json({ ok: true, marcate: 0 }, 200, origin);
        const now = new Date().toISOString();
        /* a scaglioni: D1 ha un tetto sul numero di variabili per statement, e una
           casella rimasta indietro per giorni puo' averne piu' di quante ne passano */
        let marked = 0;
        for (let i = 0; i < ids.length; i += 100) {
          const chunk = ids.slice(i, i + 100);
          const r = await env.DB.prepare(
            `UPDATE ops SET applied_at = ? WHERE applied_at IS NULL AND id IN (${
              chunk.map(() => "?").join(",")})`).bind(now, ...chunk).run();
          marked += (r.meta && r.meta.changes) || 0;
        }
        return json({ ok: true, marcate: marked }, 200, origin);
      }

      return json({ errore: "non trovato" }, 404, origin);
    } catch (e) {
      return json({ errore: String(e && e.message || e) }, 500, origin);
    }
  },
};
