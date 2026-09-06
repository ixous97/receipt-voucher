"""파이썬이 만든 문서와 브라우저가 만든 문서를 항목별로 대조한다.

XML 을 통째로 비교하면 속성 차례나 네임스페이스 접두사 같은, 워드가 신경 쓰지 않는
차이까지 걸린다. 그래서 문서의 생김새를 실제로 좌우하는 것만 뽑아 견준다 —
글자, 표의 칸 나눔, 행 높이, 그림 크기, 가운데 경계선.
"""
import base64
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

여기 = Path(__file__).resolve().parent
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def 문서읽기(경로: Path):
    with zipfile.ZipFile(경로) as z:
        본문 = ET.fromstring(z.read("word/document.xml"))
        그림수 = len([n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")])
    return 본문, 그림수


def 글자들(뿌리):
    return [t.text or "" for t in 뿌리.iter(W + "t") if (t.text or "").strip()]


def 표구조(뿌리):
    """중첩표(영수증 대지)의 칸 나눔과 행 높이를 뽑는다."""
    표들 = list(뿌리.iter(W + "tbl"))
    안표 = 표들[1]                      # 0번은 바깥 표, 1번이 대지
    줄들 = []
    for tr in 안표.findall(W + "tr"):
        높이 = tr.find(f"{W}trPr/{W}trHeight")
        칸들 = []
        for tc in tr.findall(W + "tc"):
            tcPr = tc.find(W + "tcPr")
            폭 = tcPr.find(W + "tcW") if tcPr is not None else None
            병합 = tcPr.find(W + "gridSpan") if tcPr is not None else None
            경계 = tcPr.find(f"{W}tcBorders/{W}right") if tcPr is not None else None
            칸들.append({
                "폭": 폭.get(W + "w") if 폭 is not None else None,
                "병합": 병합.get(W + "val") if 병합 is not None else "1",
                "오른선": 경계.get(W + "sz") if 경계 is not None else None,
            })
        줄들.append({
            "높이": 높이.get(W + "val") if 높이 is not None else None,
            "칸들": 칸들,
        })
    격자 = [gc.get(W + "w") for gc in 안표.find(W + "tblGrid").findall(W + "gridCol")]
    return {"격자": 격자, "줄들": 줄들}


def 그림크기들(뿌리):
    return [(e.get("cx"), e.get("cy")) for e in 뿌리.iter(WP + "extent")]


기준경로 = 여기 / "기준.docx"
브라우저경로 = 여기 / "브라우저.docx"

b64 = (여기.parent / "브라우저결과.b64").read_text().strip().strip('"')
브라우저경로.write_bytes(base64.b64decode(b64))

기준, 기준그림수 = 문서읽기(기준경로)
브, 브그림수 = 문서읽기(브라우저경로)

맞음 = True


def 견주기(이름, 왼, 오):
    global 맞음
    같음 = 왼 == 오
    맞음 &= 같음
    print(f"{'OK ' if 같음 else '다름'}  {이름}")
    if not 같음:
        print(f"      파이썬  : {왼}")
        print(f"      브라우저: {오}")


print(f"파일 크기   파이썬 {기준경로.stat().st_size:,}  /  "
      f"브라우저 {브라우저경로.stat().st_size:,} 바이트\n")

견주기("글자", 글자들(기준), 글자들(브))
견주기("그림 개수", 기준그림수, 브그림수)
견주기("그림 크기", 그림크기들(기준), 그림크기들(브))

ㄱ, ㄴ = 표구조(기준), 표구조(브)
견주기("표 격자(칸 폭)", ㄱ["격자"], ㄴ["격자"])
견주기("표 줄 수", len(ㄱ["줄들"]), len(ㄴ["줄들"]))
for i, (a, b) in enumerate(zip(ㄱ["줄들"], ㄴ["줄들"])):
    견주기(f"  {i}번째 줄 높이", a["높이"], b["높이"])
    견주기(f"  {i}번째 줄 칸", a["칸들"], b["칸들"])

print()
if 맞음:
    print("결과: 두 문서의 구조가 완전히 같다. 이식이 옳다.")
else:
    print("결과: 어긋난 곳이 있다. 위의 '다름' 줄을 보라.")
    sys.exit(1)
