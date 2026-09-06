"""지출결의서 데이터 모델과 검산.

문서 한 장은 **왼쪽 쪽 / 오른쪽 쪽** 두 덩어리로 이루어지고, 쪽마다 설명 문구 하나와
영수증을 최대 6장 담는다. 쪽 번호는 1부터 이어지며 두 개가 한 장이 된다 —
1쪽=1장 왼쪽, 2쪽=1장 오른쪽, 3쪽=2장 왼쪽 … 이런 식이다.

영수증을 어디에 넣을지는 **사람이 쪽 번호로 정한다.** 한 쪽이 6장으로 차면 더 넣지 못하게
막아서, 다음 쪽으로 옮기도록 안내한다(자동으로 옮기지 않는다).
"""
import re
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path

최대섹션수 = 10         # 쪽 1~10. 두 쪽이 한 장이 된다 (쪽1·2 → 1장, 쪽3·4 → 2장 …)
섹션최대장수 = 6        # 한 쪽에 넣을 수 있는 영수증 수. 넘으면 넣지 못하게 막는다
섹션가로전환 = 4        # 이 장수부터는 한 쪽 안에서 두 줄로 나눠 넣는다
쪽당섹션수 = 2          # 한 장에 왼쪽·오른쪽 두 쪽


def 쪽위치(번호: int) -> str:
    """쪽 번호를 '2장 왼쪽' 같은 사람이 읽는 말로 바꾼다."""
    장 = (번호 + 1) // 2
    좌우 = "왼쪽" if 번호 % 2 == 1 else "오른쪽"
    return f"{장}장 {좌우}"


@dataclass
class 영수증:
    경로: Path
    금액: int = 0
    날짜: str = ""          # "0813" 형태
    상호: str = ""
    확인필요: bool = True    # 사람이 확인하기 전에는 True
    후보: list = field(default_factory=list)   # 판독이 읽어낸 금액 후보들
    근거: str = ""

    @property
    def 이름(self) -> str:
        return self.경로.name


@dataclass
class 섹션:
    """문서의 왼쪽 또는 오른쪽 한 덩어리. 설명 문구 하나와 영수증 여러 장."""
    설명: str = ""
    영수증들: list = field(default_factory=list)
    직접입력: bool = False    # 사람이 설명을 고쳤으면 True — 자동 갱신하지 않는다

    @property
    def 금액(self) -> int:
        return sum(r.금액 for r in self.영수증들)

    @property
    def 매수(self) -> int:
        return len(self.영수증들)

    def 가로칸수(self) -> int:
        """섹션 안에서 영수증을 몇 줄로 나눠 넣을지.

        영수증은 세로로 긴 모양이라 적은 장수는 위아래로 쌓는 편이 크게 보인다.
        장수가 늘면 두 줄로 나눠야 한 장 한 장이 덜 작아진다.
        """
        return 1 if self.매수 < 섹션가로전환 else 2

    def 세로칸수(self) -> int:
        return max(1, ceil(self.매수 / self.가로칸수()))

    def 설명초안(self) -> str:
        """원본 형식(`0813,20,27 스텝 식대 3건`)에 맞춘 자동 초안.

        날짜와 건수는 영수증에서 얻을 수 있지만 '누구 식대인지' 같은 성격은
        영수증에 없는 정보다. 폴더명·파일명을 가져다 쓰고 사람이 다듬는다.
        """
        날짜들 = sorted({r.날짜 for r in self.영수증들 if r.날짜})
        날짜부 = ",".join(날짜들)
        성격 = re.sub(r"^[\d,\s]+", "", self.설명.strip())   # 파일명 앞 날짜는 중복이라 뗀다
        건수 = f" {self.매수}건" if self.매수 > 1 else ""
        return " ".join(x for x in (날짜부, 성격) if x).strip() + 건수

    def 설명완성(self) -> str:
        """사람이 손댄 문구는 그대로 두고, 그렇지 않으면 초안을 새로 만든다.

        초안을 쓰면 영수증을 옮길 때마다 날짜와 건수가 자동으로 따라 바뀐다.
        """
        if self.직접입력 and self.설명.strip():
            return self.설명.strip()
        return self.설명초안()


# 예전 이름으로 부르던 곳이 있어 남겨 둔다
항목 = 섹션


