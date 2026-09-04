# -*- coding: utf-8 -*-
"""Dialogue-expansion test, targeting the lines actually seen on screen.

Locates strings by a kana fragment (kanji carry ruby markup like [神谷/かみや]
so they are not directly searchable), appends a run of full-width digits to
each, and rebuilds .pck -> CRILAYLA -> CPK TOC -> PGD -> ISO.

Strings are addressed by ordinal inside a blob, so lengthening one needs no
internal offset fixups: only blob header field [3] (total string bytes), the
.pck blob table and the TOC row change.
"""
import os, shutil, struct, sys

import cpk, dnsfile, crilayla, pgd

SRC = r'D:\psp\타임트레블러즈\Time Travelers.iso'
DST = r'D:\psp\타임트레블러즈\Time Travelers (expand test).iso'
DNS_LBA, SEC = 285712, 2048
TARGET = 'P01.pck'
FRAGS = [u'とぶつかった', u'なんでこうなった']
MARK = u'０１２３４５６７８９'          # 10 full-width chars = 20 SJIS bytes
REPEAT = 3


def blobs_of(d):
    n = struct.unpack('<I', d[:4])[0]
    return n, [struct.unpack('<III', d[4 + i * 12:16 + i * 12]) for i in range(n)]


def fields(b):
    """The header carries `type` extra hash words, shifting the table fields."""
    t = struct.unpack('<H', b[2:4])[0]
    return 0x08 + t * 4, 0x0C + t * 4, 0x10 + t * 4


def split_strings(b):
    fb, ft, fc = fields(b)
    if fc + 4 > len(b):
        return None
    total = struct.unpack('<I', b[ft:ft + 4])[0]
    count = struct.unpack('<I', b[fc:fc + 4])[0]
    if not 0 < count < 4096 or not 0 < total <= len(b):
        return None
    # The table start is not stored; locate it from total/count instead.
    # Strings sit at the end of the blob, so search downwards from there.
    for base in range(len(b) - total, -1, -1):
        seg = b[base:base + total]
        if not seg.endswith(b'\x00') or seg.count(b'\x00') != count:
            continue
        try:
            # cp932, not shift_jis: seven blobs carry a circled numeral
            # (87 40 / 87 41, NEC row 13), which the stricter codec rejects.
            # The pool was being found and then thrown away, so four scenes of
            # Rusanchi and one each of Sagishi and Keiji were never extracted
            # and played in Japanese while the rest of the chapter was Korean.
            seg.decode('cp932')
        except UnicodeDecodeError:
            continue
        return base, total, seg.split(b'\x00')[:-1]
    return None


def _offsets(strs):
    out, p = [], 0
    for s in strs:
        out.append(p)
        p += len(s) + 1
    return out


def fixed_slots(old_strs, new_strs):
    """Keep every string at its original byte offset.

    Records address strings by byte offset, so the safest edit is one that
    does not move them: write the translation, then pad the slot back out to
    the length it had. Nothing downstream needs rewriting. Returns None when
    a translation is too long for its slot.
    """
    out = []
    for old, new in zip(old_strs, new_strs):
        if len(new) > len(old):
            return None
        # Filler after the terminator, not more NULs: the region has to keep
        # exactly as many terminators as the header says strings.
        out.append(new + b'\x00' + b'\xff' * (len(old) - len(new)))
    return b''.join(out)


def remap_refs(head, old, new):
    """Records address strings by byte offset into the table, so every one of
    those offsets has to move with the text. They sit 4-byte aligned and are
    introduced by 00 00 or FF FF; requiring that marker keeps the handful of
    unrelated words that happen to equal an offset from being rewritten."""
    table = dict(zip(old, new))
    buf = bytearray(head)
    n = 0
    for i in range(0, len(buf) - 3, 4):
        if i < 2 or buf[i - 2:i] not in (b'\x00\x00', b'\xff\xff'):
            continue
        v = struct.unpack('<I', buf[i:i + 4])[0]
        if v in table and table[v] != v:
            buf[i:i + 4] = struct.pack('<I', table[v])
            n += 1
    return bytes(buf), n


