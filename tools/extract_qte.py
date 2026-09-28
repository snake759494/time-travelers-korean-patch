# -*- coding: utf-8 -*-
"""The interview quiz in Rusanchi's chapter: its answer buttons.

R03Q_2120..2170.qte are Lua, like the menu scripts, but they live inside the
chapter bundle psp/cpk/separate/R03.cpk rather than in psp/script, so the
Lua pass never saw them and the four answers of each question stayed in
Japanese -- drawn through a font whose kanji now carry Hangul (issue #3).
Only the literals handed to Start() are drawn; the （ＱＴＥ成功） labels are
branch names and must stay byte for byte.

The quiz is a spelling test -- pick the right way to write your own name --
so the Korean keeps the same game with near-misses, the right answer in the
same place, and the same readings the dialogue after each answer uses.

  python extract_qte.py            -> ui_json/qte.json
"""
import json, sys
import cpk, dnsfile, extract_lua as L, pack_korean as P

OUT = r'D:\psp\타임트레블러즈\ui_json\qte.json'
KO = {
    '[大山/おおやま]': '오야마', '[太山/ふとやま]': '후토야마',
    '[犬山/いぬやま]': '이누야마', '[天山/てんざん]': '텐잔',
    'かける': '카케루', 'かげる': '카게루', 'がける': '가케루', 'かけゐ': '카케이',
    '２９[歳/さい]': '29살', '３０[歳/さい]': '30살', '３１[歳/さい]': '31살',
    '[秘密/ひみつ]①': '비밀①',
    'リアルライスヒーロー': '리얼 라이스 히어로',
    'リアルワイフヒーロー': '리얼 와이프 히어로',
    'リアルライフヒーロー': '리얼 라이프 히어로',
    'リア[充/じゅう]ライフヒーロー': '리얼충 라이프 히어로',
    '[自警囚/じけいしゅう]': '자경수', '[自爆団/じばくだん]': '자폭단',
    '[自誉団/じほめだん]': '자찬단', '[自警団/じけいだん]': '자경단',
}


def qte_files(d, c):
    """{name: (absolute offset, bytes)} for every distinct .qte in a bundle."""
    out = {}
    for e in sorted((x for x in c.files if x['dir'] == 'psp/cpk/separate'),
                    key=lambda x: x['name']):
        try:
            inner = cpk.CPK(P.Window(d, e['offset'], e['size']))
        except Exception:
            continue
        for x in inner.files:
            if x['name'].endswith('.qte') and x['name'] not in out:
                assert x['size'] == x['extract'], x['name']
                out[x['name']] = (e['offset'] + x['offset'], inner.read(x))
    return out


def drawn(src):
    body = L.uncomment(src)
    for form, a, b, t in L.strings(src):
        if form == 'quote' and L.caller_of(body, a) == b'Start':
            yield a, b, t


def main():
    d = dnsfile.DNSFile(iso=P.SRC)
    c = cpk.CPK(d)
    entries = []
    for name, (_, src) in sorted(qte_files(d, c).items()):
        for a, b, t in drawn(src):
            entries.append({'id': '%s@%d' % (name, a), 'room': b - a,
                            'ja': t, 'ko': KO.get(t, '')})
    json.dump({'schema': 'tt1-ui/1',
               'source': 'psp/cpk/separate/*.cpk :: *.qte',
               'note': 'QTE answer buttons; quoted Lua literals, same length',
               'count': len(entries), 'entries': entries},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    miss = [e['ja'] for e in entries if not e['ko']]
    print('%d answer labels, %d untranslated -> %s' % (len(entries), len(miss), OUT))
    for m in miss:
        print('   no Korean:', m)


if __name__ == '__main__':
    main()
