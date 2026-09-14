# -*- coding: utf-8 -*-
"""Legacy x264 movie builder.

The x264 implementation below is retained for diagnosis, but its AVC syntax
does not play reliably on a real PSP.  The command-line entry point delegates
to op_build_sony.py, which uses Sony's official PSMF encoder and composer.

    python op_build.py [name.pmf ...]

Pulls each film out of the original ISO, takes the burnt-in Japanese off the
picture, draws the Korean in its place, and re-encodes to a stream the PSP's
Media Engine will take: Main profile at level 2.1, CABAC, one reference frame,
no B-frames, no weighted prediction, an access unit delimiter and SPS/PPS
ahead of every frame, and -- the part that only matters on real hardware --
an HRD in the VUI with a pic_timing SEI on each frame, from nal-hrd=vbr.

The result is muxed back through op_mux, which keeps the original container
byte for byte and byte-aligns each frame to its original offset, so the
arrival clock and the presentation clock stay the distance apart the disc
shipped with. Written to MOVIE_DIR for pack_korean to drop into the ISO.

The hardware requirements above are from snake759494/vc2-korean-patch, which
established them against a real PSP for Valkyria Chronicles 2. An x264 stream
without them plays in PPSSPP and is refused by the console.
"""
import gc
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import cv2
import numpy as np
import imageio_ffmpeg

import cpk
import op_mux
import op_render
import op_subs
import pack_korean as P

RATE = '30000/1001'
X264 = ('no-scenecut:bframes=0:cabac=1:ref=1:no-open-gop:repeat-headers=1:'
        'aud=1:weightp=0:pic-struct:nal-hrd=vbr')
TRIES = 14
EARLY = 0.0        # frames sit where the original's did; the gaps left
ZEROS = 8         # over are padding, and a long run of it stalls the engine

PEAK = 1.0         # ceiling as a multiple of the average
VBV = 0.35          # encoder buffer, in seconds, to bound the drift


def load(name):
    c = cpk.CPK(P.SRC, base=P.CPK_LBA * P.SEC)
    e = [x for x in c.files if x['name'] == name][0]
    return c.read(e)


def seconds(pmf):
    first = int.from_bytes(pmf[0x54:0x5A], 'big') / 90000.0
    last = int.from_bytes(pmf[0x5A:0x60], 'big') / 90000.0
    return max(0.1, last - first)


def decode(es, tmp):
    """Frames as a memory-mapped array on disk.

    avant_title is fifteen thousand frames, which is six gigabytes held as
    pixels; the render writes through to the file instead of to RAM.
    """
    p = os.path.join(tmp, 'in.264')
    open(p, 'wb').write(es)
    cap = cv2.VideoCapture(p)
    n = 0
    while cap.grab():
        n += 1
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.release()
    out = np.lib.format.open_memmap(os.path.join(tmp, 'frames.npy'), 'w+',
                                    np.uint8, (n, h, w, 3))
    cap = cv2.VideoCapture(p)
    i = 0
    while i < n:
        ok, f = cap.read()
        if not ok:
            break
        out[i] = f
        i += 1
    cap.release()
    return out[:i]


def encode(frames, out, tmp, keyint, kbps):
    size = '%dx%d' % (frames.shape[2], frames.shape[1])
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    log = os.path.join(tmp, 'x264')
    # The film is delivered by a fixed grid of 2048-byte packs, so the stream
    # has to hold its rate the way the original did. Letting the peak run above
    # the average -- the usual VBV setting -- let x264 spend ten per cent over
    # for minutes at a time, and every frame after that arrived late.
    # A ceiling well above the average, but a short buffer. The original
    # spends heavily on a scene cut and little in between; pinning the peak to
    # the average forbade that shape entirely and the schedule check then had
    # to drive the whole bitrate down to compensate. A short buffer still stops
    # an overspend being sustained, which is what caused the drift.
    mr, buf = int(kbps * PEAK), max(64, int(kbps * VBV))
    opts = ('keyint=%d:%s:vbv-maxrate=%d:vbv-bufsize=%d'
            % (keyint, X264, mr, buf))
    for p in (1, 2):
        cmd = [ff, '-y', '-hide_banner', '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', size,
               '-r', RATE, '-i', '-', '-an', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', '-profile:v', 'main', '-level', '2.1',
               '-b:v', '%dk' % kbps, '-maxrate', '%dk' % mr,
               '-bufsize', '%dk' % buf, '-x264opts', opts,
               '-pass', str(p), '-passlogfile', log, '-f', 'h264',
               os.devnull if p == 1 else out]
        q = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for f in frames:
            q.stdin.write(np.ascontiguousarray(f).tobytes())
        q.stdin.close()
        if q.wait():
            raise SystemExit('x264 failed on pass %d' % p)


