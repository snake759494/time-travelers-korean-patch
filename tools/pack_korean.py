# -*- coding: utf-8 -*-
"""Build the Korean test ISO from the translated script JSON.

The engine converts CP932 -> Unicode and binary-searches the font table, so
Hangul is carried by re-using kanji code points: every distinct syllable is
assigned one kanji slot, the script is written with those kanji, and the
font's glyph bitmaps at those slots are redrawn as Hangul.

  python pack_korean.py [--dry]
"""
import json, os, glob, re, shutil, struct, subprocess, sys, tempfile, collections
import numpy as np
from PIL import Image, ImageFont, ImageDraw

import cpk, dnsfile, crilayla, pgd, fnt, xpck, imgp, l5enc, aux_fonts
import extract_lua, extract_flo, imgp8, menu_tex, menu_ko, cfgbin, pgdtool
import patch_table
import build_expand2 as B

SRC = r'D:\psp\타임트레블러즈\Time Travelers.iso'
DST = r'D:\psp\타임트레블러즈\Time Travelers (KR).iso'
DST_NOFONT = r'D:\psp\타임트레블러즈\Time Travelers (text only).iso'
JSON_DIR = r'D:\psp\타임트레블러즈\script_fix'      # proof-read dialogue
UI_DIR = r'D:\psp\타임트레블러즈\ui_json'           # tips, tutorials, menus
GLYPH_MAP = r'D:\psp\타임트레블러즈\script_json\_glyph_map.json'
CFG_DIRS = ['psp/txt/tip', 'psp/txt/tutorial', 'psp/txt/help',
            'psp/txt/outline', 'psp/txt/staffroll']
XF_DIR = r'D:\psp\타임트레블러즈\extract\fnt'
MOVIE_DIR = r'D:\psp\타임트레블러즈\movie'      # Sony-encoded subtitled .pmf
TTF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'NanumSquareNeo-cBd.ttf')
SYLLABLES = []   # filled in by main(); the size is measured against these
DNS_LBA, CPK_LBA, EBOOT_LBA, SEC = 285712, 55248, 544, 2048
DNS_SIZE = 591537680
EBOOT_DUMP = (r'D:\psp\ppsspp_win\memstick\PSP\SYSTEM\DUMP'
              '\\NPJH50597_smp_rom.BIN')

# The emulator's dump folder is shared with every other game and does get
# overwritten: when it vanished, the build quietly shipped without the 52
# executable strings (chapter cards, character intros). Keep our own copy,
# decrypted once from the retail EBOOT with _eboot_decrypt, and fall back
# to it rather than silently dropping the lot.
EBOOT_PLAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '_assets', 'NPJH50597_eboot_plain.BIN')
ENC = 'cp932'
# The dump is a decrypted ELF produced by PPSSPP.  It is useful for reading
# and translating the strings, but it must not replace the encrypted ~PSP PRX
# in a real-hardware ISO.  The VC2 hardware build kept its EBOOT untouched.
HARDWARE_SAFE_EBOOT = False
# Nothing inside the CPK may move. A sister project (원격수사) traced the very
# same console error, C1-2858-3, to an archive that had been relocated, and
# fixed it by replacing every file where it already lay. This build holds that
# line: a file that would outgrow its slot is left in Japanese rather than
# repacked somewhere else.
KEEP_LAYOUT = False
# Diagnostic: leave the PGD-encrypted install stream completely alone. The
# emulator decrypts PGD in software, the console does it in the KIRK engine,
# so a re-encryption that satisfies one need not satisfy the other -- and the
# game reads this stream on its way to the title screen.
SKIP_DNS = False
# Diagnostic: cycle the same blocks through decrypt and re-encrypt but leave
# their contents alone. If the console still refuses the disc, the round trip
# itself is not faithful; if it boots, the crypto is fine and it is what the
# edits do to the data that upsets it.
PGD_IDENTITY = False
# Nothing in the archive may change size either. CRILAYLA stops at the length
# the header declares, so a shorter re-compression can simply be padded back
# out to the room it had -- and then the TOC row never needs touching.
KEEP_SIZE = True
# Diagnostic: keep only the first N edits to the encrypted stream. If even one
# changed string is enough to stop the console, something is checking the
# stream's contents rather than its layout.
DNS_LIMIT = 0
# Diagnostic: which kinds of edit to the encrypted stream this build carries.
# A prefix of the edit list, which is what DNS_LIMIT cuts, does not correspond
# to anything you can name afterwards; these do, so a failure points at work
# rather than at an index.
#   pck  chapter dialogue         cfg  tips, tutorials, help, outlines
#   flo  time-travel chart        scn  choices
#   menu menu artwork             lua  menu and system messages
DNS_STAGES = frozenset(['pck', 'cfg', 'flo', 'scn', 'menu', 'lua', 'table'])
# Diagnostic: leave these sheets in Japanese. The two named here are the only
# ones whose rewritten block comes out of the method-2 encoder, which is the
# one encoder whose output was never shown to match what the game shipped --
# every method-4 block in the game re-encodes byte for byte, method 2 only
# round-trips through our own decoder.
MENU_SKIP = frozenset(())
# Diagnostic: when either of these is non-empty, patch only what it names.
# Narrowing to one file at a time is the only way left to get a reproducer:
# the sheets are stored plain, so patching one changes its bytes in place and
# nothing else in the archive at all -- no TOC row, no offsets, no sizes.
MENU_ONLY = frozenset(())
LUA_ONLY = frozenset(())
# Diagnostic: leave every font exactly as it shipped. The rebuilt glyph atlas
# goes into the encrypted stream alongside the text edits and is not covered
# by DNS_STAGES, so it has been in every build tested so far -- including all
# of the ones meant to isolate something else. The one build the console ever
# accepted, the one that left the stream alone, dropped the fonts with it.
SKIP_FONTS = False
# CRILAYLA 블롭이 고정된 슬롯보다 짧을 때 남는 자리를 어떻게 채울지.
#   'front' 압축 스트림 앞에 넣고 comp_len 에 포함 (지난 세션이 만든 형태.
#           리테일에는 이런 파일이 없다)
#   'back'  블롭 뒤에 0 을 붙인다 (그 이전 형태)
#   'none'  채우지 않는다. TOC 가 실제 크기를 말하므로 패딩 자체가 불필요하며
#           리테일과 같은 모양이 된다. 파일 시작 위치는 그대로다.
CRILAYLA_PAD = 'none'
# Re-encrypt the whole install stream with pgdecrypt.exe rather than rewriting
# its blocks in place. The tool writes a fresh header and key alongside the
# data; patching blocks under the original header is what the console refused.
PGD_TOOL = True


# ---------------------------------------------------------------- assignment
class Window:
    """Read-only view of a nested archive inside the decrypted DNS stream."""

    def __init__(self, f, base, size):
        self.f, self.base, self.size, self.pos = f, base, size, 0

    def seek(self, off, whence=0):
        self.pos = off

    def read(self, n):
        self.f.seek(self.base + self.pos)
        d = self.f.read(min(n, self.size - self.pos))
        self.pos += len(d)
        return d


def separate_copies(d, c):
    """psp/cpk/separate/<CH>.cpk each bundle their own copy of the script.

    They are stored uncompressed and the engine reads chapter data from them,
    so a patch that only touches psp/txt/event/pck leaves half the game
    running on the original text.
    """
    out = {}
    for e in (x for x in c.files if x['dir'] == 'psp/cpk/separate'):
        ch = e['name'][:-4]
        try:
            inner = cpk.CPK(Window(d, e['offset'], e['size']))
        except Exception:
            continue
        for x in inner.files:
            if x['dir'] == 'psp/txt/event/pck' and x['name'] == ch + '.pck':
                out[ch] = (e['offset'] + x['offset'], x['size'], x['extract'])
                break
    return out


def load_ui():
    """id -> (ja, ko) for the tip/tutorial/help/outline/staffroll/menu text."""
    out = {}
    for p in sorted(glob.glob(os.path.join(UI_DIR, '*.json'))):
        b = os.path.basename(p)
        if b == 'manifest.json' or b.startswith('_'):
            continue                       # _sprites.json is a coordinate table
        for e in json.load(open(p, encoding='utf-8'))['entries']:
            if e.get('ko', '').strip():
                out[e['id']] = (e['ja'], e['ko'])
    return out


def split_cfg(d):
    """A .cfg.bin is one bare blob: strings sit at the end, count in the header."""
    if len(d) < 16:
        return None
    cnt = struct.unpack('<I', d[12:16])[0]
    if not 0 < cnt < 4096:
        return None
    end = len(d)
    while end > 0 and d[end - 1] == 0xFF:
        end -= 1
    for base in range(end - 1, 0, -1):
        seg = d[base:end]
        if not seg.endswith(b'\x00') or seg.count(b'\x00') != cnt:
            continue
        try:
            seg.decode(ENC)
        except UnicodeDecodeError:
            continue
        return base, end, seg.split(b'\x00')[:-1]
    return None


