// 화면과 각 조각을 잇는다 — src/ui/메인창.py 가 하던 일.
//
// 이 프로그램은 회계 문서를 만든다. 그래서 자동 판독을 **초안**으로만 쓰고,
// 사람이 금액을 하나하나 확인하기 전에는 문서를 만들지 못하게 막는다.
// 창을 다루는 방식은 웹에 맞게 바꿨지만 그 원칙은 윈도우판과 같다.

import { 결의서, 섹션, 영수증, 검산, 장수, 페이지나누기,
         쪽위치, 섹션최대장수, 최대섹션수 } from "./모델.js";
import { 정규화, 전처리 } from "./전처리.js";
import { 판독, 준비됐나 } from "./판독.js";
import { 만들기 } from "./docx생성.js";

const 결 = new 결의서();
let 고른것 = null;          // 지금 선택된 영수증
let 읽는중 = false;

const 요소 = (id) => document.getElementById(id);
const 몸 = 요소("몸");
const 알림 = (말) => { 요소("알림").textContent = 말; };

// ── 처음 화면 ────────────────────────────────────────────────────

{
  const 오늘 = new Date();
  요소("날짜").value =
    `${오늘.getFullYear()}-${String(오늘.getMonth() + 1).padStart(2, "0")}-` +
    `${String(오늘.getDate()).padStart(2, "0")}`;
}

function 날짜글() {
  const v = 요소("날짜").value;
  if (!v) return "";
  const [y, m, d] = v.split("-").map(Number);
  return `${y}년 ${m}월 ${d}일`;
}

// ── 영수증 들이기 ────────────────────────────────────────────────

/** 파일 여러 개를 받아 영수증으로 만든다. 워드에 넣을 JPEG 로 미리 줄여 둔다. */
async function 들이기(파일들) {
  const 것들 = [...파일들].filter((f) => f.type.startsWith("image/"));
  if (!것들.length) return;

  알림(`영수증 ${것들.length}장 준비 중…`);
  for (const f of 것들) {
    const { blob, 폭, 높이 } = await 정규화(f);
    const 영 = new 영수증({
      이름: f.name || `붙여넣은영수증${결.매수 + 1}.jpg`,
      자료: new Uint8Array(await blob.arrayBuffer()),
      폭, 높이,
    });
    영.미리보기 = URL.createObjectURL(blob);
    영.원본 = f;                       // 판독은 원본을 써야 글자가 덜 뭉개진다
    넣을자리에(영);
  }
  알림(`영수증 ${것들.length}장을 넣었습니다. [영수증 읽기]를 눌러 주세요.`);
  그리기();
}

/** 빈자리가 있는 첫 쪽에 넣는다. 한 쪽이 6장을 넘지 않게 한다. */
function 넣을자리에(영) {
  let 번호 = 1;
  while (번호 <= 최대섹션수) {
    const s = 결.항목들[번호 - 1];
    if (!s || s.매수 < 섹션최대장수) break;
    번호++;
  }
  if (번호 > 최대섹션수) {
    알림(`쪽이 모두 찼습니다. 최대 ${최대섹션수 * 섹션최대장수}장까지 넣을 수 있습니다.`);
    return;
  }
  while (결.항목들.length < 번호) 결.항목들.push(new 섹션());
  const s = 결.항목들[번호 - 1];
  if (!s.설명) s.설명 = (영.이름 || "").replace(/\.[^.]+$/, "");
  s.영수증들.push(영);
}

요소("파일고르기").onclick = () => 요소("파일입력").click();
요소("파일입력").onchange = (e) => { 들이기(e.target.files); e.target.value = ""; };

const 떨구는곳 = 요소("떨구는곳");
for (const 이름 of ["dragenter", "dragover"]) {
  떨구는곳.addEventListener(이름, (e) => {
    e.preventDefault(); 떨구는곳.classList.add("닿음");
  });
}
for (const 이름 of ["dragleave", "drop"]) {
  떨구는곳.addEventListener(이름, (e) => {
    e.preventDefault(); 떨구는곳.classList.remove("닿음");
  });
}
떨구는곳.addEventListener("drop", (e) => 들이기(e.dataTransfer.files));

// 카드사 앱 화면을 캡처해 바로 붙여넣는 길. 파일로 저장할 필요가 없어 가장 빠르다.
document.addEventListener("paste", (e) => {
  const 것들 = [...(e.clipboardData?.items || [])]
    .filter((i) => i.type.startsWith("image/"))
    .map((i) => i.getAsFile())
    .filter(Boolean);
  if (것들.length) { e.preventDefault(); 들이기(것들); }
});

