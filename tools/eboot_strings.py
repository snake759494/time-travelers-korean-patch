# -*- coding: utf-8 -*-
"""Japanese strings inside the decrypted EBOOT.

Scanning a whole executable for CP932 turns up a lot of code that happens to
decode, so a run only counts when every character is one a script would use
and the run is NUL terminated on both ends.
"""
import re, sys, collections

DUMP = r'D:\psp\ppsspp_win\memstick\PSP\SYSTEM\DUMP\NPJH50597_smp_rom.BIN'
# kana, CJK, full-width forms, ASCII text, and the markup the engine uses.
# Half-width katakana is excluded on purpose: the game never uses it, but
# MIPS instruction words decode into it constantly and that noise otherwise
# swamps the real strings.
# U+2606 is there for one name: \u30eb\u30b5\u30f3\u30c1\u2606\u30de\u30f3[\u7de8/\u3078\u3093], the chapter card's
# heading, which without it never reached eboot.json (issue #3).
OK = re.compile(r'^[\u3000-\u30ff\u4e00-\u9fff\uff01-\uff60\u2606'
                r'\u2010-\u201f\u2026\u3001-\u303f'
                r' -~\r\n\t]+$')
JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')


def scan(d):
    out, i, n = [], 0, len(d)
    while i < n:
        j = d.find(b'\x00', i)
        if j < 0:
            break
        s = d[i:j]
        if 3 <= len(s) <= 400:
            try:
                t = s.decode('cp932')
            except UnicodeDecodeError:
                t = None
            if t and JP.search(t) and OK.match(t) and len(JP.findall(t)) >= 2:
                out.append((i, t))
        i = j + 1
    return out


def main():
    d = open(DUMP, 'rb').read()
    got = scan(d)
    print('%d Japanese strings' % len(got))
    if got:
        lo, hi = got[0][0], got[-1][0]
        print('spread over 0x%X .. 0x%X' % (lo, hi))
    seen = {}
    for o, t in got:
        seen.setdefault(t, o)
    for t, o in sorted(seen.items(), key=lambda kv: kv[1]):
        print('  %8d  %s' % (o, t[:110]))
    print()
    print('%d unique, %d chars' % (len(seen), sum(len(t) for t in seen)))


if __name__ == '__main__':
    main()
