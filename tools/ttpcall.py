# -*- coding: utf-8 -*-
"""psp/ttp/call/*.bin -- the phone conversations. Magic 'TTP_CAL'.

Header is magic(8) + count(4) + table offset(4), then the file's own name and
a run of cue records. The words sit in a pool at the end of the file and are
reached by 32-bit offsets scattered through the cue data; unlike the mail and
TIPS tables there is no one table of them, so the pool start is not stored
anywhere and the offsets are not in one place.

It is still recoverable, because the file proves it itself: take every
4-byte-aligned word that could be an offset, try each as a pool start, and
keep the first where the rest of the file reads as a run of NUL-terminated
CP932 strings *and every one of those strings is pointed at*. A wrong guess
fails one of the two -- either the region does not decode, or it contains a
string nothing references. On the retail disc this identifies the pool in all
304 files, 6131 strings.

Replacements are appended past the end and their slots repointed, the same way
ttptable does it: a reference the scan failed to find then still points at the
Japanese it always did, rather than into the middle of a Korean line.
"""
import struct

MAGIC = b'TTP_CAL\x00'
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


class Call(object):
    def __init__(self, data, pool, starts, refs):
        self.data = data
        self.pool = pool
        self.starts = starts             # string offsets, in file order
        self.refs = refs                 # {string offset: [slot offset]}

    def strings(self):
        """[(offset, raw)] for each string in the pool."""
        return [(s, self.data[s:self.data.find(b'\x00', s)]) for s in self.starts]

    def pack(self, replace):
        """The file with {offset: new_raw} applied.

        A line that fits where it already is stays there and the rest of its
        room is zeroed, so the file does not grow at all; the Japanese it
        replaces carries ruby markup the Korean does not need, so nearly all
        of them do. Only the few that would not fit are appended past the end
        with their slots repointed, which is what makes the whole set fit the
        slots the disc gives these files.
        """
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
    """A Call for `data`, or None if it does not look like one of these."""
    if data[:8] != MAGIC or len(data) < HDR:
        return None
    refs = {}
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack('<I', data[off:off + 4])[0]
        if HDR < v < len(data):
            refs.setdefault(v, []).append(off)
    for start in sorted(refs):
        starts = _pool(data, start)
        if starts and all(s in refs for s in starts):
            return Call(data, start, starts, refs)
    return None