// ── 표 그리기 ────────────────────────────────────────────────────

function 그리기() {
  몸.textContent = "";
  결.항목들.forEach((s, i) => {
    const 번호 = i + 1;

    const 머리 = 몸.insertRow();
    머리.className = "쪽머리";
    const c = 머리.insertCell();
    c.colSpan = 6;
    const 설명칸 = document.createElement("input");
    설명칸.value = s.설명완성();
    설명칸.style.width = "60%";
    설명칸.title = "설명 문구. 손대지 않으면 날짜와 건수가 자동으로 따라 바뀝니다.";
    설명칸.onchange = () => {
      s.설명 = 설명칸.value; s.직접입력 = true; 그리기();
    };
    c.append(`${번호}쪽 · ${쪽위치(번호)} · ${s.매수}/${섹션최대장수}장  `, 설명칸);
    const 합 = document.createElement("span");
    합.style.float = "right";
    합.textContent = `${s.금액.toLocaleString()}원`;
    c.append(합);

    for (const r of s.영수증들) {
      const tr = 몸.insertRow();
      if (r === 고른것) tr.className = "고른것";
      tr.onclick = () => 고르기(r);

      tr.insertCell().textContent = "  " + r.이름;

      const 금액칸 = 칸에입력(tr, r.금액 ? r.금액.toLocaleString() : "", "금액");
      금액칸.onchange = () => {
        const v = parseInt(금액칸.value.replace(/[^\d]/g, ""), 10);
        r.금액 = Number.isFinite(v) ? v : 0;
        r.확인필요 = false;              // 사람이 직접 고쳤으니 확인된 것으로 본다
        그리기();
      };
      // 판독이 총액을 잘못 골라도 정답은 대개 후보 안에 있다(실측 11/12).
      // 목록에서 고르게 해 두면 타자 없이 한 번에 고칠 수 있다.
      if (r.후보.length > 1) {
        const 목록 = document.createElement("datalist");
        목록.id = `후보${r.이름}`.replace(/\W/g, "_");
        for (const v of r.후보.slice(0, 12)) {
          const o = document.createElement("option");
          o.value = v.toLocaleString();
          목록.append(o);
        }
        금액칸.setAttribute("list", 목록.id);
        금액칸.after(목록);
        금액칸.title = "영수증에서 읽은 숫자 중에서 고를 수 있습니다";
      }

      tr.insertCell().textContent = r.날짜 || "";

      const 쪽칸 = 칸에입력(tr, String(번호));
      쪽칸.onchange = () => {
        const 탈 = parseInt(쪽칸.value, 10);
        const 안됨 = 결.섹션옮기기(r, 탈);
        if (안됨) alert(안됨);
        그리기();
      };

      const 확인칸 = tr.insertCell();
      const 단추 = document.createElement("button");
      단추.className = "확인단추 " + (r.확인필요 ? "경고" : "좋음");
      단추.textContent = r.확인필요 ? "⚠" : "확인됨";
      단추.title = r.확인필요
        ? "금액을 영수증과 대조한 뒤 눌러 주세요"
        : "다시 누르면 미확인으로 되돌립니다";
      단추.onclick = (e) => {
        e.stopPropagation();
        if (r.금액 <= 0) { alert("금액이 비어 있습니다. 먼저 금액을 넣어 주세요."); return; }
        r.확인필요 = !r.확인필요;
        그리기();
      };
      확인칸.append(단추);

      tr.insertCell().textContent = r.근거 || "";
    }
  });

  const 쪽수 = 결.매수 ? 장수(결) : 0;
  요소("합계").textContent =
    `영수증 ${결.매수}매 · ${결.총금액.toLocaleString()}원 · 문서 ${쪽수}장`;
  요소("읽기").disabled = !결.매수 || 읽는중;
  요소("만들기").disabled = !결.매수 || 읽는중;
  for (const id of ["앞으로", "뒤로", "빼기"]) 요소(id).disabled = !고른것;
  요소("떨구는곳").style.display = 결.매수 ? "none" : "";
  문제보이기();
}

function 칸에입력(tr, 값, 반) {
  const td = tr.insertCell();
  if (반) td.className = "수";
  const i = document.createElement("input");
  i.value = 값;
  if (반) i.className = 반;
  i.onclick = (e) => e.stopPropagation();
  td.append(i);
  return i;
}

