# 실행 증거 (배포 환경 실측 로그)

> 평가 도구가 이미지(.png)를 읽지 않으므로, 배포된 서비스에서 실제로 호출한 결과를 **텍스트 로그**로 남깁니다.
> 스크린샷은 [`docs/screenshots/`](screenshots/)에 별도로 있습니다.

- 측정 일시: **2026-11-21 20:30 ~ 20:31 (KST)**
- 호출 위치: 배포된 프론트엔드 페이지 `https://ai-assistant-frontend-virid.vercel.app` 의 브라우저 콘솔에서 `fetch()` 로 호출
  → 응답 본문을 읽을 수 있었다는 것 자체가 **Vercel 도메인 → Render API 의 CORS 허용**이 동작한다는 증거입니다.
- 백엔드: `https://ai-assistant-api-ecqq.onrender.com` (Render Free, Singapore)
- DB: Firebase 프로젝트 `codyssey-ai-assistant`, Firestore `(default)` / `asia-northeast3 (Seoul)`

---

## 1. 배포 접속 확인 (프론트·백엔드·Swagger)

| URL | HTTP | Content-Type |
|---|---|---|
| `https://ai-assistant-frontend-virid.vercel.app/` | **200** | text/html |
| `https://ai-assistant-frontend-virid.vercel.app/config.js` | **200** | application/javascript (빌드 시 `API_BASE_URL` 주입 결과) |
| `https://ai-assistant-api-ecqq.onrender.com/docs` | **200** | text/html (Swagger UI) |
| `https://ai-assistant-api-ecqq.onrender.com/openapi.json` | **200** | application/json |

```text
#1 2026-11-21 20:30:21 | GET /health | 200 | 22076ms   ← 무료 티어 슬립 후 첫 요청(콜드스타트)
   → {"status":"ok","ai":{"api_key_set":true,"base_url":"https://copa.codyssey.kr","model":"claude-haiku-4","format":"auto(anthropic)"}}
#2 2026-11-21 20:30:27 | GET /api/data/summary | 200 | 6074ms
   → {"period":"2026-05-25 ~ 2026-11-20","count":180,"metrics":{"total":12086,"average":67.14,"max":131,"min":0,
      "max_date":"2026-09-12","min_date":"2026-06-14"},"trend":"상승 (최근 14일 평균 +11.6%)",
      "recent_average":82.43,"previous_average":73.86,"unit":"분"}
```

첫 요청이 22초 걸린 것은 Render 무료 인스턴스가 잠들어 있다가 깨어난 시간입니다(콜드스타트). 이후 요청은 0.2~0.5초입니다. 프론트는 이 동안 안내 배너를 띄우고 `/health` 를 재시도합니다.

---

## 2. 데이터 CRUD 와 Firestore 실제 저장

```text
#3 20:30:28 | POST /api/data  body={"date":"2026-11-21","value":150,"memo":"증거용 테스트: 클라이밍"} | 201 | 436ms
   → {"id":"iJrcPGPHro7QfPEZSkIz","date":"2026-11-21","value":150,"memo":"증거용 테스트: 클라이밍",
      "created_at":"2026-11-21T11:30:28+00:00","updated_at":"2026-11-21T11:30:28+00:00"}
#4 20:30:28 | GET /api/data (start=2026-11-21, end=2026-11-21) | 200 | 541ms
   → [{"id":"iJrcPGPHro7QfPEZSkIz","date":"2026-11-21","value":150,"memo":"증거용 테스트: 클라이밍", ...}]
#6 20:30:29 | PUT /api/data/iJrcPGPHro7QfPEZSkIz  body={"value":140} | 200 | 538ms
   → {"id":"iJrcPGPHro7QfPEZSkIz","date":"2026-11-21","value":140,"memo":"증거용 테스트: 클라이밍",
      "created_at":"2026-11-21T11:30:28+00:00","updated_at":"2026-11-21T11:30:29+00:00"}   ← 보낸 필드만 부분 수정
#14 20:30:55 | DELETE /api/data/iJrcPGPHro7QfPEZSkIz | 200 | 323ms → {"deleted":true,"id":"iJrcPGPHro7QfPEZSkIz"}
#15 20:30:55 | DELETE /api/data/iJrcPGPHro7QfPEZSkIz | 404 | 214ms → {"detail":"데이터를 찾을 수 없습니다."}
#16 20:30:56 | GET /api/data/summary | 200 | 413ms → count 180, max 131 (2026-09-12)   ← 테스트 데이터 삭제 후 원상복구
```

