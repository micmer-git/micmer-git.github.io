#!/usr/bin/env python3
"""top-20, v3: lo stesso racconto come **video**, non piu' come GIF.

Perche' un file diverso e non una bandiera in piu' su `build_top20_reel.py`: quel
tool e' costruito attorno a un vincolo che qui non esiste. In una GIF **tenere un
frame e' gratis** e **cambiare la scala della mappa costa 40 kB**, e da quelle due
frasi discende tutto il montaggio: camera bloccata mentre la traccia si disegna,
zoom ridotti a due frame, note spinte in una colonna di lato perche' una pagina a
tutto schermo in piu' voleva dire una dissolvenza in piu' da pagare. In un video
non e' vero niente di tutto cio': i fermo-immagine costano (sono frame veri) e il
movimento e' quasi gratis, perche' h264 — o qui MPEG-4 — comprime bene proprio
quello che la GIF comprimeva male. Sono due montaggi opposti, e tenerli nello
stesso file avrebbe voluto dire un `if` a ogni riga. Le primitive di disegno,
quelle si', sono le stesse: si importano da `build_top20_reel`.

Cosa cambia rispetto al reel:

1. **La durata di un testo si stima dalla sua lunghezza.** Nella GIF ogni blocco
   stava cinque secondi, lungo o corto che fosse: una regola sola perche' tenere
   costava zero e non valeva la pena distinguere. Qui una pausa sono trenta frame
   al secondo di file, quindi `read_ms()` conta le parole e paga il giusto.

2. **Le note vanno a tutto schermo.** Erano in una colonna di fianco alla traccia
   perche' era l'unico posto gratis. Ora il montaggio e' quello chiesto: la mappa
   si dissolve nel commento, il commento si legge, si torna sulla mappa **e la
   traccia riparte da dove si era fermata**, fino alla nota dopo.

3. **La camera segue il puntino, da vicino.** Il divieto di cambiare scala mentre
   si disegna era una regola di budget GIF, non di racconto. Qui il tratto si apre
   sull'inquadratura intera, stringe sul puntino e lo segue, e alla fine allarga a
   rivelare la forma completa del giro.

4. **Le dissolvenze respirano.** Mezzo secondo con una deriva di scala minima
   (1,00 → 1,04) invece del taglio in due frame: e' la differenza fra "cambio
   pagina" e "stacco".

Il video si scrive con OpenCV, che ha ffmpeg dentro. **Il codec e' `mp4v`
(MPEG-4 Part 2) e non h264**: OpenCV pretende `openh264-*.dll` per l'avc1 vero,
sul portatile non c'e', e senza quella libreria `avc1` non fallisce — ripiega in
silenzio su un intra-only da 61 kB/frame, cioe' cinque volte tanto. Misurato:
mp4v fa 45 MB per 6'28" a 760 px, e sul testo non si vede un artefatto. Se un
giorno serve h264 vero, la conversione si fa a valle da questo file.

    python tools/build_top20_video.py                       # tutto, 760 px
    python tools/build_top20_video.py --only 1,19 --size 640 --probe-sec 0
"""
import argparse
import os
import sys
import time

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_top20_reel as R                                          # noqa: E402
from build_top20_gif import AC, BG, INK3, font                        # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

OUT = os.path.join(HERE, "..", "top-20", "top-20-reel.mp4")


# ------------------------------------------------------------------ il tempo

def read_ms(*texts, base=700, wpm=205, lo=1700, hi=8000):
    """Quanto tenere un blocco di testo, dalle parole che contiene.

    205 parole al minuto e' lettura attenta, non scorrimento: e' testo grande,
    centrato, letto una volta sola e senza poter tornare indietro. `base` sono i
    decimi che servono all'occhio per trovare l'inizio della riga dopo una
    dissolvenza — non dipendono dalla lunghezza, quindi stanno fuori dal conto.

    Il tetto a otto secondi e' stato misurato al contrario, dal primo montaggio:
    senza tetto la scheda dell'Ironman (33 parole) restava 11,6 s, e undici secondi
    fermi su una pagina non si leggono come lentezza, si leggono come un video
    bloccato. Oltre le ~27 parole il testo va tagliato, non tenuto di piu'.
    """
    words = sum(len(t.split()) for t in texts if t)
    return int(min(hi, max(lo, base + words * 60000.0 / wpm)))