function 고르기(r) {
  고른것 = r;
  const 칸 = 요소("미리보기칸");
  칸.textContent = "";
  const img = new Image();
  img.src = r.미리보기;
  const 이름 = document.createElement("div");
  이름.id = "미리보기이름";
  이름.textContent = `${r.이름}${r.금액 ? ` · ${r.금액.toLocaleString()}원` : ""}`;
  칸.append(img, 이름);
  그리기();
}

function 문제보이기() {
  const 칸 = 요소("문제들");
  const 문제 = 결.매수 ? 검산(가짜채운결의서()) : [];
  if (!문제.length) { 칸.style.display = "none"; return; }
  칸.style.display = "block";
  칸.innerHTML = "<b>아직 문서를 만들 수 없습니다</b><ul>" +
    문제.slice(0, 6).map((m) => `<li>${m}</li>`).join("") +
    (문제.length > 6 ? `<li>… 그 밖에 ${문제.length - 6}건</li>` : "") + "</ul>";
}

/** 검산은 지출인·날짜까지 본다. 화면 입력값을 넣은 사본으로 검사한다. */
function 가짜채운결의서() {
  결.부서명 = 요소("부서명").value;
  결.날짜 = 날짜글();
  결.지출인 = 요소("지출인").value;
  return 결;
}

for (const id of ["부서명", "날짜", "지출인"]) 요소(id).oninput = () => 문제보이기();

// ── 단추들 ───────────────────────────────────────────────────────

function 옮기기(더할값) {
  if (!고른것) return;
  const 지금 = 결.섹션번호(고른것);
  const 안됨 = 결.섹션옮기기(고른것, 지금 + 더할값);
  if (안됨) alert(안됨);
  그리기();
}
요소("앞으로").onclick = () => 옮기기(-1);
요소("뒤로").onclick = () => 옮기기(+1);

요소("빼기").onclick = () => {
  if (!고른것) return;
  for (const s of 결.항목들) {
    const i = s.영수증들.indexOf(고른것);
    if (i >= 0) s.영수증들.splice(i, 1);
  }
  결.빈섹션정리();
  고른것 = null;
  요소("미리보기칸").innerHTML = '<div class="안내">영수증을 고르면 여기에 크게 보입니다</div>';
  그리기();
};

요소("읽기").onclick = async () => {
  읽는중 = true;
  그리기();
  const 것들 = 결.영수증들;
  if (!준비됐나()) {
    알림("판독기를 준비하는 중입니다. 처음 한 번은 한국어 데이터를 내려받느라 좀 걸립니다…");
  }
  for (let i = 0; i < 것들.length; i++) {
    const r = 것들[i];
    알림(`${i + 1}/${것들.length}  ${r.이름} 읽는 중…`);
    try {
      const 판 = await 전처리(r.원본 || new Blob([r.자료]));
      const 답 = await 판독(판, (말) => 알림(`${i + 1}/${것들.length}  ${말}`));
      Object.assign(r, {
        금액: 답.금액, 날짜: 답.날짜, 후보: 답.후보,
        근거: 답.근거, 확인필요: 답.확인필요,
      });
    } catch (e) {
      r.근거 = "읽지 못함";
      console.error(r.이름, e);
    }
    그리기();
  }
  읽는중 = false;
  const 남은 = 결.영수증들.filter((r) => r.확인필요).length;
  알림(남은
    ? `다 읽었습니다. ⚠ 표시 ${남은}건의 금액을 영수증과 대조해 주세요.`
    : "다 읽었습니다. 금액을 한 번씩 확인해 주세요.");
  그리기();
};

요소("만들기").onclick = async () => {
  const 문제 = 검산(가짜채운결의서());
  if (문제.length) {
    alert("아직 문서를 만들 수 없습니다.\n\n" + 문제.slice(0, 8).join("\n"));
    return;
  }
  알림("워드 문서를 만드는 중…");
  try {
    const 템플릿 = await (await fetch("양식/결의서_템플릿.docx")).arrayBuffer();
    const blob = await 만들기(페이지나누기(결), 템플릿);
    const 이름 = `${요소("날짜").value}_지출결의서증빙.docx`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = 이름;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    알림(`${이름} 을 내려받았습니다. 워드로 열어 확인해 주세요.`);
  } catch (e) {
    console.error(e);
    alert("문서를 만들지 못했습니다.\n" + e);
    알림("문서를 만들지 못했습니다.");
  }
};

그리기();
