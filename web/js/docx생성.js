// 결의서 데이터로 워드 문서를 만든다 — src/core/문서생성.py 를 브라우저로 옮긴 것.
//
// 파이썬 쪽은 python-docx 가 zip·관계파일·그림 XML 을 대신 처리해 준다.
// 브라우저에는 그런 라이브러리가 없으므로 여기서 직접 만든다.
//   · 표 복제·행열 조작 → DOM 조작 (python-docx 의 lxml 자리)
//   · 그림 삽입        → word/media 에 바이트 추가 + 관계 등록 + drawing XML 조립
//
// 원본 표를 복제해 쓰므로 테두리·글꼴·정렬이 저절로 보존된다. 이 점은 파이썬과 같다.

import { 쪽당섹션수 } from "./모델.js";

const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const CT = "http://schemas.openxmlformats.org/package/2006/content-types";

// ── 단위 ─────────────────────────────────────────────────────────
// 워드는 길이를 여러 단위로 섞어 쓴다. EMU(그림), dxa=twip(표 폭·행 높이).
const mm당EMU = 36000;
const dxa당EMU = 635;
const mm = (x) => x * mm당EMU;
const mm를twip = (x) => Math.floor((x * mm당EMU) / dxa당EMU);

// ── 문서생성.py 와 같은 값 — 한쪽만 고치면 두 프로그램의 결과가 어긋난다 ──
const 셀여백 = mm(1.5);          // 이미지가 셀 테두리에 닿지 않도록
const 헤더행높이mm = 42.0;        // 항목 설명 행 — 설명이 길어 줄바꿈될 여지까지 감안한 여유값
const 대지높이_첫장mm = 198.0;    // 첫 장은 "지출결의서 증빙" 제목이 얹혀 세로 공간이 좁다
const 대지높이mm = 218.0;         // 둘째 장부터는 제목이 없어 영수증을 더 크게 넣을 수 있다
const 안전비율 = 0.92;            // 행 높이 여유
const 기본칸수 = 4;               // 중첩표는 늘 네 칸. 왼쪽 두 칸 / 오른쪽 두 칸으로 폭이 반반이 된다

// ── DOM 도우미 ───────────────────────────────────────────────────
// lxml 의 find/findall 은 **직계 자식**만, iter 는 후손 전부를 훑는다.
// 이 구분이 무너지면 중첩표의 행까지 딸려 와 표가 망가진다.

/** 직계 자식 중 이름이 맞는 것들 (lxml 의 findall) */
function 자식들(el, 이름) {
  return Array.from(el.children).filter(
    (c) => c.localName === 이름 && c.namespaceURI === W);
}

/** 직계 자식 하나 (lxml 의 find) */
function 자식(el, 이름) {
  return 자식들(el, 이름)[0] || null;
}

/** 후손 전부 (lxml 의 iter) */
function 후손들(el, 이름) {
  return Array.from(el.getElementsByTagNameNS(W, 이름));
}

function 새요소(doc, 이름, 속성 = {}) {
  const el = doc.createElementNS(W, "w:" + 이름);
  for (const [k, v] of Object.entries(속성)) el.setAttributeNS(W, "w:" + k, v);
  return el;
}

/** 자식이 없으면 만들어서 돌려준다. 위치가 중요한 것은 앞쪽에 넣는다. */
function 자식보장(doc, 부모, 이름, 앞쪽 = false) {
  let el = 자식(부모, 이름);
  if (!el) {
    el = 새요소(doc, 이름);
    if (앞쪽) 부모.insertBefore(el, 부모.firstChild);
    else 부모.appendChild(el);
  }
  return el;
}

const tcPr보장 = (doc, tc) => 자식보장(doc, tc, "tcPr", true);

// ── 글쓰기 ───────────────────────────────────────────────────────

/** 셀의 문단을 하나만 남기고 지운다. 서식은 첫 문단 것을 유지. */
function 문단비우기(tc) {
  const ps = 자식들(tc, "p");
  for (const p of ps.slice(1)) tc.removeChild(p);
  const p = ps[0];
  for (const r of 자식들(p, "r")) p.removeChild(r);
  return p;
}

