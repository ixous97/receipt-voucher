"""결의서 데이터로 워드 문서를 만든다. 원본 표를 복제해 서식을 그대로 보존한다."""
import copy
import sys
from math import ceil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Emu, Mm
from PIL import Image, ImageOps

from 모델 import 쪽당섹션수

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
def _자원(상대: str) -> Path:
    """개발 중에는 프로젝트 폴더, exe로 묶은 뒤에는 번들 안에서 파일을 찾는다."""
    묶음 = getattr(sys, "_MEIPASS", None)
    뿌리 = Path(묶음) if 묶음 else Path(__file__).resolve().parent.parent.parent
    return 뿌리 / 상대


템플릿경로 = _자원("양식/결의서_템플릿.docx")

셀여백 = Mm(1.5)          # 이미지가 셀 테두리에 닿지 않도록
헤더행높이mm = 42.0        # 항목 설명 행 — 설명이 길어 줄바꿈될 여지까지 감안한 여유값
대지높이_첫장mm = 198.0    # 첫 장은 "지출결의서 증빙" 제목이 얹혀 세로 공간이 좁다
대지높이mm = 218.0         # 둘째 장부터는 제목이 없어 영수증을 더 크게 넣을 수 있다
안전비율 = 0.92            # 행 높이 여유 — 첫 장은 제목이 있어 세로 공간이 더 좁다
기본칸수 = 4              # 중첩표는 늘 네 칸. 왼쪽 두 칸 / 오른쪽 두 칸으로 폭이 반반이 된다


def _문단비우기(cell):
    """셀의 문단을 하나만 남기고 지운다. 서식은 첫 문단 것을 유지."""
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    p = cell.paragraphs[0]
    for r in p.runs:
        r._element.getparent().remove(r._element)
    return p


def _글쓰기(cell, 줄들):
    """셀에 여러 줄을 쓴다. 첫 문단의 서식을 복제해 이어붙인다."""
    첫 = _문단비우기(cell)
    첫.add_run(str(줄들[0]))
    for 줄 in 줄들[1:]:
        새 = copy.deepcopy(첫._element)
        for r in 새.findall(W + "r"):
            새.remove(r)
        첫._element.addnext(새)
        첫 = cell.paragraphs[-1]
        첫.add_run(str(줄))


def _열맞추기(표, 목표열수: int, 전체폭_dxa: int):
    """중첩표를 목표 열 수로 정규화한다. 셀 병합(gridSpan)을 풀고 폭을 균등 배분."""
    tbl = 표._tbl
    그리드 = tbl.find(W + "tblGrid")

    # 1) 병합 해제 — 템플릿 헤더 행은 첫 칸이 2칸 병합되어 있다
    for tc in tbl.iter(W + "tc"):
        tcPr = tc.find(W + "tcPr")
        if tcPr is not None:
            gs = tcPr.find(W + "gridSpan")
            if gs is not None:
                tcPr.remove(gs)

    # 2) 모든 행의 칸 수를 목표에 맞춘다
    for tr in tbl.findall(W + "tr"):
        tcs = tr.findall(W + "tc")
        while len(tcs) > 목표열수:
            tr.remove(tcs.pop())
        while len(tcs) < 목표열수:
            새 = copy.deepcopy(tcs[-1])
            tcs[-1].addnext(새)
            tcs = tr.findall(W + "tc")

    # 3) 그리드와 셀 폭을 균등 재배분
    칸폭 = 전체폭_dxa // 목표열수
    for gc in 그리드.findall(W + "gridCol"):
        그리드.remove(gc)
    for _ in range(목표열수):
        그리드.append(그리드.makeelement(W + "gridCol", {W + "w": str(칸폭)}))

    tblW = tbl.find(W + "tblPr").find(W + "tblW")
    if tblW is not None:
        tblW.set(W + "w", str(칸폭 * 목표열수))
        tblW.set(W + "type", "dxa")

    for tr in tbl.findall(W + "tr"):
        for tc in tr.findall(W + "tc"):
            tcPr = tc.find(W + "tcPr")
            if tcPr is None:
                tcPr = tc.makeelement(W + "tcPr", {})
                tc.insert(0, tcPr)
            tcW = tcPr.find(W + "tcW")
            if tcW is None:
                tcW = tcPr.makeelement(W + "tcW", {})
                tcPr.append(tcW)
            tcW.set(W + "w", str(칸폭))
            tcW.set(W + "type", "dxa")


