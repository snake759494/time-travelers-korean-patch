# -*- coding: utf-8 -*-
"""Korean for the button-hint bar, keyed by the sprite rectangle it sits in.

Coordinates are the texture rectangle from the .pvb vertex buffer -- each
already includes the label's furigana, so the whole box is cleared.
"""
NAVI = {
    (60, 21, 87, 43): '이동',
    (90, 21, 123, 43): '결정',
    (124, 21, 154, 43): '뒤로',
    (156, 21, 212, 43): '조작 설명',
    (5, 28, 58, 43): '커서',
    (0, 45, 144, 66): '스크린샷 촬영',
    (149, 45, 180, 67): '확대',
    (185, 45, 218, 66): '재생',
    (273, 45, 304, 66): '재독',      # 31px of quad: '다시 읽기' only fits at 7px
    (6, 69, 75, 91): '모델 회전',
    (82, 69, 151, 90): '도움말 전환',
    (158, 69, 227, 90): '페이지 전환',
    (229, 69, 301, 90): 'TIPS 전환',
    (49, 93, 115, 114): '정렬 변경',
    (125, 93, 180, 115): '일시정지',
    (181, 93, 244, 114): '설정 변경',
    (273, 93, 304, 114): '재독',
    (132, 116, 179, 139): '이전 화',
    (180, 117, 228, 138): '다음 화',
    (233, 117, 264, 138): '선택',
    (269, 117, 300, 138): '선택',
    (48, 140, 126, 163): '확대／축소',
    (132, 140, 179, 163): '이전 화',
    (180, 141, 228, 162): '다음 화',
    (229, 141, 301, 162): 'TIPS 전환',
    (164, 168, 308, 183): '타임 트래블 차트',
    (40, 184, 108, 208): '카메라 이동',
    (108, 184, 176, 208): '카메라 이동',
    (60, 213, 87, 235): '이동',
    (90, 213, 123, 235): '결정',
    (137, 213, 197, 234): '항목 전환',
    (5, 220, 58, 235): '커서',
    (200, 221, 240, 234): '씬',
    # No quad names these four, but they are drawn through the whole-row
    # sprites, so they have to be redrawn as well. Found by looking for what
    # ink was left once the named rectangles were done.
    (212, 21, 277, 43): '카메라 조작',   # below the L/R icons
    (228, 46, 264, 65): '닫기',
    (49, 115, 123, 140): '힌트 보기',   # stops above 확대／축소
    (184, 184, 243, 210): '설정 변경',   # stops below the chart label
}

# The title menu. Eleven pills, three labels between them in normal, dim and
# highlighted flavours. The lettering sits on a coloured pill, so these are
# drawn over the artwork instead of on a cleared box: `bg` is a column of the
# pill the lettering never reaches, and every row is rebuilt from it.
TITLE = [
    (60, 31, 206, 53, '처음부터'),
    (60, 58, 206, 81, '이어서'),
    (60, 88, 206, 110, '처음부터'),
    (60, 115, 206, 137, '이어서'),
    (60, 143, 206, 165, '처음부터'),
    (60, 171, 206, 193, '이어서'),
    (60, 203, 206, 225, '이어서'),
    (60, 230, 206, 253, '데이터 설치'),
    (60, 263, 206, 285, '이어서'),
    (60, 290, 206, 313, '데이터 설치'),
    (60, 322, 206, 345, '데이터 설치'),
]

# The save/load screen. The two headings sit on nothing, so they are cleared
# and redrawn; the guidance line and the chapter badges sit on the panel's
# pattern and have to be composited over it. Every badge box reaches up over
# its furigana, which then goes away with the rest.
SAVELOAD = {
    (1, 273, 102, 290): '세이브 데이터',
    (101, 273, 202, 290): '로드 데이터',
}
# White lettering on nothing, exactly like the button bar -- the panel's
# pattern lives on another texture, not behind these. Boxes are the .pvb
# quads: the chapter labels are set flush to x=255 with their furigana in
# the last few columns, and boxes stopping at the word left the reading
# behind as a mark after every '편'.
SAVELOAD_2 = {
    (4, 3, 197, 26): '저장할 위치를 선택하세요',
    (180, 27, 255, 49): '고교생 편',
    (180, 51, 255, 73): '사기꾼 편',
    (169, 75, 255, 97): '루상치 편',
    (200, 99, 255, 121): '형사 편',
    (166, 123, 255, 145): '캐스터 편',
    (185, 147, 255, 169): '미코토 편',
    (148, 171, 255, 187): '불러올 데이터',
    (124, 187, 255, 209): '타임 트래블러 편',
}

