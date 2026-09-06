// 영수증에서 금액과 날짜를 읽어낸다 — src/core/영수증판독.py 를 브라우저로 옮긴 것.
//
// 윈도우판은 운영체제에 딸린 OCR 을 쓰지만 그것은 브라우저에 없다. 대신 Tesseract 를
// WebAssembly 로 돌린다. 실제 영수증 12장으로 두 엔진을 견줘 본 결과 금액 11/12,
// 날짜 11/12 로 대등했다(psm 4 기준).
//
// OCR 이 글자를 읽어 준 다음이 진짜 문제다. 영수증 한 장에는 단가·수량·공급가액·
// 부가세·합계·받은돈·거스름돈·카드번호·승인번호가 뒤섞여 있고, 그중 어느 것이
// 총액인지 OCR 은 모른다. 아래 규칙이 그것을 고른다.

// ── 총액을 가리키는 말. 앞쪽일수록 우선 ──────────────────────────────
const 키워드 = ["이용금액합계", "결제대상금액", "결제금액", "청구액", "합계", "총액",
                "받을금액", "판매금액", "승인금액"];
// 총액이 아닌 것이 확실한 줄
const 제외키워드 = ["부가세", "과세", "면세", "봉사료", "보증금", "단가", "포인트",
                    "적립", "잔여", "거스름", "받은금액", "공급가", "행사"];

// 콤마 뒤 공백까지 허용 (OCR이 "15,000"을 "15, 000"으로 읽는다).
// 점(.)은 허용하지 않는다 — 날짜 2026.08.27을 금액으로 오인하기 때문.
// 실측에서 점을 콤마로 고쳐 읽게 했더니 정확도가 92%에서 83%로 떨어졌다.
const 금액패턴 = /\d{1,3}(?:\s*,\s*\d{3})+|\d+(?=\s*원)/g;
// OCR은 날짜 구분자를 흘리거나(2026.082718:32) 엉뚱한 문자로 읽는다(2026~08~27).
const 날짜패턴 = /(20\d{2})[.\-/~_,]?\s?(\d{1,2})[.\-/~_,]?\s?(\d{1,2})/g;

function 금액들(줄) {
  const 값 = [];
  for (const m of 줄.matchAll(금액패턴)) {
    const v = parseInt(m[0].replace(/[,\s]/g, ""), 10);
    if (v >= 100 && v <= 50_000_000) 값.push(v);
  }
  return 값;
}

/** n 개를 골라내는 조합. 파이썬 itertools.combinations 자리. */
function 조합들(것들, n) {
  if (n === 0) return [[]];
  const 답 = [];
  for (let i = 0; i <= 것들.length - n; i++) {
    for (const 뒤 of 조합들(것들.slice(i + 1), n - 1)) 답.push([것들[i], ...뒤]);
  }
  return 답;
}

/** 공급가액+부가세=합계 구조를 찾는다. 항이 많은 조합이 더 믿을 만하다.
 *
 * 키워드를 못 읽었을 때 쓰는 두 번째 수단이다. 영수증에 적힌 숫자들끼리
 * 실제로 덧셈이 맞아떨어지면 그 합이 총액일 가능성이 높다. */
function 검산조합(후보) {
  let 집합 = [...new Set(후보)].sort((a, b) => a - b);
  if (집합.length > 14) 집합 = 집합.slice(-14);   // 조합 폭발 방지
  const 있음 = new Set(집합);
  const 찾음 = [];
  for (const n of [3, 2]) {
    for (const c of 조합들(집합, n)) {
      const s = c.reduce((a, b) => a + b, 0);
      if (있음.has(s) && s > Math.max(...c)) 찾음.push([n, s]);
    }
  }
  return 찾음;
}

