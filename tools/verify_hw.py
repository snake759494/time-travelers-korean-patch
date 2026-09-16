# -*- coding: utf-8 -*-
"""Refuse a build that steps outside what has been seen to run on a PSP.

PPSSPP forgives what the console does not, and every hardware failure this
patch has had was invisible in the emulator: a pixel block one byte off its
alignment, a CRILAYLA slot padded to its old size, and -- v1.9 -- a disc that
passes every one of those checks and still does not boot. v1.9 added two
mechanisms at once (a .cfg.bin that grew, and boot-screen textures written
into the outer CPK) and nothing static tells them apart, so the rule this
file enforces is the conservative one: a build may only do what a build that
booted has done. Anything new has to come in on its own, and be seen to
boot, before it is added to the envelope below.

  python verify_hw.py            # checks the ISO pack_korean wrote
  python verify_hw.py <iso>      # checks that one

Exit status is non-zero on any finding, so it can gate a release.
"""
import collections
import hashlib
import io
import struct
import sys

import cpk
import dnsfile
import menu_ko
import telop_ko
import xpck
import pack_korean as P
from pack_korean import Window

ISO = sys.argv[1] if len(sys.argv) > 1 else P.DST

# The outer CPK (TT1_PSP.CPK) is read before anything else. Only the two
# dialogue fonts in it have ever been rewritten in a disc that booted.
OUTER_ALLOWED = frozenset(['nrm_sub.xf', 'nrm_main.xf'])
# The chart (tt1.flo) outgrows its slot and is repacked together with the
# nine .scn that follow it into the same span, so those ten files move. That
# relocation has shipped since v1.4 and runs on hardware; nothing else may.
MAY_MOVE = frozenset(['tt1.flo']) | frozenset(
    'tt1%s.scn' % s for s in ('', '_A01A_0000', '_C05A_0020', '_I02A_0000',
                              '_I03A_0000', '_I04A_0000', '_I06A_0000',
                              '_M07A_0000', '_P01A_0000'))
# Outer entries the build never touches and that are too big to hash for
# nothing (movies, audio).
OUTER_SKIP_DIRS = ('psp/mov', 'psp/snd')

findings = []


def bad(msg):
    findings.append(msg)


def entries(c):
    return {(x['dir'], x['name']): x for x in c.files}


def xi_shape(xi):
    t_off, t_sz, p_off, p_sz = struct.unpack('<IIII', xi[0x40:0x50])
    return (len(xi), t_off, xi[0x58 + t_off] & 7, p_off, xi[0x58 + p_off] & 7)


def check_xi(where, name, xi_name, orig, new):
    lo, to, tm, po, pm = xi_shape(orig)
    ln, tn, tmn, pn, pmn = xi_shape(new)
    if ln != lo:
        bad('%s %s/%s: length %d -> %d' % (where, name, xi_name, lo, ln))
    if pn % 4:
        bad('%s %s/%s: pixel block at %d, not 4-aligned' % (where, name, xi_name, pn))
    if (tm, pm) != (tmn, pmn):
        bad('%s %s/%s: compression method %d/%d -> %d/%d'
            % (where, name, xi_name, tm, pm, tmn, pmn))