/** 문단에 글자 하나를 붙인다. 앞뒤 공백이 있으므로 xml:space 를 반드시 켠다. */
function 런추가(doc, p, 글) {
  const r = 새요소(doc, "r");
  const t = 새요소(doc, "t");
  t.setAttribute("xml:space", "preserve");
  t.appendChild(doc.createTextNode(String(글)));
  r.appendChild(t);
  p.appendChild(r);
  return r;
}

/** 셀에 여러 줄을 쓴다. 첫 문단의 서식을 복제해 이어붙인다. */
function 글쓰기(doc, tc, 줄들) {
  let 첫 = 문단비우기(tc);
  런추가(doc, 첫, 줄들[0]);
  for (const 줄 of 줄들.slice(1)) {
    const 새 = 첫.cloneNode(true);
    for (const r of 자식들(새, "r")) 새.removeChild(r);
    첫.parentNode.insertBefore(새, 첫.nextSibling);
    첫 = 새;
    런추가(doc, 첫, 줄);
  }
}

// ── 표 구조 ──────────────────────────────────────────────────────

/** 중첩표를 목표 열 수로 정규화한다. 셀 병합(gridSpan)을 풀고 폭을 균등 배분.
 *
 * gridSpan 을 남겨 두면 같은 칸이 두 번 잡혀 앞 내용이 덮어써진다.
 * 일단 전부 풀고, 필요한 병합은 `칸병합`으로 다시 만든다. */
function 열맞추기(doc, tbl, 목표열수, 전체폭_dxa) {
  const 그리드 = 자식(tbl, "tblGrid");

  // 1) 병합 해제 — 템플릿 헤더 행은 첫 칸이 2칸 병합되어 있다
  for (const tc of 후손들(tbl, "tc")) {
    const tcPr = 자식(tc, "tcPr");
    if (tcPr) {
      const gs = 자식(tcPr, "gridSpan");
      if (gs) tcPr.removeChild(gs);
    }
  }

  // 2) 모든 행의 칸 수를 목표에 맞춘다
  for (const tr of 자식들(tbl, "tr")) {
    let tcs = 자식들(tr, "tc");
    while (tcs.length > 목표열수) tr.removeChild(tcs.pop());
    while (tcs.length < 목표열수) {
      const 끝 = tcs[tcs.length - 1];
      끝.parentNode.insertBefore(끝.cloneNode(true), 끝.nextSibling);
      tcs = 자식들(tr, "tc");
    }
  }

  // 3) 그리드와 셀 폭을 균등 재배분
  const 칸폭 = Math.floor(전체폭_dxa / 목표열수);
  for (const gc of 자식들(그리드, "gridCol")) 그리드.removeChild(gc);
  for (let i = 0; i < 목표열수; i++) {
    그리드.appendChild(새요소(doc, "gridCol", { w: String(칸폭) }));
  }

  const tblW = 자식(자식(tbl, "tblPr"), "tblW");
  if (tblW) {
    tblW.setAttributeNS(W, "w:w", String(칸폭 * 목표열수));
    tblW.setAttributeNS(W, "w:type", "dxa");
  }

  for (const tr of 자식들(tbl, "tr")) {
    for (const tc of 자식들(tr, "tc")) {
      const tcW = 자식보장(doc, tcPr보장(doc, tc), "tcW");
      tcW.setAttributeNS(W, "w:w", String(칸폭));
      tcW.setAttributeNS(W, "w:type", "dxa");
    }
  }
}

function 행높이설정(doc, tr, 높이mm) {
  const th = 자식보장(doc, 자식보장(doc, tr, "trPr", true), "trHeight");
  th.setAttributeNS(W, "w:val", String(mm를twip(높이mm)));
  th.setAttributeNS(W, "w:hRule", "atLeast");
}

/** 이미지 행(2번째 행 이후) 개수를 맞춘다. 마지막 행을 복제해 늘린다. */
function 행맞추기(doc, tbl, 목표행수, 행높이mm) {
  let trs = 자식들(tbl, "tr");
  const 현재 = trs.length - 1;                    // 헤더 행 제외
  for (let i = 0; i < 목표행수 - 현재; i++) {
    tbl.appendChild(trs[trs.length - 1].cloneNode(true));
  }
  trs = 자식들(tbl, "tr");
  for (let i = 0; i < trs.length - 1 - 목표행수; i++) {
    tbl.removeChild(trs.pop());
  }
  for (const tr of 자식들(tbl, "tr").slice(1)) 행높이설정(doc, tr, 행높이mm);
}