def patch_cfg(c, d, ui, table):
    """Same treatment as a dialogue blob: swap the strings, then move every
    byte offset in the record area that pointed at them.

    The blob keeps its original uncompressed length, so ExtractSize never
    changes; only the stored size does, and only for the compressed ones.
    """
    edits, done, skipped = [], 0, []
    trimmed = collections.Counter()
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(toc.rows)}
    toc_base = c.header['TocOffset'] + 24 + toc.rows_off
    for e in sorted((x for x in c.files if x['dir'] in CFG_DIRS),
                    key=lambda x: x['name']):
        data = c.read(e)
        got = split_cfg(data)
        if not got:
            continue
        base, end, strs = got
        new = list(strs)
        hit = 0
        for i, s in enumerate(strs):
            k = '%s#%d' % (e['name'], i)
            if k not in ui:
                continue
            ja, ko = ui[k]
            try:
                new[i] = recode(normalize(ja, ko), table)
            except UnicodeEncodeError:
                continue
            hit += 1
        if not hit:
            continue
        # These files carry dense offset tables -- the tip and tutorial
        # indexes have hundreds of entries. cfgbin reads where those offsets
        # are, so the table can be rebuilt at whatever length the Korean needs
        # and every offset that pointed into it moved to match; it only hands
        # back a file it can reproduce byte for byte. Anything it will not
        # vouch for keeps each string in the slot it already occupies and has
        # the few that do not fit trimmed, so nothing moves.
        # Rebuilding is a change inside the file, not to where it sits, so it
        # is compatible with the pinned layout: what comes out still has to
        # fit the slot below, and pin_sizes refuses anything that does not.
        cfg = cfgbin.parse(data)
        blob = None
        if cfg is not None:
            rebuilt = [s for _, s in cfg.strs]
            at, cur = cfg.index(), base - cfg.base
            for i, s in enumerate(strs):
                j = at.get(cur)
                if j is not None:
                    rebuilt[j] = new[i]
                cur += len(s) + 1
            cand = cfg.pack(rebuilt)
            # A rebuilt file may only shrink. staffroll_ja.cfg.bin comes out
            # 1008 bytes longer than it shipped, and the reader has already
            # sized its buffer from the original; keeping each string in the
            # slot it had, trimmed, is the safe answer even though it costs
            # the tail of the longest lines.
            if len(cand) <= len(data):
                blob = cand
            else:
                print('  %s would grow %d bytes; kept in its own slots'
                      % (e['name'], len(cand) - len(data)))
        if blob is None:
            for i in range(len(new)):
                while len(new[i]) > len(strs[i]):
                    new[i] = new[i].decode(ENC)[:-1].encode(ENC)
                    trimmed[e['name']] += 1
            keep = B.fixed_slots(strs, new)
            if keep is None:
                continue
            blob = bytearray(data[:base]) + keep + data[end:]
        grew_here = len(blob) > len(data)
        if not grew_here:
            blob = bytes(blob) + bytes([0xFF]) * (len(data) - len(blob))
        blob = bytes(blob)

        row = toc_base + row_of[(e['dir'], e['name'])] * toc.row_len
        nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
        slot = nxt - e['offset']

        if e['size'] == e['extract'] and not grew_here:
            edits.append((e['offset'], blob))            # stays raw, same size
        else:
            # Offsets inside a .cfg.bin are file-relative, so it may grow; pay
            # for it with compression and tell the TOC both new sizes.
            slot = pinned(slot, e)
            comp = fit_crilayla(blob, slot)
            if len(comp) > slot:
                skipped.append((e['name'], len(comp), slot))
                continue
            edits.append((e['offset'], comp))
            edits.append((row + 8, struct.pack('>I', len(comp))))
            edits.append((row + 12, struct.pack('>I', len(blob))))
        done += hit
    if trimmed:
        print('  trimmed to fit their slot: %s'
              % dict(trimmed.most_common(5)))
    return edits, done, skipped


def patch_eboot(table):
    """Rewrite the system messages compiled into the executable.

    A PPSSPP dump is a decrypted ELF, whereas the disc carries an encrypted
    ~PSP PRX.  Without a PRX re-encryptor, replacing the whole EBOOT is not
    hardware-safe, so the default build preserves the retail executable.
    The JSON remains available for a future properly re-encrypted build.

    Only what the game's own renderer draws is touched; see eboot_ko.
    """
    if HARDWARE_SAFE_EBOOT:
        return [], 0, ['hardware-safe build: encrypted EBOOT.BIN preserved']
    src = EBOOT_DUMP if os.path.exists(EBOOT_DUMP) else EBOOT_PLAIN
    if not os.path.exists(src):
        raise SystemExit('no decrypted EBOOT in %s nor %s; the build would '
                         'drop all 52 executable strings'
                         % (EBOOT_DUMP, EBOOT_PLAIN))
    d = bytearray(open(src, 'rb').read())
    doc = json.load(open(os.path.join(UI_DIR, 'eboot.json'), encoding='utf-8'))
    done, over = 0, []
    for e in doc['entries']:
        if not e.get('ko', '').strip():
            continue
        off = int(e['id'].split('@')[1])
        room = e['room']
        if bytes(d[off:off + room]) != e['ja'].encode(ENC):
            over.append((e['id'], 'dump no longer matches'))
            continue
        try:
            raw = recode(e['ko'], table)
        except UnicodeEncodeError:
            continue
        if len(raw) > room:
            over.append((e['id'], '%d > %d bytes' % (len(raw), room)))
            continue
        d[off:off + room] = raw + b'\x00' * (room - len(raw))
        done += 1
    return sign_eboot(bytes(d)), done, over


SEBOOT = r'D:\psp\디크립트 툴\PSP-ISO-Tools\EBOOT\_seboot.exe'
EBOOT_TAG = '5'                 # d91613f0, the tag the disc's own EBOOT carries
EBOOT_RECORD = 51352            # /PSP_GAME/SYSDIR/EBOOT.BIN directory record


def sign_eboot(plain):
    """Encrypt the patched executable back into a ~PSP PRX.

    A decrypted ELF runs under PPSSPP but the console refuses it before the
    title menu (C1-2858-3). Signing it again with the tag the disc itself uses
    means one build serves both. The result is 336 bytes longer, which still
    lands inside the same 1943 sectors, so nothing in the image has to move --
    only the size in the directory record.
    """
    work = tempfile.mkdtemp(prefix='eboot_')
    src = os.path.join(work, 'BOOT.BIN')
    dst = os.path.join(work, 'EBOOT.BIN')
    open(src, 'wb').write(plain)
    r = subprocess.run([SEBOOT, '-t' + EBOOT_TAG, 'BOOT.BIN', 'EBOOT.BIN'],
                       cwd=work, capture_output=True, text=True)
    if r.returncode or not os.path.exists(dst):
        shutil.rmtree(work, ignore_errors=True)
        raise SystemExit('EBOOT 서명 실패: %s' % (r.stdout or r.stderr)[-200:])
    signed = open(dst, 'rb').read()
    shutil.rmtree(work, ignore_errors=True)
    if signed[:4] != b'~PSP':
        raise SystemExit('서명 결과가 ~PSP 가 아닙니다')
    if -(-len(signed) // SEC) > -(-len(plain) // SEC):
        raise SystemExit('서명본이 원래 섹터 수를 넘습니다: %d' % len(signed))
    print('  EBOOT re-signed: %d bytes, tag %s' % (len(signed), EBOOT_TAG))
    size = struct.pack('<I', len(signed)) + struct.pack('>I', len(signed))
    return [(EBOOT_LBA * SEC, signed),
            (EBOOT_RECORD + 10, size)]      # both-endian size in the ISO record


def rewrite_pgd(edits):
    return pgdtool.rewrite(edits, SRC, DNS_LBA, DNS_SIZE, SEC)


def stage(name, got):
    """`got`, unless this build is leaving that kind of edit out."""
    if name in DNS_STAGES:
        return got
    print('  [%s] %d edits dropped (diagnostic)' % (name, len(got)))
    return []


def pinned(limit, e):
    """`limit` narrowed to the stored size when the layout is pinned.

    KEEP_SIZE holds every file's FileSize at what it shipped with, so the
    reader only ever reads that many bytes. A blob that fits the gap to the
    next file but overruns the pinned size gets its tail cut -- and CRILAYLA
    keeps the original's first 0x100 bytes at the very end of the blob, so
    the cut lands there and the file comes out short and shifted from byte
    255 on. That is how menu_mainmenu.lua came to be corrupt on the console
    while the emulator, reading one byte past the buffer, limped through it.
    """
    return min(limit, e['size']) if KEEP_SIZE else limit


def fit_crilayla(blob, limit):
    """Compress `blob` into `limit`, working harder before giving up.

    Holding a match back costs a couple of percent on most files and pays it
    back on a few, so the plain greedy pass stays in the running too.
    """
    best = None
    for effort, lazy in ((256, True), (1024, True), (256, False), (4096, True)):
        comp = crilayla.compress(blob, effort=effort, lazy=lazy)
        if len(comp) <= limit:
            return comp
        if best is None or len(comp) < len(best):
            best = comp
    return best                       # the caller reports it as too big


def fit_crilayla_slot(blob, target):
    """Fill a shorter CRILAYLA blob without leaving bytes after its tail.

    The CPK FileSize is pinned so that no following file moves.  Appending
    zeroes to a shorter CRILAYLA blob makes the declared compressed length end
    before the stored file ends.  Our reader ignores that slack, but the PSP
    CRI decoder expects ``16 + comp_len + 0x100`` to be the complete stored
    blob.  Extra bytes must therefore be placed *before* the reversed bit
    stream and included in comp_len; the decoder consumes the original stream
    from the end and never reaches the leading slack.
    """
    if len(blob) >= target:
        return blob
    if blob[:8] != b'CRILAYLA' or len(blob) < 16:
        return blob + bytes(target - len(blob))
    comp_len = struct.unpack('<I', blob[12:16])[0]
    comp_end = 16 + comp_len
    if comp_end + 0x100 != len(blob):
        # Not a freshly produced canonical blob; retain the conservative
        # fallback rather than guessing at an already padded layout.
        return blob + bytes(target - len(blob))
    pad = target - len(blob)
    out = bytearray(blob[:16])
    struct.pack_into('<I', out, 12, comp_len + pad)
    out += bytes(pad)
    out += blob[16:]
    assert len(out) == target
    return bytes(out)


def pin_sizes(c, d, edits):
    """Drop every TOC size update, padding its file back to the room it had.

    A file that re-compresses smaller still has to occupy what it occupied:
    a sister project traced this console's C1-2858-3 to an archive whose
    layout had shifted, and size is part of that layout. The slack is put at
    the beginning of CRILAYLA's backwards-read bitstream and included in its
    compressed length, so no bytes remain after the 0x100-byte raw tail.
    """
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    base = c.header['TocOffset'] + 24 + toc.rows_off
    room, where, rows = {}, {}, {}
    for i, r in enumerate(toc.rows):
        row = base + i * toc.row_len
        key = (r['DirName'], r['FileName'])
        e = next((x for x in c.files if (x['dir'], x['name']) == key), None)
        if e:
            room[row + 8] = e['size']
            # ExtractSize is left alone: it is the length the reader allocates
            # and decompresses into, so it has to keep telling the truth. Only
            # the stored length is pinned, and the data padded back out to it.
            where[e['offset']] = e['size']
            rows[e['offset']] = (row + 8, row + 12)

    # A blob that outgrew its pinned size cannot go in at all: its TOC entry
    # will keep saying the old, smaller number, so the reader would take the
    # front of it and drop the tail. Refuse the whole file -- its data and
    # both of its TOC words -- rather than write something that reads short.
    veto = set()
    for off, blob in edits:
        if off in where and len(blob) > where[off]:
            veto.add(off)
    dead = {w for off in veto for w in rows[off]} | veto

    out, dropped = [], 0
    for off, blob in edits:
        if off in dead:
            continue
        if off in room and len(blob) == 4 and CRILAYLA_PAD != 'none':
            dropped += 1
            continue
        if off in where and len(blob) < where[off]:
            if CRILAYLA_PAD == 'front':
                blob = fit_crilayla_slot(blob, where[off])
            elif CRILAYLA_PAD == 'back':
                blob = blob + bytes(where[off] - len(blob))
        out.append((off, blob))
    print('  layout pinned: %d TOC size updates dropped' % dropped)
    if veto:
        names = [x['name'] for x in c.files if x['offset'] in veto]
        print('  %d files outgrew their pinned size and were left in Japanese:'
              ' %s' % (len(veto), ', '.join(sorted(names)[:6])))
    return out


def patch_movie():
    """Drop the subtitled opening in over the original.

    Built separately by op_build.py -- decoding and re-encoding the film takes
    a minute, and nothing else in the build depends on it. It is muxed back
    into the original container at exactly the original length, so it goes in
    where it already sits, uncompressed, with nothing in the CPK to update.
    """
    out = []
    outer = cpk.CPK(SRC, base=CPK_LBA * SEC)
    for e in (x for x in outer.files if x['dir'] == 'psp/mov'):
        p = os.path.join(MOVIE_DIR, e['name'])
        if not os.path.exists(p):
            continue
        blob = open(p, 'rb').read()
        if len(blob) != e['size'] or blob[:8] != b'PSMF0015':
            print('  %s: %d bytes, slot is %d -- skipped'
                  % (e['name'], len(blob), e['size']))
            continue
        out.append((CPK_LBA * SEC + e['offset'], blob))
    return out


def patch_menu(c, d):
    """Redraw the Korean into the menu art.

    The button hints are pictures, not text -- furigana and all -- so the
    label rectangles come from the archive's own vertex buffer and the
    Korean is drawn into them. The texture keeps its length, so the .xa
    around it does not have to move.
    """
    edits, done, skipped = [], 0, []
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(toc.rows)}
    toc_base = c.header['TocOffset'] + 24 + toc.rows_off
    # A texture can need both treatments -- the character-select screen has
    # its guidance line on nothing and its name plates on colour -- so the
    # jobs for one texture are a list, not one entry that replaces the other.
    jobs = {}
    for tag, table in (('clear', menu_ko.SPRITES), ('over', menu_ko.OVER)):
        for name, sheets in table.items():
            for k, v in sheets.items():
                jobs.setdefault(name, {}).setdefault(k, []).append((tag, v))
    for name, sheets in jobs.items():
        if MENU_ONLY and name not in MENU_ONLY:
            continue
        e = [x for x in c.files if x['name'] == name][0]
        blob = bytearray(c.read(e))
        parts = {p['name']: p for p in xpck.parse(bytes(blob))}
        hit = 0
        for xi_name, todo in sheets.items():
            if (name, xi_name) in MENU_SKIP:
                print('  [%s %s] left in Japanese (diagnostic)'
                      % (name, xi_name))
                continue
            xi = parts[xi_name]['data']
            ind, _ = imgp8.indices(xi)
            pal = imgp8.palette(xi)
            for mode, spec in todo:
                if mode == 'clear':
                    for box, text in spec.items():
                        if menu_tex.draw(ind, pal, box, text):
                            hit += 1
                else:
                    boxes, bg = spec
                    for x0, y0, x1, y1, text in boxes:
                        if menu_tex.draw_over(ind, pal, (x0, y0, x1, y1),
                                              text, bg):
                            hit += 1
            new = menu_tex.encode(xi, ind)
            if new is None or len(new) != len(xi):
                skipped.append((name, xi_name))
                continue
            off = parts[xi_name]['offset']
            blob[off:off + len(new)] = new
        if not hit:
            continue
        out = bytes(blob)
        nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
        row = toc_base + row_of[(e['dir'], e['name'])] * toc.row_len
        if e['size'] == e['extract']:
            edits.append((e['offset'], out))
        else:
            slot = pinned(nxt - e['offset'], e)
            comp = fit_crilayla(out, slot)
            if len(comp) > slot:
                skipped.append((name, 'too big'))
                continue
            edits += [(e['offset'], comp),
                      (row + 8, struct.pack('>I', len(comp))),
                      (row + 12, struct.pack('>I', len(out)))]
        done += hit
    return edits, done, skipped


