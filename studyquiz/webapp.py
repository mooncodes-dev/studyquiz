"""StudyQuiz 웹 데모.

파이썬 표준 라이브러리 http.server만으로 만든 웹 화면입니다.
실행:  python -m studyquiz.webapp   (http://localhost:8000)

흐름: 텍스트 붙여넣기 또는 PDF 업로드 -> 요약 + 퀴즈 표시 -> 답 제출 -> 채점 결과.
서버에 상태를 저장하지 않기 위해, 퀴즈(정답 포함)를 숨은 필드에 담아
채점 요청 때 그대로 돌려받는 방식을 씁니다.
Gemini 키는 서버에 저장하지 않고, 입력한 그 요청을 처리할 때만 사용합니다.
multipart/form-data(PDF 업로드)는 cgi 모듈 없이 직접 파싱합니다.
"""
from __future__ import annotations

import base64
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .extract import extract_text_from_bytes, ScannedDocumentError
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
  * { box-sizing: border-box; }
  body { font-family: "Malgun Gothic", sans-serif; background: #f4f6f8; color: #222;
         max-width: 820px; margin: 0 auto; padding: 2rem 1rem 3rem; line-height: 1.6; }
  h1 { margin: 0 0 0.3rem; font-size: 1.7rem; }
  .sub { color: #555; margin-top: 0; }
  .card { background: #fff; border: 1px solid #dde3e8; border-radius: 12px;
          padding: 1.2rem 1.4rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .card h2 { margin-top: 0; font-size: 1.15rem; }
  textarea { width: 100%; border: 1px solid #c9d2d9; border-radius: 8px; padding: 0.6rem; }
  input[type="number"], input[type="password"] { border: 1px solid #c9d2d9;
          border-radius: 6px; padding: 0.35rem 0.5rem; }
  .row { display: flex; flex-wrap: wrap; gap: 1rem 1.6rem; align-items: center; margin: 0.7rem 0; }
  button { background: #2563eb; color: #fff; border: 0; border-radius: 8px;
           padding: 0.6rem 1.4rem; font-size: 1rem; cursor: pointer; }
  button:hover { background: #1d4ed8; }
  .ok { color: #0a7d2c; font-weight: bold; } .no { color: #c0392b; font-weight: bold; }
  .error { border-color: #e5a3a3; background: #fdf1f1; white-space: pre-wrap; }
  .hint { color: #666; font-size: 0.9rem; }
  label.opt { display: inline-flex; gap: 0.35rem; align-items: center; }
</style>
</head>
<body>
<h1>📚 StudyQuiz</h1>
<p class="sub">강의 자료를 넣으면 핵심 요약과 자동 퀴즈를 만들어 드립니다.</p>
"""

_PAGE_TAIL = "</body>\n</html>"


def _encode_payload(questions: list[dict]) -> str:
    raw = json.dumps(questions, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_payload(payload: str) -> list[dict]:
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _error_page(message: str) -> str:
    return (_PAGE_HEAD
            + f'<div class="card error">{html.escape(message)}</div>'
            + '<p><a href="/">처음으로</a></p>' + _PAGE_TAIL)


# ---------------------------------------------------------------------------
# 화면 렌더링
# ---------------------------------------------------------------------------

def render_index() -> str:
    return _PAGE_HEAD + """
<form method="post" action="/quiz" enctype="multipart/form-data">
  <div class="card">
    <h2>1. 입력</h2>
    <textarea name="text" rows="12" placeholder="여기에 강의 자료 텍스트를 붙여 넣으세요."></textarea>
    <p>또는 PDF 파일 업로드: <input type="file" name="file" accept=".pdf,.txt">
       <span class="hint">(스캔본 PDF는 OCR 패키지가 있을 때만 읽을 수 있습니다)</span></p>
  </div>
  <div class="card">
    <h2>2. 옵션</h2>
    <div class="row">
      <label>요약 문장 수 <input type="number" name="snum" value="3" min="1" max="10"></label>
      <label>문제 수 <input type="number" name="num" value="5" min="1" max="20"></label>
    </div>
    <div class="row">
      <span>방식</span>
      <label class="opt"><input type="radio" name="mode" value="local" checked> 기본 (내장 알고리즘)</label>
      <label class="opt"><input type="radio" name="mode" value="gemini"> Gemini (AI)</label>
    </div>
    <div class="row">
      <label>Gemini API 키 <input type="password" name="gemini_key" size="34"
             placeholder="Gemini 방식을 쓸 때만 입력" autocomplete="off"></label>
    </div>
    <p class="hint">키는 서버에 저장되지 않고, 이 요청을 처리할 때만 사용됩니다.
       모델은 키로 쓸 수 있는 것 중 자동으로 선택됩니다.</p>
  </div>
  <button type="submit">요약 + 퀴즈 만들기</button>
</form>
""" + _PAGE_TAIL


def render_quiz(text: str, num: int, snum: int,
                use_ai: bool = False, api_key: str | None = None) -> str:
    if use_ai:
        from .gemini import summarize_with_gemini, quiz_with_gemini, GeminiError
        try:
            summary = summarize_with_gemini(text, snum, api_key)
            questions = quiz_with_gemini(text, num, api_key)
        except GeminiError as exc:
            return _error_page(f"Gemini를 사용할 수 없습니다.\n{exc}")
    else:
        summary = summarize(text, snum)
        questions = generate_quiz(text, num)
    if not questions:
        return _error_page("문제를 만들 수 없습니다. 텍스트를 더 길게 입력해 주세요.")

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

    parts = [_PAGE_HEAD, '<div class="card">',
             f"<h2>채점 결과: {result['score']}점 "
             f"({result['correct']}/{result['total']})</h2></div>"]
    for i, r in enumerate(result["results"], 1):
        css = "ok" if r["is_correct"] else "no"
        parts.append('<div class="card">')
        parts.append(f"<p><strong>[{i}]</strong> {html.escape(str(r['question']))}</p>")
        parts.append(f"<p>내 답: {html.escape(str(r['user_answer']) or '(없음)')}</p>")
        parts.append(f'<p class="{css}">{html.escape(r["feedback"])}</p>')
        parts.append("</div>")
    parts.append('<p><a href="/">처음으로</a></p>')
    return "".join(parts) + _PAGE_TAIL


# ---------------------------------------------------------------------------
# multipart/form-data 파싱 (cgi 모듈 없이 직접)
# ---------------------------------------------------------------------------

def parse_multipart(body: bytes, content_type: str) -> tuple[dict, dict]:
    """multipart 본문을 (텍스트 필드, 파일) 으로 나눕니다.

    텍스트 필드: {이름: [값, ...]} (parse_qs와 같은 형태)
    파일: {이름: (파일 이름, 바이트)}
    """
    fields: dict[str, list[str]] = {}
    files: dict[str, tuple[str, bytes]] = {}
    match = None
    for piece in content_type.split(";"):
        piece = piece.strip()
        if piece.startswith("boundary="):
            match = piece[len("boundary="):].strip('"')
    if not match:
        return fields, files
    delimiter = b"--" + match.encode("utf-8")

    for segment in body.split(delimiter):
        segment = segment.strip(b"\r\n")
        if not segment or segment == b"--":
            continue
        if segment.endswith(b"--"):
            segment = segment[:-2].rstrip(b"\r\n")
        header_blob, sep, content = segment.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = {}
        for line in header_blob.split(b"\r\n"):
            name, _, value = line.partition(b":")
            headers[name.strip().lower().decode("utf-8", "replace")] = \
                value.strip().decode("utf-8", "replace")
        disposition = headers.get("content-disposition", "")
        params = {}
        for piece in disposition.split(";"):
            piece = piece.strip()
            if "=" in piece:
                k, v = piece.split("=", 1)
                params[k.strip()] = v.strip().strip('"')
        field_name = params.get("name")
        if not field_name:
            continue
        if "filename" in params:
            if params["filename"]:
                files[field_name] = (params["filename"], content)
        else:
            fields.setdefault(field_name, []).append(
                content.decode("utf-8", "replace"))
    return fields, files


# ---------------------------------------------------------------------------
# HTTP 핸들러
# ---------------------------------------------------------------------------

class StudyQuizHandler(BaseHTTPRequestHandler):
    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_post(self) -> tuple[dict, dict]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return parse_multipart(raw, content_type)
        return parse_qs(raw.decode("utf-8", "replace")), {}

    def do_GET(self):  # noqa: N802 (http.server 규약)
        if self.path in ("/", "/index.html"):
            self._send_html(render_index())
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        # 어떤 오류가 나도 연결을 그냥 끊지(빈 응답) 않고 안내 화면으로 답합니다.
        # extract는 CLI용으로 SystemExit에 안내 문구를 담아 올리기도 합니다.
        try:
            self._do_post()
        except SystemExit as exc:
            self._send_html(_error_page(str(exc)))
        except Exception as exc:
            self._send_html(_error_page(f"처리 중 오류가 발생했습니다.\n{exc}"))

    def _do_post(self):
        form, files = self._read_post()
        if self.path == "/quiz":
            text = form.get("text", [""])[0]
            if "file" in files:
                filename, data = files["file"]
                if data:
                    try:
                        text = extract_text_from_bytes(data, filename)
                    except ScannedDocumentError as exc:
                        self._send_html(_error_page(str(exc)))
                        return
            num = int(form.get("num", ["5"])[0] or 5)
            snum = int(form.get("snum", ["3"])[0] or 3)
            use_ai = form.get("mode", ["local"])[0] == "gemini"
            api_key = form.get("gemini_key", [""])[0] or None
            self._send_html(render_quiz(text, num, snum, use_ai, api_key))
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
