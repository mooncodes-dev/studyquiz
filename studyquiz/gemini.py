"""Gemini 연동 모듈 (선택 기능).

표준 라이브러리 urllib만으로 Google Gemini API를 호출합니다.
API 키가 있을 때만 동작하며, 키는 인자나 GEMINI_API_KEY 환경 변수로 받습니다.
키를 코드에 적거나 로그에 남기지 않습니다.

모델은 자동 선택입니다: 키로 쓸 수 있는 모델 목록을 조회해
generateContent를 지원하는 모델 중 우선순위(최신 Flash 계열 먼저)로 고르고,
호출이 실패하면 다음 후보 모델로 넘어갑니다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .quizgen import MC, CLOZE

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = 60

# 모델 이름에 포함되면 우선하는 패턴(앞쪽일수록 우선).
_MODEL_PATTERNS = ("gemini-3.8-flash", "gemini-3", "gemini-2.5-flash", "flash", "gemini")


class GeminiError(RuntimeError):
    """Gemini 호출이 불가능하거나 실패했을 때 발생합니다."""


def _resolve_key(api_key: str | None) -> str:
    key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise GeminiError(
            "Gemini API 키가 없습니다. GEMINI_API_KEY 환경 변수를 설정하거나 "
            "키를 입력해 주세요.")
    return key


# ---------------------------------------------------------------------------
# 모델 자동 선택
# ---------------------------------------------------------------------------

def pick_model(model_names: list[str]) -> str | None:
    """모델 이름 목록에서 우선순위가 가장 높은 모델 하나를 고릅니다.

    이름은 "models/gemini-..." 형태든 접두사 없는 형태든 받을 수 있고,
    반환값은 접두사를 뗀 모델 ID입니다. 고를 모델이 없으면 None입니다.
    """
    candidates = []
    for raw in model_names or []:
        name = str(raw).removeprefix("models/")
        if name:
            candidates.append(name)
    for pattern in _MODEL_PATTERNS:
        for name in candidates:
            if pattern in name.lower():
                return name
    return None


def _model_rank(name: str) -> int:
    lowered = name.lower()
    for rank, pattern in enumerate(_MODEL_PATTERNS):
        if pattern in lowered:
            return rank
    return len(_MODEL_PATTERNS)


def _candidate_models(api_key: str) -> list[str]:
    """쓸 수 있는 모델들을 우선순위 순으로 정렬해 돌려줍니다."""
    url = f"{_API_BASE}/models?key={api_key}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GeminiError(
            f"Gemini 모델 목록을 가져오지 못했습니다 (HTTP {exc.code}). "
            "API 키가 올바른지 확인해 주세요.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GeminiError(
            "Gemini 서버에 연결하지 못했습니다. 네트워크 상태를 확인해 주세요."
        ) from exc

    names = []
    for model in payload.get("models", []):
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
            names.append(str(model.get("name", "")).removeprefix("models/"))
    ranked = sorted((n for n in names if n), key=_model_rank)
    # 같은 순위의 중복을 제거하면서 순서를 유지합니다.
    seen: list[str] = []
    for name in ranked:
        if name not in seen:
            seen.append(name)
    if not seen:
        raise GeminiError(
            "이 API 키로 쓸 수 있는 Gemini 모델이 없습니다. 키의 권한을 확인해 주세요.")
    return seen


# ---------------------------------------------------------------------------
# 텍스트 생성
# ---------------------------------------------------------------------------

def _call_model(model: str, prompt: str, api_key: str) -> str:
    url = f"{_API_BASE}/models/{model}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,  # 키를 URL에 남기지 않기 위해 헤더로 보냅니다.
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = []
    for candidate in payload.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def generate_text(prompt: str, api_key: str | None = None) -> str:
    """프롬프트를 보내고 모델의 텍스트 응답을 돌려줍니다.

    자동 선택된 모델이 오류를 내면 다음 후보 모델로 차례로 시도합니다.
    """
    key = _resolve_key(api_key)
    candidates = _candidate_models(key)
    last_error: Exception | None = None
    for model in candidates:
        try:
            text = _call_model(model, prompt, key)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            continue
        if text:
            return text
        last_error = GeminiError(f"모델 {model}의 응답이 비어 있습니다.")
    raise GeminiError(
        "Gemini 모델 호출에 모두 실패했습니다. 잠시 뒤 다시 시도하거나 "
        "API 키와 네트워크 상태를 확인해 주세요.") from last_error


# ---------------------------------------------------------------------------
# 요약 / 퀴즈
# ---------------------------------------------------------------------------

def summarize_with_gemini(text: str, num_sentences: int = 3,
                          api_key: str | None = None) -> list[str]:
    """Gemini로 요약 문장 리스트를 만듭니다(로컬 summarize와 같은 반환 형식)."""
    prompt = (
        "다음 강의 자료를 한국어로 요약해 주세요.\n"
        f"- 핵심 문장 {num_sentences}개만, 한 줄에 한 문장씩 출력하세요.\n"
        "- 번호, 글머리 기호, 설명, 따옴표 없이 문장만 출력하세요.\n\n"
        f"[강의 자료]\n{text}"
    )
    raw = generate_text(prompt, api_key)
    sentences = []
    for line in raw.splitlines():
        cleaned = re.sub(r"^[\s\-*•\d.)]+", "", line).strip()
        if cleaned:
            sentences.append(cleaned)
    if not sentences:
        raise GeminiError("Gemini 응답에서 요약 문장을 찾지 못했습니다.")
    return sentences[:num_sentences]


def _parse_quiz_json(raw: str) -> list:
    """모델 응답에서 JSON 배열을 방어적으로 뽑아냅니다."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except ValueError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise GeminiError("Gemini 응답을 문제 형식으로 해석하지 못했습니다.")
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise GeminiError("Gemini 응답을 문제 형식으로 해석하지 못했습니다.")
    return data