def widen(text):
    """Latin and digits to their full-width forms.

    The telop fonts carry no half-width glyphs at all -- the chart's own
    '爆発３０秒前' is full-width -- so an ASCII 30 drew nothing.
    """
    return ''.join(chr(ord(ch) - 0x20 + 0xFF00)
                   if '0' <= ch <= '9' or 'A' <= ch <= 'Z' or 'a' <= ch <= 'z'
                   else ch for ch in text)


def patch_flo(c, d, ui, table):
    """The time-travel chart lives in psp/script/tt1.flo.

    Its node titles and the telops that head each scene -- '爆発30秒前' and
    the rest -- were never translated, and untranslated Japanese does not
    stay Japanese here: the kanji it uses are the ones the Hangul rides on,
    so it drew nonsense syllables. Each field is written back inside the
    length it already had; nothing addresses them from outside.
    """
    p = os.path.join(UI_DIR, 'flo.json')
    if not os.path.exists(p):
        return [], 0, []
    ko = {e['ja']: e['ko']
          for e in json.load(open(p, encoding='utf-8'))['entries']
          if e.get('ko', '').strip()}
    e = [x for x in c.files if x['name'] == 'tt1.flo'][0]
    data = bytearray(c.read(e))
    done, over = 0, []
    # jp_only would skip any field written in kanji alone -- the chart's
    # automatic-branch label is one of those and appears 98 times, so it
    # stayed Japanese and drew as garbage once its kanji were re-pointed.
    # Only fields the table names are touched, so widening this is safe.
    for a, b, ja in sorted(extract_flo.spans(bytes(data), jp_only=False),
                           key=lambda r: -r[0]):
        if ja not in ko:
            continue
        try:
            raw = recode(widen(ko[ja]), table)
        except UnicodeEncodeError:
            continue
        if len(raw) + 1 > b - a:
            over.append((ja[:24], len(raw), b - a))
            continue
        # The field is read to its NUL, and the original filled it exactly.
        # A shorter translation has to bring its own terminator or the
        # filler is read as part of the string -- which is what put a row of
        # slashes after '폭발 30초 전'.
        data[a:b] = raw + b'\x00' + b'\xff' * (b - a - len(raw) - 1)
        done += 1
    if not done:
        return [], 0, over
    blob = bytes(data)
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(toc.rows)}
    row = (c.header['TocOffset'] + 24 + toc.rows_off
           + row_of[(e['dir'], e['name'])] * toc.row_len)
    nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
    slot = pinned(nxt - e['offset'], e)
    comp = fit_crilayla(blob, slot)
    if len(comp) <= slot:
        return [(e['offset'], comp),
                (row + 8, struct.pack('>I', len(comp)))], done, over
    if KEEP_LAYOUT:
        print('  tt1.flo would need %d bytes for a %d-byte slot; left alone'
              % (len(comp), slot))
        return [], 0, over
    # Korean does not compress the way the Japanese did -- the kana it
    # replaces are a handful of repeated byte values, the kanji the Hangul
    # rides on are scattered -- so the file no longer fits where it sat.
    # The archive has megabytes of unused tail; move it there and point the
    # directory entry at the new place.
    end = max(x['offset'] + x['size'] for x in c.files)
    tail = (max(end, c.header['ContentOffset'] + c.header['ContentSize'])
            + SEC - 1) // SEC * SEC
    # Korean does not compress the way the Japanese did -- the kana it
    # replaces are a handful of repeated byte values, the kanji the Hangul
    # rides on are scattered -- so the file no longer fits where it sat.
    # Past the end of the archive is no good (the reader would not follow),
    # but every file is padded up to a 2048 boundary, and a dozen of those
    # pads together are more than enough. Slide the run that follows forward
    # until the slack absorbs the growth.
    # Sliding everything after it does not work -- the pads are smaller than
    # the 2048 alignment, so the shift never gets absorbed and 1,588 files
    # end up moving. What does work is repacking just this file and the nine
    # .scn that follow it: those are Korean now too and compress smaller, and
    # together the ten sit in one region that nothing else reaches into.
    order = sorted(c.files, key=lambda x: x['offset'])
    i = order.index(e)
    group = [e]
    for x in order[i + 1:]:
        if not x['name'].endswith('.scn'):
            break
        group.append(x)
    limit = order[i + len(group)]['offset']
    blobs = {e['name']: comp}
    for x in group[1:]:
        blobs[x['name']] = crilayla.compress(scn_blob(c, x, ui, table)[0],
                                             effort=256)
    cursor = e['offset']
    zero = min(c.header['TocOffset'], c.header['ContentOffset'])
    edits = []
    for x in group:
        b = blobs[x['name']]
        end = cursor + len(b)
        if end > limit:
            print('  tt1.flo does not fit even after repacking; left alone')
            return [], 0, over + [('tt1.flo', len(comp), nxt - e['offset'])]
        r = (c.header['TocOffset'] + 24 + toc.rows_off
             + row_of[(x['dir'], x['name'])] * toc.row_len)
        edits += [(cursor, b), (r + 8, struct.pack('>I', len(b))),
                  (r + 16, struct.pack('>Q', cursor - zero))]
        x['offset'] = cursor
        x['size'] = len(b)
        x['placed'] = True          # patch_scn must not compress it again
        # 16, not the archive's usual 2048: rounding each of these up to a
        # sector gives back exactly what the shorter Korean saved, and then
        # nothing fits. The reader seeks to the offset the row gives it.
        cursor = (end + 15) // 16 * 16
    print('  tt1.flo grew to %d; repacked with %d .scn into %d..%d'
          % (len(comp), len(group) - 1, e['offset'], limit))
    return edits, done, over


