"""지출결의서 증빙 만들기 — 프로그램 시작점.

`--자가진단` 을 붙여 실행하면 화면 없이 핵심 기능만 점검하고 결과를 파일로 남긴다.
exe로 묶은 뒤 다른 PC에서 제대로 도는지 확인할 때 쓴다.
"""
import sys
from pathlib import Path

여기 = Path(__file__).parent
sys.path.insert(0, str(여기 / "core"))
sys.path.insert(0, str(여기 / "ui"))


def 자가진단() -> int:
    """설치된 PC에서 필요한 것이 다 갖춰졌는지 점검한다."""
    from datetime import datetime

    줄 = []

    def 적기(항목, 성공, 설명=""):
        줄.append(f"[{'OK' if 성공 else '실패'}] {항목}{('  ' + 설명) if 설명 else ''}")
        return 성공

    모두성공 = True
    적기("점검 시각", True, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    try:
        import 문서생성
        모두성공 &= 적기("워드 템플릿", 문서생성.템플릿경로.exists(), str(문서생성.템플릿경로))
    except Exception as e:
        모두성공 &= 적기("워드 템플릿", False, f"{type(e).__name__}: {e}")

    try:
        import 영수증판독
        영수증판독._ocr엔진()
        모두성공 &= 적기("한국어 OCR", True, "Windows 내장 OCR 사용 가능")
    except Exception as e:
        모두성공 &= 적기("한국어 OCR", False, f"{type(e).__name__}: {e}")

    try:
        from 모델 import 결의서, 항목, 영수증, 검산
        모두성공 &= 적기("검산 기능", 검산(결의서()) != [], "빈 결의서를 제대로 막음")
    except Exception as e:
        모두성공 &= 적기("검산 기능", False, f"{type(e).__name__}: {e}")

    # 실제로 영수증을 읽고 워드 문서까지 만들어 본다
    표본 = Path(sys.argv[sys.argv.index("--표본") + 1]) if "--표본" in sys.argv else None
    if 표본 and 표본.exists():
        try:
            import 파이프라인
            from 모델 import 결의서
            작업 = Path.home() / ".wjm_자가진단"
            항목들 = 파이프라인.읽어오기(표본, 작업)
            장수 = sum(it.매수 for it in 항목들)
            모두성공 &= 적기("영수증 읽기", 장수 > 0, f"{장수}장 읽음")
            for it in 항목들:
                for r in it.영수증들:
                    r.확인필요 = False
            결 = 결의서(날짜="자가진단", 지출인="자가진단", 항목들=항목들)
            나온것 = 파이프라인.문서만들기([결], 작업 / "진단결과.docx", 작업)
            모두성공 &= 적기("워드 문서 만들기", 나온것.exists(),
                          f"{나온것.stat().st_size // 1024}KB, 총 {결.총금액:,}원 / {결.매수}매")
        except Exception as e:
            모두성공 &= 적기("영수증 읽기·문서 만들기", False, f"{type(e).__name__}: {e}")

    보고 = "\n".join(줄) + f"\n\n종합: {'모두 정상' if 모두성공 else '문제 있음'}\n"
    나갈곳 = Path.home() / "지출결의서_자가진단.txt"
    나갈곳.write_text(보고, encoding="utf-8")
    print(보고)
    print(f"결과를 {나갈곳} 에 저장했습니다.")
    return 0 if 모두성공 else 1


def main():
    if "--자가진단" in sys.argv:
        sys.exit(자가진단())

    from PySide6.QtWidgets import QApplication
    from 메인창 import 메인창

    앱 = QApplication(sys.argv)
    앱.setApplicationName("지출결의서 증빙 만들기")
    창 = 메인창()
    창.show()
    sys.exit(앱.exec())


if __name__ == "__main__":
    main()
