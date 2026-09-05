# -*- coding: utf-8 -*-
"""Redraw the Korean into a menu texture's label sprites.

The label rectangles come from the .pvb vertex buffer (see xpvb). Each one
already contains its furigana, so clearing the whole rectangle and centring
the Korean in it takes the ruby away for free.

The art is 8bpp: a label is one grey with an alpha ramp spread over its own
palette entries, so the Korean is drawn as coverage and mapped onto the ramp
the label already uses. No palette entry is added.
"""
import struct
import numpy as np
from PIL import Image, ImageFont, ImageDraw

import imgp8, l5enc, l5enc2

TTF = r'D:\gc\rom\SRW_GC\NanumSquareNeo-cBd.ttf'
_font = {}


def font(size):
    if size not in _font:
        _font[size] = ImageFont.truetype(TTF, size)
    return _font[size]


def ramp(pal, ind, box):
    """The alpha ramp this label is drawn with, as (alpha, index) pairs."""
    x0, y0, x1, y1 = box
    used, count = np.unique(ind[y0:y1, x0:x1], return_counts=True)
    rgb = {}
    for i, n in zip(used, count):
        r, g, b, a = pal[int(i)]
        if a:
            rgb.setdefault((r, g, b), []).append((int(a), int(i), int(n)))
    if not rgb:
        return None
    # The lettering, not the backdrop. Taking the family with the brightest
    # opaque colour picked a stray highlight out of the artwork behind the
    # main menu's description lines -- a colour the sheet held one pixel of --
    # and redrew them in a grey that was not theirs. Take the family covering
    # the most of the box instead: on all but one of these quads the backdrop
    # is transparent, so it is not in the running, and where it is opaque it
    # gives itself away by filling half the box, which no word does.
    fill = int(used[count.argmax()])
    area = (y1 - y0) * (x1 - x0)
    word = [v for v in rgb.values()
            if not (sum(n for _, _, n in v) * 2 > area
                    and any(i == fill for _, i, _ in v))]
    best = max(word or list(rgb.values()), key=lambda v: sum(n for _, _, n in v))
    return sorted((a, i) for a, i, _ in best)


def clip(ind, box):
    """`box` cut down to the part that is actually on the texture.

    A quad's uv rectangle can reach past the edge of the sheet -- several of
    the operation-guide labels do -- and writing the drawn text at its full
    height then runs off the array.
    """
    h, w = ind.shape
    x0, y0, x1, y1 = box
    return max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)


def around(ind, box, band=2):
    """The commonest index in a ring just outside `box` -- its background."""
    h, w = ind.shape
    x0, y0, x1, y1 = box
    ox0, oy0 = max(x0 - band, 0), max(y0 - band, 0)
    ox1, oy1 = min(x1 + band, w), min(y1 + band, h)
    ring = np.concatenate([
        ind[oy0:y0, ox0:ox1].ravel(), ind[y1:oy1, ox0:ox1].ravel(),
        ind[y0:y1, ox0:x0].ravel(), ind[y0:y1, x1:ox1].ravel()])
    if not ring.size:
        ring = ind[y0:y1, x0:x1].ravel()
    vals, freq = np.unique(ring, return_counts=True)
    return vals[freq.argmax()]


def label_ink(ind, pal, box, ramp_=None):
    """Where the retail lettering actually sits inside `box`.

    A quad is bigger than the word on it: it carries the furigana, and on a
    menu list it runs on over empty strip past the end of a short label.
    Spreading the Korean across the whole quad therefore put it where the
    Japanese never was -- the main menu's help entry started a quarter of
    the way along its row and its lower half disappeared under the row
    below -- so the drawing is kept inside the rectangle the retail
    lettering occupied, which is by definition a place the game shows.
    """
    ramp_ = ramp_ or ramp(pal, ind, box)
    if not ramp_:
        return None
    sel = np.zeros(256, bool)
    for _, i in ramp_:
        sel[i] = True
    sub = sel[ind[box[1]:box[3], box[0]:box[2]].astype(np.uint8)]
    xs, ys = np.where(sub.any(0))[0], np.where(sub.any(1))[0]
    if not len(xs) or not len(ys):
        return None
    return (box[0] + int(xs[0]), box[1] + int(ys[0]),
            box[0] + int(xs[-1]) + 1, box[1] + int(ys[-1]) + 1)


