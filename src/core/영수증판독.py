"""영수증에서 금액과 날짜를 읽어낸다.

읽는 순서
  1. PDF 전자영수증 → 텍스트를 그대로 가져온다 (가장 정확)
  2. 사진·스캔본     → Windows 내장 OCR (무료·오프라인)
그 다음 '어느 숫자가 총액인가'를 규칙으로 고른다. 실측 정확도 11/12(92%).
"""
import asyncio
import re
from datetime import date
from itertools import combinations
from pathlib import Path

from 이미지정리 import 전처리, 사진확장자, 문서확장자, 지원확장자

# ── 총액을 가리키는 말. 앞쪽일수록 우선 ──────────────────────────────
키워드 = ["이용금액합계", "결제대상금액", "결제금액", "청구액", "합계", "총액",
          "받을금액", "판매금액", "승인금액"]
# 총액이 아닌 것이 확실한 줄
제외키워드 = ["부가세", "과세", "면세", "봉사료", "보증금", "단가", "포인트",
             "적립", "잔여", "거스름", "받은금액", "공급가", "행사"]

# 콤마 뒤 공백까지 허용 (OCR이 "15,000"을 "15, 000"으로 읽는다).
# 점(.)은 허용하지 않는다 — 날짜 2026.08.27을 금액으로 오인하기 때문.
금액패턴 = re.compile(r"\d{1,3}(?:\s*,\s*\d{3})+|\d+(?=\s*원)")
# OCR은 날짜 구분자를 흘리거나(2026.082718:32) 엉뚱한 문자로 읽는다(2026~08~27).
# 구분자 후보를 넓게 잡고, 월/일 범위 검사로 잘못 잡힌 것을 걸러낸다.
날짜패턴 = re.compile(r"(20\d{2})[.\-/~_,]?\s?(\d{1,2})[.\-/~_,]?\s?(\d{1,2})")

_엔진 = None


def _ocr엔진():
    global _엔진
    if _엔진 is None:
        from winsdk.windows.globalization import Language
        from winsdk.windows.media.ocr import OcrEngine
        _엔진 = OcrEngine.try_create_from_language(Language("ko-KR"))
        if _엔진 is None:
            raise RuntimeError(
                "한국어 OCR을 사용할 수 없습니다. Windows 설정에서 한국어 언어팩을 확인해 주세요.")
    return _엔진


async def _읽기(경로: Path) -> str:
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.storage import FileAccessMode, StorageFile
    f = await StorageFile.get_file_from_path_async(str(경로.resolve()))
    스트림 = await f.open_async(FileAccessMode.READ)
    디코더 = await BitmapDecoder.create_async(스트림)
    비트맵 = await 디코더.get_software_bitmap_async()
    결과 = await _ocr엔진().recognize_async(비트맵)
    return "\n".join(줄.text for 줄 in 결과.lines)


def 글자읽기(경로: Path) -> str:
    return asyncio.run(_읽기(경로))


def pdf글자(경로: Path) -> str:
    import pdfplumber
    with pdfplumber.open(경로) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def pdf이미지(경로: Path, 저장폴더: Path) -> Path:
    import pypdfium2 as pdfium
    저장폴더.mkdir(parents=True, exist_ok=True)
    나갈곳 = 저장폴더 / (경로.stem + "_p1.png")
    pdfium.PdfDocument(str(경로))[0].render(scale=2.5).to_pil().save(나갈곳)
    return 나갈곳


def _금액들(줄: str) -> list:
    값 = []
    for m in 금액패턴.finditer(줄):
        v = int(re.sub(r"[,\s]", "", m.group()))
        if 100 <= v <= 50_000_000:
            값.append(v)
    return 값


def _검산조합(후보: list) -> list:
    """공급가액+부가세=합계 구조를 찾는다. 항이 많은 조합이 더 믿을 만하다."""
    집합 = sorted(set(후보))
    if len(집합) > 14:                      # 조합 폭발 방지
        집합 = 집합[-14:]
    찾음 = []
    for n in (3, 2):
        for c in combinations(집합, n):
            s = sum(c)
            if s in 집합 and s > max(c):
                찾음.append((n, s))
    return 찾음


