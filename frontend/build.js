// Vercel 빌드 단계: 환경 변수 API_BASE_URL → public/config.js 생성
// (프론트 코드에 서버 주소를 하드코딩하지 않기 위함. 비밀값은 절대 넣지 말 것 — 브라우저에 공개됨)
const fs = require("fs");
const path = require("path");

const apiBase = (process.env.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const out = path.join(__dirname, "public", "config.js");
fs.writeFileSync(out, `window.APP_CONFIG = ${JSON.stringify({ API_BASE_URL: apiBase })};\n`);
console.log(`[build] config.js 생성: API_BASE_URL=${apiBase}`);