# The in-game main menu. Six chapter archives carry it and five of them share
# the very same texture, so one table covers the lot. The clock values and the
# option arrows are left where they are; only the wording changes.
# These are the sprite rectangles themselves, read out of 000.pvb (xpvb) --
# not boxes measured off the sheet. Measured boxes were wrong in both
# directions and both mistakes showed on hardware. Two of the explanation
# lines had been widened to the left so the Korean could be set larger, but
# a quad is all the game samples: everything outside it simply is not drawn,
# so 'タイトル画面に戻ります。' lost its first characters. The other way round,
# the help entry's box was twice its quad -- 88px against 41 -- and centring
# the Korean in it pushed most of the word past the right edge of what the
# game shows, leaving one visible syllable.
MAINMENU = {
    (37, 332, 182, 348): '타임 트래블 차트',
    (40, 348, 167, 364): '타임 스톱 리스트',
    # 181, not the 184 one archive rounds to: the retail katakana starts at
    # 181 and a tighter box leaves its first three columns behind.
    (181, 343, 333, 364): '아방 타이틀＆예고편 목록',
    (40, 364, 121, 379): 'TIPS 목록',
    (40, 380, 104, 396): '옵션',   # the ◀▶ arrows are quads of their own
    (40, 396, 81, 412): '도움말',
    # 41px of quad, so the wording has to be the short one: '타이틀로
    # 돌아가기' only fits at 10px and dragged the whole column down with it.
    (40, 412, 131, 432): '타이틀로',
    # The heading, and the line of explanation that follows the cursor.
    (348, 308, 464, 329): '메인 메뉴',
    (333, 344, 512, 368): '게임 도움말을 표시합니다．',
    (340, 368, 512, 393): '게임 설정을 변경합니다．',
    (340, 400, 512, 425): '타이틀 화면으로 돌아갑니다．',
    (297, 432, 512, 457): '타임 스톱 리스트를 표시합니다．',
    (282, 456, 512, 481): '타임 트래블 차트를 표시합니다．',
    (350, 480, 512, 505): 'TIPS 목록을 표시합니다．',
}
# The chapter name that heads the same menu, on the archive's second sheet.
# It was never in this file, so 'キャスター編' sat in Japanese over a menu that
# was otherwise all Korean.
#
# The sheet carries all six names on a 24px pitch, but each archive's .pvb
# names only its own, and every one of those quads is tight around its own
# word -- 43px for the three of 刑事編, 84 for the six of キャスター編. Giving
# them all the widest box let '형사 편' be set flush to x=78 and start at 18,
# well left of the 37 the game samples from, so the first syllable was simply
# not drawn. These are the quads themselves, with the two the disc does not
# name taken from where the retail lettering sits (x0 = ink - 2).
MAINMENU_CHAPTER = {
    (22, 224, 84, 244): '고교생 편',
    (24, 248, 84, 268): '사기꾼 편',
    (12, 272, 84, 292): '루상치 편',
    (37, 296, 80, 316): '형사 편',
    (0, 320, 84, 340): '캐스터 편',
    (25, 344, 84, 364): '미코토 편',
}
MAINMENU_ARCHIVES = ['mainmenu_keijihen_big.xa', 'mainmenu_koukouseihen_big.xa',
                     'mainmenu_kyasutahen_big.xa', 'mainmenu_mikotohen_big.xa',
                     'mainmenu_rusanchihen_big.xa', 'mainmenu_sagishihen_big.xa']