/** 한 행의 칸들을 `칸폭들`대로 합친다. 합친 뒤 남은 칸 목록을 돌려준다.
 *
 * 예를 들어 왼쪽이 한 줄만 쓰면 [2, 2] 를 넘겨 네 칸을 두 칸으로 만든다.
 * 그래야 왼쪽·오른쪽 폭이 정확히 반반이 된다. */
function 칸병합(doc, tr, 칸폭들, 한칸_dxa) {
  const tcs = 자식들(tr, "tc");
  let 자리 = 0;
  const 남은 = [];
  for (const 폭 of 칸폭들) {
    if (자리 >= tcs.length) break;
    const tc = tcs[자리];
    const tcPr = tcPr보장(doc, tc);
    if (폭 > 1) {
      for (let j = 자리 + 1; j < Math.min(자리 + 폭, tcs.length); j++) {
        tr.removeChild(tcs[j]);                   // 합쳐지는 칸은 없앤다
      }
      let gs = 자식(tcPr, "gridSpan");
      if (!gs) {
        gs = 새요소(doc, "gridSpan");
        tcPr.insertBefore(gs, tcPr.firstChild);
      }
      gs.setAttributeNS(W, "w:val", String(폭));
    }
    const tcW = 자식보장(doc, tcPr, "tcW");
    tcW.setAttributeNS(W, "w:w", String(한칸_dxa * 폭));
    tcW.setAttributeNS(W, "w:type", "dxa");
    남은.push(tc);
    자리 += 폭;
  }
  return 남은;
}

/** 칸 오른쪽에 굵은 세로선을 그어 왼쪽·오른쪽 경계를 분명히 한다. */
function 가운데선(doc, tc, 굵기 = 18) {
  const 선들 = 자식보장(doc, tcPr보장(doc, tc), "tcBorders");
  const 오른 = 자식보장(doc, 선들, "right");
  오른.setAttributeNS(W, "w:val", "single");
  오른.setAttributeNS(W, "w:sz", String(굵기));   // 1/8 pt 단위. 18 = 2.25pt
  오른.setAttributeNS(W, "w:space", "0");
  오른.setAttributeNS(W, "w:color", "000000");
}

// ── 그림 삽입 ────────────────────────────────────────────────────
// python-docx 의 add_picture 가 해 주던 일을 손으로 한다.
//   ① word/media 에 바이트를 넣고
//   ② document.xml.rels 에 관계를 등록해 rId 를 얻고
//   ③ 그 rId 를 가리키는 drawing XML 을 문단에 넣는다
// 셋 중 하나라도 빠지면 워드가 "읽을 수 없는 내용"이라며 파일을 거부한다.

class 그림창고 {
  constructor(rels문서) {
    this.rels = rels문서;
    this.파일들 = new Map();       // zip 경로 → 바이트
    this.번호 = 0;
    // 이미 쓰이는 rId 와 겹치지 않게 가장 큰 번호부터 이어 붙인다
    this.다음rId = 1 + Math.max(0, ...Array.from(
      rels문서.documentElement.children,
      (el) => parseInt((el.getAttribute("Id") || "").replace(/\D/g, ""), 10) || 0));
  }

  /** 바이트를 등록하고 rId 를 돌려준다. */
  등록(바이트, 확장자) {
    const 이름 = `image${++this.번호}.${확장자}`;   // 워드 규격상 파트 이름은 ASCII 로 둔다
    this.파일들.set(`word/media/${이름}`, 바이트);
    const id = `rId${this.다음rId++}`;
    const rel = this.rels.createElementNS(
      "http://schemas.openxmlformats.org/package/2006/relationships", "Relationship");
    rel.setAttribute("Id", id);
    rel.setAttribute("Type", `${R}/image`);
    rel.setAttribute("Target", `media/${이름}`);
    this.rels.documentElement.appendChild(rel);
    return id;
  }
}