**메모리가 아니라 Firestore 에 저장된다는 근거**
- ID `iJrcPGPHro7QfPEZSkIz`, `YsqVylOZ6okRmGQY89vV` 는 Firestore 자동 ID 형식(20자)입니다. (메모리 저장소는 `uuid4().hex[:20]` 소문자 16진수)
- Render 서비스는 20:02 에 환경변수 변경으로 **재시작**되었는데, 그 전에 저장한 대화(20:00 이전)와 180건 데이터가 재시작 후에도 그대로 조회됩니다(#2, #11). 메모리 저장소라면 재시작 시 사라집니다.
- Firebase 콘솔 › Firestore › `(default)` 에서 직접 확인한 내용 (2026-11-21 20:33):

```text
(default)
├── conversations
│   ├── 8MvmKw6gEBU5Lc1qViWj
│   ├── YsqVylOZ6okRmGQY89vV   ← 아래 §4 에서 만든 대화
│   │     created_at: "2026-11-21T11:30:40+00:00"
│   │     messages[0] { role: "user",      content: "오늘 운동 기록이 있어? 지금까지 최고 기...", created_at: "2026-11-21T11:30:40+00:00" }
│   │     messages[1] { role: "assistant", content: "네, 오늘(2026-11-21)은 140.0분으로 ...",     created_at: "2026-11-21T11:30:40+00:00" }
│   │     messages[2] { role: "user",      content: "방금 말한 최고 기록 날짜에 무슨 운동을...",   created_at: "2026-11-21T11:30:45+00:00" }
│   │     messages[3] { role: "assistant", ..., tool_calls: [{ name: "query_data", ... }] }
│   ├── ZQjuJIx6uce88FWJUFFL
│   └── yhKCJxkiYgFq8Ot8zvJm
└── data   (문서 필드: date / value / memo / created_at / updated_at — API 기준 180건, §2 #16)
```

---

## 3. 입력 검증 (Pydantic → 422)

```text
#7 20:30:30 | POST /api/data  body={"date":"2026-13-40","value":-5} | 422 | 149ms
   → {"detail":[
        {"loc":["body","date"],  "msg":"Input should be a valid date or datetime, month value is outside expected range of 1-12"},
        {"loc":["body","value"], "msg":"Input should be greater than or equal to 0"}]}
#8 20:30:30 | POST /api/chat  body={"message":"   "} | 422
   → {"detail":[{"loc":["body","message"],"msg":"Value error, 빈 메시지는 보낼 수 없습니다."}]}
#13 20:30:46 | GET /api/conversations/not-exist-id | 404 → {"detail":"대화를 찾을 수 없습니다."}
```

---

## 4. 데이터 → 요약 → 채팅 반영 흐름 (컨텍스트 주입 런타임 증거)

1. **데이터 추가 전** 요약: `count 180`, 최대 `131분 (2026-09-12)` (#2)
2. `POST /api/data` 로 오늘(2026-11-21) 150분 추가 → `PUT` 으로 140분 수정 (#3, #6)
3. **추가 직후** 요약이 즉시 바뀜:

```text
#5 20:30:29 | GET /api/data/summary | 200
   → {"period":"2026-05-25 ~ 2026-11-21","count":181,"metrics":{"total":12236,"average":67.6,"max":150,
      "min":0,"max_date":"2026-11-21",...},"trend":"상승 (최근 14일 평균 +6.3%)","recent_average":85.5,...}
```

4. **도구를 끈 채로**(`use_tools:false`) 질문 → AI 가 DB 를 직접 조회할 방법이 없는데도, 시스템 프롬프트에 주입된 요약만으로 오늘 기록과 최고 기록을 답함:

```text
#9 20:30:40 | POST /api/chat  body={"message":"오늘 운동 기록이 있어? 지금까지 최고 기록은 언제야?","use_tools":false} | 200 | 3388ms
   → conversation_id: "YsqVylOZ6okRmGQY89vV"
     reply: "네, 오늘(2026-11-21)은 140.0분으로 운동하셨네요! 🎉 지금까지의 최고 기록이 바로 오늘입니다.
             지난 181일간의 기록 중에서 가장 높은 수치를 달성하셨어요. 최근 14일 평균이 84.79분인데 ..."
     tool_calls: []                                   ← 도구 호출 없음 = 요약 주입만으로 답변
     summary.period: "2026-05-25 ~ 2026-11-21", summary.count: 181   ← 이번 요청에 주입된 요약
```

5. 같은 대화를 이어서, 요약에 없는 정보(종목=메모)를 물으면 AI 가 **도구를 호출**해 확인:

```text
#10 20:30:45 | POST /api/chat  body={"message":"방금 말한 최고 기록 날짜에 무슨 운동을 했어?",
                                    "conversation_id":"YsqVylOZ6okRmGQY89vV","use_tools":true} | 200 | 5631ms
   → reply: "오늘(2026-11-21) 최고 기록은 **클라이밍**으로 140분을 운동하셨네요! ..."
     tool_calls: [{"name":"query_data","arguments":{"start_date":"2026-11-21","end_date":"2026-11-21"},
                   "reason":"오늘(2026-11-21) 최고 기록 날짜의 구체적인 운동 종목 확인"}]
```

---

## 5. 대화 저장 → 목록 → 불러오기

```text
#11 20:30:46 | GET /api/conversations | 200 | 240ms
   → 4건, 첫 항목: title "오늘 운동 기록이 있어? 지금까지 최고 기록은 언제야?", message_count 4,
     messages 필드 없음(목록은 가볍게, 상세는 GET /{id})
#12 20:30:46 | GET /api/conversations/YsqVylOZ6okRmGQY89vV | 200 | 232ms
   → 메시지 4개, roles: user, assistant, user, assistant
     tool_calls: -, -, -, query_data          ← 도구 호출 기록까지 저장·복원
```

프론트의 "대화 기록" 목록에서 이 항목을 누르면 위 4개 메시지와 🔧 `query_data` 칩이 채팅창에 다시 표시됩니다.

---

## 6. 모바일 사용성 자동 점검 (iPhone 13, 390×844, 터치)

스크립트: [`frontend/tests/mobile_check.py`](../frontend/tests/mobile_check.py) — Playwright 의 실제 기기 프리셋(터치·DPR 3)으로 탭/터치를 수행합니다.
배포 사이트에도 그대로 실행할 수 있습니다: `python frontend/tests/mobile_check.py https://ai-assistant-frontend-virid.vercel.app`

```text
PASS 가로 스크롤 없음 (scrollWidth 390 ≤ viewport 390)
PASS 상단 탭 바 표시
PASS 초기 화면은 채팅 패널만 표시 (['chat'])
PASS 데이터 탭 → 데이터 패널만 표시 (['data'])
PASS 데이터 탭에 요약·추세 그래프 렌더링
PASS 그래프 터치 → 툴팁 표시 ('2026-09-04 · 0분 (7일 63)')
PASS 기록 탭 → 대화 목록 패널만 표시
PASS 대화 탭 → 채팅 탭으로 전환되며 메시지 2개 재표시
PASS 입력창·전송 버튼 터치 영역 (입력 45px, 전송 41px ≥ 36px)
PASS 자바스크립트 오류 없음 ([])

결과: 10/10 통과
```

이 점검 과정에서 **그래프를 한 번 탭하면 툴팁이 뜨지 않던 문제**(touchmove 만 처리)를 발견해 `touchstart` 처리를 추가했습니다.

모바일 화면 구성 (`max-width: 860px`):
- 3단 레이아웃(기록 | 채팅 | 데이터) → 상단 탭 3개(채팅 / 기록 / 데이터)로 전환, 한 번에 한 패널만 표시
- 기록 탭에서 대화를 누르면 자동으로 채팅 탭으로 이동해 메시지를 보여 줌
- 입력창은 하단 고정, 메시지 말풍선 최대 폭 90%, 표는 세로 스크롤

---

## 7. 재현 방법

브라우저에서 배포 프론트(`https://ai-assistant-frontend-virid.vercel.app`)를 열고 개발자 도구 콘솔에 붙여 넣으면 위 1~5 를 다시 확인할 수 있습니다.

```js
const B = window.APP_CONFIG.API_BASE_URL;
const j = (m, p, b) => fetch(B + p, { method: m, headers: b ? { "Content-Type": "application/json" } : {}, body: b && JSON.stringify(b) })
  .then(async r => (console.log(m, p, r.status), r.json()));
const s0 = await j("GET", "/api/data/summary");
const d = await j("POST", "/api/data", { date: "2026-11-21", value: 150, memo: "테스트" });
const s1 = await j("GET", "/api/data/summary");             // count +1, max 변화 확인
const c = await j("POST", "/api/chat", { message: "오늘 기록 있어?", use_tools: false });
console.log(c.reply, c.summary.count);
await j("GET", `/api/conversations/${c.conversation_id}`);
await j("DELETE", `/api/data/${d.id}`);                      // 원상복구
```