def patch_lua(c, d, table):
    """Menu and system wording lives in psp/script/lua/**/*.lua.

    The scripts are plain Lua source with every literal written as
    string.char(0x..,..), so the text can simply be spliced -- nothing
    addresses it by offset. Splices run back to front to keep the offsets
    that follow them valid.

    Asset and animation names are left alone: they are lookup keys, and
    Chr_SetMotion would find nothing if they were translated.
    """
    ko = {}
    for e in json.load(open(os.path.join(UI_DIR, 'lua.json'),
                            encoding='utf-8'))['entries']:
        if e.get('ko', '').strip():
            ko[e['id']] = e['ko']
    edits, done, skipped = [], 0, []
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(toc.rows)}
    toc_base = c.header['TocOffset'] + 24 + toc.rows_off
    for e in sorted((x for x in c.files if x['name'].endswith('.lua')),
                    key=lambda x: (x['dir'], x['name'])):
        if LUA_ONLY and e['name'] not in LUA_ONLY:
            continue
        src = c.read(e)
        out = bytearray(src)
        hit = 0
        for form, a, b, _ in sorted(extract_lua.strings(src),
                                    key=lambda r: -r[1]):
            k = '%s@%d' % (e['name'], a)
            if k not in ko:
                continue
            try:
                raw = recode(ko[k], table)
            except UnicodeEncodeError:
                continue
            out[a:b] = extract_lua.encode(form, raw)
            hit += 1
        if not hit:
            continue
        blob = bytes(out)
        nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
        slot = nxt - e['offset']
        row = toc_base + row_of[(e['dir'], e['name'])] * toc.row_len
        if e['size'] == e['extract'] and len(blob) <= slot:
            edits.append((e['offset'], blob))
            edits.append((row + 8, struct.pack('>I', len(blob))))
            edits.append((row + 12, struct.pack('>I', len(blob))))
        else:
            slot = pinned(slot, e)
            comp = fit_crilayla(blob, slot)
            if len(comp) > slot:
                skipped.append((e['name'], len(comp), slot))
                continue
            edits.append((e['offset'], comp))
            edits.append((row + 8, struct.pack('>I', len(comp))))
            edits.append((row + 12, struct.pack('>I', len(blob))))
        done += hit
    return edits, done, skipped


SCN_TABLES = (0x30, 0x34, 0x38)     # header words holding each table's start


def scn_blob(c, e, ui, table):
    """One .scn with its Korean written in. Returns (blob, replaced, trimmed).

    Nothing moves: every string stays at its own offset and keeps its own
    length, the leftover filled with spaces.
    """
    by_text = {ja: ko for k, (ja, ko) in ui.items() if k.startswith('scn#')}
    data = c.read(e)
    bounds = [struct.unpack('<I', data[o:o + 4])[0] for o in SCN_TABLES]
    bounds.append(len(data))
    out = bytearray(data)
    hit, cut, idx = 0, 0, 0
    for t in range(len(bounds) - 1):
        a, b = bounds[t], bounds[t + 1]
        body = bytearray()
        for raw in data[a:b].split(b'\x00')[:-1]:
            k = 'scn#%d' % idx
            idx += 1
            new = raw
            pair = ui.get(k)
            if pair is None and raw:
                try:
                    txt = raw.decode(ENC)
                except UnicodeDecodeError:
                    txt = None
                if txt in by_text:
                    pair = (txt, by_text[txt])
            if pair and raw:
                ja, ko = pair
                try:
                    new = recode(normalize(ja, ko), table)
                except UnicodeEncodeError:
                    new = raw
                while len(new) > len(raw):
                    new = new.decode(ENC)[:-1].encode(ENC)
                    cut += 1
                if new != raw:
                    hit += 1
            body += new + b' ' * (len(raw) - len(new)) + b'\x00'
        assert len(body) == b - a, (e['name'], t, len(body), b - a)
        out[a:b] = body
    return bytes(out), hit, cut


def patch_scn(c, d, ui, table):
    """Choice text lives in psp/script/*.scn. All nine files are identical
    here, so one translation covers them all.

    There are three string tables, not one: choices, time-stop titles and
    hints, each starting at an address the header records. Treating the lot
    as a single table and repacking it left the second and third tables
    reading from the middle of the first -- which is how a choice box ended
    up showing someone else's line with its first characters missing.

    So nothing moves. Every string stays at its own offset and keeps its own
    length, the leftover filled with spaces: shorter would let the reader run
    into the next slot, and 0xFF filler is what put ????? in front of the
    choices before.
    """
    edits, done, short = [], 0, 0
    # The extraction dropped repeats, so a line that appears twice only has a
    # translation under its first index. Look the text up as well.
    by_text = {ja: ko for k, (ja, ko) in ui.items() if k.startswith('scn#')}
    toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(toc.rows)}
    toc_base = c.header['TocOffset'] + 24 + toc.rows_off
    for e in sorted((x for x in c.files if x['name'].endswith('.scn')),
                    key=lambda x: x['name']):
        if e.get('placed'):
            done += 1               # already written by the chart repack
            continue
        blob, hit, cut = scn_blob(c, e, ui, table)
        short += cut
        if not hit:
            continue
        nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
        slot = pinned(nxt - e['offset'], e)
        comp = fit_crilayla(blob, slot)
        if len(comp) > slot:
            continue
        row = toc_base + row_of[(e['dir'], e['name'])] * toc.row_len
        edits.append((e['offset'], comp))
        edits.append((row + 8, struct.pack('>I', len(comp))))
        done += hit
    if short:
        print('  %d choice strings trimmed to their slot' % short)
    return edits, done


def load_translation():
    out = {}
    for p in sorted(glob.glob(os.path.join(JSON_DIR, '*.json'))):
        b = os.path.basename(p)
        if b == 'manifest.json' or b.startswith('_'):
            continue
        doc = json.load(open(p, encoding='utf-8'))
        for e in doc['entries']:
            if e.get('ko'):
                out[e['id']] = e['ko']
    return out


# Fonts the engine draws dialogue with. A code point must exist in all of
# them, otherwise scenes that use one of the others render nothing at all.
DIALOGUE_FONTS = [('nrm_sub.xf', 'outer'),
                  ('nrm_main.xf', 'outer'),
                  ('ttp_main.xf', 'dns')]


def load_fonts(dnsf):
    outer = cpk.CPK(SRC, base=CPK_LBA * SEC)
    inner = cpk.CPK(dnsf)
    out = {}
    for name, where in DIALOGUE_FONTS:
        c = outer if where == 'outer' else inner
        e = [x for x in c.files if x['name'] == name][0]
        files = {f['name']: f for f in xpck.parse(c.read(e))}
        out[name] = {'where': where, 'entry': e, 'files': files,
                     'meta': fnt.parse(files['FNT.bin']['data'])}
    return out


def atlas_ink(F, drop_kanji=True):
    """Which atlas pixels are inked, per texture.

    The kanji are optionally cleared first: the translation borrows their
    slots and never draws the rest, so their ink is not an obstacle -- and
    the boxes the font declares overlap each other anyway, which makes them
    useless as a measure of the room actually available.
    """
    m = F['meta']
    out = {}
    for i in range(m['textures']):
        aw, ah, rgba, _ = imgp.decode(F['files']['%03d.xi' % i]['data'])
        out[i] = (np.frombuffer(rgba, np.uint8)
                  .reshape(ah, aw, 4)[:, :, 3] > 0).copy()
    if drop_kanji:
        for c in m['large']:
            if 0x4E00 <= c['code'] <= 0x9FFF:
                _, _, w, h = m['sizes'][c['size']]
                out[c['tex']][c['y']:c['y'] + h, c['x']:c['x'] + w] = False
    return out


def has_room(F, ink, c, w, h):
    """Can a w x h box be drawn at this glyph's place without hitting another?"""
    _, _, gw, gh = F['meta']['sizes'][c['size']]
    a = ink[c['tex']]
    patch = a[c['y']:c['y'] + h, c['x']:c['x'] + w]
    if patch.shape != (h, w):
        return False
    patch = patch.copy()
    patch[:min(gh, h), :min(gw, w)] = False       # its own box is ours to use
    return not patch.any()


def slot_pool(fonts):
    """Full-width kanji code points every dialogue font can host a box in."""
    sets = []
    for f in fonts.values():
        ink = f.setdefault('_ink', atlas_ink(f))
        s = set()
        for c in f['meta']['large']:
            if not 0x4E00 <= c['code'] <= 0x9FFF or c['advance'] < 13:
                continue
            if not has_room(f, ink, c, UNIFORM[2], UNIFORM[3]):
                continue
            try:
                chr(c['code']).encode(ENC)
            except UnicodeEncodeError:
                continue
            s.add(c['code'])
        sets.append(s)
    return sorted(set.intersection(*sets))


AUX_TEXT = {'telop_main.xf': ['eboot.json', 'lua.json'],
            'staffroll.xf': ['staffroll.json']}


def aux_priority(dnsf, syllables):
    """Which syllables the small fonts draw, and what they can already show.

    Returns [(syllables, code points)] with the syllables both fonts need
    first: those can only come from the code points both already carry, so
    they have to be placed before anything eats into that overlap.
    """
    c = cpk.CPK(dnsf)
    need, codes = {}, {}
    for name, files in AUX_TEXT.items():
        e = [x for x in c.files if x['name'] == name][0]
        parts = {f['name']: f for f in xpck.parse(c.read(e))}
        m = fnt.parse(parts['FNT.bin']['data'])
        codes[name] = {ch['code'] for ch in m['large']
                       if 0x4E00 <= ch['code'] <= 0x9FFF
                       and m['sizes'][ch['size']][2] >= UNIFORM[2] - 1
                       and m['sizes'][ch['size']][3] >= UNIFORM[3] - 1}
        s = set()
        for f in files:
            p = os.path.join(UI_DIR, f)
            if os.path.exists(p):
                for x in json.load(open(p, encoding='utf-8'))['entries']:
                    s.update(ch for ch in x.get('ko', '') if ch in syllables)
        need[name] = s
    a, b = AUX_TEXT
    both = need[a] & need[b]
    out = [(both, codes[a] & codes[b]),
           (need[a] - both, codes[a]), (need[b] - both, codes[b])]
    print('  small fonts: %s needs %d syllables, %s needs %d, %d shared'
          % (a, len(need[a]), b, len(need[b]), len(both)))
    return out