def card_ms(st, minus=0):
    """La scheda del giorno. Due correzioni sul conto crudo delle parole.

    La **data non si legge**, si riconosce: "5 giugno 2016" sono tre parole che
    costano un decimo di secondo, non un secondo, quindi il kicker resta fuori dal
    conto. E `minus` toglie il tempo del montaggio della scheda, durante il quale
    il testo e' gia' in pagina e gia' si sta leggendo: contarlo due volte era quel
    che rendeva le schede interminabili.
    """
    card = st.get("card") or [["date", st["kicker"]], ["lead", st["title"]]]
    body = [t for k, t in card if k != "date"]
    return max(1600, read_ms(*body, base=900) - minus)


# ------------------------------------------------------------------ le pagine

def note_card(S, fonts, text, st, n, total, ac, alpha=1.0):
    """Un commento a tutto schermo: la pagina che nella GIF non ci si poteva
    permettere.

    Il testo breve va grande, quello lungo va in corpo: sopra le novanta battute
    il "big" andrebbe a quattro righe e a quel punto non e' piu' un'affermazione,
    e' un paragrafo, e si legge meglio piccolo. `text_card` mette gia' in corsivo
    le citazioni in corpo, che e' esattamente il caso delle note prese dal diario.
    """
    kind = "big" if len(R.plain(text)) <= 90 else "body"
    lines = [("%02d · %s" % (n, st["kicker"].upper()), "kicker"), (text, kind)]
    return R.text_card(S, fonts, alpha, lines, ac, n, total)


# ------------------------------------------------------------------ i raccordi

