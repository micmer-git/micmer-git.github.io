#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""gifweigh.py — how many bytes each frame of a GIF actually costs.

Written because three guesses in a row about what made top-20-reel.gif big were
wrong. Walks the GIF's blocks and reports the encoded size of every frame, so a
change to the cut can be judged against the file instead of against intuition.

    python gifweigh.py ../top-20/top-20-reel.gif
    python gifweigh.py x.gif --runs      # raggruppa i frame consecutivi simili
"""
import argparse
import io
import statistics
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def frames(path):
    """(bytes, delay_ms) per frame, by walking the block structure."""
    d = io.open(path, "rb").read()
    i = 13
    if d[10] & 0x80:
        i += 3 * (1 << ((d[10] & 7) + 1))
    out, start, delay = [], None, 0
    while i < len(d):
        b = d[i]
        if b == 0x21:                                 # extension
            if d[i + 1] == 0xF9 and start is None:
                start = i
                delay = (d[i + 4] | (d[i + 5] << 8)) * 10
            i += 2
            while d[i]:
                i += 1 + d[i]
            i += 1
        elif b == 0x2C:                               # image descriptor
            head = i
            i += 10
            if d[i - 1] & 0x80:
                i += 3 * (1 << ((d[i - 1] & 7) + 1))
            i += 1
            while d[i]:
                i += 1 + d[i]
            i += 1
            out.append((i - (start if start is not None else head), delay))
            start = None
        elif b == 0x3B:
            break
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--runs", action="store_true", help="raggruppa i frame vicini")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    fr = frames(a.path)
    sz = [x[0] for x in fr]
    ms = [x[1] for x in fr]
    tot = sum(sz)
    print("%s: %d frame · %.2f MB · %.1f s" % (a.path, len(fr), tot / 1e6, sum(ms) / 1000.0))
    print("mediana %.1f kB · media %.1f kB · max %.1f kB"
          % (statistics.median(sz) / 1024.0, tot / len(fr) / 1024.0, max(sz) / 1024.0))

    for cut in (5, 10, 20, 40):
        big = [k for k in range(len(sz)) if sz[k] > cut * 1024]
        print("  > %2d kB: %4d frame, %5.2f MB (%2.0f%% del file)"
              % (cut, len(big), sum(sz[k] for k in big) / 1e6,
                 100.0 * sum(sz[k] for k in big) / tot))

    if a.runs:
        print("\nsequenze (frame consecutivi sopra/sotto i 10 kB):")
        k = 0
        while k < len(sz):
            heavy = sz[k] > 10 * 1024
            j = k
            while j < len(sz) and (sz[j] > 10 * 1024) == heavy:
                j += 1
            print("   %4d-%-4d  %s  %5.2f MB  (%d frame, %.1f kB medi)"
                  % (k, j - 1, "PESANTI" if heavy else "leggeri",
                     sum(sz[k:j]) / 1e6, j - k, sum(sz[k:j]) / (j - k) / 1024.0))
            k = j
    else:
        print("\ni %d frame piu grossi:" % a.top)
        for k in sorted(range(len(sz)), key=lambda i: -sz[i])[:a.top]:
            print("   #%4d  %6.1f kB  %d ms" % (k, sz[k] / 1024.0, ms[k]))


if __name__ == "__main__":
    main()
