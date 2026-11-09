"""녹음 받아적기용 모델 호출(complete_json_audio). 진짜 API를 부르지 않는다.

complete_json과 같은 약속을 지키는지 본다 — 무슨 일이 있어도 None을 돌려줄 뿐
예외를 올리지 않는다. 그리고 녹음이 OpenAI 호환 input_audio 모양으로 실리는지.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.shared import llm


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_ENABLED", raising=False)


def _reply(status: int = 200, content: str = "{}") -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "https://example.test/chat/completions"),
    )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake(url, **kw):
        calls.append({"url": url, **kw})
        return _reply(content='{"lines": [{"speaker": "화자1", "text": "안녕"}]}')

    monkeypatch.setattr(llm.httpx, "post", fake)
    return calls


def test_녹음을_input_audio로_실어_보내고_JSON을_받는다(sent):
    result = llm.complete_json_audio("받아적어", b"\x01\x02mp3")

    assert result == {"lines": [{"speaker": "화자1", "text": "안녕"}]}
    body = sent[0]["json"]
    text, audio = body["messages"][0]["content"]
    assert text == {"type": "text", "text": "받아적어"}
    assert audio["type"] == "input_audio"
    assert base64.b64decode(audio["input_audio"]["data"]) == b"\x01\x02mp3"
    assert audio["input_audio"]["format"] == "mp3"
    assert body["temperature"] == 0
    assert sent[0]["timeout"] == llm.AUDIO_TIMEOUT_SEC


def test_키가_없거나_꺼져_있으면_부르지_않고_None(monkeypatch, sent):
    monkeypatch.setenv("LLM_ENABLED", "false")

    assert llm.complete_json_audio("받아적어", b"x") is None
    assert sent == []


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("네트워크 끊김"),
        httpx.ReadTimeout("120초 초과"),
        _reply(status=500),
        _reply(content="받아적을 수 없습니다"),
    ],
)
def test_무엇이_실패해도_예외_없이_None(monkeypatch, outcome):
    def fake(*args, **kw):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(llm.httpx, "post", fake)

    assert llm.complete_json_audio("받아적어", b"x") is None