def drift(im, S, k):
    """La stessa immagine con una deriva di scala minima attorno al centro.

    Serve solo alle dissolvenze: due pagine che si scambiano stando perfettamente
    ferme sembrano un errore di caricamento, le stesse due con un quarantesimo di
    scala addosso sembrano un movimento di macchina. Sotto l'1 % non si vede, sopra
    il 6 % si legge come uno zoom e distrae dal testo.
    """
    if abs(k - 1.0) < 0.002:
        return im
    w = max(1, int(round(S * k)))
    big = im.resize((w, w), Image.LANCZOS)
    if k >= 1.0:
        o = (w - S) // 2
        return big.crop((o, o, o + S, o + S))
    c = Image.new("RGB", (S, S), BG)
    c.paste(big, ((S - w) // 2, (S - w) // 2))
    return c


# ------------------------------------------------------------------ montaggio

def build(stories, S, fonts, args, emit):
    """Il taglio. `emit(im, ms)` incassa un frame e per quanto resta a schermo.

    Il montaggio e' quello chiesto: scheda del giorno a tutto schermo, volo sul
    globo, poi il tratto che si disegna **a segmenti**, e fra un segmento e
    l'altro il commento prende tutto lo schermo. Al ritorno la traccia non
    ricomincia: riparte dal punto esatto in cui l'aveva lasciata, che e' l'unica
    cosa che rende la sequenza un racconto invece che una serie di clip.
    """
    total = len(stories)
    dots = [(s["clat"], s["clon"], AC.get(s["st"]["accent"], AC["stone"])) for s in stories]
    FMS = 1000.0 / args.fps                       # un frame di video
    nf = lambda sec: max(1, int(round(sec * args.fps)))

    def moving(n, fn, ms=None):
        for k in range(n):
            emit(fn((k + 1) / float(n)), ms or FMS)

    def cross(a, b, sec, k0=1.0, k1=1.02):
        """Da una pagina all'altra, con la deriva addosso a tutte e due."""
        n = nf(sec)
        for k in range(n):
            t = R.ease((k + 1) / float(n))
            emit(Image.blend(drift(a, S, R.lerp(k0, k1, t)),
                             drift(b, S, R.lerp(2.0 - k1, 1.0, t)), t), FMS)

    def page(make, hold_ms, sec_in=0.45, sec_out=0.35, prev=None):
        """Una pagina di testo: entra, si legge, esce sulla carta."""
        full = make(1.0)
        if prev is not None:
            cross(prev, full, sec_in)
        else:
            moving(nf(sec_in), lambda t: make(R.ease(t)))
        emit(full, hold_ms)
        if sec_out:
            moving(nf(sec_out), lambda t: R.to_paper(full, R.ease(t), S))
        return full

    # --- apertura
    if args.intro or not args.only:
        page(lambda a: R.text_card(S, fonts, a,
                                   [("micmer · archivio 2015 – 2026", "kicker"),
                                    ("Venti giorni", "big"), ("su 2.923", "big"),
                                    ("Undici anni di GPS. Ogni traccia è quella vera.", "body")]),
             read_ms("Venti giorni su 2.923", "Undici anni di GPS. Ogni traccia è quella vera.",
                     base=1400))
        page(lambda a: R.text_card(S, fonts, a,
                                   [("98.830 chilometri. 1.843.198 metri di dislivello.", "body"),
                                    ("4.928 ore in movimento.", "body"),
                                    ("Venti giorni raccontati, uno alla volta.", "body")]),
             read_ms("98.830 chilometri. 1.843.198 metri di dislivello.",
                     "4.928 ore in movimento.", "Venti giorni raccontati, uno alla volta."))
        moving(nf(1.6), lambda t: R.globe_frame(S, 46, 9, dots, fonts,
                                                upto=int(t * (total - 1)),
                                                radius=R.lerp(0.30, 0.86, R.ease(t))))
        emit(R.globe_frame(S, 46, 9, dots, fonts, upto=total - 1), 900)

    prev_map = None
    for si, story in enumerate(stories):
        st = story["st"]
        ac = AC.get(st["accent"], AC["stone"])
        race = st.get("mode") == "race"
        plat, plon = (stories[si - 1]["clat"], stories[si - 1]["clon"]) if si else (46, 9)

        # --- si esce dalla mappa precedente sciogliendola nella carta
        if prev_map is not None:
            moving(nf(0.5), lambda t: R.to_paper(R.on_paper(prev_map,
                                                            R.lerp(1.0, 0.55, R.ease(t)), S),
                                                 R.ease(t), S))

        # --- la scheda del giorno, che si monta da sola e resta il tempo che serve
        cin = nf(args.cardin_sec)
        moving(cin, lambda t: R.story_card(S, fonts, st, si + 1, total, t, ac))
        full_card = R.story_card(S, fonts, st, si + 1, total, 1.0, ac)
        emit(full_card, card_ms(st, minus=int(args.cardin_sec * 1000 * 0.6)))
        moving(nf(0.4), lambda t: R.to_paper(full_card, R.ease(t), S))

        # --- il volo: il globo cresce, ruota, e la mappa entra sulla carta
        target = R.map_frame(story, 0, 0.0, 1.0, S, fonts, cap_alpha=0.0, total=total)
        moving(nf(args.fly_sec),
               lambda t: R.globe_frame(S, R.lerp(plat, story["clat"], R.ease(t)),
                                       R.lerp(plon, story["clon"], R.ease(t)), dots, fonts,
                                       upto=si if t > .45 else max(0, si - 1),
                                       radius=R.lerp(0.26, 0.90, R.ease(min(1, t * 1.25)))))
        moving(nf(0.55), lambda t: R.on_paper(target, R.lerp(0.38, 1.0, R.ease(t)), S))

        for li, l in enumerate(story["legs"]):
            if race and li > 0:
                break                     # in gara le cinque edizioni corrono insieme

            # quanto dura il disegno di questo tratto: la gara si guarda di piu',
            # i tratti di una giornata spezzata di meno
            sec = (args.draw_sec * 1.7 if race else
                   args.draw_sec if len(story["legs"]) == 1 else
                   max(2.4, args.draw_sec * 0.62))
            # la camera stringe solo se c'e' una traccia sola da seguire: in gara
            # servono tutte e cinque nell'inquadratura, o non c'e' confronto
            zmax = 1.0 if race else args.zdraw

            notes = sorted(l["leg"].get("notes") or [], key=lambda x: R.note_at(l, x))
            stops = [(R.note_at(l, nt), nt) for nt in notes]
            stops = [(p, nt) for p, nt in stops if 0.04 < p < 0.985]

            def cam(p):
                """Zoom e inseguimento a questo punto del tratto.

                Si apre largo, stringe entro il primo 18 % e molla nell'ultimo 12 %:
                cosi' il tratto si legge tre volte — la forma prima, il dettaglio
                durante, la forma finita dopo.
                """
                if zmax <= 1.0:
                    return 1.0, 0.0
                u = (min(1.0, p / 0.18) if p < 0.18 else
                     1.0 - min(1.0, (p - 0.88) / 0.12) if p > 0.88 else 1.0)
                z = R.lerp(1.0, zmax, R.ease(u))
                return z, R.ease(u)

            def shot(p, note=None, na=0.0):
                z, fo = cam(p)
                return R.map_frame(story, li, p, z, S, fonts, cap_alpha=1.0,
                                   total=total, follow=fo, caption="")

            # apertura del tratto sull'inquadratura intera, per leggere la forma
            emit(shot(0.005), 700 if li == 0 else 400)

            prev_p = 0.0
            for k, (at, nt) in enumerate(stops + [(1.0, None)]):
                span = max(0.02, at - prev_p)
                n = max(2, nf(sec * span))
                for j in range(n):
                    p = prev_p + span * (j + 1) / float(n)
                    emit(shot(p), FMS)
                prev_p = at
                if nt is None:
                    break
                # --- il commento prende tutto lo schermo, poi si torna
                held = shot(at)
                emit(held, 260)                       # un attimo di sospensione
                card = note_card(S, fonts, nt["text"], st, si + 1, total, ac)
                cross(held, card, 0.55)
                emit(card, read_ms(nt["text"]))
                cross(card, held, 0.5, k1=1.03)
                emit(held, 200)

            # --- si allarga a mostrare il giro finito
            if zmax > 1.0:
                moving(nf(0.7), lambda t: R.map_frame(
                    story, li, 1.0, R.lerp(cam(0.5)[0], 1.0, R.ease(t)), S, fonts,
                    total=total, follow=R.lerp(cam(0.5)[1], 0.0, R.ease(t)), caption=""))
            end = R.map_frame(story, li, 1.0, 1.0, S, fonts, total=total,
                              follow=0.0, caption="")
            emit(end, args.hold if li == len(story["legs"]) - 1 else args.hold_leg)
            prev_map = end

    # --- finale
    moving(nf(0.5), lambda t: R.to_paper(prev_map, R.ease(t), S))
    page(lambda a: R.text_card(S, fonts, a,
                               [("2015 – 2026", "kicker"), ("Venti giorni", "big"),
                                ("su 2.923", "big"),
                                ("Il resto è nell'archivio: micmer-git.github.io", "body")],
                               credit_too=True),
         read_ms("Venti giorni su 2.923",
                 "Il resto è nell'archivio: micmer-git.github.io", base=1600),
         sec_out=0.6)


# ------------------------------------------------------------------ il file

class Video:
    """Frame + durata in ms → un mp4 a passo costante.

    Si rende una volta sola ogni immagine **diversa** e si riscrive tante volte
    quanti frame di video occupa: un fermo-immagine di cinque secondi sono 150
    frame nel file ma una sola resa, che e' la parte cara. Il resto del debito lo
    paga il codec, che su frame identici spende quasi niente.
    """

    def __init__(self, path, S, fps):
        import cv2
        import numpy as np
        self.cv2, self.np, self.S, self.fps = cv2, np, S, fps
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (S, S))
        if not self.w.isOpened():
            raise SystemExit("VideoWriter non si apre: %s" % path)
        self.path, self.n, self.uniq, self.carry = path, 0, 0, 0.0

    def __call__(self, im, ms):
        bgr = self.cv2.cvtColor(self.np.asarray(im.convert("RGB")),
                                self.cv2.COLOR_RGB2BGR)
        # il resto frazionario si porta avanti, o su un video lungo la somma degli
        # arrotondamenti sposta la fine di qualche secondo
        self.carry += ms / 1000.0 * self.fps
        reps = int(self.carry)
        self.carry -= reps
        for _ in range(max(1, reps)):
            self.w.write(bgr)
        self.n += max(1, reps)
        self.uniq += 1

    def close(self):
        self.w.release()
        mb = os.path.getsize(self.path) / 1e6
        print("\n%d frame di video (%d resi), %.0f s, %.1f MB — %s"
              % (self.n, self.uniq, self.n / float(self.fps), mb, self.path))


class Gif:
    """Lo stesso montaggio, riversato in GIF. Non e' una conversione del file.

    Convertire l'mp4 sarebbe il modo peggiore: si ricomprimerebbe roba gia'
    compressa, e soprattutto si partirebbe da 30 fps costanti, che in GIF vuol
    dire pagare per intero anche i cinque secondi in cui non si muove niente. Qui
    si intercettano gli **stessi frame** prima dell'encoder e si fa il contrario:

    - **le pause tornano un frame solo** con la durata giusta, che e' l'unica cosa
      che la GIF regala e il video no;
    - **il movimento si decima** a `gif_fps`, perche' trenta passi al secondo su
      una traccia che si disegna sono invisibili e costano un frame l'uno;
    - i frame identici di fila si fondono in uno.

    In piu' la GIF esce piu' piccola del video: il testo regge la riduzione, la
    mappa pure, e il conto dei byte no.
    """

    HOLD = 200          # oltre questa soglia un frame e' una pausa, non movimento

    def __init__(self, path, S, gif_fps, colors):
        self.path, self.S, self.colors = path, S, colors
        self.step = 1000.0 / gif_fps
        self.frames, self.durs = [], []
        self.buf, self.acc = None, 0.0

    def _push(self, im, ms):
        # frame identico al precedente: si allunga quello invece di aggiungerne uno
        if self.frames and im.tobytes() == self.frames[-1].tobytes():
            self.durs[-1] += ms
        else:
            self.frames.append(im)
            self.durs.append(ms)

    def __call__(self, im, ms):
        small = im if im.size == (self.S, self.S) else im.resize((self.S, self.S),
                                                                 Image.LANCZOS)
        if ms >= self.HOLD:
            if self.buf is not None:
                self._push(self.buf, self.acc)
                self.buf, self.acc = None, 0.0
            self._push(small, ms)
            return
        self.buf, self.acc = small, self.acc + ms
        if self.acc >= self.step:
            self._push(self.buf, self.acc)
            self.buf, self.acc = None, 0.0

    def close(self):
        if self.buf is not None:
            self._push(self.buf, self.acc)
        fr, du = self.frames, [max(20, int(round(d))) for d in self.durs]
        # la tavolozza si prende su un campione sparso su tutto il montaggio: da un
        # frame solo i quattro accenti collassano nello stesso grigio
        step = max(1, len(fr) // 40)
        sample = Image.new("RGB", (self.S, self.S * len(fr[::step])), BG)
        for i, f in enumerate(fr[::step]):
            sample.paste(f, (0, i * self.S))
        pal = R.fixed_palette(sample, self.colors)
        q = R.punch_holes([f.quantize(palette=pal, dither=Image.NONE) for f in fr],
                          self.colors)
        q[0].save(self.path, save_all=True, append_images=q[1:], loop=0, duration=du,
                  optimize=False, disposal=1, transparency=self.colors)
        print("%d frame di GIF, %.0f s, %.1f MB — %s"
              % (len(q), sum(du) / 1000.0, os.path.getsize(self.path) / 1e6, self.path))


class Both:
    """Un solo giro di resa, due file: il video pieno e la GIF ridotta."""

    def __init__(self, *targets):
        self.targets = [t for t in targets if t is not None]

    def __call__(self, im, ms):
        for t in self.targets:
            t(im, ms)

    def close(self):
        for t in self.targets:
            t.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=760, help="lato del video")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--px", type=int, default=2400,
                    help="lato del mosaico basemap. Deve stare sopra size*zdraw o "
                         "la mappa si ingrandisce da sola e sfoca")
    ap.add_argument("--style", default="light_nolabels")
    ap.add_argument("--draw-sec", type=float, default=7.0,
                    help="quanto ci mette una traccia intera a disegnarsi")
    ap.add_argument("--zdraw", type=float, default=2.2,
                    help="quanto stringe la camera mentre insegue il puntino")
    ap.add_argument("--cardin-sec", type=float, default=1.5,
                    help="quanto ci mette la scheda del giorno a montarsi")
    ap.add_argument("--fly-sec", type=float, default=1.8, help="il volo sul globo")
    ap.add_argument("--hold-leg", type=int, default=700, help="pausa a fine tratto")
    ap.add_argument("--hold", type=int, default=1500, help="pausa a fine giornata")
    ap.add_argument("--only", help="solo queste storie, numerate da 1: 1,17,18")
    ap.add_argument("--intro", action="store_true",
                    help="tieni apertura e finale anche con --only")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--gif", nargs="?", const=OUT.replace(".mp4", "-v3.gif"),
                    help="scrivi anche la GIF, dagli stessi frame, ridotti")
    ap.add_argument("--gif-size", type=int, default=440, help="lato della GIF")
    ap.add_argument("--gif-fps", type=float, default=10.0,
                    help="passo del movimento in GIF: le pause restano lunghe comunque")
    ap.add_argument("--colors", type=int, default=44)
    args = ap.parse_args()

    S = args.size
    allst = R.load_stories()
    fonts = (font("arialbd.ttf", int(S * 0.023)), font("georgia.ttf", int(S * 0.050)),
             font("arial.ttf", int(S * 0.0335)), font("arialbd.ttf", int(S * 0.0225)),
             font("arial.ttf", int(S * 0.0165)), font("seguiemj.ttf", int(S * 0.034)),
             font("seguiemj.ttf", int(S * 0.022)), font("georgia.ttf", int(S * 0.078)),
             font("arial.ttf", int(S * 0.031)), font("arialbd.ttf", int(S * 0.0245)),
             font("georgiai.ttf", int(S * 0.0345)), font("georgia.ttf", int(S * 0.062)))

    pick = allst
    if args.only:
        pick = [allst[int(x) - 1] for x in args.only.split(",")]

    if args.px < S * args.zdraw:
        print("attenzione: px %d < size*zdraw %d — la mappa sfochera' nello zoom"
              % (args.px, int(S * args.zdraw)))
    print("mosaici basemap (%d px, %s):" % (args.px, args.style))
    stories = R.prepare(pick, args.px, args.style)

    out = Both(Video(args.out, S, args.fps),
               Gif(args.gif, args.gif_size, args.gif_fps, args.colors) if args.gif else None)
    t0 = time.time()
    build(stories, S, fonts, args, out)
    out.close()
    print("resa in %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
