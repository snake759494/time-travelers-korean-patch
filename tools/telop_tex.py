# -*- coding: utf-8 -*-
"""The plate that announces a character.

When a new face appears the game shows their job over a rule and their name
in heavy type under it, with the reading in small kana between. None of that
is text the engine draws: it is one 512x256 texture per character, sitting in
that chapter's own CPK, which is why it stayed Japanese while the script
around it turned Korean.

The plate says where to write, if you ask it the right question. A rule and
the coloured bar under the name are each a single unbroken run of pixels
across the design width -- which is precisely what a row of lettering never
is, since letters have gaps between them. That one test sorts every row into
title, rule, reading, name and bar without a table of coordinates.

Korean carries no reading, so the kana rows are given back to the name and it
is set larger than the Japanese was. The lettering is white with a black
halo: the palette holds one solid white and a long ramp of black at rising
alpha, so the halo is drawn from the ramp and the body from the white.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import menu_tex

HEAVY = r'D:\gc\rom\SRW_GC\NanumSquareNeo-eHv.ttf'
BOLD = r'D:\gc\rom\SRW_GC\NanumSquareNeo-cBd.ttf'
SOLID = 0.97                     # of the column, to count as a rule
# Not lower: a dense line of kanji reached 85% of the column on its own,
# and taking that for a rule cut the plate three rows below its title.
COLOUR = 0.15                    # saturation that makes a run decoration


def _font(path, size):
    return ImageFont.truetype(path, size)


def _rows(ind, pal):
    """(opaque mask, run count per row, saturation per row)."""
    p = np.array(pal, np.int16)
    op = p[ind, 3] > 8
    rgb = p[ind, :3]
    mx, mn = rgb.max(2), rgb.min(2)
    sat = np.where(mx > 0, (mx - mn) * 255 // np.maximum(mx, 1), 0)
    runs = np.zeros(len(ind), int)
    for y in range(len(ind)):
        m = op[y]
        runs[y] = int(np.count_nonzero(m[1:] & ~m[:-1]) + m[0])
    return op, runs, sat


def _column(op, ys):
    """The design's own width: the widest run of opaque pixels on the plate.

    Rules and bars are drawn to the design width and lettering never is, so
    the widest single run is the column the plate is set in.
    """
    best = None
    for y in ys:
        m = op[y]
        if not m.any():
            continue
        on = np.nonzero(m)[0]
        if int(np.count_nonzero(m[1:] & ~m[:-1]) + m[0]) != 1:
            continue
        if best is None or on[-1] - on[0] > best[1] - best[0]:
            best = (int(on[0]), int(on[-1]) + 1)
    return best


def structure(ind, pal):
    """Where the title, the name and the decoration are.

    Returns (title box, name box, (band top, band bottom)) or None when the
    plate does not look like a character telop; the band is None when there
    is nothing drawn under the name.
    """
    op, runs, sat = _rows(ind, pal)
    ys = np.nonzero(op.any(1))[0]
    if not len(ys):
        return None
    y0, y1 = int(ys[0]), int(ys[-1]) + 1
    col = _column(op, range(y0, y1))
    if col is None:
        return None
    cx0, cx1 = col

    # A rule and the bar under a name are drawn to the full column; lettering
    # never fills a row that far, so counting opaque pixels tells them apart.
    # Counting, not testing the two end columns: a bar fades out at its ends,
    # and asking whether its last row reached the very edge said no and left
    # the whole band to be read as a rule.
    wide = [y for y in range(y0, y1)
            if int(op[y, cx0:cx1].sum()) >= (cx1 - cx0) * SOLID]
    groups = []
    for y in wide:
        if groups and y - groups[-1][-1] <= 4:
            groups[-1].append(y)
        else:
            groups.append([y])

    # Decoration sits at the foot of the plate, and the name is set low enough
    # to cross it. Everything from where that last group starts is decoration,
    # so the name's box stops there and the strokes lying on the bar are swept
    # off afterwards.
    band = None
    if groups and groups[-1][-1] >= y1 - 6:
        band = (groups[-1][0], y1)
        y1 = band[0]
        groups.pop()

    kind = {}
    for y in range(y0, y1):
        if not op[y].any():
            kind[y] = 'gap'
        elif any(y in g for g in groups):
            kind[y] = 'rule'
        else:
            kind[y] = 'text'
    order = sorted(kind)
    text = [y for y in order if kind[y] == 'text']
    if not text:
        return None

    rule = [g for g in groups if text[0] < g[0] and g[-1] < text[-1]]
    if rule:
        cut = rule[0][len(rule[0]) // 2]
    else:
        # No rule: the plate separates its two lines with blank rows, and the
        # widest run of them is the split.
        gaps, run = [], []
        for y in order:
            if kind[y] == 'gap':
                run.append(y)
            elif run:
                gaps.append(run)
                run = []
        if not gaps:
            return None
        best = max(gaps, key=len)
        cut = best[len(best) // 2]

    top = [y for y in text if y < cut]
    bot = [y for y in text if y > cut]
    if not top or not bot:
        return None
    return ((cx0, top[0], cx1, top[-1] + 1),
            (cx0, bot[0], cx1, bot[-1] + 1), band)


def scrub(ind, pal, band, x0, x1):
    """Sweep the leftovers of the old name off the decoration band.

    The name is set low enough that its strokes cross the bar, so clearing
    only the rows above leaves the bottom of the kanji lying on it.

    A stroke is found by how far it stands out from the bar around it, not by
    its colour: the artwork has the old name composited into the gradient, so
    what is left of it is a muddy blend of the two and matching black or white
    caught none of it. Each run that stands out is then bridged from the bar
    on either side -- a median over the whole row instead, which was the first
    thing tried, smoothed the gradient into a grey smear.
    """
    if band is None:
        return
    p = np.array(pal, np.int16)
    w = 15
    for y in range(band[0], band[1]):
        row = ind[y, x0:x1]
        rgba = p[row].astype(np.float32)
        pad = np.pad(rgba, ((w // 2, w // 2), (0, 0)), mode='edge')
        base = np.stack([np.median(pad[i:i + w], 0) for i in range(len(row))])
        off = np.abs(rgba - base).sum(1)
        cut = max(40.0, float(np.median(off)) + 4 * float(np.median(
            np.abs(off - np.median(off)))))
        bad = off > cut
        if not bad.any() or bad.all():
            continue
        at = np.nonzero(bad)[0]
        good = np.nonzero(~bad)[0]
        want = rgba.copy()
        for ch in range(4):
            want[at, ch] = np.interp(at, good, want[good, ch])
        d = ((p[None, :, :].astype(np.float32) - want[:, None, :]) ** 2).sum(2)
        ind[y, x0:x1] = np.where(bad, d.argmin(1).astype(np.uint8), row)


def _ink(pal):
    """(white body index, [(alpha, index)] black halo ramp)."""
    p = np.array(pal, np.int16)
    lum = p[:, :3].sum(1)
    solid = np.nonzero(p[:, 3] > 250)[0]
    if not len(solid):
        return None, None
    white = int(solid[lum[solid].argmax()])
    ramp = sorted((int(p[i, 3]), int(i)) for i in range(len(pal))
                  if lum[i] <= 24 and 8 < p[i, 3])
    seen, out = set(), []
    for a, i in ramp:                # one index per alpha, the lowest
        if a not in seen:
            seen.add(a)
            out.append((a, i))
    return white, out


def draw(ind, pal, box, text, ttf=HEAVY, pad=2):
    """Set `text` across `box` as white lettering with the plate's halo."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w < 8 or h < 8 or not text:
        return False
    white, ramp = _ink(pal)
    if white is None or not ramp:
        return False

    for size in range(h + 4, 5, -1):
        f = _font(ttf, size)
        body = Image.new('L', (w * 4, h * 4), 0)
        halo = Image.new('L', (w * 4, h * 4), 0)
        ImageDraw.Draw(body).text((w * 2, h * 2), text, font=f, fill=255,
                                  anchor='mm')
        ImageDraw.Draw(halo).text((w * 2, h * 2), text, font=f, fill=255,
                                  anchor='mm', stroke_width=2,
                                  stroke_fill=255)
        bb = halo.getbbox()
        if bb and bb[2] - bb[0] <= w - pad and bb[3] - bb[1] <= h - pad:
            break
    else:
        return False

    b = np.asarray(body.crop(bb), np.uint8)
    e = np.asarray(halo.crop(bb), np.uint8)
    ch, cw = e.shape
    oy, ox = y0 + (h - ch) // 2, x0 + (w - cw) // 2

    ind[y0:y1, x0:x1] = menu_tex.around(ind, box)
    alphas = np.array([a for a, _ in ramp], np.int16)
    idxs = np.array([i for _, i in ramp], np.uint8)
    want = (e.astype(np.int32) * alphas.max() // 255).clip(0, alphas.max())
    pick = idxs[np.abs(alphas[None, None, :] - want[:, :, None]).argmin(2)]
    area = ind[oy:oy + ch, ox:ox + cw]
    area[:] = np.where(e > 8, pick, area)
    area[:] = np.where(b > 128, np.uint8(white), area)
    return True