/** 비율을 유지하며 주어진 크기 안에 들어가도록 그림을 넣는다. */
function 그림넣기(doc, 창고, 문단, 영, 최대폭EMU, 최대높이EMU) {
  const 배율 = Math.min(최대폭EMU / 영.폭, 최대높이EMU / 영.높이);
  const cx = Math.floor(영.폭 * 배율);
  const cy = Math.floor(영.높이 * 배율);
  const 확장자 = 영.이름.toLowerCase().endsWith(".png") ? "png" : "jpg";
  const rId = 창고.등록(영.자료, 확장자);
  const n = 창고.번호;

  // 문단 여백이 붙으면 칸을 넘친다 — 파이썬 쪽에서 겪은 문제라 여기서도 0으로 못박는다
  const pPr = 자식보장(doc, 문단, "pPr", true);
  자식보장(doc, pPr, "jc").setAttributeNS(W, "w:val", "center");
  const 간격 = 자식보장(doc, pPr, "spacing");
  간격.setAttributeNS(W, "w:before", "0");
  간격.setAttributeNS(W, "w:after", "0");

  const 조각 = `<w:r xmlns:w="${W}"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
      xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
      xmlns:r="${R}">
    <w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
      <wp:extent cx="${cx}" cy="${cy}"/>
      <wp:docPr id="${n}" name="영수증 ${n}"/>
      <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:pic>
          <pic:nvPicPr><pic:cNvPr id="${n}" name="영수증 ${n}"/><pic:cNvPicPr/></pic:nvPicPr>
          <pic:blipFill><a:blip r:embed="${rId}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
          <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
        </pic:pic>
      </a:graphicData></a:graphic>
    </wp:inline></w:drawing></w:r>`;
  const 조각문서 = new DOMParser().parseFromString(조각, "application/xml");
  문단.appendChild(doc.importNode(조각문서.documentElement, true));
}

// ── 채우기 ───────────────────────────────────────────────────────

function 채우기(doc, 창고, tbl, 결, 첫장) {
  const 행 = (i) => 자식들(tbl, "tr")[i];
  const 칸 = (i, j) => 자식들(행(i), "tc")[j];

  글쓰기(doc, 칸(0, 1), [`${결.부서명}  /  ${결.날짜}`]);
  글쓰기(doc, 칸(1, 1), [`${결.매수}매 /  \\${결.총금액.toLocaleString()}`]);
  글쓰기(doc, 칸(2, 1), [`( 지출인 : ${결.지출인} )`]);

  const 대지 = 첫장 ? 대지높이_첫장mm : 대지높이mm;
  행높이설정(doc, 행(3), 대지);
  const 안표 = 후손들(칸(3, 0), "tbl")[0];
  const 전체폭 = parseInt(자식(자식(안표, "tblPr"), "tblW").getAttributeNS(W, "w"), 10);

  const 쪽들 = 결.항목들.slice(0, 쪽당섹션수);     // 한 장에는 왼쪽·오른쪽 두 쪽만
  const 행수 = Math.max(1, ...쪽들.map((s) => s.세로칸수()));

  // 표를 늘 네 칸으로 만들어 둔다. 왼쪽 두 칸 / 오른쪽 두 칸으로 폭이 정확히 반반이 된다.
  열맞추기(doc, 안표, 기본칸수, 전체폭);
  const 한칸 = Math.floor(전체폭 / 기본칸수);
  const 행높이 = ((대지 - 헤더행높이mm) / 행수) * 안전비율;
  행맞추기(doc, 안표, 행수, 행높이);

  // 어느 칸이 어느 쪽의 몇 번째 줄인지 미리 정해 둔다
  let 폭들 = [];
  let 소속 = [];
  쪽들.forEach((s, 쪽번호) => {
    if (s.가로칸수() === 1) {          // 한 줄만 쓰면 두 칸을 합쳐 반쪽을 다 쓴다
      폭들.push(2);
      소속.push([쪽번호, 0]);
    } else {
      폭들.push(1, 1);
      소속.push([쪽번호, 0], [쪽번호, 1]);
    }
  });
  if (!폭들.length) { 폭들 = [기본칸수]; 소속 = []; }

  // 설명 행 — 쪽마다 반쪽씩
  const 헤더칸들 = 칸병합(
    doc, 자식들(안표, "tr")[0], 쪽들.length ? Array(쪽들.length).fill(2) : [기본칸수], 한칸);
  헤더칸들.forEach((tc, i) => {
    if (i < 쪽들.length) {
      const s = 쪽들[i];
      글쓰기(doc, tc, [s.설명완성(), `${s.금액.toLocaleString()}원`]);
    } else {
      문단비우기(tc);
    }
  });
  if (쪽들.length > 1) 가운데선(doc, 헤더칸들[0]);   // 왼쪽 쪽 오른쪽에 굵은 경계선

  // 영수증 칸 — 각 쪽 안에서 위→아래로 먼저 채운 뒤 옆 줄로 넘어간다
  자식들(안표, "tr").slice(1).forEach((tr, r) => {
    const 칸들 = 칸병합(doc, tr, 폭들, 한칸);
    칸들.forEach((tc, k) => {
      if (k >= 소속.length) { 문단비우기(tc); return; }
      const [쪽번호, 줄] = 소속[k];
      const s = 쪽들[쪽번호];
      const 자리 = 줄 * s.세로칸수() + r;
      const p = 문단비우기(tc);
      if (자리 < s.매수) {
        const 칸폭 = 한칸 * 폭들[k] * dxa당EMU - 셀여백 * 2;
        그림넣기(doc, 창고, p, s.영수증들[자리], 칸폭, mm(행높이) - 셀여백);
      }
      if (쪽들.length > 1 && 쪽번호 === 0 &&
          (k + 1 >= 소속.length || 소속[k + 1][0] !== 0)) {
        가운데선(doc, tc);                  // 왼쪽 쪽의 마지막 칸에 경계선
      }
    });
  });
}

