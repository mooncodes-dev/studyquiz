"""채점 모듈.

퀴즈 문제 리스트와 사용자의 답 리스트를 받아 점수와 문항별 피드백을 돌려줍니다.
- 객관식: 보기 문장 자체로 답하거나, 1부터 시작하는 보기 번호로 답할 수 있습니다.
- 빈칸형: 공백/대소문자를 무시하고 비교합니다.
- OX형: O/X 외에 1/2(보기 번호), 참/거짓, 맞다/틀리다로도 답할 수 있습니다.
"""
from __future__ import annotations

import re


def _normalize(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


_OX_ALIASES = {
    "o": "O", "0": "O", "○": "O", "참": "O", "맞다": "O", "맞음": "O", "true": "O",
    "x": "X", "×": "X", "거짓": "X", "틀리다": "X", "틀림": "X", "false": "X",
}


def _resolve_answer(question: dict, user_answer) -> str:
    """객관식에서 번호로 답한 경우 해당 보기 문장으로 바꿉니다."""
    options = question.get("options")
    text = str(user_answer or "").strip()
    if options and text.isdigit():
        idx = int(text) - 1  # 사용자는 1번부터 셉니다.
        if 0 <= idx < len(options):
            return options[idx]
    if question.get("type") == "OX형":
        return _OX_ALIASES.get(text.lower(), text)
    return text


def grade(questions: list[dict], answers: list) -> dict:
    """채점 결과를 dict로 돌려줍니다.

    반환 형식:
        {"total": 전체 문항 수, "correct": 맞힌 수, "score": 100점 만점 점수,
         "results": [{"question": 문제, "user_answer": 제출 답,
                      "answer": 정답, "is_correct": bool, "feedback": "..."}]}
    """
    results = []
    correct = 0
    for i, question in enumerate(questions):
        raw = answers[i] if i < len(answers) else ""
        resolved = _resolve_answer(question, raw)
        is_correct = _normalize(resolved) == _normalize(question.get("answer"))
        if is_correct:
            correct += 1
            feedback = "정답입니다!"
        else:
            feedback = f"오답입니다. 정답은 '{question.get('answer')}'입니다."
        if question.get("explanation") and question.get("answer") == "X":
            feedback += f" ({question['explanation']})"
        results.append({
            "question": question.get("question"),
            "type": question.get("type"),
            "user_answer": resolved,
            "answer": question.get("answer"),
            "is_correct": is_correct,
            "feedback": feedback,
        })
    total = len(questions)
    score = round(correct / total * 100, 1) if total else 0.0
    return {"total": total, "correct": correct, "score": score, "results": results}