def check(es):
    """What the Media Engine wants to see, and what it must not."""
    filler = timing = 0
    i = 0
    while True:
        i = es.find(b'\x00\x00\x01', i)
        if i < 0:
            break
        t = es[i + 3] & 0x1F
        if t == 12:
            filler += 1
        elif t == 6:
            p, kind = i + 4, 0
            while p < len(es) and es[p] == 0xFF:
                kind += 255
                p += 1
            if p < len(es) and kind + es[p] == 1:
                timing += 1
        i += 3
    return filler, timing


def one(name):
    pmf = load(name)
    tmp = tempfile.mkdtemp(prefix='mov_')
    es = op_mux.video_es(pmf)
    keyint, idr = op_mux.gop(es)
    print('%s  %d 바이트, %.1f초, GOP %d' % (name, len(pmf), seconds(pmf), keyint))
    frames = decode(es, tmp)
    print('  디코딩 %d 프레임' % len(frames))
    ko = op_render.render(name, frames, lambda p, i, n: sys.stdout.write(
        '\r  %s %d/%d ' % (p, i + 1, n)) or sys.stdout.flush())
    print('\r  자막 %d개 교체 완료      ' % len(op_subs.MOVIES[name]))
    out264 = os.path.join(tmp, 'out.264')
    # Aim just under what the original spent. A frame that comes out bigger than
    # the one it replaces only ever lands later than the original did, which is
    # the safe side of the buffer model; the retry below backs off if the whole
    # stream will not fit.
    rate = len(es) / seconds(pmf)                 # bytes a second of video
    early, slack = int(rate * EARLY), 1 << 30
    kbps = max(200, int(len(es) * 0.98 * 8 / seconds(pmf) / 1000))
    # Look for the most video the slots will hold. Padding is what is left over
    # once the coded frames are in, so the fuller the grid the less of it there
    # is -- and a thin, evenly spread padding is what the disc's own streams
    # look like. A bitrate that overruns brackets the search from above.
    hi, best = 0, None
    for attempt in range(TRIES):
        encode(ko, out264, tmp, keyint, kbps)
        new = open(out264, 'rb').read()
        try:
            blob, late, worst, over = op_mux.build(pmf, new, early, slack)
        except ValueError as e:
            if 'lower the bitrate' not in str(e):
                raise
            hi = kbps
            kbps = int(kbps * 0.93)
            print('  슬롯 넘침 -> %d kbps 로 다시' % kbps)
            continue
        zeros, run, total = op_mux.padding(blob)
        if best is None or run < best[3]:
            best = (blob, new, zeros, run, total, kbps)
        if run <= ZEROS:
            break
        nxt = min(hi - 1, int(kbps * 1.06)) if hi else int(kbps * 1.06)
        if nxt <= kbps:                       # the bracket has closed
            print('  0 연속 %d바이트 -- %d kbps 가 한계' % (run, kbps))
            break
        kbps = nxt
        print('  0 연속 %d바이트 (목표 %d) -> %d kbps 로 다시' % (run, ZEROS, kbps))
    if best is None:
        raise SystemExit('스트림을 슬롯에 맞추지 못했습니다')
    blob, new, zeros, run, total, kbps = best
    filler, timing = check(op_mux.video_es(blob))
    fill = 100.0 * len(new) / op_mux.capacity(pmf)
    zeros, run, total = op_mux.padding(blob)
    print('  %d kbps, ES %d 바이트, 슬롯 채움 %.1f%%, filler NAL %d, '
          'pic_timing SEI %d, 0바이트 %.1f%%, 최장연속 %d'
          % (kbps, len(new), fill, filler, timing, 100.0 * zeros / total, run))
    off = op_mux.mislabelled(blob)
    base = op_mux.mislabelled(pmf)
    print('  PTS 표시가 가리키는 프레임 불일치 %d개 (원본 %d개)' % (off, base))
    if filler or timing < len(frames) * 0.9 or len(blob) != len(pmf) or off > base:
        raise SystemExit('실기 조건 불충족')
    os.makedirs(P.MOVIE_DIR, exist_ok=True)
    open(os.path.join(P.MOVIE_DIR, name), 'wb').write(blob)
    del frames, ko                       # the frame store is memory mapped;
    gc.collect()                         # Windows will not unlink it while open
    shutil.rmtree(tmp, ignore_errors=True)
    print('  -> %s' % os.path.join(P.MOVIE_DIR, name))


def main(names):
    for n in names or sorted(op_subs.MOVIES):
        one(n)


if __name__ == '__main__':
    import op_build_sony
    op_build_sony.main(sys.argv[1:])