def _행맞추기(표, 목표행수: int, 행높이mm: float):
    """이미지 행(2번째 행 이후) 개수를 맞춘다. 마지막 행을 복제해 늘린다."""
    trs = 표._tbl.findall(W + "tr")
    현재 = len(trs) - 1                       # 헤더 행 제외
    for _ in range(목표행수 - 현재):
        표._tbl.append(copy.deepcopy(trs[-1]))
    trs = 표._tbl.findall(W + "tr")
    for _ in range(len(trs) - 1 - 목표행수):
        표._tbl.remove(trs.pop())

    for tr in 표._tbl.findall(W + "tr")[1:]:
        _행높이설정(tr, 행높이mm)


def _행높이설정(tr, 높이mm: float):
    trPr = tr.find(W + "trPr")
    if trPr is None:
        trPr = tr.makeelement(W + "trPr", {})
        tr.insert(0, trPr)
    th = trPr.find(W + "trHeight")
    if th is None:
        th = trPr.makeelement(W + "trHeight", {})
        trPr.append(th)
    th.set(W + "val", str(int(Mm(높이mm).twips)))
    th.set(W + "hRule", "atLeast")


def _그림넣기(문단, 경로: Path, 최대폭: Emu, 최대높이: Emu):
    """비율을 유지하며 주어진 크기 안에 들어가도록 그림을 넣는다."""
    with Image.open(경로) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size
    배율 = min(최대폭 / w, 최대높이 / h)
    문단.alignment = WD_ALIGN_PARAGRAPH.CENTER
    문단.paragraph_format.space_before = 0      # 문단 여백이 붙으면 칸을 넘친다
    문단.paragraph_format.space_after = 0
    문단.add_run().add_picture(str(경로), width=Emu(int(w * 배율)), height=Emu(int(h * 배율)))


def _이미지넣기(cell, 영, 최대폭: Emu, 최대높이: Emu):
    """칸 하나에 영수증 한 장을 넣는다."""
    _그림넣기(_문단비우기(cell), 영.경로, 최대폭, 최대높이)


def _칸병합(tr, 칸폭들: list, 한칸_dxa: int) -> list:
    """한 행의 칸들을 `칸폭들`대로 합친다. 합친 뒤 남은 칸 목록을 돌려준다.

    예를 들어 왼쪽이 한 줄만 쓰면 [2, 2] 를 넘겨 네 칸을 두 칸으로 만든다.
    그래야 왼쪽·오른쪽 폭이 정확히 반반이 된다.
    """
    tcs = tr.findall(W + "tc")
    자리 = 0
    남은 = []
    for 폭 in 칸폭들:
        if 자리 >= len(tcs):
            break
        tc = tcs[자리]
        tcPr = tc.find(W + "tcPr")
        if tcPr is None:
            tcPr = tc.makeelement(W + "tcPr", {})
            tc.insert(0, tcPr)
        if 폭 > 1:
            for j in range(자리 + 1, min(자리 + 폭, len(tcs))):
                tr.remove(tcs[j])                       # 합쳐지는 칸은 없앤다
            gs = tcPr.find(W + "gridSpan")
            if gs is None:
                gs = tcPr.makeelement(W + "gridSpan", {})
                tcPr.insert(0, gs)
            gs.set(W + "val", str(폭))
        tcW = tcPr.find(W + "tcW")
        if tcW is None:
            tcW = tcPr.makeelement(W + "tcW", {})
            tcPr.append(tcW)
        tcW.set(W + "w", str(한칸_dxa * 폭))
        tcW.set(W + "type", "dxa")
        남은.append(tc)
        자리 += 폭
    return 남은


def _가운데선(tc, 굵기: int = 18):
    """칸 오른쪽에 굵은 세로선을 그어 왼쪽·오른쪽 경계를 분명히 한다."""
    tcPr = tc.find(W + "tcPr")
    if tcPr is None:
        tcPr = tc.makeelement(W + "tcPr", {})
        tc.insert(0, tcPr)
    선들 = tcPr.find(W + "tcBorders")
    if 선들 is None:
        선들 = tcPr.makeelement(W + "tcBorders", {})
        tcPr.append(선들)
    오른 = 선들.find(W + "right")
    if 오른 is None:
        오른 = 선들.makeelement(W + "right", {})
        선들.append(오른)
    오른.set(W + "val", "single")
    오른.set(W + "sz", str(굵기))          # 1/8 pt 단위. 18 = 2.25pt
    오른.set(W + "space", "0")
    오른.set(W + "color", "000000")


