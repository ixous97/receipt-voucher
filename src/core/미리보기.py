"""설치된 Word로 docx를 PDF로 변환하고 페이지를 이미지로 렌더링한다(결과 눈 검증용)."""
from pathlib import Path


def pdf로(docx: Path, pdf: Path = None) -> Path:
    import win32com.client as win32
    docx = docx.resolve()
    pdf = (pdf or docx.with_suffix(".pdf")).resolve()
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(docx), ReadOnly=True)
        doc.SaveAs(str(pdf), FileFormat=17)   # 17 = wdFormatPDF
        doc.Close(False)
    finally:
        word.Quit()
    return pdf


def 이미지로(pdf: Path, 출력폴더: Path, 배율: float = 1.6) -> list:
    import pypdfium2 as pdfium
    출력폴더.mkdir(parents=True, exist_ok=True)
    문서 = pdfium.PdfDocument(str(pdf))
    나온것 = []
    for i in range(len(문서)):
        p = 출력폴더 / f"page{i+1}.png"
        문서[i].render(scale=배율).to_pil().save(p)
        나온것.append(p)
    return 나온것