# The notices that slide across the screen in play, plus the three headings
# on the menu strip. The English badges next to them -- AUTO PLAY, PAUSE,
# SAVE, SKIP -- are already English and are left alone, which is why the
# second line stops short of the PAUSE beside it.
NOTICE = {
    (4, 153, 430, 176): '스킵 플레이가 꺼졌습니다．',
    (5, 185, 420, 208): '오토 플레이가 꺼졌습니다．',   # clear of the PAUSE badge
    (5, 304, 326, 334): '헤드폰 모드로 설정했습니다．',
    (414, 314, 479, 336): '힌트',   # the quad, not the word: it carries furigana
    (5, 359, 381, 392): '스피커 모드로 설정했습니다．',
    (13, 432, 121, 448): '텍스트 로그',
    (12, 456, 81, 472): '줄거리',
    (12, 480, 158, 512): '캐릭터 선택',
}

# The character-select screen. Each name plate carries the Japanese name over
# its romanisation, so only the top half of the plate is touched -- the
# English line underneath stays. The plates are coloured, so they are drawn
# over rather than cleared.
CHARSEL = {
    (8, 281, 236, 304): '캐릭터를 선택하세요',
}
CHARSEL_OVER = [
    (366, 288, 491, 308, '루상치☆맨'),
    (254, 327, 350, 347, '후시미 히나'),
    (368, 331, 490, 351, '신도 큐고'),
    (382, 376, 490, 396, '신도 미코토'),
    (271, 420, 378, 440, '카미야 소마'),
    (388, 420, 490, 440, '후카세 유리'),
]

# The TIPS list's category strip, down the right of the screen. The brackets
# are part of the artwork rather than the font, so they are drawn back in with
# the word; the reading printed above each one goes when the box is cleared.
TIPCAT = {
    (91, 0, 157, 25): '《전체》',
    (91, 32, 157, 57): '《신규》',
    (91, 64, 157, 89): '《캐릭터》',
    (91, 96, 157, 121): '《사회》',
    (91, 128, 157, 153): '《과학》',
    (91, 160, 157, 185): '《유행》',
    (91, 192, 157, 217): '《잡학》',
    (91, 224, 157, 249): '《비화》',
}

# The beginner's-guide popup that opens over the dialogue window. Neither of
# these is a string: the lua files mention both words, but only inside
# comments -- every literal the game draws is a string.char run, and decoding
# all of them turns up neither. They are painted into this sheet.
# The heading is yellow on the blue tab and the button is white on its plate,
# so both boxes stop short of the plate edges that frame them.
TUTORIAL = {
    (30, 52, 80, 70): '가이드',
}
# The Cancel button's plate is a vertical gradient, so clearing it to one
# colour left a visible seam where the word had been; it is drawn over the
# artwork instead. The right edge stops at 452, short of the plate's own
# inner highlight.
TUTORIAL_OVER = [
    (399, 21, 452, 36, '취소'),
]

# The three full-screen operation guides. Unlike the other sheets these could
# not be keyed off the .pvb quads: a quad here bundles a button badge and up to
# four lines of text, so clearing one would take the ○△□ badges with it. The
# rectangles below are the lettering alone, measured off the sheet, and each
# already covers the reading printed above the word.
CONTROL_A = {
    (271, 275, 411, 294): '스크린샷 촬영',
    (148, 277, 199, 288): '△ 버튼',
    (30, 278, 126, 290): '오토 플레이 OFF',
    (30, 292, 135, 311): 'TIPS 선택 해제',
    (148, 293, 199, 304): '□ 버튼',
    (386, 308, 444, 328): '터치 조작',
    (455, 308, 503, 328): '읽어 넘기기',
    (449, 330, 508, 349): '각종 결정',
    (360, 351, 506, 370): '오토 플레이 일시정지 / 재개',
    (255, 309, 303, 328): '읽어 넘기기',
    (251, 330, 309, 349): '각종 결정',
    (208, 351, 354, 370): '오토 플레이 일시정지 / 재개',
    (1, 326, 77, 346): '방향키(왼쪽)',
    (100, 329, 199, 340): 'START 버튼',
    (82, 346, 195, 357): '터치스크린을',
    (1, 350, 77, 370): '방향키(오른쪽)',
    (133, 362, 169, 373): '터치',
    (2, 374, 77, 394): '방향키(아래)',
    (195, 378, 284, 390): '오토 플레이 ON',
    (299, 378, 350, 390): '○ 버튼',
    (358, 378, 406, 390): '× 버튼',
    (323, 393, 404, 413): '줄거리 열기',
    (434, 393, 509, 413): '선택지 선택',
    (1, 398, 77, 418): '방향키(위)',
    (127, 398, 243, 417): 'TIPS 선택 / 해제',
    (378, 419, 503, 442): '메인 메뉴 열기',
    (1, 422, 90, 442): '방향키(좌우)',
    (192, 422, 328, 442): '오토 플레이 속도 조절',
    (1, 446, 90, 466): '방향키(상하)',
    (133, 449, 181, 470): '읽어 넘기기',
    (212, 449, 315, 470): '텍스트 로그 열기',
    (367, 450, 505, 472): 'HOME 메뉴로 돌아가기',
    (5, 469, 65, 480): 'PS 버튼',
    (199, 478, 248, 489): 'R 버튼',
    (28, 487, 190, 508): '타임 트래블 차트 열기',
    (199, 494, 247, 505): 'L 버튼',
}