// ── 진입점 ───────────────────────────────────────────────────────

/** 결의서 여러 건을 한 문서로 만든다. 건마다 새 페이지.
 *
 * `템플릿바이트`는 양식/결의서_템플릿.docx 를 fetch 로 받아 온 ArrayBuffer.
 * 돌려주는 것은 내려받을 수 있는 Blob 이다. */
export async function 만들기(결의서들, 템플릿바이트) {
  const zip = await JSZip.loadAsync(템플릿바이트);
  const 파서 = new DOMParser();
  const 직렬 = new XMLSerializer();

  const doc = 파서.parseFromString(await zip.file("word/document.xml").async("string"),
                                  "application/xml");
  const relsPath = "word/_rels/document.xml.rels";
  const rels = 파서.parseFromString(await zip.file(relsPath).async("string"),
                                   "application/xml");
  const 창고 = new 그림창고(rels);

  const body = 후손들(doc.documentElement, "body")[0];
  const 표들 = [후손들(body, "tbl")[0]];

  // 결의서 건수만큼 표를 복제하고 사이에 쪽 나눔을 끼운다
  for (let i = 1; i < 결의서들.length; i++) {
    const 이전 = 표들[표들.length - 1];
    const 나눔 = 새요소(doc, "p");
    const r = 새요소(doc, "r");
    r.appendChild(새요소(doc, "br", { type: "page" }));
    나눔.appendChild(r);
    이전.parentNode.insertBefore(나눔, 이전.nextSibling);
    const 복제 = 이전.cloneNode(true);
    나눔.parentNode.insertBefore(복제, 나눔.nextSibling);
    표들.push(복제);
  }

  표들.forEach((tbl, n) => 채우기(doc, 창고, tbl, 결의서들[n], n === 0));

  // 그림 확장자가 [Content_Types].xml 에 없으면 워드가 파일을 열지 못한다
  const ctPath = "[Content_Types].xml";
  const ct = 파서.parseFromString(await zip.file(ctPath).async("string"), "application/xml");
  const 있는확장자 = new Set(Array.from(ct.documentElement.children)
    .filter((el) => el.localName === "Default")
    .map((el) => (el.getAttribute("Extension") || "").toLowerCase()));
  for (const [확장, 형식] of [["jpg", "image/jpeg"], ["jpeg", "image/jpeg"],
                              ["png", "image/png"]]) {
    if (!있는확장자.has(확장)) {
      const d = ct.createElementNS(CT, "Default");
      d.setAttribute("Extension", 확장);
      d.setAttribute("ContentType", 형식);
      ct.documentElement.insertBefore(d, ct.documentElement.firstChild);
    }
  }

  zip.file("word/document.xml", 직렬.serializeToString(doc));
  zip.file(relsPath, 직렬.serializeToString(rels));
  zip.file(ctPath, 직렬.serializeToString(ct));
  for (const [경로, 바이트] of 창고.파일들) zip.file(경로, 바이트);

  return zip.generateAsync({
    type: "blob",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    compression: "DEFLATE",
  });
}
