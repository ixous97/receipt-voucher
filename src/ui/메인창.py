"""지출결의서 증빙 만들기 — 메인 화면.

문서 한 장은 왼쪽·오른쪽 두 쪽으로 나뉜다.
영수증의 '쪽' 번호(1쪽=1장 왼쪽, 2쪽=1장 오른쪽, 3쪽=2장 왼쪽 …)만 바꾸면 자리를 옮긴다.
왼쪽에 영수증 원본을 크게 띄우고, 오른쪽 표에서 금액을 고친다.
"""
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from 모델 import (결의서, 섹션, 영수증, 검산, 장수, 쪽위치,
                최대섹션수, 섹션최대장수)
import 영수증판독 as 판독기
import 파이프라인

열_설명, 열_금액, 열_날짜, 열_쪽, 열_확인 = range(5)


class 판독작업(QThread):
    """영수증 읽기는 시간이 걸리므로 화면이 멈추지 않게 따로 돌린다."""
    진행 = Signal(int, int, str)
    완료 = Signal(list)
    실패 = Signal(str)

    def __init__(self, 폴더: Path, 작업폴더: Path):
        super().__init__()
        self.폴더, self.작업폴더 = 폴더, 작업폴더

    def run(self):
        try:
            섹션들 = 파이프라인.읽어오기(
                self.폴더, self.작업폴더,
                진행=lambda i, n, f: self.진행.emit(i, n, f))
            self.완료.emit(섹션들)
        except Exception as e:
            self.실패.emit(f"{type(e).__name__}: {e}")