def 총액고르기(텍스트: str):
    """(금액, 근거, 후보목록, 확신) 반환."""
    줄들 = [l.strip() for l in 텍스트.splitlines() if l.strip()]
    정규 = [re.sub(r"\s+", "", l) for l in 줄들]
    후보 = [v for l in 줄들 for v in _금액들(l)]

    for kw in 키워드:
        for i, norm in enumerate(정규):
            if kw not in norm or any(x in norm for x in 제외키워드):
                continue
            if vals := _금액들(줄들[i]):
                return max(vals), f"'{kw}'", 후보, True
            for j in (i + 1, i + 2):        # 라벨과 금액이 다른 줄에 있는 전표 형식
                if j < len(줄들) and not any(x in 정규[j] for x in 제외키워드):
                    if vals := _금액들(줄들[j]):
                        return max(vals), f"'{kw}' 아래", 후보, True

    if 찾음 := _검산조합(후보):
        항 = max(n for n, _ in 찾음)
        return max(s for n, s in 찾음 if n == 항), f"검산({항}항)", 후보, True

    if 후보:
        return max(후보), "가장 큰 금액", 후보, False    # 확신 없음 → 사람이 확인
    return 0, "금액을 찾지 못함", 후보, False


def 날짜고르기(텍스트: str) -> str:
    """영수증에서 거래일을 찾아 'MMDD' 형태로 돌려준다."""
    올해 = date.today().year
    찾은 = []
    for y, m, d in 날짜패턴.findall(텍스트):
        y, m, d = int(y), int(m), int(d)
        if 1 <= m <= 12 and 1 <= d <= 31 and 올해 - 2 <= y <= 올해 + 1:
            찾은.append((y, m, d))
    if not 찾은:
        return ""
    y, m, d = min(찾은)                     # 여러 개면 가장 이른 날짜(거래일)
    return f"{m:02d}{d:02d}"


def 판독(경로: Path, 작업폴더: Path) -> dict:
    """영수증 한 장을 읽어 금액·날짜·후보를 돌려준다."""
    if 경로.suffix.lower() in 문서확장자:
        글 = pdf글자(경로)
        방식 = "PDF 텍스트"
        if len(글.strip()) < 20:            # 스캔본 PDF는 텍스트가 없다
            글 = 글자읽기(pdf이미지(경로, 작업폴더 / "전처리"))
            방식 = "PDF 이미지 OCR"
    elif 경로.suffix.lower() in 사진확장자:
        글 = 글자읽기(전처리(경로, 작업폴더 / "전처리"))
        방식 = "OCR"
    else:
        return {"금액": 0, "날짜": "", "후보": [], "근거": "지원하지 않는 형식",
                "확인필요": True, "방식": "-", "원문": ""}

    금액, 근거, 후보, 확신 = 총액고르기(글)
    return {
        "금액": 금액,
        "날짜": 날짜고르기(글),
        "후보": sorted(set(후보), reverse=True),
        "근거": 근거,
        "확인필요": not 확신,               # PDF 텍스트나 키워드 매칭이면 비교적 믿을 만하다
        "방식": 방식,
        "원문": 글,
    }


# ── 폴더 읽기 ────────────────────────────────────────────────────────
def 폴더읽기(폴더: Path) -> list:
    """영수증 폴더를 훑어 항목 후보를 만든다.

    낱장 파일  → 각각 독립된 항목 (대부분의 경우)
    하위 폴더  → 폴더 안 영수증을 한 항목으로 묶고, 폴더명을 설명에 쓴다
    """
    폴더 = Path(폴더)
    묶음 = []

    for 하위 in sorted(p for p in 폴더.iterdir() if p.is_dir()):
        # 프로그램이 만든 작업용 폴더(_작업 등)는 영수증 항목이 아니다
        if 하위.name.startswith("_") or 하위.name in ("처리완료", "전처리", "작업"):
            continue
        파일들 = sorted(f for f in 하위.iterdir()
                     if f.is_file() and f.suffix.lower() in 지원확장자)
        if 파일들:
            묶음.append({"설명": 하위.name, "파일들": 파일들, "출처": "폴더"})

    for f in sorted(폴더.iterdir()):
        if f.is_file() and f.suffix.lower() in 지원확장자:
            묶음.append({"설명": f.stem, "파일들": [f], "출처": "낱장"})

    return 묶음