def 만들기(결의서들: list, 저장경로: Path) -> Path:
    """결의서 여러 건을 한 문서로 만든다. 건마다 새 페이지."""
    doc = Document(템플릿경로)
    기준표 = doc.tables[0]
    본문 = doc.element.body

    표들 = [기준표]
    for _ in range(len(결의서들) - 1):
        복제 = copy.deepcopy(기준표._tbl)
        본문.insert(list(본문).index(표들[-1]._tbl) + 1, 복제)
        나눔 = doc.add_paragraph()
        나눔.add_run().add_break(WD_BREAK.PAGE)
        복제.addprevious(나눔._element)
        from docx.table import Table
        표들.append(Table(복제, doc))

    for n, (표, 결) in enumerate(zip(표들, 결의서들)):
        _채우기(표, 결, 첫장=(n == 0))

    저장경로.parent.mkdir(parents=True, exist_ok=True)
    doc.save(저장경로)
    return 저장경로


def _채우기(표, 결, 첫장: bool = True):
    _글쓰기(표.rows[0].cells[1], [f"{결.부서명}  /  {결.날짜}"])
    _글쓰기(표.rows[1].cells[1], [f"{결.매수}매 /  \\{결.총금액:,}"])
    _글쓰기(표.rows[2].cells[1], [f"( 지출인 : {결.지출인} )"])

    from docx.table import _Cell

    대지 = 대지높이_첫장mm if 첫장 else 대지높이mm
    _행높이설정(표.rows[3]._tr, 대지)
    안표 = 표.rows[3].cells[0].tables[0]
    전체폭 = int(안표._tbl.find(W + "tblPr").find(W + "tblW").get(W + "w"))

    쪽들 = 결.항목들[:쪽당섹션수]          # 한 장에는 왼쪽·오른쪽 두 쪽만
    행수 = max((s.세로칸수() for s in 쪽들), default=1)

    # 표를 늘 네 칸으로 만들어 둔다. 왼쪽 두 칸 / 오른쪽 두 칸으로 폭이 정확히 반반이 된다.
    _열맞추기(안표, 기본칸수, 전체폭)
    한칸 = 전체폭 // 기본칸수
    행높이 = (대지 - 헤더행높이mm) / 행수 * 안전비율
    _행맞추기(안표, 행수, 행높이)

    # 어느 칸이 어느 쪽의 몇 번째 줄인지 미리 정해 둔다
    폭들, 소속 = [], []
    for 쪽번호, s in enumerate(쪽들):
        가로 = s.가로칸수()
        if 가로 == 1:                       # 한 줄만 쓰면 두 칸을 합쳐 반쪽을 다 쓴다
            폭들.append(2)
            소속.append((쪽번호, 0))
        else:
            폭들.extend([1, 1])
            소속.extend([(쪽번호, 0), (쪽번호, 1)])
    if not 폭들:
        폭들, 소속 = [기본칸수], []

    # 설명 행 — 쪽마다 반쪽씩
    헤더칸들 = _칸병합(안표._tbl.findall(W + "tr")[0], [2] * len(쪽들) or [기본칸수], 한칸)
    for i, tc in enumerate(헤더칸들):
        cell = _Cell(tc, 안표)
        if i < len(쪽들):
            s = 쪽들[i]
            _글쓰기(cell, [s.설명완성(), f"{s.금액:,}원"])
        else:
            _문단비우기(cell)
    if len(쪽들) > 1:
        _가운데선(헤더칸들[0])                # 왼쪽 쪽 오른쪽에 굵은 경계선

    # 영수증 칸 — 각 쪽 안에서 위→아래로 먼저 채운 뒤 옆 줄로 넘어간다
    for r, tr in enumerate(안표._tbl.findall(W + "tr")[1:]):
        칸들 = _칸병합(tr, 폭들, 한칸)
        for k, tc in enumerate(칸들):
            cell = _Cell(tc, 안표)
            if k >= len(소속):
                _문단비우기(cell)
                continue
            쪽번호, 줄 = 소속[k]
            s = 쪽들[쪽번호]
            자리 = 줄 * s.세로칸수() + r
            if 자리 < s.매수:
                칸폭 = Emu(int(한칸 * 폭들[k] * 635)) - 셀여백 * 2
                _이미지넣기(cell, s.영수증들[자리], 칸폭, Mm(행높이) - 셀여백)
            else:
                _문단비우기(cell)
            if len(쪽들) > 1 and 쪽번호 == 0 and (k + 1 >= len(소속) or 소속[k + 1][0] != 0):
                _가운데선(tc)                # 왼쪽 쪽의 마지막 칸에 경계선