def _render(text, size, w, h):
    """`text` at `size`, as (coverage image, its bounding box)."""
    pane = (max(w, size) * 4, max(h, size) * 4)
    tmp = Image.new('L', pane, 0)
    ImageDraw.Draw(tmp).text((pane[0] // 2, pane[1] // 2), text, font=font(size),
                             fill=255, anchor='mm')
    return tmp, tmp.getbbox()


def plan(ind, pal, box, text, pad=1):
    """What drawing `text` into `box` would need, or None if it cannot.

    `size` is the biggest that fits; a caller that is drawing a whole column
    lowers it to the one the column shares.
    """
    box = clip(ind, box)
    if box[2] - box[0] < 6 or box[3] - box[1] < 6 or not text:
        return None
    ramp_ = ramp(pal, ind, box)
    if not ramp_:
        return None
    ink = label_ink(ind, pal, box, ramp_) or box
    left, right = ink[0] - box[0], box[2] - ink[2]
    align = 'left' if left < right - 3 else 'right' if right < left - 3 else 'mid'
    # The retail ink says where the label is anchored, not how big it may be:
    # the quad keeps a few rows of slack under the lettering and Hangul needs
    # them, since a syllable with a final consonant runs lower than the kana
    # it replaces. So measure from the anchor to the far side of the quad.
    w = {'left': box[2] - ink[0], 'right': ink[2] - box[0]}.get(
        align, box[2] - box[0])
    # Vertically the quad is only a ceiling. Filling it makes the Korean
    # bigger than the Japanese ever was -- the main menu's heading sits 13
    # rows deep in a quad 21 rows tall -- so stay near the retail lettering
    # and keep a few rows for the final consonants kana do not have.
    h = min(box[3] - box[1], ink[3] - ink[1] + 4)
    for size in range(h, 5, -1):
        bb = _render(text, size, w, h)[1]
        if bb and bb[2] - bb[0] <= w - pad and bb[3] - bb[1] <= h - pad:
            break
    else:
        return None
    return {'box': box, 'ink': ink, 'ramp': ramp_, 'text': text,
            'size': size, 'align': align, 'pad': pad}


def draw_all(ind, pal, items, pad=1):
    """Draw every (box, text), with one size shared down each column.

    The retail sheet sets a whole menu column in one size. Sizing each label
    to its own quad instead stepped the main menu from 15px at the top to
    10px at the bottom, which is what the column looked wrong for.
    """
    plans = [p for p in (plan(ind, pal, b, t, pad) for b, t in items) if p]
    # Labels lined up on a common edge belong to the same column. A label
    # can share its left edge with one run and its right edge with another --
    # the menu rows are flush left and two of them happen to end together --
    # so it joins whichever run is longer.
    for edge, key in ((0, 'l'), (2, 'r')):
        run = []
        for p in sorted(plans, key=lambda q: q['box'][edge]):
            if run and p['box'][edge] - run[0]['box'][edge] <= 5:
                run.append(p)
            else:
                run = [p]
            p[key] = run
    done = 0
    for p in plans:
        col = p['l'] if len(p['l']) >= len(p['r']) else p['r']
        if _paint(ind, p, min(p['size'], _shared(col)), _edge(col) or p['align']):
            done += 1
    return done


def _shared(col):
    """The size a column settles on.

    Plainly the smallest that every label can reach -- except that one label
    too long for its quad should not take the column with it. The button bar
    has a 31px quad holding two kanji, and the four words beside it dropped
    from 16px to 7px to keep it company. A label that far off the pace is
    left at its own size instead.
    """
    sizes = sorted(q['size'] for q in col)
    mid = sizes[len(sizes) // 2]
    return min([s for s in sizes if s * 4 >= mid * 3] or sizes)


def _edge(col):
    """Which side a column of labels is set from, if it is set from one.

    A label whose word fills its quad says nothing on its own about where
    the line begins, and centring the shorter Korean in it left the main
    menu ragged where the Japanese had been flush. A column gives the
    answer the label cannot: the side its words line up on.
    """
    if len(col) < 3:
        return None
    lo = max(p['ink'][0] for p in col) - min(p['ink'][0] for p in col)
    hi = max(p['ink'][2] for p in col) - min(p['ink'][2] for p in col)
    # One side flush and the other plainly not. Where the words fill their
    # quads neither side is flush by choice and there is nothing to read off,
    # so leave those labels centred where the Japanese was.
    if min(lo, hi) > 4 or max(lo, hi) < 8:
        return None
    return 'left' if lo < hi else 'right'


def draw(ind, pal, box, text, pad=1):
    """Clear the rectangle and set `text` where the retail label was."""
    p = plan(ind, pal, box, text, pad)
    return bool(p) and _paint(ind, p, p['size'])


def _paint(ind, p, size, align=None):
    box, ink, ramp_ = p['box'], p['ink'], p['ramp']
    x0, y0, x1, y1 = box
    tmp, bb = _render(p['text'], size, x1 - x0, y1 - y0)
    if not bb:
        return False
    cov = np.asarray(tmp.crop((bb[0], bb[1], bb[2], bb[3])), np.uint8)
    ch, cw = cov.shape
    oy = (ink[1] + ink[3] - ch) // 2
    align = align or p['align']
    if align == 'left':
        ox = ink[0]
    elif align == 'right':
        ox = ink[2] - cw
    else:
        ox = (box[0] + box[2] - cw) // 2
    ox = max(x0, min(ox, x1 - cw))
    oy = max(y0, min(oy, y1 - ch))

    alphas = np.array([a for a, _ in ramp_], np.int16)
    idxs = np.array([i for _, i in ramp_], np.uint8)
    top = alphas.max()
    # The whole quad, not just the word: the furigana above a label is a
    # colour family of its own, so wiping only the lettering's own ink left
    # a row of tiny kana over half the operation guide.
    # Clear to whatever this box's background actually is. Index 0 is the
    # transparent one in the button bar but not everywhere -- on the save
    # screen it is opaque, and clearing to it drew a dark block behind
    # every label. Read it from a ring just outside the box rather than from
    # the box itself: on the operation-guide sheets the rectangles hug the
    # lettering, so inside them the commonest colour is the text and clearing
    # to that painted a solid white slab where the words had been.
    ind[y0:y1, x0:x1] = around(ind, (x0, y0, x1, y1))
    # At these sizes a stroke is barely a pixel wide and the rasteriser never
    # reaches full coverage, so mapping it straight onto the ramp gave hollow
    # letters. Stretch the coverage so its peak is the ramp's top.
    peak = int(cov.max()) or 255
    want = (cov.astype(np.int32) * top // peak).clip(0, top)
    pick = idxs[np.abs(alphas[None, None, :] - want[:, :, None]).argmin(2)]
    ind[oy:oy + ch, ox:ox + cw] = np.where(cov > 8, pick,
                                           ind[oy:oy + ch, ox:ox + cw])
    return True


def draw_over(ind, pal, box, text, bg_col, pad=2):
    """Replace the text inside a box that has artwork behind it.

    The title buttons are white lettering on a coloured pill, so clearing the
    box would take the pill with it. The background is rebuilt from a column
    of the pill the lettering does not reach -- the gradient runs top to
    bottom, so one clean column carries every row -- and the Korean is then
    composited over it and matched back to the palette.
    """
    x0, y0, x1, y1 = clip(ind, box)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return False
    p = np.array(pal, np.int16)
    area = ind[y0:y1, x0:x1]
    lum = p[:, :3].sum(1)
    # The pill's own colour for a row is simply the commonest index in it --
    # the lettering never covers a whole row. Taking one fixed column instead
    # picked up the glow at the pill's edge and washed the whole thing out.
    back = np.empty_like(area)
    for r in range(area.shape[0]):
        vals, freq = np.unique(area[r], return_counts=True)
        back[r] = vals[freq.argmax()]

    seen = np.unique(area)
    opaque = seen[p[seen, 3] > 128]
    if not len(opaque):
        return False
    white = int(opaque[lum[opaque].argmax()])
    dark = int(opaque[lum[opaque].argmin()])

    w, h = x1 - x0, y1 - y0
    for size in range(h, 5, -1):
        f = font(size)
        tmp = Image.new('L', (w * 4, h * 4), 0)
        edge = Image.new('L', (w * 4, h * 4), 0)
        ImageDraw.Draw(tmp).text((w * 2, h * 2), text, font=f, fill=255,
                                 anchor='mm')
        # The lettering on these plates carries a dark edge; white on a pale
        # plate without one is barely legible.
        ImageDraw.Draw(edge).text((w * 2, h * 2), text, font=f, fill=255,
                                  anchor='mm', stroke_width=1,
                                  stroke_fill=255)
        bb = edge.getbbox()
        if bb and bb[2] - bb[0] <= w - pad and bb[3] - bb[1] <= h - pad:
            break
    else:
        return False
    cov = np.zeros((h, w), np.float32)
    out = np.zeros((h, w), np.float32)
    c = np.asarray(tmp.crop(bb), np.uint8)
    e = np.asarray(edge.crop(bb), np.uint8)
    oy, ox = (h - c.shape[0]) // 2, (w - c.shape[1]) // 2
    cov[oy:oy + c.shape[0], ox:ox + c.shape[1]] = c / 255.0
    out[oy:oy + e.shape[0], ox:ox + e.shape[1]] = e / 255.0

    fg = p[white][:3].astype(np.float32)
    dk = p[dark][:3].astype(np.float32)
    bg = p[back][:, :, :3].astype(np.float32)
    mix = bg + (dk - bg) * out[:, :, None]          # edge first
    mix = mix + (fg - mix) * cov[:, :, None]        # then the letter
    alpha = p[back][:, :, 3].astype(np.float32)
    want = np.concatenate([mix, alpha[:, :, None]], 2)
    d = ((p[None, None, :, :].astype(np.float32) - want[:, :, None, :]) ** 2)
    ind[y0:y1, x0:x1] = d.sum(3).argmin(2).astype(np.uint8)
    return True


def encode(xi, ind):
    """Put the index plane back into the .xi, same block sizes as before."""
    w, h, ncol, (t_off, t_sz, p_off, p_sz) = imgp8.info(xi)
    lin = ind.astype(np.uint8).tobytes()
    sw = imgp8.swizzle(lin, w, 8)
    store, table, blank = {}, [], bytes(64)
    for i in range(len(sw) // 64):
        c = sw[i * 64:(i + 1) * 64]
        if c == blank:
            table.append(0xFFFF)
            continue
        if c not in store:
            store[c] = len(store)
        table.append(store[c])
    tiles = struct.pack('<%dH' % len(table), *table)
    pix = b''.join(store)
    # Use the whole remainder of the fixed-size .xi subfile.  A few retail
    # images have 2--4 bytes of padding after the pixel block; those bytes are
    # part of the slot and are needed when the aligned pixel offset moves
    # forward.
    room = len(xi) - 0x58 - t_off
    was_t = xi[0x58 + t_off:0x58 + t_off + t_sz]
    was_p = xi[0x58 + p_off:0x58 + p_off + p_sz]

    # Keep a block exactly as it shipped when its contents did not change,
    # and otherwise re-emit it in the method it arrived in -- writing
    # title_new.xa's tile table back as LZ10 instead of the RLE it shipped
    # with gave a disc the console refuses, dying just before the title
    # screen while PPSSPP showed it.
    a = was_t if imgp8.l5_decompress(was_t) == tiles else _fit(tiles, was_t, room)
    b = was_p if imgp8.l5_decompress(was_p) == pix else _fit(pix, was_p, room)
    if a is None or b is None or len(a) + len(b) > room:
        return None
    for blk, orig in ((a, was_t), (b, was_p)):
        if blk is not orig and (blk[0] & 7) != (orig[0] & 7):
            print('    compression %d -> %d; the console may refuse it'
                  % (orig[0] & 7, blk[0] & 7))
            return None
    new_p_off = (t_off + len(a) + 3) & ~3
    gap = new_p_off - (t_off + len(a))
    # navi.xa has no trailing padding.  If preserving its old pixel block
    # would make the alignment pad overflow the slot, rebuild that block in
    # the same compression method with a fresh tree; the decoded pixels stay
    # identical while the block becomes smaller.
    if len(a) + gap + len(b) > room and b == was_p:
        tighter = _fit(imgp8.l5_decompress(was_p), was_p, room)
        if tighter is not None:
            b = tighter
    if len(a) + gap + len(b) > room:
        return None
    out = bytearray(xi)
    out[0x58 + t_off:0x58 + t_off + room] = (
        a + bytes(gap) + b + bytes(room - len(a) - gap - len(b)))
    struct.pack_into('<IIII', out, 0x40, t_off, len(a), new_p_off,
                     len(b))
    assert new_p_off % 4 == 0 and 0x58 + new_p_off + len(b) <= len(out), \
        'menu texture pixel block misaligned or overruns the .xi'
    return bytes(out)


def _fit(raw, orig, room):
    """The smallest block holding `raw` that fits, keeping `orig`'s method.

    Only if nothing in that method fits does this hand back a block in
    another one; the caller checks and skips the texture rather than ship
    something the console might refuse.
    """
    out = []
    for enc in (lambda: struct.pack('<I', len(raw) << 3) + raw,
                # The save screen's art needs the longer match search: at the
                # default effort it came out 72 bytes over its slot, and these
                # blocks are 70 kB, so the extra work is worth it.
                lambda: l5enc.lz10_block(raw, effort=256),
                lambda: l5enc2.huff4_block(raw, l5enc.tree_of(orig)),
                lambda: l5enc2.huff4_block(raw),
                lambda: l5enc.block(raw, l5enc.tree_of(orig)),
                lambda: l5enc2.huff8_block(raw),
                lambda: l5enc2.rle_block(raw)):
        try:
            blk = enc()
        except Exception:
            continue                 # a tree without every symbol the new data uses
        if len(blk) <= room:
            out.append(blk)
    if not out:
        return None
    same = [x for x in out if (x[0] & 7) == (orig[0] & 7)]
    return min(same or out, key=len)


def draw_notice(ind, pal, items, pad=2):
    """The notices shown before the title: centred lines, one size, flat page.

    These two screens are not menu art. Each is a whole page of one colour --
    the piracy warning is white on black, the autosave notice black on white --
    with the body set in centred lines and a reading in kana over each of them.

    ramp() is the wrong tool here. It reads a label's colour from the colours
    inside its box, which is right where a label sits on artwork, but on a flat
    page the commonest colour after the page itself is the near-white of the
    page's own anti-aliasing. Two lines of the autosave notice came out drawn
    in (254, 254, 254) on (255, 255, 255) -- present, and invisible. So the ink
    here is taken as the opaque colour furthest from the page in luminance, and
    the shades between the two are matched back to the palette.

    One size for the block, and centred: the retail lines are, and sizing each
    line to its own box stepped them.
    """
    p = np.array(pal, np.int16)
    lum = p[:, :3].sum(1)
    opaque = np.nonzero(p[:, 3] > 128)[0]
    out = 0
    plans = []
    for box, text in items:
        box = clip(ind, box)
        if box[2] - box[0] < 8 or box[3] - box[1] < 8 or not text:
            continue
        area = ind[box[1]:box[3], box[0]:box[2]]
        vals, freq = np.unique(area, return_counts=True)
        page = int(vals[freq.argmax()])
        ink = int(opaque[np.abs(lum[opaque] - lum[page]).argmax()])
        h = box[3] - box[1]
        for size in range(h, 5, -1):
            bb = _render(text, size, box[2] - box[0], h)[1]
            if bb and bb[2] - bb[0] <= box[2] - box[0] - pad \
                    and bb[3] - bb[1] <= h - pad:
                break
        else:
            continue
        plans.append((box, text, page, ink, size))
    if not plans:
        return 0
    size = min(q[4] for q in plans)
    for box, text, page, ink, _ in plans:
        x0, y0, x1, y1 = box
        tmp, bb = _render(text, size, x1 - x0, y1 - y0)
        if not bb:
            continue
        cov = np.asarray(tmp.crop(bb), np.float32) / 255.0
        ch, cw = cov.shape
        oy, ox = y0 + (y1 - y0 - ch) // 2, x0 + (x1 - x0 - cw) // 2
        ind[y0:y1, x0:x1] = page
        want = (p[page][:3].astype(np.float32)
                + (p[ink][:3] - p[page][:3]).astype(np.float32)
                * cov[:, :, None])
        d = ((p[opaque][None, None, :, :3].astype(np.float32)
              - want[:, :, None, :]) ** 2).sum(3)
        pick = opaque[d.argmin(2)].astype(np.uint8)
        area = ind[oy:oy + ch, ox:ox + cw]
        area[:] = np.where(cov > 0.02, pick, area)
        out += 1
    return out