def join_strings(b, base, total, strs):
    data = b''.join(s + b'\x00' for s in strs)
    _, ft, _ = fields(b)
    tail = b[base + total:]

    old_strs = b[base:base + total].split(b'\x00')[:-1]
    head, _ = remap_refs(b[:base], _offsets(old_strs), _offsets(strs))

    out = bytearray(head) + data + tail
    filler = tail[-1] if tail else 0xFF
    # Keep the blob exactly as long as the original. That leaves every blob
    # offset in the .pck, and the file size itself, byte-identical -- so
    # nothing downstream can be looking at a stale layout. Korean is shorter
    # than the Japanese it replaces, so there is always room.
    if len(out) < len(b):
        out += bytes([filler]) * (len(b) - len(out))
    elif len(out) > len(b):
        # A few lines come out longer than the Japanese; give back trailing
        # filler to stay the same length rather than shifting every blob.
        excess = len(out) - len(b)
        if tail and len(tail) >= excess and all(x == filler for x in tail):
            out = bytearray(head) + data + tail[:len(tail) - excess]
        else:
            pad = (-len(out)) % 4      # otherwise at least stay 4-byte aligned
            if pad:
                out += bytes([filler]) * pad
    out[ft:ft + 4] = struct.pack('<I', len(data))
    return bytes(out)


def main(repeat=REPEAT):
    suffix = (MARK * repeat).encode('shift_jis')
    d = dnsfile.DNSFile()
    c = cpk.CPK(d)
    ent = [e for e in c.files if e['name'] == TARGET][0]
    nxt = min(e['offset'] for e in c.files if e['offset'] > ent['offset'])
    slot = nxt - ent['offset']
    raw = c.read(ent)
    n, recs = blobs_of(raw)
    print('%s: stored %d, extract %d, slot %d' % (TARGET, ent['size'], ent['extract'], slot))

    pats = [f.encode('shift_jis') for f in FRAGS]
    blobs, hits = [], 0
    for bi, (h, off, sz) in enumerate(recs):
        b = raw[off:off + sz]
        if len(b) < 20:
            blobs.append(b); continue
        got = split_strings(b)
        if got is None:
            blobs.append(b); continue
        base, total, strs = got
        touched = False
        for si, s in enumerate(strs):
            if any(p in s for p in pats):
                strs[si] = s + suffix
                touched = True
                hits += 1
                print('  blob[%d] string #%d: %d -> %d bytes' % (bi, si, len(s), len(strs[si])))
        blobs.append(join_strings(b, base, total, strs) if touched else b)
    assert hits, 'no target line found'

    hdr = bytearray(struct.pack('<I', n))
    body = bytearray()
    start = 4 + n * 12
    for i, (h, _, _) in enumerate(recs):
        hdr += struct.pack('<III', h, start + len(body), len(blobs[i]))
        body += blobs[i]
    newpck = bytes(hdr) + bytes(body)
    comp = crilayla.compress(newpck, effort=256)
    assert cpk.crilayla(comp) == newpck, 'round-trip failed'
    print('.pck %d -> %d ; compressed %d (slot %d)' % (len(raw), len(newpck), len(comp), slot))
    if len(comp) > slot:
        print('DOES NOT FIT - retry with fewer repeats')
        return False

    toc_off = c.header['TocOffset']
    toc = cpk.read_chunk(d, toc_off, b'TOC ')
    idx = [i for i, r in enumerate(toc.rows)
           if r['FileName'] == TARGET and r['DirName'] == ent['dir']][0]
    row = toc_off + 16 + 8 + toc.rows_off + idx * toc.row_len
    edits = [(ent['offset'], comp),
             (row + 8, struct.pack('>I', len(comp))),
             (row + 12, struct.pack('>I', len(newpck)))]

    if not os.path.exists(DST):
        print('copying ISO ...')
        shutil.copyfile(SRC, DST)
    base_off = DNS_LBA * SEC
    f = open(DST, 'r+b')
    f.seek(base_off)
    p = pgd.PGD(f.read(0x90), 2)
    bs = p.block_size
    touched_blocks = {}
    for off, blob in edits:
        for k in range(off // bs, (off + len(blob) - 1) // bs + 1):
            if k not in touched_blocks:
                f.seek(base_off + p.data_offset + k * bs)
                touched_blocks[k] = bytearray(p.decrypt_block(k, f.read(bs)))
        for i, byte in enumerate(blob):
            k, o = divmod(off + i, bs)
            touched_blocks[k][o] = byte
    for k, buf in touched_blocks.items():
        f.seek(base_off + p.data_offset + k * bs)
        f.write(p.decrypt_block(k, bytes(buf)))
    f.close()
    print('patched %d PGD blocks' % len(touched_blocks))

    d2 = dnsfile.DNSFile(iso=DST)
    c2 = cpk.CPK(d2)
    e2 = [e for e in c2.files if e['name'] == TARGET][0]
    print('verify: TOC %d/%d, readback matches: %s'
          % (e2['size'], e2['extract'], c2.read(e2) == newpck))
    return True


if __name__ == '__main__':
    r = int(sys.argv[1]) if len(sys.argv) > 1 else REPEAT
    main(r)
