# -*- coding: utf-8 -*-
"""End-to-end check of the built ISO."""
import json, re, sys, collections
import cpk, dnsfile, extract_flo, pack_korean as P, audit_fonts as A

ISO = sys.argv[1] if len(sys.argv) > 1 else P.DST
TAG = re.compile(r'<[^>]{0,24}>')
gm = json.load(open(P.GLYPH_MAP, encoding='utf-8'))
back = {v: k for k, v in gm.items()}

print('=== the relocated chart file ===')
c = cpk.CPK(dnsfile.DNSFile(iso=ISO))
e = [x for x in c.files if x['name'] == 'tt1.flo'][0]
d = c.read(e)
orig = cpk.CPK(dnsfile.DNSFile()).read(
    [x for x in cpk.CPK(dnsfile.DNSFile()).files if x['name'] == 'tt1.flo'][0])
print('  offset %d, stored %d, extract %d, readback %d bytes, same length: %s'
      % (e['offset'], e['size'], e['extract'], len(d), len(d) == len(orig)))
ko = {x['ja']: x['ko'] for x in
      json.load(open(r'D:\psp\타임트레블러즈\ui_json\flo.json',
                     encoding='utf-8'))['entries']}
left = extract_flo.spans(d)
fields = extract_flo.spans(d, jp_only=False)
kor = 0
for a, b, t in fields:
    s = ''.join(back.get(ord(ch), ch) for ch in t)
    if any('가' <= ch <= '힣' for ch in s):
        kor += 1
print('  text fields %d: Korean %d, still Japanese %d'
      % (len(fields), kor, len(left)))
for a, b, t in left[:5]:
    print('     left: %s' % t[:50])

print()
print('=== fonts ===')
drawn = A.korean_glyphs(A.font_files(ISO), A.font_files(A.ORIG))
for n in sorted(drawn):
    print('  %-16s %4d Korean glyphs' % (n, len(drawn[n])))

print()
print('=== every string against the font that draws it ===')
need = collections.defaultdict(set)
for src, i, t in A.texts():
    need[src] |= {ch for ch in TAG.sub('', t) if ch in gm}


def sub(pred):
    s = set()
    for x in json.load(open(r'D:\psp\타임트레블러즈\ui_json\eboot.json',
                            encoding='utf-8'))['entries']:
        if pred(x.get('ko', '')):
            s |= {ch for ch in x['ko'] if ch in gm}
    return s


need['chapter name'] = sub(lambda t: t.endswith(' 편'))
need['character label'] = sub(lambda t: t.endswith('의 경우'))
ROUTE = {'eboot.json': 'telop_main.xf', 'lua.json': 'telop_main.xf',
         'staffroll.json': 'staffroll.xf', 'tip.json': 'ttp_main.xf',
         'tutorial.json': 'ttp_main.xf', 'help.json': 'ttp_main.xf',
         'outline.json': 'ttp_main.xf', 'table.json': 'ttp_main.xf',
         'flo.json': 'telop_main.xf',
         'choice.json': 'nrm_sub.xf', 'call.json': 'nrm_sub.xf',
         'dialogue': 'nrm_sub.xf',
         'chapter name': 'telop_player.xf',
         'character label': 'telop_sp.xf'}
bad = 0
for src, font in ROUTE.items():
    if src not in need:
        continue
    miss = need[src] - drawn[font]
    bad += len(miss)
    print('  %-16s %-16s missing %d %s'
          % (src, font, len(miss), ''.join(sorted(miss))[:36]))
print()
print('total missing glyphs: %d' % bad)

print()
print('=== word space ===')
for n, (files, meta) in A.font_files(ISO).items():
    codes = {ch['code'] for ch in meta['large']}
    print('  %-16s space present: %s' % (n, 0x20 in codes))