/** 읽어낸 글에서 총액을 고른다. {금액, 근거, 후보, 확신} 을 돌려준다. */
export function 총액고르기(텍스트) {
  const 줄들 = 텍스트.split("\n").map((l) => l.trim()).filter(Boolean);
  const 정규 = 줄들.map((l) => l.replace(/\s+/g, ""));
  const 후보 = 줄들.flatMap(금액들);

  for (const kw of 키워드) {
    for (let i = 0; i < 정규.length; i++) {
      if (!정규[i].includes(kw) || 제외키워드.some((x) => 정규[i].includes(x))) continue;
      const vals = 금액들(줄들[i]);
      if (vals.length) return { 금액: Math.max(...vals), 근거: `'${kw}'`, 후보, 확신: true };
      for (const j of [i + 1, i + 2]) {   // 라벨과 금액이 다른 줄에 있는 전표 형식
        if (j < 줄들.length && !제외키워드.some((x) => 정규[j].includes(x))) {
          const v2 = 금액들(줄들[j]);
          if (v2.length) {
            return { 금액: Math.max(...v2), 근거: `'${kw}' 아래`, 후보, 확신: true };
          }
        }
      }
    }
  }

  const 찾음 = 검산조합(후보);
  if (찾음.length) {
    const 항 = Math.max(...찾음.map(([n]) => n));
    const 값 = Math.max(...찾음.filter(([n]) => n === 항).map(([, s]) => s));
    return { 금액: 값, 근거: `검산(${항}항)`, 후보, 확신: true };
  }

  if (후보.length) {
    // 확신이 없다 — 사람이 확인해야 한다
    return { 금액: Math.max(...후보), 근거: "가장 큰 금액", 후보, 확신: false };
  }
  return { 금액: 0, 근거: "금액을 찾지 못함", 후보, 확신: false };
}

/** 영수증에서 거래일을 찾아 'MMDD' 형태로 돌려준다. */
export function 날짜고르기(텍스트, 올해 = new Date().getFullYear()) {
  const 찾은 = [];
  for (const [, y, m, d] of 텍스트.matchAll(날짜패턴)) {
    const [Y, M, D] = [+y, +m, +d];
    if (M >= 1 && M <= 12 && D >= 1 && D <= 31 && Y >= 올해 - 2 && Y <= 올해 + 1) {
      찾은.push([Y, M, D]);
    }
  }
  if (!찾은.length) return "";
  찾은.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  const [, m, d] = 찾은[0];                 // 여러 개면 가장 이른 날짜(거래일)
  return String(m).padStart(2, "0") + String(d).padStart(2, "0");
}

// ── OCR 엔진 ─────────────────────────────────────────────────────────
// 학습 데이터가 12MB 라 처음 한 번은 내려받는 데 시간이 걸린다. 그 뒤로는
// 브라우저가 캐시해 두므로 빠르다. 일꾼(worker)도 한 번만 만들어 돌려 쓴다.

let _일꾼 = null;
let _준비중 = null;

export function 준비됐나() {
  return _일꾼 !== null;
}

export async function 엔진준비(알림 = () => {}) {
  if (_일꾼) return _일꾼;
  if (_준비중) return _준비중;

  _준비중 = (async () => {
    const 뿌리 = new URL("../vendor/", import.meta.url).href;
    const 일꾼 = await Tesseract.createWorker("kor+eng", 1, {
      workerPath: 뿌리 + "tesseract-worker.min.js",
      corePath: 뿌리 + "tesseract-core-simd.wasm.js",
      langPath: 뿌리 + "학습데이터",
      gzip: true,
      logger: (m) => {
        if (m.status && m.progress != null) {
          알림(`${말로(m.status)} ${Math.round(m.progress * 100)}%`);
        }
      },
    });
    // psm 4 = '한 단(段)으로 본다'. 실측에서 세 가지 중 가장 잘 읽었다.
    await 일꾼.setParameters({ tessedit_pageseg_mode: "4" });
    _일꾼 = 일꾼;
    _준비중 = null;
    return 일꾼;
  })();
  return _준비중;
}

function 말로(상태) {
  return {
    "loading tesseract core": "판독기 준비",
    "initializing tesseract": "판독기 시작",
    "loading language traineddata": "한국어 데이터 내려받기",
    "initializing api": "판독기 여는 중",
    "recognizing text": "글자 읽는 중",
  }[상태] || 상태;
}

/** 전처리된 캔버스 하나를 읽어 금액·날짜·후보를 돌려준다. */
export async function 판독(전처리된판, 알림) {
  const 일꾼 = await 엔진준비(알림);
  const { data } = await 일꾼.recognize(전처리된판);
  const 글 = data.text || "";
  const { 금액, 근거, 후보, 확신 } = 총액고르기(글);
  return {
    금액,
    날짜: 날짜고르기(글),
    후보: [...new Set(후보)].sort((a, b) => b - a),
    근거,
    확인필요: !확신,
    원문: 글,
  };
}

export async function 엔진정리() {
  if (_일꾼) {
    await _일꾼.terminate();
    _일꾼 = null;
  }
}