class 메인창(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("지출결의서 증빙 만들기")
        self.resize(1300, 880)
        self.영수증폴더 = None
        self.항목들 = []          # 섹션 목록 (왼쪽부터)
        self.작업 = None

        self.상단 = self._상단만들기()
        self.setCentralWidget(self._본문())
        QShortcut(QKeySequence.Paste, self, activated=self.클립보드에서넣기)
        self.statusBar().showMessage(
            "영수증 폴더를 열거나, 캡처한 이미지를 Ctrl+V 로 바로 붙여넣으세요.")

    # ── 화면 구성 ────────────────────────────────────────────────
    def _상단만들기(self) -> QWidget:
        위 = QWidget()
        가로 = QHBoxLayout(위)
        가로.setContentsMargins(8, 8, 8, 4)

        self.폴더열기 = QPushButton("영수증 폴더 열기")
        self.폴더열기.setMinimumHeight(34)
        self.폴더열기.clicked.connect(self.폴더선택)
        가로.addWidget(self.폴더열기)

        self.읽기 = QPushButton("영수증 읽기")
        self.읽기.setMinimumHeight(34)
        self.읽기.setEnabled(False)
        self.읽기.clicked.connect(self.판독시작)
        가로.addWidget(self.읽기)
        가로.addSpacing(24)

        양식 = QFormLayout()
        오늘 = date.today()
        self.부서명 = QLineEdit("위드지저스미니스트리(WJM)")
        self.날짜 = QLineEdit(f"{오늘.year}년 {오늘.month}월 {오늘.day}일")
        self.지출인 = QLineEdit()
        self.지출인.setPlaceholderText("이름을 입력하세요")
        for 이름, 칸 in (("부서명", self.부서명), ("날짜", self.날짜), ("지출인", self.지출인)):
            칸.setMinimumWidth(200)
            양식.addRow(이름, 칸)
        가로.addLayout(양식)
        가로.addStretch()

        self.진행바 = QProgressBar()
        self.진행바.setVisible(False)
        self.진행바.setMaximumWidth(260)
        가로.addWidget(self.진행바)

        self.만들기 = QPushButton("워드 문서 만들기")
        self.만들기.setMinimumHeight(40)
        self.만들기.setMinimumWidth(150)
        self.만들기.clicked.connect(self.문서만들기)
        가로.addWidget(self.만들기)
        return 위

    def _본문(self) -> QWidget:
        나눔 = QSplitter(Qt.Horizontal)

        왼 = QGroupBox("영수증 원본")
        왼세로 = QVBoxLayout(왼)
        self.그림 = QLabel("오른쪽 목록에서 영수증을 고르면\n여기에 크게 보입니다.")
        self.그림.setAlignment(Qt.AlignCenter)
        self.그림.setMinimumWidth(420)
        self.그림.setStyleSheet("background:#f4f4f4; color:#888; border:1px solid #ddd;")
        왼세로.addWidget(self.그림, 1)
        self.파일이름 = QLabel("")
        self.파일이름.setAlignment(Qt.AlignCenter)
        self.파일이름.setStyleSheet("color:#555;")
        왼세로.addWidget(self.파일이름)
        나눔.addWidget(왼)

        오 = QGroupBox("문서에 들어갈 내용   (칸을 두 번 누르면 고칠 수 있습니다)")
        오세로 = QVBoxLayout(오)
        self.표 = QTreeWidget()
        self.표.setColumnCount(5)
        self.표.setHeaderLabels(["쪽 / 영수증", "금액", "날짜", "쪽", "확인"])
        self.표.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.표.setAlternatingRowColors(True)
        self.표.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.표.itemSelectionChanged.connect(self.선택바뀜)
        self.표.itemClicked.connect(self.칸눌림)
        self.표.itemChanged.connect(self.값바뀜)
        self.표.setContextMenuPolicy(Qt.CustomContextMenu)
        self.표.customContextMenuRequested.connect(self.오른쪽메뉴)
        머리 = self.표.header()
        머리.setSectionResizeMode(열_설명, QHeaderView.Stretch)
        for c in (열_금액, 열_날짜, 열_쪽, 열_확인):
            머리.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        오세로.addWidget(self.표, 1)

        도구 = QHBoxLayout()
        self.앞으로 = QPushButton("◀ 앞쪽으로")
        self.앞으로.setToolTip("고른 영수증을 한 쪽 앞으로 옮깁니다 (2쪽 → 1쪽).")
        self.앞으로.clicked.connect(lambda: self.쪽이동(-1))
        도구.addWidget(self.앞으로)
        self.뒤로 = QPushButton("뒤쪽으로 ▶")
        self.뒤로.setToolTip("고른 영수증을 한 쪽 뒤로 옮깁니다 (1쪽 → 2쪽). "
                          "쪽이 꽉 찼을 때 다음 쪽으로 넘길 때 씁니다.")
        self.뒤로.clicked.connect(lambda: self.쪽이동(1))
        도구.addWidget(self.뒤로)
        self.붙여넣기 = QPushButton("붙여넣기 (Ctrl+V)")
        self.붙여넣기.setToolTip("화면 캡처나 복사한 이미지를 그대로 영수증으로 넣습니다.")
        self.붙여넣기.clicked.connect(self.클립보드에서넣기)
        도구.addWidget(self.붙여넣기)
        도구.addStretch()
        오세로.addLayout(도구)

        self.합계 = QLabel("합계: 0원  /  영수증 0매")
        self.합계.setStyleSheet("font-size:17px; font-weight:bold; padding:6px;")
        오세로.addWidget(self.합계)

        self.안내 = QLabel(
            "문서 한 장은 왼쪽·오른쪽 두 쪽으로 나뉩니다. 1쪽=1장 왼쪽, 2쪽=1장 오른쪽, "
            "3쪽=2장 왼쪽 … 순서이며, '쪽' 칸에 번호를 넣으면 그리로 옮겨집니다. "
            f"한 쪽에는 {섹션최대장수}장까지만 들어갑니다.\n"
            "⚠ 표시는 자동 판독이 확신하지 못한 금액입니다. 왼쪽에서 영수증을 보고 금액이 맞으면 "
            "'확인' 칸을 누르고, 틀렸으면 금액 칸을 두 번 눌러 고치세요.")
        self.안내.setWordWrap(True)
        self.안내.setStyleSheet("color:#a15c00;")
        오세로.addWidget(self.안내)
        나눔.addWidget(오)
        나눔.setSizes([440, 860])

        전체 = QWidget()
        세로 = QVBoxLayout(전체)
        세로.setContentsMargins(0, 0, 0, 0)
        세로.addWidget(self.상단)
        세로.addWidget(나눔, 1)
        return 전체

    # ── 영수증 읽기 ──────────────────────────────────────────────
    def 폴더선택(self):
        고른곳 = QFileDialog.getExistingDirectory(self, "영수증이 들어 있는 폴더를 고르세요")
        if not 고른곳:
            return
        self.영수증폴더 = Path(고른곳)
        self.읽기.setEnabled(True)
        self.statusBar().showMessage(f"{self.영수증폴더}  —  '영수증 읽기'를 누르세요.")

    def 판독시작(self):
        if not self.영수증폴더:
            return
        self.읽기.setEnabled(False)
        self.폴더열기.setEnabled(False)
        self.진행바.setVisible(True)
        self.진행바.setValue(0)
        self.작업 = 판독작업(self.영수증폴더, self.영수증폴더 / "_작업")
        self.작업.진행.connect(self.진행표시)
        self.작업.완료.connect(self.판독끝)
        self.작업.실패.connect(self.판독실패)
        self.작업.start()

    def 진행표시(self, i, n, 이름):
        self.진행바.setMaximum(n)
        self.진행바.setValue(i)
        self.statusBar().showMessage(f"읽는 중 ({i}/{n}) — {이름}")

    def 판독실패(self, 메시지):
        self.진행바.setVisible(False)
        self.읽기.setEnabled(True)
        self.폴더열기.setEnabled(True)
        QMessageBox.critical(self, "영수증을 읽지 못했습니다", 메시지)

    def 판독끝(self, 섹션들):
        self.항목들 = 섹션들
        self.진행바.setVisible(False)
        self.읽기.setEnabled(True)
        self.폴더열기.setEnabled(True)
        self.표채우기()
        전체 = sum(s.매수 for s in 섹션들)
        미확인 = sum(1 for s in 섹션들 for r in s.영수증들 if r.확인필요)
        self.statusBar().showMessage(
            f"{전체}장을 읽었습니다. 확인이 필요한 금액 {미확인}건.")

    # ── 표 ──────────────────────────────────────────────────────
    def 표채우기(self):
        고른것 = {id(d[1]) for w in self.표.selectedItems()
                if (d := w.data(0, Qt.UserRole)) and d[0] == "영수증"}
        self.표.blockSignals(True)
        self.표.clear()
        for i, s in enumerate(self.항목들):
            찼나 = "  ← 꽉 참" if s.매수 >= 섹션최대장수 else ""
            부모 = QTreeWidgetItem(
                self.표, [f"[{i+1}쪽 · {쪽위치(i+1)}]  {s.설명완성()}",
                        f"{s.금액:,}", "", "", f"{s.매수}/{섹션최대장수}장{찼나}"])
            부모.setFlags(부모.flags() | Qt.ItemIsEditable)
            부모.setData(0, Qt.UserRole, ("섹션", s))
            for r in s.영수증들:
                상태 = "⚠ 확인 필요" if r.확인필요 else "확인됨"
                자식 = QTreeWidgetItem(
                    부모, [r.이름, f"{r.금액:,}", r.날짜, str(i + 1), 상태])
                자식.setFlags(자식.flags() | Qt.ItemIsEditable)
                자식.setData(0, Qt.UserRole, ("영수증", r))
                if id(r) in 고른것:
                    자식.setSelected(True)
            부모.setExpanded(True)
        self.표.blockSignals(False)
        self.합계갱신()

    def 합계갱신(self):
        결 = self._결의서()
        장 = 장수(결) if 결.항목들 else 0
        글 = f"합계: {결.총금액:,}원  /  영수증 {결.매수}매"
        if 장 >= 1:
            글 += f"  /  문서 {장}장"
        넘친쪽 = [f"{i+1}쪽" for i, s in enumerate(결.항목들) if s.매수 > 섹션최대장수]
        문제 = bool(넘친쪽) or len(결.항목들) > 최대섹션수
        if 넘친쪽:
            글 += (f"    ⚠ {', '.join(넘친쪽)}이 {섹션최대장수}장을 넘었습니다 "
                  "— 다음 쪽으로 옮겨 주세요")
        elif len(결.항목들) > 최대섹션수:
            글 += f"    ⚠ 쪽이 {최대섹션수}개를 넘었습니다"
        self.합계.setText(글)
        self.합계.setStyleSheet(
            "font-size:17px; font-weight:bold; padding:6px;"
            + ("color:#c0392b;" if 문제 else ""))

    def _결의서(self) -> 결의서:
        return 결의서(부서명=self.부서명.text(), 날짜=self.날짜.text(),
                    지출인=self.지출인.text(), 항목들=self.항목들)

    def _고른영수증들(self) -> list:
        골라진 = []
        for w in self.표.selectedItems():
            데이터 = w.data(0, Qt.UserRole)
            if 데이터 and 데이터[0] == "영수증" and 데이터[1] not in 골라진:
                골라진.append(데이터[1])
        return 골라진

    def 선택바뀜(self):
        고른것 = self.표.selectedItems()
        if not 고른것:
            return
        데이터 = 고른것[0].data(0, Qt.UserRole)
        if not 데이터 or 데이터[0] != "영수증":
            return
        값 = 데이터[1]
        그림 = QPixmap(str(값.경로))
        if 그림.isNull():
            self.그림.setText("(이 형식은 미리보기를 만들 수 없습니다)")
        else:
            self.그림.setPixmap(그림.scaled(self.그림.size(), Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        self.파일이름.setText(f"{값.이름}    ·    읽은 근거: {값.근거}")

    def 칸눌림(self, 위젯, 열):
        """확인 칸을 누르면 확인 상태를 바꾼다. 영수증을 보고 한 번 누르면 된다."""
        if 열 != 열_확인:
            return
        데이터 = 위젯.data(0, Qt.UserRole)
        if not 데이터 or 데이터[0] != "영수증":
            return
        값 = 데이터[1]
        값.확인필요 = not 값.확인필요
        self.표.blockSignals(True)
        위젯.setText(열_확인, "⚠ 확인 필요" if 값.확인필요 else "확인됨")
        self.표.blockSignals(False)
        남은 = sum(1 for s in self.항목들 for r in s.영수증들 if r.확인필요)
        self.statusBar().showMessage(
            "확인할 금액이 남지 않았습니다. 문서를 만들 수 있습니다."
            if 남은 == 0 else f"확인이 필요한 금액 {남은}건이 남았습니다.")

    def 값바뀜(self, 위젯, 열):
        데이터 = 위젯.data(0, Qt.UserRole)
        if not 데이터:
            return
        종류, 값 = 데이터
        self.표.blockSignals(True)
        다시그리기 = False
        try:
            if 종류 == "영수증" and 열 == 열_금액:
                숫자 = "".join(ch for ch in 위젯.text(열_금액) if ch.isdigit())
                if 숫자:
                    값.금액 = int(숫자)
                    값.확인필요 = False        # 사람이 손댔으니 확인된 것으로 본다
                    위젯.setText(열_확인, "확인됨")
                위젯.setText(열_금액, f"{값.금액:,}")
            elif 종류 == "영수증" and 열 == 열_날짜:
                값.날짜 = 위젯.text(열_날짜).strip()
            elif 종류 == "영수증" and 열 == 열_쪽:
                숫자 = "".join(ch for ch in 위젯.text(열_쪽) if ch.isdigit())
                번호 = int(숫자) if 숫자 else 0
                if 1 <= 번호 <= 최대섹션수:
                    다시그리기 = True
                else:
                    QMessageBox.information(
                        self, f"1부터 {최대섹션수}까지 넣어 주세요",
                        f"'쪽' 칸에는 1부터 {최대섹션수}까지 넣을 수 있습니다.\n"
                        "1쪽=1장 왼쪽, 2쪽=1장 오른쪽, 3쪽=2장 왼쪽 … 순서입니다.")
                    위젯.setText(열_쪽, str(self._결의서().섹션번호(값)))
            elif 종류 == "섹션" and 열 == 열_설명:
                글 = 위젯.text(열_설명)
                값.설명 = 글.split("]", 1)[-1].strip() if "]" in 글 else 글.strip()
                값.직접입력 = bool(값.설명)      # 사람이 고쳤으니 자동 갱신을 멈춘다
                다시그리기 = True

            for i in range(self.표.topLevelItemCount()):     # 섹션 합계 다시 계산
                부모 = self.표.topLevelItem(i)
                s = 부모.data(0, Qt.UserRole)[1]
                부모.setText(열_금액, f"{s.금액:,}")
                부모.setText(열_확인, f"{s.매수}장")
        finally:
            self.표.blockSignals(False)

        if 다시그리기 and 종류 == "영수증" and 열 == 열_쪽:
            self._옮기기실행([값], 번호)
        elif 다시그리기:
            self.표채우기()
        else:
            self.합계갱신()

    # ── 섹션 옮기기 ──────────────────────────────────────────────
    def 쪽으로옮기기(self, 번호: int):
        고른것 = self._고른영수증들()
        if not 고른것:
            QMessageBox.information(
                self, "영수증을 고르세요",
                "옮길 영수증을 먼저 고른 뒤 다시 눌러 주세요.\n"
                "Ctrl 키를 누른 채 누르면 여러 장을 함께 고를 수 있습니다.")
            return
        self._옮기기실행(고른것, 번호)

    def 쪽이동(self, 증감: int):
        """고른 영수증을 한 쪽 앞이나 뒤로 옮긴다."""
        고른것 = self._고른영수증들()
        if not 고른것:
            QMessageBox.information(
                self, "영수증을 고르세요",
                "옮길 영수증을 먼저 고른 뒤 다시 눌러 주세요.\n"
                "Ctrl 키를 누른 채 누르면 여러 장을 함께 고를 수 있습니다.")
            return
        지금 = self._결의서().섹션번호(고른것[0])
        갈곳 = min(최대섹션수, max(1, 지금 + 증감))
        if 갈곳 == 지금:
            self.statusBar().showMessage(
                "더 옮길 곳이 없습니다." if 증감 > 0 else "이미 첫 쪽입니다.")
            return
        self._옮기기실행(고른것, 갈곳)

    def _옮기기실행(self, 영수증들: list, 번호: int):
        결 = self._결의서()
        옮긴수, 막힌이유 = 0, ""
        for r in 영수증들:
            이유 = 결.섹션옮기기(r, 번호)
            if 이유:
                막힌이유 = 막힌이유 or 이유
            else:
                옮긴수 += 1
        self.항목들 = 결.항목들
        self.표채우기()

        if 막힌이유:
            QMessageBox.warning(
                self, "옮기지 못했습니다",
                막힌이유 + (f"\n\n{옮긴수}장만 옮겼습니다." if 옮긴수 else ""))
            return
        self.statusBar().showMessage(
            f"{옮긴수}장을 {번호}쪽({쪽위치(번호)})으로 옮겼습니다.")

    # ── 오른쪽 버튼 메뉴 ─────────────────────────────────────────
    def 오른쪽메뉴(self, 위치):
        위젯 = self.표.itemAt(위치)
        if not 위젯:
            return
        데이터 = 위젯.data(0, Qt.UserRole)
        if not 데이터 or 데이터[0] != "영수증":
            return
        영 = 데이터[1]
        지금 = self._결의서().섹션번호(영)
        메뉴 = QMenu(self)

        for 번호 in range(max(1, 지금 - 1), min(최대섹션수, 지금 + 2) + 1):
            if 번호 == 지금:
                continue
            동작 = QAction(f"{번호}쪽({쪽위치(번호)})으로 옮기기", self)
            동작.triggered.connect(lambda _=False, n=번호: self.쪽으로옮기기(n))
            메뉴.addAction(동작)

        지우기 = QAction("이 영수증 목록에서 빼기", self)
        지우기.triggered.connect(lambda: self.영수증빼기(영))
        메뉴.addAction(지우기)

        if 영.후보:
            메뉴.addSeparator()
            머리 = QAction("영수증에서 읽어낸 숫자", self)
            머리.setEnabled(False)
            메뉴.addAction(머리)
            for 후보 in 영.후보[:12]:
                동작 = QAction(f"{후보:,}원", self)
                동작.triggered.connect(
                    lambda _=False, v=후보, w=위젯: self.후보선택(w, v))
                메뉴.addAction(동작)

        if not 메뉴.isEmpty():
            메뉴.exec(self.표.viewport().mapToGlobal(위치))

    def 후보선택(self, 위젯, 금액):
        self.표.blockSignals(True)
        위젯.setText(열_금액, f"{금액:,}")
        self.표.blockSignals(False)
        self.값바뀜(위젯, 열_금액)

    def 영수증빼기(self, 영):
        for s in self.항목들:
            if 영 in s.영수증들:
                s.영수증들.remove(영)
        self.항목들 = [s for s in self.항목들 if s.영수증들]
        self.표채우기()
        self.statusBar().showMessage(f"'{영.이름}'을 목록에서 뺐습니다. 파일은 지워지지 않습니다.")

    # ── 붙여넣기 ────────────────────────────────────────────────
    def 클립보드에서넣기(self):
        """화면 캡처나 복사한 이미지를 그대로 영수증으로 넣는다."""
        그림 = QApplication.clipboard().image()
        if 그림.isNull():
            QMessageBox.information(
                self, "붙여넣을 이미지가 없습니다",
                "카드사 앱이나 화면을 캡처해 복사한 뒤 다시 눌러 주세요.\n"
                "(캡처 도구: 윈도우 키 + Shift + S)")
            return

        if not self.영수증폴더:                  # 폴더를 안 열었어도 붙여넣기만으로 쓸 수 있게
            self.영수증폴더 = Path(tempfile.mkdtemp(prefix="영수증_"))
            self.statusBar().showMessage(f"임시 폴더를 만들었습니다: {self.영수증폴더}")

        저장폴더 = self.영수증폴더 / "붙여넣은영수증"
        저장폴더.mkdir(parents=True, exist_ok=True)
        경로 = 저장폴더 / f"붙여넣기_{datetime.now():%m%d_%H%M%S}.png"
        if not 그림.save(str(경로)):
            QMessageBox.critical(self, "저장하지 못했습니다", f"{경로} 에 쓸 수 없습니다.")
            return

        self.setEnabled(False)
        self.statusBar().showMessage("붙여넣은 이미지를 읽는 중…")
        QApplication.processEvents()
        try:
            읽음 = 판독기.판독(경로, self.영수증폴더 / "_작업")
        except Exception as e:
            self.setEnabled(True)
            QMessageBox.critical(self, "읽지 못했습니다", f"{type(e).__name__}: {e}")
            return
        self.setEnabled(True)

        새것 = 영수증(경로=경로, 금액=읽음["금액"], 날짜=읽음["날짜"],
                  확인필요=읽음["확인필요"], 후보=읽음["후보"], 근거=읽음["근거"])

        대상 = None                              # 고른 섹션이 있으면 그 안에 넣는다
        고른것 = self.표.selectedItems()
        if 고른것:
            데이터 = 고른것[0].data(0, Qt.UserRole)
            if 데이터:
                대상 = 데이터[1] if 데이터[0] == "섹션" else self._섹션찾기(데이터[1])
        if 대상 is None:
            대상 = self.항목들[0] if self.항목들 else None
        if 대상 is None:
            대상 = 섹션(설명="붙여넣은 영수증")
            self.항목들.append(대상)
        대상.영수증들.append(새것)

        self.표채우기()
        번호 = self._결의서().섹션번호(새것)
        어디 = f"{번호}쪽({쪽위치(번호)})" if 번호 else "새 쪽"
        self.statusBar().showMessage(
            f"붙여넣었습니다 — {새것.금액:,}원 ({읽음['근거']}). {어디}에 넣었습니다. "
            "금액을 확인해 주세요.")

    def _섹션찾기(self, 영):
        for s in self.항목들:
            if 영 in s.영수증들:
                return s
        return None

    # ── 문서 만들기 ──────────────────────────────────────────────
    def 문서만들기(self):
        결 = self._결의서()
        문제 = 검산(결)
        if 문제:
            QMessageBox.warning(
                self, "아직 문서를 만들 수 없습니다",
                "다음을 먼저 정리해 주세요.\n\n• " + "\n• ".join(문제[:12]))
            return
        기본이름 = f"{date.today():%Y-%m-%d}_지출결의서증빙.docx"
        고른곳, _ = QFileDialog.getSaveFileName(self, "저장 위치", 기본이름, "워드 문서 (*.docx)")
        if not 고른곳:
            return
        작업폴더 = (self.영수증폴더 or Path(tempfile.gettempdir())) / "_작업"
        try:
            나온것 = 파이프라인.문서만들기([결], Path(고른곳), 작업폴더)
        except Exception as e:
            QMessageBox.critical(self, "문서를 만들지 못했습니다", f"{type(e).__name__}: {e}")
            return

        답 = QMessageBox.question(
            self, "완성했습니다",
            f"{나온것}\n\n총 {결.총금액:,}원 / {결.매수}매로 만들었습니다.\n\n"
            "지금 열어서 확인해 보시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if 답 == QMessageBox.Yes:
            try:
                os.startfile(str(나온것))
            except Exception as e:
                QMessageBox.warning(
                    self, "열지 못했습니다",
                    f"파일은 만들어졌습니다. 직접 열어 주세요.\n{나온것}\n\n{e}")
        self.statusBar().showMessage(f"만들었습니다 — {나온것}")
