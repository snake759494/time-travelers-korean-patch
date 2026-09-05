# -*- coding: utf-8 -*-
"""TTP_MAIL / TTP_DIAR / TTP_TIPS tables: offset arrays over a string pool.

Header is magic(8) + count(4) + table offset(4), then a run of fixed-size
records. A record does not hold its text; it holds offsets, and some of those
offsets point at *further arrays* of offsets rather than at words. Only past
all of that does the pool of NUL-terminated strings begin.

That indirection is what the first parser here missed. It took the pool to
start at the lowest offset the record table names, which in mail.bin is 5680 --
the array, not the pool -- and then read that array's 32-bit entries as though
they were text. Each one decoded as a stray kanji, so the extraction produced
440 entries reading 襷, 祗, 侵, 単 and nothing worth translating, and the mail
and diary went untranslated on the grounds that there was nothing there. There
are 1,329 strings.

The pool is found the way ttpcall finds its own: take every 4-byte-aligned word
as a candidate start and keep the first where the rest of the file reads as a
run of NUL-terminated CP932 strings *and every one of those strings is pointed
at*. A wrong guess breaks one of the two -- an array's entries do not decode as
a clean run of strings, and a start inside the pool leaves the strings above it
referenced by nothing. On the retail disc this lands the pool in all three
tables, 820 + 504 + 6 strings, and each rebuilds byte for byte untouched.

Replacements go in place when they fit and are appended past the end when they
do not, with only those slots repointed. The Japanese carries ruby the Korean
does not need, so nearly all of them fit and the file barely grows -- which
matters, because these tables are compressed into slots with about 3% of room
to spare.
"""
import struct

MAGIC = b'TTP_'
HDR = 16
MAX_STR = 400


def _pool(data, start):
    """String starts in [start, end), or None if that is not what it holds."""
    out, i, n = [], start, len(data)
    while i < n:
        j = data.find(b'\x00', i)
        if j < 0:
            return None
        if j == i:                       # padding, and only at the very end
            return out if not data[i:].strip(b'\x00') else None
        if j - i > MAX_STR:
            return None
        try:
            data[i:j].decode('cp932')
        except UnicodeDecodeError:
            return None
        out.append(i)
        i = j + 1
    return out or None


class Table(object):
    def __init__(self, data, pool, starts, refs):
        self.data = data
        self.pool = pool
        self.starts = starts             # string offsets, in file order
        self.refs = refs                 # {string offset: [slot offset]}

    def strings(self):
        """[(string_offset, raw)] for each string in the pool."""
        return [(s, self.data[s:self.data.find(b'\x00', s)])
                for s in self.starts]

    def pack(self, replace):
        """The file with {string_offset: new_raw} applied."""
        out = bytearray(self.data)
        tail = {}
        for so in sorted(replace):
            new = replace[so]
            room = self.data.find(b'\x00', so) - so
            if len(new) <= room:
                out[so:so + room + 1] = new + b'\x00' * (room - len(new) + 1)
            else:
                tail[so] = new
        for so in sorted(tail):
            at = len(out)
            out += tail[so] + b'\x00'
            for slot in self.refs[so]:
                struct.pack_into('<I', out, slot, at)
        return bytes(out)


def parse(data):
    """A Table for `data`, or None if it does not look like one of these."""
    if data[:4] != MAGIC or len(data) < HDR:
        return None
    refs = {}
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack('<I', data[off:off + 4])[0]
        if HDR < v < len(data):
            refs.setdefault(v, []).append(off)
    for start in sorted(refs):
        starts = _pool(data, start)
        if starts and all(s in refs for s in starts):
            return Table(data, start, starts, refs)
    return None