def assign(syllables, fonts, prefer=()):
    """Pick one kanji slot per syllable, no two of them overlapping.

    At the size the boxes have grown to they are wider than the tightest
    spacing the atlas uses, so a pair of neighbours would share a column and
    whichever is drawn second would clip the first. Slots are taken in order
    and one that lands on an already-taken box is skipped.

    `prefer` is [(syllables, code points)], most constrained first. The small
    telop and staff-roll fonts carry only a few hundred kanji each and have
    almost no free slots left, so a syllable they have to draw is given a
    code point they already carry -- then nothing has to be re-pointed at
    all. Without this the chapter card came out as ?????.
    """
    pool = slot_pool(fonts)
    taken = {n: collections.defaultdict(list) for n in fonts}
    usable = []
    for code in pool:
        ok = True
        for n, f in fonts.items():
            g = next(c for c in f['meta']['large'] if c['code'] == code)
            for x, y in taken[n][g['tex']]:
                if (abs(g['x'] - x) < UNIFORM[2]
                        and abs(g['y'] - y) < UNIFORM[3]):
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            continue
        for n, f in fonts.items():
            g = next(c for c in f['meta']['large'] if c['code'] == code)
            taken[n][g['tex']].append((g['x'], g['y']))
        usable.append(code)
    if len(usable) < len(syllables):
        raise RuntimeError('need %d slots, %d usable without overlap'
                           % (len(syllables), len(usable)))

    out, used = {}, set()
    left = sorted(syllables)
    for want, codes in prefer:
        pick = [c for c in usable if c in codes and c not in used]
        for s in list(left):
            if s not in want or not pick:
                continue
            out[s] = pick.pop(0)
            used.add(out[s])
            left.remove(s)
    rest = [c for c in usable if c not in used]
    for i, s in enumerate(left):
        out[s] = rest[i]
    return out


import re as _re
_ANYTAG = _re.compile(r'<[^>]{0,16}>')
_GOODTAG = _re.compile(r'^</?[A-Za-z][A-Za-z0-9]*>$')
QUOTES = '「」『』“”‘’"＜＞〈〉'
_TIP = _re.compile(r'(<TIP\d*>)(.*?)(</TIP>)', _re.S)
_RUBY = _re.compile(r'^\[([^/\]]*)/([^\]]*)\]$')


def normalize(ja, ko):
    """Undo translator habits the engine cannot parse.

    The script marks speech as 이름「…」; the engine scans for those brackets
    to split speaker from line, so a translation that swapped them for ASCII
    quotes leaves it searching for a close bracket that never arrives.
    """
    # Tags the source itself uses are authoritative, whatever they look like:
    # <ICON"font_18"> is real markup, not a typo to be cleaned up.
    known = set(_ANYTAG.findall(ja))

    def fixtag(m):
        s = m.group(0)
        if s in known or _GOODTAG.match(s):
            return s
        inner = _re.sub(r'[^A-Za-z0-9/]', '', s[1:-1])
        return '<%s>' % inner if inner else ''
    ko = _ANYTAG.sub(fixtag, ko)

    # Inside <TIPnnn>…</TIP> the [base/key] brackets are structural, not
    # furigana: the engine reads the key to find the glossary entry. Plain
    # ruby can safely lose its brackets, this cannot.
    ja_tips = _TIP.findall(ja)
    if not ja_tips and '<TIP' in ko:        # invented glossary reference
        ko = _re.sub(r'</?TIP\d*>', '', ko)
    if ja_tips and len(ja_tips) == len(_TIP.findall(ko)):
        src = iter(ja_tips)

        def fix(m):
            o = next(src)
            inner, ja_inner = m.group(2), o[1]
            mj = _RUBY.match(ja_inner)
            if mj:
                # 117 of the source's own TIP tags hold plain text, so the
                # brackets are not required -- what broke the parser before was
                # a bare "/reading" left dangling. Drop the furigana instead of
                # re-attaching it: Japanese kana above a Korean word is wrong.
                key = mj.group(2)
                if inner.endswith('/' + key):
                    inner = inner[:-len(key) - 1]
                inner = _RUBY.sub(lambda r: r.group(1), inner)
                inner = inner.replace('[', '').replace(']', '')
                if '/' in inner and '[' not in inner:
                    inner = inner.split('/')[0]
            return m.group(1) + inner + m.group(3)
        ko = _TIP.sub(fix, ko)

    # Re-impose the source's bracket sequence positionally: whatever quote
    # characters the translation used, the nth one becomes the nth of the
    # original. Only safe when the counts agree, so bail out otherwise.
    src = [c for c in ja if c in QUOTES]
    dst = [c for c in ko if c in QUOTES]
    if src and len(src) == len(dst) and src != dst:
        it = iter(src)
        ko = ''.join(next(it) if c in QUOTES else c for c in ko)

    # Whatever happened above, never ship an unclosed bracket: the original
    # script has none, and the engine scans forward for the closer.
    for op, cl in (('「', '」'), ('『', '』'), ('＜', '＞')):
        d = ko.count(op) - ko.count(cl)
        if d > 0:
            ko += cl * d
        while d < 0:
            i = ko.rfind(cl)
            if i < 0:
                break
            ko = ko[:i] + ko[i + 1:]
            d += 1
    return ko


# Punctuation the translation uses that some dialogue font has no glyph for.
# The Japanese script used the full-width forms throughout; the half-width
# ones the translator reached for are missing from at least one font, and the
# engine draws its missing-glyph box for them.
try:
    PUNCT = json.load(open(r'D:\psp\타임트레블러즈\script_json\_punct_map.json',
                           encoding='utf-8'))
except OSError:
    PUNCT = {}


# Characters the translation uses that CP932 has no room for.
FIXUP = {
    '·': '・',   # ·  -> ・
    '​': '',         # zero-width space -> drop
    '≤': '≦',   # ≤  -> ≦
    '₩': 'W',        # ₩  -> W
    'ㅀ': '',         # stray lone jamo -> drop
}


FULL_STOP = '．'                  # U+FF0E, not the ideographic 。
_TAG = re.compile(r'(<[^>]{0,24}>)')
# every period but a decimal one, plus the ideographic stops the translation
# carried over from the Japanese
_DOT = re.compile(r'(?<!\d)\.|\.(?!\d)|[。｡]')


def full_stops(text):
    """One sentence end throughout, the Korean full-width period.

    The translator typed an ASCII period in most places and left the
    Japanese 。 in others, so the two were showing side by side. Decimal
    points keep the half-width form, and tags are left alone.
    """
    return ''.join(p if p.startswith('<') else _DOT.sub(FULL_STOP, p)
                   for p in _TAG.split(text))


_CTRL = re.compile(r'(:[a-zA-Z_]+=[^:]*)')


def recode(text, table):
    """Hangul -> assigned kanji, then CP932 bytes.

    A `:texture=`, `:model=` or `:movie=` run carries a resource path and its
    coordinates, so the punctuation pass has to stay out of it: turning the
    dot of tip0040.xa into a full-width one leaves the game looking for a file
    that is not there, and it stops. normalize() already protects these; this
    is the same protection one stage later.
    """
    out = []
    for i, seg in enumerate(_CTRL.split(text)):
        if i % 2:                       # the tag itself -- leave it alone
            out.append(seg)
            continue
        seg = full_stops(seg)
        for a, b in PUNCT.items():
            if a in seg:
                seg = seg.replace(a, b)
        for a, b in FIXUP.items():
            if a in seg:
                seg = seg.replace(a, b)
        out.append(''.join(chr(table[c]) if c in table else c for c in seg))
    return ''.join(out).encode(ENC)


# ---------------------------------------------------------------- font redraw
def _smallest(raw, orig_blk, room):
    """Re-encode with whichever method still fits the original block."""
    out = []
    try:
        out.append(l5enc.block(raw, l5enc.tree_of(orig_blk)))
    except Exception:
        pass
    out.append(l5enc.lz10_block(raw))
    out = [b for b in out if len(b) <= room]
    return min(out, key=len) if out else None


UNIFORM = (0, 4, 14, 14)      # offX, offY, w, h -- as large as the atlas will
UNIFORM_ADV = 14              # take; the pen step stays what the kanji used


def rebuild_fnt(F, codes):
    """Give every borrowed slot one box and one advance.

    Those slots come in 15 different boxes and two advances; drawing into each
    as-is is what made the text ripple. There is no spare size-table entry, so
    one that only kanji use is redefined and everything points at it. 13x13
    fits inside every allocation in the atlas, so nothing bleeds into the
    neighbouring glyph.
    """
    data = F['files']['FNT.bin']['data']
    h = struct.unpack('<6H', data[0x1C:0x28])
    sz_off, sz_cnt, lg_off, lg_cnt, sm_off = h[0] * 4, h[1], h[2] * 4, h[3], h[4] * 4
    m = F['meta']

    owner = collections.defaultdict(set)
    for c in m['large']:
        owner[c['size']].add(c['code'])
    for c in m['small']:
        owner[c['size']].add(-1)
    spare = [i for i, cs in owner.items()
             if -1 not in cs and all(0x4E00 <= x <= 0x9FFF for x in cs)]
    if not spare:
        raise RuntimeError('no size entry free to redefine')

    sz_blk = data[sz_off:lg_off]
    lg_blk = data[lg_off:sm_off]
    sz_base = bytearray(imgp.l5_decompress(sz_blk)[:sz_cnt * 4])
    lg_base = imgp.l5_decompress(lg_blk)[:lg_cnt * 8]

    # The re-encode reuses the file's own Huffman tree, so how well it packs
    # depends on which index we point at. Try the candidates and keep one
    # that still fits its block.
    best = None
    for slot in sorted(spare, key=lambda i: -len(owner[i])):
        sz_raw = bytearray(sz_base)
        sz_raw[slot * 4:slot * 4 + 4] = struct.pack('<bbBB', *UNIFORM)
        sz_new = _smallest(bytes(sz_raw), sz_blk, lg_off - sz_off)
        if sz_new is None:
            continue
        lg_raw = bytearray(lg_base)
        packed = (slot & 0x3FF) | (UNIFORM_ADV << 10)
        n = 0
        for i, c in enumerate(m['large']):
            if c['code'] in codes:
                lg_raw[i * 8 + 2:i * 8 + 4] = struct.pack('<H', packed)
                n += 1
        lg_new = _smallest(bytes(lg_raw), lg_blk, sm_off - lg_off)
        if lg_new is not None:
            best = (sz_new, lg_new, n)
            break
    if best is None:
        return None            # caller falls back to bottom-aligned drawing
    sz_new, lg_new, n = best

    out = bytearray(data)
    out[sz_off:lg_off] = sz_new + bytes(lg_off - sz_off - len(sz_new))
    out[lg_off:sm_off] = lg_new + bytes(sm_off - lg_off - len(lg_new))
    return bytes(out), n