@dataclass
class 결의서:
    """지출결의서 1건 = 워드 1페이지."""
    부서명: str = "위드지저스미니스트리(WJM)"
    날짜: str = ""            # "2026년 9월 4일"
    지출인: str = ""
    항목들: list = field(default_factory=list)     # 왼쪽부터 순서대로. 최대 2개

    @property
    def 섹션들(self) -> list:
        return self.항목들

    @property
    def 영수증들(self) -> list:
        return [r for s in self.항목들 for r in s.영수증들]

    @property
    def 총금액(self) -> int:
        return sum(s.금액 for s in self.항목들)

    @property
    def 매수(self) -> int:
        return len(self.영수증들)

    def 섹션옮기기(self, 영: 영수증, 번호: int) -> str:
        """영수증을 `번호`쪽으로 옮긴다. 옮기지 못하면 그 이유를 돌려준다(성공하면 빈 문자열)."""
        if not 1 <= 번호 <= 최대섹션수:
            return f"쪽 번호는 1부터 {최대섹션수}까지만 쓸 수 있습니다."
        if self.섹션번호(영) == 번호:
            return ""
        if 번호 <= len(self.항목들) and self.항목들[번호 - 1].매수 >= 섹션최대장수:
            return (f"{쪽위치(번호)}({번호}쪽)이 이미 {섹션최대장수}장으로 꽉 찼습니다. "
                    "다른 쪽으로 옮겨 주세요.")

        while len(self.항목들) < 번호:
            self.항목들.append(섹션())
        for s in self.항목들:
            if 영 in s.영수증들:
                s.영수증들.remove(영)
        self.항목들[번호 - 1].영수증들.append(영)
        self.빈섹션정리()
        return ""

    def 섹션번호(self, 영: 영수증) -> int:
        for i, s in enumerate(self.항목들, 1):
            if 영 in s.영수증들:
                return i
        return 0

    def 빈섹션정리(self):
        """영수증이 하나도 없는 섹션은 없앤다. 단 순서는 유지한다."""
        self.항목들 = [s for s in self.항목들 if s.영수증들]


def 페이지나누기(결: 결의서) -> list:
    """쪽 두 개를 묶어 한 장으로 만든다. 쪽1·2 → 1장, 쪽3·4 → 2장 …

    영수증을 자동으로 옮기지 않는다. 어느 쪽에 넣을지는 사람이 '쪽' 번호로 정하고,
    한 쪽이 꽉 차면(6장) 넣지 못하게 막아 다음 쪽으로 옮기도록 안내한다.
    """
    if not 결.항목들:
        return [결]
    페이지들 = []
    for i in range(0, len(결.항목들), 쪽당섹션수):
        페이지들.append(결의서(부서명=결.부서명, 날짜=결.날짜, 지출인=결.지출인,
                          항목들=결.항목들[i:i + 쪽당섹션수]))
    return 페이지들


def 장수(결: 결의서) -> int:
    return len(페이지나누기(결))


# 예전 이름
쪽수 = 장수


def 검산(결: 결의서) -> list:
    """문서를 만들기 전 반드시 통과해야 하는 검사. 문제 목록을 돌려준다."""
    문제 = []
    if not 결.항목들:
        문제.append("영수증이 하나도 없습니다.")
    if not 결.지출인.strip():
        문제.append("지출인을 입력해 주세요.")
    if not 결.날짜.strip():
        문제.append("날짜를 입력해 주세요.")

    if len(결.항목들) > 최대섹션수:
        문제.append(
            f"쪽이 {len(결.항목들)}개입니다. 쪽 번호는 1부터 {최대섹션수}까지만 쓸 수 있습니다.")

    for i, s in enumerate(결.항목들):
        어디 = 쪽위치(i + 1)
        if s.매수 > 섹션최대장수:
            문제.append(
                f"{어디}({i+1}쪽)에 영수증이 {s.매수}장입니다. "
                f"한 쪽에는 {섹션최대장수}장까지만 들어갑니다. "
                f"{s.매수 - 섹션최대장수}장을 다른 쪽으로 옮겨 주세요.")
        if not s.설명완성():
            문제.append(f"{어디}의 설명 문구가 비어 있습니다.")
        for r in s.영수증들:
            if r.금액 <= 0:
                문제.append(f"'{r.이름}'의 금액이 비어 있습니다.")
            if r.확인필요:
                문제.append(f"'{r.이름}'의 금액({r.금액:,}원)이 아직 확인되지 않았습니다.")

    return 문제
