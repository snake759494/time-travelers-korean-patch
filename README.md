# 타임 트래블러즈 한글 패치 (PSP / NPJH50597)

레벨파이브 『타임 트래블러즈(TIME TRAVELERS)』 PSP판의 비공식 한국어 번역 패치입니다.

배포물은 **xdelta 바이너리 패치 한 개**입니다. 실기와 PPSSPP 모두에서 동작합니다. 게임 데이터는 일절 포함하지 않으며,
적용하려면 본인이 소유한 정품 UMD에서 직접 만든 ISO가 필요합니다.

---

## 1. 준비물

| 항목 | 내용 |
|---|---|
| 원본 ISO | `Time Travelers.iso` — 아래 해시와 **정확히 일치**해야 합니다 |
| 패치 파일 | `Time Travelers (KR).xdelta` (릴리스에서 내려받기) |
| 적용 도구 | [xdelta3](https://github.com/jmacd/xdelta-gpl/releases) 또는 xdeltaUI |

### 원본 ISO 해시 (반드시 확인)

```
파일명 : Time Travelers.iso
크기   : 1,176,698,880 바이트
MD5    : ff66a1628385c829812983d319c5c92b
SHA-1  : e8b6a6fdab73b50948c57818b127cb9b36b87caa
```

해시가 다르면 패치가 적용되지 않거나, 적용되더라도 게임이 정상 동작하지 않습니다.
재압축(CSO/ZSO)하거나 다른 툴로 리마스터한 ISO는 사용할 수 없습니다.

**해시 확인 방법**

Windows PowerShell:
```powershell
Get-FileHash "Time Travelers.iso" -Algorithm MD5
```

macOS / Linux:
```bash
md5sum "Time Travelers.iso"
```

### 패치 적용 후 결과물 해시

```
파일명 : Time Travelers (KR).iso
크기   : 1,176,698,880 바이트
MD5    : b50652bb36e3ec5235bb622dd351e296
SHA-1  : 460c6c52930e847d15d4d84c239853e86aeddfba
```

이 값과 일치하면 정상적으로 적용된 것입니다.

---

## 2. 패치 방법

### 방법 A — 명령줄 (권장)

원본 ISO와 `.xdelta` 파일을 같은 폴더에 두고:

```bash
xdelta3 -d -f -s "Time Travelers.iso" "Time Travelers (KR).xdelta" "Time Travelers (KR).iso"
```

* `-d` 디코드(적용) · `-f` 출력 파일 덮어쓰기 허용 · `-s` 원본(소스) 지정
* 1분 이내에 끝납니다.
* 파일명에 공백이 있으므로 **따옴표를 반드시** 넣으세요.

Windows에서 `xdelta3.exe` 대신 `xdelta.exe`로 배포된 빌드를 쓴다면 명령 이름만 바꾸면 됩니다.

### 방법 B — xdeltaUI (그래픽)

1. `xdeltaUI.exe` 실행 → **Apply Patch** 탭
2. **Patch** — 내려받은 `Time Travelers (KR).xdelta`
3. **Source File** — 원본 `Time Travelers.iso`
4. **Output File** — 만들 파일 이름 (예: `Time Travelers (KR).iso`)
5. **Apply** 클릭

### 적용 후

위의 결과물 해시를 확인한 뒤, 평소 쓰시는 방법대로 실행하세요.

* **PPSSPP** — ISO를 그대로 열면 됩니다.
* **실기 PSP / PS Vita(Adrenaline)** — ISO를 `ms0:/ISO/` (Vita는 `ux0:/pspemu/ISO/`)에 넣습니다.

---

## 3. 번역 범위

| 대상 | 분량 |
|---|---|
| 본편 대사 | 8,776줄 |
| 선택지 | 325개 |
| TIPS · 튜토리얼 · 도움말 · 줄거리 | 1,460개 문자열 / 997개 파일 |
| 전화 통화 | 3,016개 문장 (등장 5,462곳) |
| 메일 · 일기 | 1,329개 문장 (약 38,000자) |
| 타임 트래블 차트 | 489개 |
| 메뉴·시스템 메시지 (Lua) | 170개 |
| 실행 파일 내 메시지 (EBOOT) | 52개 |
| 메뉴 이미지 라벨 (버튼·제목 등) | 276개 |
| 캐릭터 소개 텔롭 | 24장 |
| 동영상 자막 | 5개 영상 |

한글 글꼴은 게임 폰트 아틀라스를 다시 그려 넣었습니다. 대사·TIPS용 폰트는 14×14 픽셀로
원본보다 크게 키웠고, 문장부호는 전각으로 통일했습니다.

---

## 4. 알려진 제한

* 동영상 자막은 **화면 상단**에 표시되며, 영상에 원래 새겨진 일본어 자막은 그대로 남습니다.
  일본어를 지우려면 자막 구간의 화면 아래쪽을 통째로 다시 그려야 하는데, 그러면 해당
  프레임의 부호화 비용이 급증해 재생이 끊깁니다(자세한 이유는 `docs/TECHNICAL.md`).
* `avant_title.pmf`(아방 타이틀, 8분 20초)는 자막 125줄이 들어가 있습니다. 원본과
  프레임 단위로 대조하면 검출된 일본어 자막 구간 119개 중 97개에 대응하는 한글이
  있고, 나머지 22개는 영문 캐스트 크레딧이거나 밝은 장면을 자막으로 잘못 잡은
  구간입니다. 구간표는 `tools/cues/` 에 있습니다.
* 누락 글리프 검사 결과 0건입니다. 실행 파일 안의 메시지와 챕터 카드 라벨도
  한글로 들어갑니다 — EBOOT를 디스크와 같은 태그로 다시 서명하는 방식입니다
  (`docs/TECHNICAL.md` 5장).

---

## 5. 직접 빌드하기

패치를 직접 만들고 싶거나 번역을 수정하고 싶다면.

### 필요한 것

* Python 3.11 이상
* `pip install numpy opencv-python pillow imageio-ffmpeg`
* 원본 `Time Travelers.iso` (위 해시와 일치)
* 한글 글꼴 — [나눔스퀘어 네오](https://hangeul.naver.com/font) `NanumSquareNeo-cBd.ttf`
  (캐릭터 소개 텔롭의 이름에는 같은 계열의 `NanumSquareNeo-eHv.ttf` 를 씁니다)

### 경로 설정

`tools/pack_korean.py` 상단의 상수를 자기 환경에 맞게 고칩니다.

```python
SRC       = r'...\Time Travelers.iso'          # 원본
DST       = r'...\Time Travelers (KR).iso'     # 출력
JSON_DIR  = r'...\translation\script_fix'      # 대사 번역
UI_DIR    = r'...\translation\ui_json'         # UI 번역
GLYPH_MAP = r'...\translation\_glyph_map.json' # 글자 배정표
TTF       = r'...\NanumSquareNeo-cBd.ttf'      # 한글 글꼴
MOVIE_DIR = r'...\movie'                       # 자막 입힌 .pmf
```

### 빌드

```bash
python tools/pack_korean.py   # 본 빌드 — 텍스트·폰트·메뉴 이미지
python tools/verify_all.py    # 검증 — 누락 글리프 0 이어야 정상
```

텍스트·폰트·메뉴 이미지는 위 두 줄이면 그대로 재현됩니다.

### 동영상은 재현 조건이 다릅니다

배포본의 자막 영상은 `tools/op_build_sony.py` 로 만들었습니다. 이쪽은 **소니의 공식
PSMF 툴**(`psmfenc` → `psmfmux` → `PsmfComposerCMD`)을 호출합니다. 이 도구들은
재배포할 수 없어 저장소에 넣지 않았습니다. 갖고 있지 않다면 동영상 부분은
그대로 재현할 수 없습니다.

`tools/op_build.py` 는 소니 툴 없이 x264로 만드는 초기 경로입니다. PPSSPP에서는
재생되지만 디스크 원본과 AVC 문법이 달라(`log2_max_frame_num` 등) 실기 미디어
엔진이 거부할 수 있습니다. 참고용으로 남겨 둔 것이며, **실기용 빌드에는 쓰지
마세요.** 자세한 경위는 `docs/TECHNICAL.md` 4장에 적어 두었습니다.

`avant_title.pmf` 는 14,916프레임이라 디코딩에 6 GB 정도의 디스크를 씁니다.

### xdelta 만들기

```bash
xdelta3 -e -1 -f -s "Time Travelers.iso" "Time Travelers (KR).iso" "Time Travelers (KR).xdelta"
```

---

## 6. 저장소 구성

```
tools/          빌드·추출·검증 도구 (Python)
  pack_korean.py    본 빌더 — 텍스트·폰트·메뉴 이미지·동영상을 ISO에 반영
  op_build.py       동영상 자막 빌드
  op_mux.py         PSMF 다중화 — 실기 재생의 핵심
  op_render.py      자막 그리기
  op_subs.py        자막 대사표
  op_band.py        영상에서 자막 구간 추출
  cfgbin.py         Level-5 .cfg.bin 읽기/쓰기
  menu_tex.py       메뉴 이미지 라벨 다시 그리기
  verify_all.py     전체 검증
  cues/             영상별 자막 구간표 (JSON)
translation/    번역 데이터 (JSON)
docs/           기술 문서
```

게임에서 추출한 데이터(폰트 아틀라스, 영상, 스크립트 바이너리)는 포함하지 않습니다.
모두 원본 ISO에서 도구가 직접 뽑아냅니다.

---

## 7. 법적 고지

* 이 저장소는 번역 데이터와 도구만 배포합니다. 게임 데이터는 포함하지 않습니다.
* 패치를 적용하려면 **정품을 소유**하고 본인이 직접 덤프한 ISO가 있어야 합니다.
* 『TIME TRAVELERS』의 모든 권리는 LEVEL-5 Inc. 에 있습니다.
* 비영리 팬 번역이며, 판매·재배포로 이익을 취하지 마세요.