def ink_band(F, atlas):
    """Where this font's own glyphs actually sit, measured from the pen.

    Aligning Hangul to the bottom of the character box puts it below the
    other glyphs, because the box reserves descender room the kana never
    use. Matching the band the existing glyphs occupy is what makes the two
    line up.
    """
    m = F['meta']
    tops, bots = [], []
    for c in m['large']:
        if not (0x3040 <= c['code'] <= 0x30FF or 0x0030 <= c['code'] <= 0x005A):
            continue
        ox, oy, w, h = m['sizes'][c['size']]
        if not w or not h:
            continue
        sub = atlas[c['tex']][c['y']:c['y'] + h, c['x']:c['x'] + w] > 0
        ys = np.where(sub)[0]
        if not len(ys):
            continue
        tops.append(oy + int(ys.min()))
        bots.append(oy + int(ys.max()) + 1)
    if not tops:
        return None
    tops.sort(); bots.sort()
    return tops[len(tops) // 2], bots[len(bots) * 9 // 10]


def uniform_target(F):
    """Pick the glyph box every Hangul slot will share.

    The kanji slots we borrow come in 15 different boxes and two advances, so
    drawing into each one as-is makes the text ripple. Rewriting the char
    table to one box and one advance is what actually makes it line up.
    """
    m = F['meta']
    cnt = collections.Counter()
    for c in m['large']:
        if not 0x4E00 <= c['code'] <= 0x9FFF:
            continue
        ox, oy, w, h = m['sizes'][c['size']]
        if ox == 0 and w >= 13 and oy + h == 18:
            cnt[(c['size'], c['advance'])] += 1
    (size_i, adv), _ = cnt.most_common(1)[0]
    return size_i, adv, m['sizes'][size_i]


def rewrite_metrics(F, codes, size_i, adv):
    """Point every borrowed slot at the same size entry and advance."""
    data = F['files']['FNT.bin']['data']
    h = struct.unpack('<6H', data[0x1C:0x28])
    off, cnt = h[2] * 4, h[3]
    blk = data[off:]
    raw = bytearray(imgp.l5_decompress(blk)[:cnt * 8])
    packed = (size_i & 0x3FF) | (adv << 10)
    n = 0
    for i, c in enumerate(F['meta']['large']):
        if c['code'] in codes:
            raw[i * 8 + 2:i * 8 + 4] = struct.pack('<H', packed)
            n += 1
    new = l5enc.block(bytes(raw), l5enc.tree_of(blk))
    room = len(data) - off
    if len(new) > room:
        raise RuntimeError('char table grew: %d > %d' % (len(new), room))
    out = bytearray(data)
    out[off:] = new + bytes(room - len(new))
    return bytes(out), n


_render = {}


FIT = 0.94        # share of syllables that must fit before a size is accepted


def render_box(ch, w, h):
    """Draw one syllable at the largest size the box will take.

    Sizing the type so that *every* syllable fits held the whole set back to
    what the few heaviest ones allowed, and the result read small next to the
    Latin and the digits. The size is chosen so nearly all of them fit, and
    the handful that still overflow drop one step -- a difference of a pixel,
    against a set that is otherwise a full size larger.
    """
    key = (ch, w, h)
    if key in _render:
        return _render[key]
    size = _best_size(w, h)
    while size > 6 and not _fits(ch, size, w, h):
        size -= 1
    org, off = _place(size, w, h)
    f = ImageFont.truetype(TTF, size)
    tmp = Image.new('L', (size * 4, size * 4), 0)
    ImageDraw.Draw(tmp).text(org, ch, font=f, fill=255, anchor='ls')
    box = tmp.crop((off[0], off[1], off[0] + w, off[1] + h))
    m = (np.asarray(box, np.uint8).astype(np.uint16) * 15 // 255).astype(np.uint8)
    _render[key] = m
    return m


_metrics_cache = {}
_place_cache = {}
_ink_cache = {}


def _ink(ch, size):
    """Bounding box of one syllable drawn on the baseline at `size`."""
    k = (ch, size)
    if k not in _ink_cache:
        pad = size * 2
        tmp = Image.new('L', (pad * 2, pad * 2), 0)
        ImageDraw.Draw(tmp).text((pad, pad), ch,
                                 font=ImageFont.truetype(TTF, size),
                                 fill=255, anchor='ls')
        _ink_cache[k] = tmp.getbbox()
    return _ink_cache[k]


def _fits(ch, size, w, h):
    bb = _ink(ch, size)
    return bb is None or (bb[2] - bb[0] <= w and bb[3] - bb[1] <= h)


def _place(size, w, h):
    """Where to crop so the set sits centred in the box at this size."""
    k = (size, w, h)
    if k in _place_cache:
        return _place_cache[k]
    sample = SYLLABLES or '가나다람뷁했음국어일이삼사오육칠팔구십'
    union = None
    for ch in sample:
        bb = _ink(ch, size)
        if bb is None:
            continue
        # a syllable too big for the box is drawn a step down; it must not
        # drag the whole set off centre
        if bb[2] - bb[0] > w or bb[3] - bb[1] > h:
            continue
        union = bb if union is None else (
            min(union[0], bb[0]), min(union[1], bb[1]),
            max(union[2], bb[2]), max(union[3], bb[3]))
    cx = union[0] - (w - (union[2] - union[0])) // 2
    cy = union[1] - (h - (union[3] - union[1])) // 2
    _place_cache[k] = ((size * 2, size * 2), (cx, cy))
    return _place_cache[k]


def _best_size(w, h):
    """Largest size at which nearly the whole set still fits the box."""
    if (w, h) in _metrics_cache:
        return _metrics_cache[(w, h)]
    sample = SYLLABLES or '가나다람뷁했음국어일이삼사오육칠팔구십'
    for size in range(h * 3, 5, -1):
        ok = sum(1 for ch in sample if _fits(ch, size, w, h))
        if ok >= FIT * len(sample):
            _metrics_cache[(w, h)] = size
            return size
    raise RuntimeError('no usable size for %dx%d' % (w, h))


def _metrics(w, h):
    """Kept for callers that just want the nominal size."""
    size = _best_size(w, h)
    org, off = _place(size, w, h)
    return size, org, off


_cache = {}


def mask(ch, w, h):
    k = (ch, w, h)
    if k not in _cache:
        size = max(h * 2, 8)
        f = ImageFont.truetype(TTF, size)
        tmp = Image.new('L', (size * 2, size * 2), 0)
        ImageDraw.Draw(tmp).text((size // 2, size // 2), ch, font=f, fill=255, anchor='mm')
        bb = tmp.getbbox()
        g = tmp.crop(bb).resize((w, h), Image.LANCZOS)
        _cache[k] = (np.asarray(g, np.uint8).astype(np.uint16) * 15 // 255).astype(np.uint8)
    return _cache[k]


def redraw(xi, boxes):
    """boxes: [(x, y, w, h, char)] to overwrite in this texture."""
    w, _ = struct.unpack('<HH', xi[0x10:0x14])
    t_off, t_sz, p_off, p_sz = struct.unpack('<IIII', xi[0x40:0x50])
    tblk = xi[0x58 + t_off:0x58 + t_off + t_sz]
    tiles = imgp.l5_decompress(tblk)
    pblk = xi[0x58 + p_off:0x58 + p_off + p_sz]
    pix = bytearray(imgp.l5_decompress(pblk))
    idx = struct.unpack('<%dH' % (len(tiles) // 2), tiles)

    sw = bytearray()
    for i in idx:
        sw += bytes(32) if i == 0xFFFF else pix[i * 32:i * 32 + 32]
    wb, H = w // 2, len(sw) // (w // 2)
    lin = bytearray(len(sw)); si = 0
    for by in range(H // 8):
        for bx in range(wb // 16):
            for y in range(8):
                d = (by * 8 + y) * wb + bx * 16
                lin[d:d + 16] = sw[si:si + 16]; si += 16
    a = np.frombuffer(bytes(lin), np.uint8)
    nib = np.empty(a.size * 2, np.uint8)
    nib[0::2] = a & 0xF; nib[1::2] = a >> 4
    nib = nib.reshape(H, w)
    for box in boxes:
        x, y, gw, gh, ch = box[:5]
        band = box[5] if len(box) > 5 else None         # (top, height) in box
        if gw <= 0 or gh <= 0 or y + gh > H or x + gw > w:
            continue
        nib[y:y + gh, x:x + gw] = 0                     # wipe the old kanji
        if ch is None:
            continue                                    # clear-only box
        # a band may name its own width: the telop fonts are drawn at two or
        # three times the size of the dialogue ones and must not be squeezed
        # into the dialogue box
        if band and len(band) > 2:
            top, bh, bw = band
            bw = min(gw, bw)
        else:
            top, bh = band if band else (gh - UNIFORM[3], UNIFORM[3])
            bw = min(gw, UNIFORM[2])
        top = max(0, min(top, gh - bh))
        nib[y + top:y + top + bh, x:x + bw] = render_box(ch, bw, bh)
    flat = nib.reshape(-1)
    packed = (flat[0::2] | (flat[1::2] << 4)).astype(np.uint8).tobytes()
    sw2 = bytearray(len(packed)); si = 0
    for by in range(H // 8):
        for bx in range(wb // 16):
            for y in range(8):
                s = (by * 8 + y) * wb + bx * 16
                sw2[si:si + 16] = packed[s:s + 16]; si += 16
    # Writing straight back through the old tile store loses pixels: a blank
    # chunk has no storage at all, and some chunks share one stored tile, so
    # drawing one syllable wiped part of its neighbour. That is what broke
    # glyphs like the Korean 'si'.
    #
    # Re-numbering every tile from scratch fixes it but the tile table then
    # compresses worse than its slot allows, so keep the original table and
    # only touch the entries that have to change. Chunks that went blank give
    # their tile back to a free list, which covers the chunks that now need
    # one of their own -- the store does not grow.
    store, table, blank = {}, [], bytes(32)
    for i in range(len(idx)):
        chunk = bytes(sw2[i * 32:i * 32 + 32])
        if chunk == blank:
            table.append(0xFFFF)
            continue
        if chunk not in store:
            store[chunk] = len(store)
        table.append(store[chunk])
    newpix = b''.join(store)
    newtiles = struct.pack('<%dH' % len(table), *table)

    # The two blocks sit back to back and the header carries both offsets, so
    # they only have to fit the pair of slots together. That matters: the
    # table no longer compresses as well as the original once the tiles are
    # renumbered, while the store gains far more than that from Hangul being
    # simpler than kanji.
    # The whole remainder of the fixed-size .xi is available, including the
    # few bytes of retail padding after the pixel block; the pixel offset must
    # come out 4-byte aligned, which every retail .xi is and which the console
    # requires -- an unaligned pixel block is read fine by PPSSPP but faults
    # the GE on hardware (this is what killed the save screen and the dialogue
    # fonts). menu_tex.encode carries the same fix for the menu textures.
    room = len(xi) - 0x58 - t_off
    tnew = _fit_block(newtiles, tblk, room)
    pnew = _fit_block(newpix, pblk, room)
    new_p_off = gap = None
    if tnew is not None:
        new_p_off = (t_off + len(tnew) + 3) & ~3
        gap = new_p_off - (t_off + len(tnew))
    if (tnew is None or pnew is None
            or len(tnew) + gap + len(pnew) > room):
        # The small auxiliary fonts have no room for a renumbered table.
        # Write back through the tiles they already have instead: pixels in
        # blank or shared chunks are lost, but those fonts only carry the
        # guide and staff-roll text and this is how they shipped before. The
        # retail p_off is used unchanged, so it stays aligned.
        for i, t in enumerate(idx):
            if t != 0xFFFF:
                pix[t * 32:t * 32 + 32] = sw2[i * 32:i * 32 + 32]
        pnew = _fit_block(bytes(pix), pblk, p_sz)
        if pnew is None:
            raise RuntimeError('atlas overflow: table %s pixels %s, room %d'
                               % (_try(newtiles, tblk), _try(newpix, pblk),
                                  room))
        out = bytearray(xi)
        out[0x58 + p_off:0x58 + p_off + p_sz] = pnew + bytes(p_sz - len(pnew))
        return bytes(out)
    out = bytearray(xi)
    out[0x58 + t_off:0x58 + t_off + room] = (
        tnew + bytes(gap) + pnew
        + bytes(room - len(tnew) - gap - len(pnew)))
    struct.pack_into('<IIII', out, 0x40, t_off, len(tnew), new_p_off, len(pnew))
    assert new_p_off % 4 == 0 and 0x58 + new_p_off + len(pnew) <= len(out), \
        'atlas pixel block misaligned or overruns the .xi'
    return bytes(out)


def _try(raw, orig_blk):
    n = [len(l5enc.lz10_block(raw))]
    try:
        n.append(len(l5enc.block(raw, l5enc.tree_of(orig_blk))))
    except Exception:
        pass
    return min(n)


def _fit_block(raw, orig_blk, room):
    out = []
    try:
        out.append(l5enc.block(raw, l5enc.tree_of(orig_blk)))
    except Exception:
        pass
    out.append(l5enc.lz10_block(raw))
    out = [b for b in out if len(b) <= room]
    return min(out, key=len) if out else None


# ---------------------------------------------------------------- main
def main(dry=False, nofont=False):
    ko = load_translation()
    ui = load_ui()
    syll = sorted({c for t in list(ko.values()) + [v[1] for v in ui.values()]
                   for c in t if 0xAC00 <= ord(c) <= 0xD7A3})
    d = dnsfile.DNSFile()
    fonts = load_fonts(d)
    if HARDWARE_SAFE_EBOOT:
        # The chapter card's wording lives inside EBOOT.BIN, and a build that
        # keeps the retail executable keeps that wording in Japanese. Drawing
        # Korean over the glyphs it uses only garbles it, so these two fonts
        # are left exactly as the disc has them.
        for name in ('telop_player.xf', 'telop_sp.xf'):
            fonts.pop(name, None)
    table = assign(syll, fonts, aux_priority(d, syll))
    SYLLABLES[:] = syll
    print('entries %d, distinct syllables %d, shared slots %d, assigned %d'
          % (len(ko), len(syll), len(slot_pool(fonts)), len(table)))
    print('fonts: %s' % ', '.join(fonts))

    # characters that are neither Hangul nor CP932-encodable
    bad = {}
    for t in ko.values():
        for ch in t:
            if ch in table:
                continue
            try:
                ch.encode(ENC)
            except UnicodeEncodeError:
                bad[ch] = bad.get(ch, 0) + 1
    if bad:
        print('NOT ENCODABLE (%d kinds): %s' % (len(bad), sorted(bad.items(), key=lambda x: -x[1])[:15]))

    c = cpk.CPK(d)
    sep = separate_copies(d, c)
    print('per-chapter copies found in psp/cpk/separate: %d' % len(sep))
    edits = []
    pck_edits = []
    grew = []
    for e in sorted((x for x in c.files if x['dir'] == 'psp/txt/event/pck'),
                    key=lambda x: x['name']):
        chapter = e['name'][:-4]
        raw = c.read(e)
        n, recs = B.blobs_of(raw)
        blobs, hit = [], 0
        for bi, (h, off, sz) in enumerate(recs):
            b = raw[off:off + sz]
            g = B.split_strings(b) if len(b) >= 20 else None
            if not g:
                blobs.append(b); continue
            base, total, strs = g
            touched = False
            for si in range(len(strs)):
                t = ko.get('%s:%d:%d' % (chapter, bi, si))
                if t is None:
                    continue
                try:
                    t = normalize(strs[si].decode(ENC), t)
                    strs[si] = recode(t, table)
                except UnicodeEncodeError:
                    continue
                touched = True; hit += 1
            blobs.append(B.join_strings(b, base, total, strs) if touched else b)
        hdr = bytearray(struct.pack('<I', n)); body = bytearray()
        start = 4 + n * 12
        for i, (h, _, _) in enumerate(recs):
            hdr += struct.pack('<III', h, start + len(body), len(blobs[i]))
            body += blobs[i]
        newpck = bytes(hdr) + bytes(body)
        nxt = min(x['offset'] for x in c.files if x['offset'] > e['offset'])
        slot = pinned(nxt - e['offset'], e)
        comp = fit_crilayla(newpck, slot)
        status = 'OK ' if len(comp) <= slot else 'BIG'
        if len(comp) > slot:
            grew.append((e['name'], len(comp), slot))
        print('  %-4s %s %5d lines  pck %6d->%6d  comp %6d/%6d'
              % (chapter, status, hit, len(raw), len(newpck), len(comp), slot))
        if len(comp) <= slot:
            toc = cpk.read_chunk(d, c.header['TocOffset'], b'TOC ')
            idx = [i for i, r in enumerate(toc.rows)
                   if r['FileName'] == e['name'] and r['DirName'] == e['dir']][0]
            row = c.header['TocOffset'] + 24 + toc.rows_off + idx * toc.row_len
            pck_edits += [(e['offset'], comp),
                          (row + 8, struct.pack('>I', len(comp))),
                          (row + 12, struct.pack('>I', len(newpck)))]
        # the chapter bundle keeps its own uncompressed copy; blob offsets are
        # self-relative so zero padding past the end is ignored by the reader
        if chapter in sep:
            off, size, _ = sep[chapter]
            if len(newpck) <= size:
                pck_edits.append((off, newpck + bytes(size - len(newpck))))
            else:
                grew.append((chapter + ' (separate)', len(newpck), size))
    if grew:
        print('\n%d chapters do not fit their slot' % len(grew))
    edits += stage('pck', pck_edits)

    cfg_edits, cfg_done, cfg_skip = patch_cfg(c, d, ui, table)
    edits += stage('cfg', cfg_edits)
    print('UI text: %d strings in %d files (tips, tutorials, help, outlines)'
          % (cfg_done, len(cfg_edits)))
    # Before the choices: this one may slide the .scn files forward to make
    # room, and everything after it has to write to where they ended up.
    flo_edits, flo_done, flo_over = patch_flo(c, d, ui, table)
    edits += stage('flo', flo_edits)
    print('time-travel chart: %d strings in psp/script/tt1.flo' % flo_done)
    if flo_over:
        print('  too long for their field: %s' % flo_over[:4])
    scn_edits, scn_done = patch_scn(c, d, ui, table)
    edits += stage('scn', scn_edits)
    print('choices: %d strings in psp/script/*.scn' % scn_done)
    menu_edits, menu_done, menu_skip = patch_menu(c, d)
    edits += stage('menu', menu_edits)
    print('menu art: %d labels redrawn' % menu_done)
    if menu_skip:
        print('  could not be rebuilt: %s' % menu_skip[:4])
    movie_edits = patch_movie()
    print('opening movie: %d subtitled .pmf' % len(movie_edits))
    tbl_edits, tbl_done, tbl_skip = patch_table.patch(
        c, d, table, UI_DIR, recode, fit_crilayla)
    edits += stage('table', tbl_edits)
    print('mail/diary/TIPS tables: %d strings' % tbl_done)
    if tbl_skip:
        print('  tables left alone: %s' % tbl_skip[:4])
    lua_edits, lua_done, lua_skip = patch_lua(c, d, table)
    edits += stage('lua', lua_edits)
    print('menu and system messages: %d strings in psp/script/lua' % lua_done)
    if lua_skip:
        print('  too long for their slot: %s' % lua_skip[:5])
    if cfg_skip:
        print('  too long for their file: %s' % cfg_skip[:5])
    if KEEP_SIZE:
        edits = pin_sizes(c, d, edits)
    if DNS_LIMIT:
        edits = edits[:DNS_LIMIT]      # original order, for bisection
        print('  DNS edits limited to %d, %d bytes at %s (diagnostic)'
              % (len(edits), sum(len(b) for _, b in edits),
                 ', '.join(str(o) for o, _ in edits)))
    if dry:
        return

    # ---- fonts ----
    # Every dialogue font gets the same syllables drawn into its own slots.
    font_edits = []
    if SKIP_FONTS:
        print('  fonts left exactly as they shipped (diagnostic)')
    for name, F in ({} if nofont or SKIP_FONTS else fonts).items():
        meta = F['meta']
        by_code = {ch['code']: ch for ch in meta['large']}
        codes = set(table.values())
        got = rebuild_fnt(F, codes)
        if got:
            newfnt, nmetrics = got
            fi = F['files']['FNT.bin']
            off = F['entry']['offset'] + fi['offset']
            (font_edits if F['where'] == 'outer' else edits).append(
                ((CPK_LBA * SEC + off) if F['where'] == 'outer' else off, newfnt))
            print('  %-14s FNT.bin: %d slots -> %s adv %d'
                  % (name, nmetrics, UNIFORM, UNIFORM_ADV))
        else:
            print('  %-14s FNT.bin unchanged (table would not fit); glyphs are '
                  'bottom-aligned in their own boxes instead' % name)
        atlas = {}
        for i in range(meta['textures']):
            aw, ah, rgba, _ = imgp.decode(F['files']['%03d.xi' % i]['data'])
            atlas[i] = np.frombuffer(rgba, np.uint8).reshape(ah, aw, 4)[:, :, 3]
        band = ink_band(F, atlas)
        print('  %-14s own glyphs occupy rows %s from the pen' % (name, band))
        boxes = {}
        used = {}
        for syl, code in table.items():
            g = by_code[code]
            # Clear the area the original kanji occupied, not just the new
            # box: leftover strokes keep those atlas tiles alive and the tile
            # table then no longer fits.
            _, ooy, ow, oh = meta['sizes'][g['size']]
            oy = UNIFORM[1] if got else ooy
            bw, bh = max(ow, UNIFORM[2]), max(oh, UNIFORM[3])
            b = (max(0, band[0] - oy), UNIFORM[3]) if band else None
            boxes.setdefault(g['tex'], []).append(
                (g['x'], g['y'], bw, bh, syl, b))
            used.setdefault(g['tex'], []).append(
                (g['x'], g['y'], max(bw, UNIFORM[2]), max(bh, UNIFORM[3])))
        # A kanji the translation does not borrow still has its ink in the
        # way when a neighbouring slot's box grew. Those, and only those, are
        # wiped -- the rest of the font is left as it shipped.
        wiped = 0
        for c in meta['large']:
            if c['code'] in codes or not 0x4E00 <= c['code'] <= 0x9FFF:
                continue
            _, _, w_, h_ = meta['sizes'][c['size']]
            if not w_ or not h_:
                continue
            for ux, uy, uw, uh in used.get(c['tex'], ()):
                if (c['x'] < ux + uw and c['x'] + w_ > ux
                        and c['y'] < uy + uh and c['y'] + h_ > uy):
                    boxes.setdefault(c['tex'], []).append(
                        (c['x'], c['y'], w_, h_, None, None))
                    wiped += 1
                    break
        if wiped:
            print('  %-14s %d unused kanji wiped to clear room' % (name, wiped))
        for tex, bs in sorted(boxes.items()):
            fi = F['files']['%03d.xi' % tex]
            blob = redraw(fi['data'], bs)
            assert len(blob) == fi['size']
            off = F['entry']['offset'] + fi['offset']
            if F['where'] == 'outer':
                font_edits.append((CPK_LBA * SEC + off, blob))
            else:
                edits.append((off, blob))          # inside the PGD stream
            print('  %-14s %03d.xi: %d glyphs' % (name, tex, len(bs)))

    # ---- secondary fonts: guide window and staff roll ----
    # They carry only ~450 kanji, so most borrowed code points are missing and
    # the engine paints its missing-glyph box. Their kanji are dead weight now,
    # so re-point each slot at a syllable we actually use.
    if not (nofont or SKIP_FONTS):
        freq = collections.Counter()
        for _, kotext in ui.values():
            freq.update(ch for ch in kotext if 0xAC00 <= ord(ch) <= 0xD7A3)
        for line in ko.values():
            freq.update(ch for ch in line if 0xAC00 <= ord(ch) <= 0xD7A3)
        wanted = [table[s] for s, _ in freq.most_common() if s in table]
        render = {code: syl for syl, code in table.items()}
        # These fonts draw the chapter cards and the menus. Those strings are
        # short and few, so reserve every syllable they use before anything
        # else -- that is the text the player meets first, and it was coming
        # out as ????? because merely-frequent syllables had taken the slots.
        def reserve(files, pick=lambda t: True):
            out = []
            for f in files:
                p = os.path.join(UI_DIR, f)
                if not os.path.exists(p):
                    continue
                for e in json.load(open(p, encoding='utf-8'))['entries']:
                    t = e.get('ko', '')
                    if not pick(t):
                        continue
                    for ch in t:
                        if ch in table and table[ch] not in out:
                            out.append(table[ch])
            return out

        # These fonts hold a few hundred glyphs against a translation that
        # uses 1,179, so what they draw has to be reserved before the merely
        # frequent syllables take the room. For the telop that is the chapter
        # card -- '캐스터 편' over '후시미 히나의 경우' -- which was coming out
        # as ?????; the rest of the executable's wording comes next.
        chap = reserve(['eboot.json'], lambda t: t.endswith(' 편'))
        who = reserve(['eboot.json'], lambda t: t.endswith('의 경우'))
        # flo.json is deliberately not reserved here. Its syllables are
        # scattered across the code range and leading with them wrecks how
        # the char table compresses -- telop_main fell from 393 usable slots
        # to 6. It is fed through `wanted` instead, by frequency.
        def literals(files, pick=lambda t: True):
            """Code points the Korean still spells out as themselves."""
            out = set()
            for f in files:
                p = os.path.join(UI_DIR, f)
                if not os.path.exists(p):
                    continue
                for e in json.load(open(p, encoding='utf-8'))['entries']:
                    t = e.get('ko', '')
                    if not pick(t):
                        continue
                    for ch in widen(full_stops(t)):
                        if ch not in table and ch > ' ':
                            out.add(ord(ch))
            return out

        KEEP = {'telop_main.xf': literals(['eboot.json', 'lua.json',
                                           'flo.json']),
                'staffroll.xf': literals(['staffroll.json']),
                'telop_player.xf': literals(['eboot.json'],
                                            lambda t: t.endswith(' 편')),
                'telop_sp.xf': literals(['eboot.json'],
                                        lambda t: t.endswith('의 경우'))}
        MUST = {'telop_main.xf': chap + who
                + reserve(['eboot.json', 'lua.json', 'flo.json']),
                'staffroll.xf': reserve(['staffroll.json']),
                # these two carry nothing but the chapter card's own wording
                'telop_player.xf': chap,
                'telop_sp.xf': who}
        inner = cpk.CPK(d)
        aux = ['telop_main.xf', 'staffroll.xf',
               'telop_player.xf', 'telop_sp.xf']
        if HARDWARE_SAFE_EBOOT:
            # telop_player and telop_sp draw nothing but the chapter card's
            # own wording, and that wording lives inside EBOOT.BIN. A build
            # that keeps the retail executable keeps the Japanese with it, so
            # re-pointing their glyphs only garbles it -- 刑事編 came out as a
            # single stray syllable because 刑, 事 and 編 had been taken over.
            # Left alone, the card reads correctly in Japanese.
            aux = [x for x in aux if x not in ('telop_player.xf',
                                               'telop_sp.xf')]
            print('  telop_player.xf / telop_sp.xf left as they are '
                  '(their text stays in the retail EBOOT)')
        for name in aux:
            e = [x for x in inner.files if x['name'] == name][0]
            files = {f['name']: f for f in xpck.parse(inner.read(e))}
            F = {'files': files, 'meta': fnt.parse(files['FNT.bin']['data'])}
            atlas = {}
            for i in range(F['meta']['textures']):
                aw, ah, rgba, _ = imgp.decode(files['%03d.xi' % i]['data'])
                atlas[i] = np.frombuffer(rgba, np.uint8).reshape(ah, aw, 4)[:, :, 3]
            band = ink_band(F, atlas)
            if name in ('telop_player.xf', 'telop_sp.xf', 'telop_main.xf'):
                # These two hold one screen's worth of glyphs in a table with
                # no slack; rebuilding it with only what they draw is the
                # only way anything fits.
                got, n = aux_fonts.remap_small(F, MUST[name], render, redraw,
                                               band=band,
                                               protect=KEEP.get(name, ()))
            else:
                got, n = aux_fonts.remap(F, wanted, render, redraw, band=band,
                                         must=MUST.get(name, ()))
            if not got:
                print('  %-14s could not be re-pointed' % name)
                continue
            newfnt, tex = got
            edits.append((e['offset'] + files['FNT.bin']['offset'], newfnt))
            for t, blob in tex.items():
                edits.append((e['offset'] + files['%03d.xi' % t]['offset'], blob))
            print('  %-14s %d slots re-pointed at Korean' % (name, n))

    eboot_edits, eboot_done, eboot_over = patch_eboot(table)
    font_edits += eboot_edits
    print('executable messages: %d strings in EBOOT.BIN' % eboot_done)
    if eboot_over:
        print('  left in Japanese: %s' % eboot_over[:5])

    out = DST_NOFONT if nofont else DST
    if not os.path.exists(out):
        print('copying ISO ...')
        shutil.copyfile(SRC, out)
    f = open(out, 'r+b')
    base_off = DNS_LBA * SEC
    f.seek(base_off)
    p = pgd.PGD(f.read(0x90), 2)
    bs_ = p.block_size
    touched = {}
    if SKIP_DNS:
        print('DNS left untouched (diagnostic build): %d edits dropped'
              % len(edits))
        edits = []
    if PGD_TOOL and edits:
        blob = rewrite_pgd(edits)
        f.seek(base_off)
        f.write(blob)
        touched = range(len(edits))          # only for the closing tally
    else:
        for off, blob in edits:
            for k in range(off // bs_, (off + len(blob) - 1) // bs_ + 1):
                if k not in touched:
                    f.seek(base_off + p.data_offset + k * bs_)
                    touched[k] = bytearray(p.decrypt_block(k, f.read(bs_)))
            if PGD_IDENTITY:
                continue
            for i, byte in enumerate(blob):
                k, o = divmod(off + i, bs_)
                touched[k][o] = byte
        for k, buf in touched.items():
            f.seek(base_off + p.data_offset + k * bs_)
            f.write(p.decrypt_block(k, bytes(buf)))
    for off, blob in font_edits + movie_edits:
        f.seek(off); f.write(blob)
    f.close()
    if PGD_IDENTITY:
        print('PGD identity round trip: %d blocks re-encrypted unchanged'
              % len(touched))
    print('patched %d PGD blocks + %d font ranges + %d movies -> %s'
          % (len(touched), len(font_edits), len(movie_edits), out))
    with open(GLYPH_MAP, 'w', encoding='utf-8') as fh:
        json.dump(table, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main('--dry' in sys.argv, '--nofont' in sys.argv)
