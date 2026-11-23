"""StudyQuiz 웹 데모.

파이썬 표준 라이브러리 http.server만으로 만든 간단한 웹 화면입니다.
실행:  python -m studyquiz.webapp   (http://localhost:8000)

흐름: 텍스트 붙여넣기 -> 요약 + 퀴즈 표시 -> 브라우저에서 답 제출 -> 채점 결과.
서버에 상태를 저장하지 않기 위해, 퀴즈(정답 포함)를 숨은 필드에 담아
채점 요청 때 그대로 돌려받는 방식을 씁니다.
"""
from __future__ import annotations

import base64
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .summarize import summarize
from .quizgen import generate_quiz, MC
from .grade import grade

HOST = "127.0.0.1"
PORT = 8000

_PAGE_HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>StudyQuiz - 강의 요약 + 자동 퀴즈</title>
<style>
  body { font-family: sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
  textarea { width: 100%; }
  .card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
  .ok { color: #0a7d2c; } .no { color: #c0392b; }
  button { padding: 0.5rem 1.2rem; font-size: 1rem; cursor: pointer; }
</style>
</head>
<body>
<h1>StudyQuiz</h1>
<p>강의 자료 텍스트를 붙여 넣으면 핵심 요약과 자동 퀴즈를 만들어 드립니다.</p>
"""

_PAGE_TAIL = "</body>\n</html>"


def _encode_payload(questions: list[dict]) -> str:
    raw = json.dumps(questions, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_payload(payload: str) -> list[dict]:
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def render_index() -> str:
    return _PAGE_HEAD + """
<form method="post" action="/quiz">
  <textarea name="text" rows="14" placeholder="여기에 강의 자료 텍스트를 붙여 넣으세요."></textarea>
  <p>문제 수: <input type="number" name="num" value="5" min="1" max="20">
     요약 문장 수: <input type="number" name="snum" value="3" min="1" max="10"></p>
  <button type="submit">요약 + 퀴즈 만들기</button>
</form>
""" + _PAGE_TAIL


def render_quiz(text: str, num: int, snum: int) -> str:
    summary = summarize(text, snum)
    questions = generate_quiz(text, num)
    if not questions:
        return _PAGE_HEAD + "<p>문제를 만들 수 없습니다. 텍스트를 더 길게 입력해 주세요.</p>" \
            '<p><a href="/">처음으로</a></p>' + _PAGE_TAIL

    parts = [_PAGE_HEAD, '<div class="card"><h2>핵심 요약</h2><ul>']
    for sentence in summary:
        parts.append(f"<li>{html.escape(sentence)}</li>")
    parts.append("</ul></div>")

    parts.append('<form method="post" action="/grade">')
    parts.append(f'<input type="hidden" name="payload" value="{_encode_payload(questions)}">')
    for i, q in enumerate(questions):
        parts.append('<div class="card">')
        parts.append(f"<p><strong>[{i + 1}] ({html.escape(q['type'])})</strong> "
                     f"{html.escape(q['question'])}</p>")
        if q["type"] == MC:
            for option in q["options"]:
                esc = html.escape(option)
                parts.append(
                    f'<label><input type="radio" name="a{i}" value="{esc}"> {esc}</label><br>')
        else:
            parts.append(f'<input type="text" name="a{i}" placeholder="빈칸에 들어갈 용어">')
        parts.append("</div>")
    parts.append('<button type="submit">채점하기</button></form>')
    parts.append('<p><a href="/">처음으로</a></p>')
    return "".join(parts) + _PAGE_TAIL


def render_grade(payload: str, form: dict) -> str:
    questions = _decode_payload(payload)
    answers = []
    for i in range(len(questions)):
        values = form.get(f"a{i}", [""])
        answers.append(values[0] if values else "")
    result = grade(questions, answers)

    parts = [_PAGE_HEAD, f"<h2>채점 결과: {result['score']}점 "
                          f"({result['correct']}/{result['total']})</h2>"]
    for i, r in enumerate(result["results"], 1):
        css = "ok" if r["is_correct"] else "no"
        parts.append('<div class="card">')
        parts.append(f"<p><strong>[{i}]</strong> {html.escape(str(r['question']))}</p>")
        parts.append(f"<p>내 답: {html.escape(str(r['user_answer']) or '(없음)')}</p>")
        parts.append(f'<p class="{css}">{html.escape(r["feedback"])}</p>')
        parts.append("</div>")
    parts.append('<p><a href="/">처음으로</a></p>')
    return "".join(parts) + _PAGE_TAIL


class StudyQuizHandler(BaseHTTPRequestHandler):
    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_form(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw)

    def do_GET(self):  # noqa: N802 (http.server 규약)
        if self.path in ("/", "/index.html"):
            self._send_html(render_index())
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        form = self._read_form()
        if self.path == "/quiz":
            text = form.get("text", [""])[0]
            num = int(form.get("num", ["5"])[0] or 5)
            snum = int(form.get("snum", ["3"])[0] or 3)
            self._send_html(render_quiz(text, num, snum))
        elif self.path == "/grade":
            payload = form.get("payload", [""])[0]
            self._send_html(render_grade(payload, form))
        else:
            self.send_error(404)

    def log_message(self, format, *args):  # 접속 로그를 조용히 합니다.
        pass


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), StudyQuizHandler)
    print(f"StudyQuiz 웹 데모 실행 중: http://{HOST}:{PORT}  (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")


if __name__ == "__main__":
    main()
