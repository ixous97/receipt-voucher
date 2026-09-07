// 내부용 문 — 공유 비밀번호를 아는 사람만 들어온다.
//
// Vercel 의 Password Protection 은 Enterprise 이거나 Pro 위에 월 $150 애드온이다.
// 그 기능의 실체가 '공유 비밀번호 게이트'라서 같은 일을 여기서 직접 한다.
// Hobby 무료 한도(월 100만 호출) 안이고 우리 트래픽은 월 수백 건이다.
//
// **비밀번호는 저장소에 두지 않는다.** 저장소가 공개(github.com/ixous97/receipt-voucher)라
// 환경변수 WEBAPP_PASSWORD 에서만 읽는다. 키가 영문인 것은 Vercel 이 ASCII 만 받기 때문이다.
import { next } from '@vercel/functions';

// **realm 은 반드시 ASCII 여야 한다.** HTTP 헤더 값은 latin-1(ByteString)이라
// 한글을 넣으면 Response 생성 단계에서 TypeError 로 죽는다 — 실제로 겪었다.
// 본문은 UTF-8 이라 한글을 써도 된다.
const 영역 = 'WJM (internal)';

// 길이가 같을 때는 끝까지 돈다. 응답 시간으로 한 글자씩 더듬는 것을 막는다.
function 같은가(가, 나) {
  if (가.length !== 나.length) return false;
  let 다름 = 0;
  for (let i = 0; i < 가.length; i++) 다름 |= 가.charCodeAt(i) ^ 나.charCodeAt(i);
  return 다름 === 0;
}

function 막기(말, 물어보기) {
  return new Response(말 + '\n', {
    status: 401,
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      ...(물어보기 ? { 'www-authenticate': `Basic realm="${영역}", charset="UTF-8"` } : {}),
    },
  });
}

export default function middleware(요청) {
  const 정답 = process.env.WEBAPP_PASSWORD;
  // 비밀번호를 설정하지 않았으면 열어 두지 않고 막는다 — 빠뜨려서 공개되는 편이 더 나쁘다.
  if (!정답) return 막기('비밀번호가 설정되지 않았습니다. 관리자에게 알려 주세요.', false);

  const 머리 = 요청.headers.get('authorization') || '';
  if (머리.startsWith('Basic ')) {
    // atob 는 바이트만 돌려준다. 한글 비밀번호도 되도록 UTF-8 로 풀어 준다.
    const 바이트 = Uint8Array.from(atob(머리.slice(6)), (글) => 글.charCodeAt(0));
    const 풀린것 = new TextDecoder().decode(바이트);
    const 비밀번호 = 풀린것.slice(풀린것.indexOf(':') + 1);
    if (같은가(비밀번호, 정답)) return next();   // ← 통과. 정적 파일로 넘어간다
  }
  return 막기('아이디에는 wjm, 비밀번호는 담당자에게 받은 값을 넣으세요.', true);
}

// 모든 경로를 막는다. 호출이 늘지만 월 수백 건이라 무료 한도의 0.1% 도 안 된다.
// edge 런타임은 Vercel 이 사용 중단을 권고한다(빌드 때 경고가 뜬다).
export const config = { matcher: '/(.*)', runtime: 'nodejs' };