def quiz_with_gemini(text: str, num_questions: int = 5,
                     api_key: str | None = None) -> list[dict]:
    """Gemini로 퀴즈를 만듭니다(로컬 generate_quiz와 같은 dict 형식)."""
    prompt = (
        "다음 강의 자료로 복습용 퀴즈를 만들어 주세요.\n"
        f"- 문제 수: {num_questions}개 (객관식과 빈칸형을 섞어서)\n"
        "- 출력은 JSON 배열만. 설명이나 코드 표시 없이 배열만 출력하세요.\n"
        "- 각 원소는 다음 형식입니다:\n"
        '  {"type": "객관식", "question": "빈칸(____)이 든 문제 문장", '
        '"options": ["보기1", "보기2", "보기3", "보기4"], "answer": "정답 보기"}\n'
        '  {"type": "빈칸형", "question": "빈칸(____)이 든 문제 문장", '
        '"options": null, "answer": "정답 용어"}\n'
        "- 객관식의 answer는 options 중 하나와 정확히 같아야 합니다.\n\n"
        f"[강의 자료]\n{text}"
    )
    raw = generate_text(prompt, api_key)
    items = _parse_quiz_json(raw)

    questions: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question_text = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question_text or not answer:
            continue
        options = item.get("options")
        if item.get("type") == MC and isinstance(options, list) and len(options) >= 2:
            options = [str(o) for o in options]
            if answer not in options:
                continue
            questions.append({
                "type": MC,
                "question": question_text,
                "options": options,
                "answer": answer,
                "answer_index": options.index(answer),
            })
        else:
            questions.append({
                "type": CLOZE,
                "question": question_text,
                "options": None,
                "answer": answer,
                "answer_index": None,
            })
        if len(questions) >= num_questions:
            break
    if not questions:
        raise GeminiError("Gemini 응답에서 유효한 문제를 찾지 못했습니다.")
    return questions
