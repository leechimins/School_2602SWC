"""구글 캘린더 연동을 실제 계정으로 확인하는 개발용 페이지.

    python -m tools.google_check

http://localhost:8001 을 열고 버튼을 차례로 누른다.
지수로 로그인 → 구글 연결 → 동기화 → 끊기. 각 응답이 화면에 그대로 나온다.

Swagger로는 연결을 확인할 수 없다. 연결에는 구글 팝업이 준 인증 코드가
필요한데, Swagger에는 그 팝업을 띄우는 길이 없어서 이 페이지를 둔다.

준비:
- .env에 GOOGLE_CLIENT_ID · GOOGLE_CLIENT_SECRET (값은 팀원에게 따로 받는다)
- 내 구글 계정이 Google Cloud 콘솔 OAuth 동의 화면의 "테스트 사용자"에 있어야 한다
- 클라이언트의 승인된 JavaScript 원본에 http://localhost:8001 이 있어야 한다

**테스트 DB(TEST_DATABASE_URL)를 쓰고, 뜰 때마다 시드로 초기화한다.**
개발 DB는 건드리지 않는다. pytest도 같은 DB를 비우므로 둘을 동시에 돌리지 않는다.
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

PORT = 8001

PAGE = """<!doctype html><meta charset="utf-8"><title>구글 연동 확인</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://accounts.google.com/gsi/client" async></script>
<body style="font-family:sans-serif;padding:16px;max-width:640px">
<h3>구글 캘린더 연동 확인 (실제 API · 테스트 DB)</h3>
<p>
<button onclick="call('POST','/api/v1/sessions',{name:'지수'})">1. 지수로 로그인</button>
<button id="c">2. 구글 연결</button>
<button onclick="call('POST','/api/v1/me/integrations/google-calendar/sync')">3. 동기화</button>
<button onclick="call('DELETE','/api/v1/me/integrations/google-calendar')">4. 끊기</button>
</p>
<pre id="o" style="white-space:pre-wrap;background:#f4f4f4;padding:8px"></pre>
<script>
const o = document.getElementById('o');
async function call(method, url, body) {
  const res = await fetch(url, {method, headers: {'Content-Type': 'application/json'},
    body: body ? JSON.stringify(body) : undefined});
  const text = await res.text();
  o.textContent = method + ' ' + url + ' → ' + res.status + '\\n' +
    (text ? JSON.stringify(JSON.parse(text), null, 2) : '');
}
document.getElementById('c').onclick = () => {
  google.accounts.oauth2.initCodeClient({
    client_id: __CLIENT_ID__,
    scope: 'https://www.googleapis.com/auth/calendar.readonly',
    ux_mode: 'popup', access_type: 'offline', prompt: 'consent',
    callback: (r) => r.error ? (o.textContent = '팝업 오류: ' + r.error)
      : call('POST', '/api/v1/me/integrations/google-calendar', {code: r.code}),
  }).requestCode();
};
</script>"""


def main() -> None:
    load_dotenv()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not client_id or not os.getenv("GOOGLE_CLIENT_SECRET", "").strip():
        sys.exit(".env에 GOOGLE_CLIENT_ID와 GOOGLE_CLIENT_SECRET을 넣어 주세요.")
    if not test_url:
        sys.exit(".env에 TEST_DATABASE_URL이 없습니다.")

    # app을 불러오기 전에 바꿔야 엔진이 테스트 DB를 잡는다.
    os.environ["DATABASE_URL"] = test_url

    import uvicorn
    from fastapi.responses import HTMLResponse

    from app.main import app
    from tools import reset_db

    reset_db.main()

    page = PAGE.replace("__CLIENT_ID__", json.dumps(client_id))

    @app.get("/", include_in_schema=False)
    def check_page() -> HTMLResponse:
        return HTMLResponse(page)

    print(f"http://localhost:{PORT} 을 여세요")
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