def main():
    src_d, dst_d = dnsfile.DNSFile(P.SRC), dnsfile.DNSFile(ISO)
    src, dst = cpk.CPK(src_d), cpk.CPK(dst_d)
    se, de = entries(src), entries(dst)

    # ---- inner CPK: layout and sizes ----
    if set(se) != set(de):
        bad('inner CPK: file list differs')
    grew, moved, shape = [], [], []
    for k, a in se.items():
        b = de.get(k)
        if b is None:
            continue
        if a['offset'] != b['offset'] and k[1] not in MAY_MOVE:
            moved.append(k[1])
        if k[1].endswith('.cfg.bin') and b['extract'] > a['extract']:
            grew.append('%s %d -> %d' % (k[1], a['extract'], b['extract']))
        if b['size'] != b['extract']:            # compressed: check its shape
            dst_d.seek(b['offset'])
            head = dst_d.read(16)
            if head[:8] == b'CRILAYLA':
                clen = struct.unpack('<I', head[12:16])[0]
                if 16 + clen + 0x100 != b['size']:
                    shape.append(k[1])
    for m in moved:
        bad('inner CPK: %s moved' % m)
    for g in grew:
        bad('inner CPK: .cfg.bin grew: %s' % g)
    for s in shape:
        bad('inner CPK: CRILAYLA shape broken (padded?): %s' % s)
    print('inner CPK: %d files, %d moved, %d .cfg.bin grew, %d bad CRILAYLA'
          % (len(se), len(moved), len(grew), len(shape)))

    # ---- rewritten menu sheets ----
    sheets = collections.defaultdict(set)
    for tbl in (menu_ko.SPRITES, menu_ko.OVER):
        for n, s in tbl.items():
            sheets[n] |= set(s)
    n_xi = 0
    for name, xis in sheets.items():
        a, b = se.get(('psp/menu', name)), de.get(('psp/menu', name))
        if a is None or b is None:
            a = next((x for k, x in se.items() if k[1] == name), None)
            b = next((x for k, x in de.items() if k[1] == name), None)
        if a is None or b is None:
            continue
        pa = {p['name']: p for p in xpck.parse(src.read(a))}
        pb = {p['name']: p for p in xpck.parse(dst.read(b))}
        for x in xis:
            check_xi('menu', name, x, pa[x]['data'], pb[x]['data'])
            n_xi += 1
    # ---- character telops, one CPK per chapter ----
    for k, a in sorted(se.items()):
        if a['dir'] != 'psp/cpk/separate':
            continue
        b = de[k]
        si = cpk.CPK(Window(src_d, a['offset'], a['size']))
        di = cpk.CPK(Window(dst_d, b['offset'], b['size']))
        dm = {x['name']: x for x in di.files if x['dir'] == 'psp/telop'}
        for x in si.files:
            if x['dir'] != 'psp/telop' or x['name'] not in telop_ko.TELOPS:
                continue
            pa = {p['name']: p for p in xpck.parse(si.read(x))}
            pb = {p['name']: p for p in xpck.parse(di.read(dm[x['name']]))}
            check_xi('telop', x['name'], '000.xi', pa['000.xi']['data'],
                     pb['000.xi']['data'])
            n_xi += 1
    print('textures: %d rewritten .xi checked' % n_xi)

    # ---- outer CPK: nothing but the two fonts may differ ----
    so = cpk.CPK(P.SRC, base=P.CPK_LBA * P.SEC)
    do = cpk.CPK(ISO, base=P.CPK_LBA * P.SEC)
    oe = {(x['dir'], x['name']): x for x in do.files}
    changed = []
    for x in so.files:
        if x['dir'].startswith(OUTER_SKIP_DIRS):
            continue
        y = oe.get((x['dir'], x['name']))
        if y is None or (x['offset'], x['size']) != (y['offset'], y['size']):
            changed.append(x['name'] + ' (layout)')
            continue
        if hashlib.md5(so.read(x)).digest() != hashlib.md5(do.read(y)).digest():
            changed.append(x['name'])
    for n in changed:
        if n.split(' ')[0] not in OUTER_ALLOWED:
            bad('outer CPK: %s changed; only %s have booted rewritten'
                % (n, sorted(OUTER_ALLOWED)))
    print('outer CPK: changed %s' % (changed or 'nothing'))

    print()
    if findings:
        print('HARDWARE ENVELOPE: %d finding(s)' % len(findings))
        for f in findings:
            print('  ' + f)
        sys.exit(1)
    print('HARDWARE ENVELOPE: OK -- nothing this disc does is new')


if __name__ == '__main__':
    main()
