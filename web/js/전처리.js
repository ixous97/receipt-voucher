// 영수증 이미지를 다듬는다 — src/core/이미지정리.py 를 캔버스로 옮긴 것.
//
// 판독 정확도는 OCR 엔진보다 **전처리**가 더 크게 좌우한다. 실측에서 이 처리를
// 넣고 빼는 것만으로 67% ↔ 83% 가 갈렸다. 그래서 파이썬 쪽 순서와 계수를
// 그대로 지킨다 — 키우고, 회색으로 바꾸고, 대비를 늘리고, 윤곽을 세운다.

/** 워드에 넣을 JPEG. EXIF 회전을 반영하고 크기를 줄여 파일을 가볍게 한다. */
export async function 정규화(원본Blob, 긴변 = 1600) {
  const 그림 = await createImageBitmap(원본Blob, { imageOrientation: "from-image" });
  const 배율 = Math.max(그림.width, 그림.height) > 긴변
    ? 긴변 / Math.max(그림.width, 그림.height) : 1;
  const 판 = 그리기(그림, Math.round(그림.width * 배율), Math.round(그림.height * 배율));
  그림.close();
  const blob = await new Promise((해결) =>
    판.toBlob(해결, "image/jpeg", 0.88));
  return { blob, 폭: 판.width, 높이: 판.height };
}

/** OCR 정확도를 높이기 위한 전처리. */
export async function 전처리(원본Blob, 목표긴변 = 2400) {
  const 그림 = await createImageBitmap(원본Blob, { imageOrientation: "from-image" });
  const 긴 = Math.max(그림.width, 그림.height);
  let 배율 = 1;
  if (긴 < 목표긴변) 배율 = 목표긴변 / 긴;      // 작은 사진은 키워야 글자를 읽는다
  else if (긴 > 4000) 배율 = 4000 / 긴;         // 너무 크면 느리기만 하다

  const 판 = 그리기(그림, Math.round(그림.width * 배율), Math.round(그림.height * 배율));
  그림.close();

  const ctx = 판.getContext("2d", { willReadFrequently: true });
  const 자료 = ctx.getImageData(0, 0, 판.width, 판.height);
  회색으로(자료);
  자동대비(자료, 2);
  const 흐린 = await 흐리게(판, 자료, 2);
  윤곽세우기(자료, 흐린, 150, 3);
  ctx.putImageData(자료, 0, 0);
  return 판;
}

// ── 아래는 PIL 이 하던 계산을 그대로 옮긴 것 ────────────────────────

function 그리기(그림, 폭, 높이) {
  const 판 = document.createElement("canvas");
  판.width = 폭;
  판.height = 높이;
  const ctx = 판.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(그림, 0, 0, 폭, 높이);
  return 판;
}

/** PIL 의 convert("L") 과 같은 계수. */
function 회색으로(자료) {
  const p = 자료.data;
  for (let i = 0; i < p.length; i += 4) {
    const v = (p[i] * 299 + p[i + 1] * 587 + p[i + 2] * 114) / 1000 | 0;
    p[i] = p[i + 1] = p[i + 2] = v;
  }
}

/** PIL 의 ImageOps.autocontrast(cutoff=n).
 *
 * 위아래 n% 를 잘라 낸 뒤 남은 범위를 0~255 로 늘린다. 감열지 사진처럼
 * 전체가 흐릿한 회색일 때 글자와 바탕을 갈라 준다. */
function 자동대비(자료, 잘라낼퍼센트) {
  const p = 자료.data;
  const 히스토 = new Array(256).fill(0);
  for (let i = 0; i < p.length; i += 4) 히스토[p[i]]++;

  const 전체 = p.length / 4;
  let 몫 = (잘라낼퍼센트 * 전체) / 100;

  let 남은 = 몫;
  for (let i = 0; i < 256; i++) {           // 어두운 쪽부터 깎는다
    if (남은 > 히스토[i]) { 남은 -= 히스토[i]; 히스토[i] = 0; }
    else { 히스토[i] -= 남은; break; }
  }
  남은 = 몫;
  for (let i = 255; i >= 0; i--) {          // 밝은 쪽에서도 같은 만큼
    if (남은 > 히스토[i]) { 남은 -= 히스토[i]; 히스토[i] = 0; }
    else { 히스토[i] -= 남은; break; }
  }

  let lo = 0;
  while (lo < 256 && 히스토[lo] === 0) lo++;
  let hi = 255;
  while (hi >= 0 && 히스토[hi] === 0) hi--;
  if (hi <= lo) return;                     // 단색 이미지 — 늘릴 것이 없다

  const 배 = 255 / (hi - lo);
  const 표 = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) 표[i] = Math.round((i - lo) * 배);
  for (let i = 0; i < p.length; i += 4) {
    const v = 표[p[i]];
    p[i] = p[i + 1] = p[i + 2] = v;
  }
}

/** 캔버스의 blur 필터를 빌려 가우시안 흐림을 얻는다.
 *
 * PIL 의 GaussianBlur 도, 브라우저의 blur() 도 상자흐림 세 번으로 근사하므로
 * 결과가 서로 가깝다. 직접 커널을 돌리는 것보다 훨씬 빠르기도 하다. */
async function 흐리게(원판, 자료, 반지름) {
  const 임시 = document.createElement("canvas");
  임시.width = 원판.width;
  임시.height = 원판.height;
  const ctx = 임시.getContext("2d", { willReadFrequently: true });
  // 회색조로 바꾼 결과를 흐려야 한다. 원본을 그대로 흐리면 색 정보가 섞인다.
  const 회색판 = document.createElement("canvas");
  회색판.width = 원판.width;
  회색판.height = 원판.height;
  회색판.getContext("2d").putImageData(자료, 0, 0);
  ctx.filter = `blur(${반지름}px)`;
  ctx.drawImage(회색판, 0, 0);
  return ctx.getImageData(0, 0, 임시.width, 임시.height);
}

/** PIL 의 UnsharpMask(radius, percent, threshold).
 *
 * 원본과 흐린 것의 차이가 threshold 를 넘을 때만 그 차이를 percent 만큼 더한다.
 * 문턱을 두는 덕에 종이 결 같은 잔 노이즈는 건드리지 않고 글자 획만 살아난다. */
function 윤곽세우기(자료, 흐린, 퍼센트, 문턱) {
  const p = 자료.data;
  const b = 흐린.data;
  for (let i = 0; i < p.length; i += 4) {
    const 차 = p[i] - b[i];
    if (Math.abs(차) > 문턱) {
      const v = p[i] + (차 * 퍼센트) / 100;
      const c = v < 0 ? 0 : v > 255 ? 255 : v | 0;
      p[i] = p[i + 1] = p[i + 2] = c;
    }
  }
}
