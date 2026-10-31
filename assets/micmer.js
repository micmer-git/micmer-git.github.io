/* Shared header and footer. One list, so a new public page is added here only. */
(function () {
  if (document.getElementById("mm-bar")) return;

  var LINKS = [
    ["Home", "/"],
    ["Vita", "/vita/"],
    ["Cibo", "/vita/cibo/"],
    ["Maratone", "/marathons/"],
    ["Come sto", "/vita/come-sto/"],
    ["Matrice", "/vita/matrice/"],
    ["Spostamenti", "/vita/spostamenti/"],
    ["Diario", "/diario-di-un-unno/"],
    ["Sogni", "/sogni-di-un-unno/"],
    ["Bici", "/bike-to-work/"],
    ["Salita", "/gazzaniga-orezzo/"],
    ["Cime", "/signoredellecime/"],
    ["Top 20", "/top-20/"],
    ["Viaggi", "/viaggi/"],
    ["kJ", "/signore-dei-kj.html"],
    ["League", "/league-of-strava/"]
  ];

  function norm(path) {
    var p = path || "/";
    if (p.length > 1 && p.endsWith("/index.html")) p = p.slice(0, -10);
    if (p === "/index.html") p = "/";
    return p;
  }

  var path = norm(location.pathname);
  var current = "";
  for (var i = 0; i < LINKS.length; i++) {
    var href = LINKS[i][1];
    if (href === "/") {
      if (path === "/") current = href;
      continue;
    }
    var hit = href.endsWith("/")
      ? path === href || path.indexOf(href) === 0
      : path === href;
    if (hit && href.length > current.length) current = href;
  }

  var bar = document.createElement("header");
  bar.className = "mm-bar";
  bar.id = "mm-bar";
  var nav = LINKS.map(function (item) {
    var on = item[1] === current ? ' aria-current="page"' : "";
    return '<a href="' + item[1] + '"' + on + ">" + item[0] + "</a>";
  }).join("");
  bar.innerHTML =
    '<a class="mm-skip" href="#mm-content">Vai al contenuto</a>' +
    '<a class="mm-brand" href="/"><i aria-hidden="true"></i>micmer</a>' +
    '<nav class="mm-nav" aria-label="Pagine di micmer">' + nav + "</nav>";

  var foot = document.createElement("footer");
  foot.className = "mm-foot";
  foot.innerHTML =
    "<p><strong>Michele Merelli</strong> · Bergamo</p>" +
    '<nav aria-label="In fondo">' + nav + "</nav>";

  document.body.insertBefore(bar, document.body.firstChild);
  if (document.documentElement.getAttribute("data-mm-mode") !== "overlay") {
    document.body.appendChild(foot);
  }

  /* Never rewrite an id that already exists. #root is where the home and the
     marathon atlas mount; renaming it leaves the page blank. */
  var target = document.querySelector("main, h1, #root");
  if (target && !target.id) target.id = "mm-content";
  var dest = document.getElementById("mm-content") || document.getElementById("root") || document.querySelector("main");
  if (dest && dest.id) bar.querySelector(".mm-skip").setAttribute("href", "#" + dest.id);
})();
