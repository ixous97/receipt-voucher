"""원본 양식에서 이미지·내용을 비운 결의서 템플릿(표 1개)을 만든다."""
import shutil, zipfile, re
from pathlib import Path
from docx import Document

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
원본 = Path("양식/원본/2026 지출결의 양식.docx")
결과 = Path("양식/결의서_템플릿.docx")
임시 = Path("양식/_작업.docx")


def 요소제거(el):
    el.getparent().remove(el)


doc = Document(원본)
표들 = doc.tables
print(f"원본 표 {len(표들)}개")

# 3열 중첩표를 가진 표를 템플릿으로 삼는다 (열 수를 줄이는 쪽이 늘리기보다 단순)
def 중첩표(tbl):
    return tbl.rows[3].cells[0].tables[0]

기준 = max(range(len(표들)), key=lambda i: len(중첩표(표들[i]).columns))
print(f"→ 표{기준+1}을 템플릿으로 채택 (중첩표 {len(중첩표(표들[기준]).columns)}열)")

# 나머지 표와 그 사이 문단(페이지 구분용 빈 문단 포함) 제거
for i, t in enumerate(표들):
    if i != 기준:
        요소제거(t._element)

inner = 중첩표(표들[기준])
# 이미지 행 전부 제거 → 항목 헤더 행 1개 + 이미지 행 1개(견본)만 남긴다
for tr in inner._element.findall(W + "tr")[2:]:
    요소제거(tr)

# 남은 이미지 행에서 그림 요소만 비운다 (셀 서식은 보존)
for tc in inner._element.findall(W + "tr")[1].findall(W + "tc"):
    for tag in ("drawing", "pict", "object"):
        for el in list(tc.iter(W + tag)):
            요소제거(el)

# 항목 헤더 행의 글자 비우기
for tc in inner._element.findall(W + "tr")[0].findall(W + "tc"):
    for t in tc.iter(W + "t"):
        t.text = ""

doc.save(임시)

# media 제거 + 이미지 관계 정리로 용량 축소
with zipfile.ZipFile(임시) as zin, zipfile.ZipFile(결과, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        if item.filename.startswith("word/media/"):
            continue
        data = zin.read(item.filename)
        if item.filename == "word/_rels/document.xml.rels":
            data = re.sub(rb'<Relationship[^>]*?Target="media/[^"]*"[^>]*?/>', b"", data)
        zout.writestr(item, data)
임시.unlink()

확인 = Document(결과)
t = 확인.tables[0]
i = t.rows[3].cells[0].tables[0]
print(f"\n템플릿 완성: {결과}")
print(f"  크기        : {결과.stat().st_size/1024:.1f} KB  (원본 {원본.stat().st_size/1024/1024:.1f} MB)")
print(f"  바깥 표     : {len(확인.tables)}개, {len(t.rows)}행")
print(f"  중첩표      : {len(i.rows)}행 x {len(i.columns)}열")
for r, row in enumerate(t.rows[:3]):
    print(f"  R{r}: " + " | ".join(repr(c.text.strip()[:40]) for c in row.cells))
