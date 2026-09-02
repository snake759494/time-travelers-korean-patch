# -*- coding: utf-8 -*-
"""TTP_MAIL / TTP_DIAR / TTP_TIPS tables: an offset table over a string pool.

Header is magic(8) + count(4) + table offset(4). The table is a run of 32-bit
offsets into a pool of NUL-terminated strings that follows it.

Rebuilding the pool from scratch does not work: it carries alignment padding
and bytes nothing points at, so a rebuilt pool never reproduces the original
byte for byte. Instead the file is kept whole and each replacement string is
*appended* past the end, with only its offset slots repointed. The no-op case
is then identical by construction, every unreferenced byte stays where it was,
and a replacement may be any length. The file grows; the caller compresses it
back into its slot as usual.
"""
import struct

MAGIC = b'TTP_'
HDR = 16
MAX_STR = 400


def _starts(data):
    """Offsets at which a NUL-terminated string begins."""
    out, i, n = set(), 0, len(data)
    while i < n:
        j = data.find(b'\x00', i)
        if j < 0:
            break
        if 1 <= j - i <= MAX_STR and i >= HDR:
            out.add(i)
        i = j + 1
    return out


class Table(object):
    def __init__(self, data, slots, pool):
        self.data = data
        self.slots = slots          # [(table_offset, string_offset)]
        self.pool = pool

    def strings(self):
        """[(string_offset, raw)] for each distinct string, in pool order."""
        out, seen = [], set()
        for _, so in self.slots:
            if so in seen:
                continue
            seen.add(so)
            out.append((so, self.data[so:self.data.find(b'\x00', so)]))
        out.sort()
        return out

    def pack(self, replace):
        """The file with {string_offset: new_raw} applied, appended at the end."""
        out = bytearray(self.data)
        moved = {}
        for so in sorted(replace):
            moved[so] = len(out)
            out += replace[so] + b'\x00'
        for to, so in self.slots:
            if so in moved:
                struct.pack_into('<I', out, to, moved[so])
        return bytes(out)


def parse(data):
    """A Table for `data`, or None if it does not look like one of these."""
    if data[:4] != MAGIC or len(data) < HDR:
        return None
    table_off = struct.unpack('<I', data[12:16])[0]
    if not HDR <= table_off < len(data) - 4:
        return None
    starts = _starts(data)
    if not starts:
        return None
    # The pool begins at the lowest offset the table names, and the table
    # cannot reach past it. Converge on that, then keep only the slots that
    # point into the pool.
    pool = len(data)
    for _ in range(8):
        low = pool
        for off in range(table_off, min(pool, len(data) - 4), 4):
            v = struct.unpack('<I', data[off:off + 4])[0]
            if v > off and v in starts:
                low = min(low, v)
        if low == pool:
            break
        pool = low
    if pool <= table_off or pool >= len(data):
        return None
    slots = []
    for off in range(table_off, min(pool, len(data) - 4), 4):
        v = struct.unpack('<I', data[off:off + 4])[0]
        if v >= pool and v in starts:
            slots.append((off, v))
    if not slots:
        return None
    t = Table(data, slots, pool)
    return t if t.pack({}) == data else None