CONTROL_B = {
    (266, 278, 420, 297): '재독 지점으로 커서 이동',
    (3, 279, 61, 298): '터치 조작',
    (7, 303, 191, 324): '재독 (재독 지점 선택 중에만)',
    (234, 306, 300, 325): '재독',
    (234, 327, 366, 347): '(재독 지점 선택 중에만)',
    (403, 306, 507, 325): 'TIPS 선택 해제',
    (401, 327, 485, 346): '이전 화면으로',
    (10, 327, 80, 346): '커서 이동',
    (10, 352, 73, 371): '페이지 전환',
    (222, 353, 292, 373): '커서 이동',
    (307, 361, 405, 372): 'START 버튼',
    (32, 378, 148, 397): 'TIPS 선택 / 해제',
    (222, 382, 284, 402): '페이지 전환',
    (321, 389, 372, 401): '○ 버튼',
    (322, 409, 372, 420): '□ 버튼',
    (49, 411, 100, 434): '조작 설명',
    (114, 413, 266, 433): 'R 버튼＋방향키(상하)',
    (324, 429, 372, 441): '× 버튼',
    (112, 440, 296, 456): '슬라이더를 드래그',
    (2, 446, 92, 466): '방향키(상하)',
    (112, 460, 219, 476): '커서를 터치',
    (2, 474, 92, 494): '방향키(좌우)',
    (126, 479, 190, 496): '터치',
}

CONTROL_C = {
    (53, 278, 137, 297): '이전 화면으로',
    (171, 278, 200, 299): '결정',
    (29, 307, 88, 326): '시간 이동',
    (27, 335, 78, 354): '편 전환',
    (307, 361, 405, 372): 'START 버튼',
    (4, 387, 131, 407): '시간 이동(1시간 단위)',
    (321, 389, 372, 401): '○ 버튼',
    (322, 409, 372, 420): '△ 버튼',
    (48, 413, 100, 433): '조작 설명',
    (114, 413, 266, 433): 'R 버튼＋방향키(상하)',
    (324, 429, 372, 441): '× 버튼',
    (2, 446, 92, 466): '방향키(상하)',
    (2, 474, 92, 494): '방향키(좌우)',
}

SPRITES = {'navi.xa': {'000.xi': NAVI},
           'chara_sellect.xa': {'000.xi': CHARSEL},
           'saveloadmenu.xa': {'000.xi': SAVELOAD, '001.xi': SAVELOAD_2},
           'text_outline_chara.xa': {'000.xi': NOTICE},
           'tiplistmenu.xa': {'001.xi': TIPCAT},
           'control_a.xa': {'000.xi': CONTROL_A},
           'control_b.xa': {'000.xi': CONTROL_B},
           'control_c.xa': {'000.xi': CONTROL_C},
           'tutorial.xa': {'000.xi': TUTORIAL}}
for _a in MAINMENU_ARCHIVES:
    SPRITES[_a] = {'000.xi': MAINMENU, '001.xi': MAINMENU_CHAPTER}
OVER = {'title_new.xa': {'001.xi': (TITLE, 40)},
        'chara_sellect.xa': {'000.xi': (CHARSEL_OVER, 0)},
        'tutorial.xa': {'000.xi': (TUTORIAL_OVER, 0)}}
