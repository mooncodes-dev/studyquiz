"""퀴즈 생성 모듈.

문서에서 핵심 용어를 뽑아 두 가지 유형의 문제를 만듭니다.
- 빈칸형(cloze): 핵심 용어가 든 문장에서 그 용어를 ____ 로 가립니다.
- 객관식: 빈칸형 문항에 정답 용어 + 문서의 다른 핵심 용어 3개를 보기로 제시합니다.

문제는 dict 형태로 표현합니다.
    {"type": "객관식", "question": "...", "options": ["...", ...],
     "answer": "정답 용어", "answer_index": 0}
    {"type": "빈칸형", "question": "...", "options": None,
     "answer": "정답 용어", "answer_index": None}
"""
from __future__ import annotations

import random

from .extract import split_sentences
from .summarize import extract_keywords

BLANK = "____"
MC = "객관식"
CLOZE = "빈칸형"
MIXED = "혼합"


def _candidate_sentences(text: str, keywords: list[str]) -> list[tuple[str, str]]:
    """핵심 용어를 포함하는 (문장, 용어) 쌍을 모읍니다. 문장당 대표 용어 하나만 씁니다."""
    candidates: list[tuple[str, str]] = []
    for sentence in split_sentences(text):
        for keyword in keywords:
            if keyword in sentence:
                candidates.append((sentence, keyword))
                break
    return candidates


def _make_question(sentence: str, keyword: str, qtype: str,
                   keywords: list[str], rng: random.Random) -> dict | None:
    stem = sentence.replace(keyword, BLANK, 1)
    if qtype == MC:
        distractors = [k for k in keywords if k != keyword]
        rng.shuffle(distractors)
        distractors = distractors[:3]
        if len(distractors) < 3:
            return None  # 오답 보기를 만들 핵심 용어가 부족하면 객관식은 건너뜁니다.
        options = distractors + [keyword]
        rng.shuffle(options)
        return {
            "type": MC,
            "question": stem,
            "options": options,
            "answer": keyword,
            "answer_index": options.index(keyword),
        }
    return {
        "type": CLOZE,
        "question": stem,
        "options": None,
        "answer": keyword,
        "answer_index": None,
    }


def generate_quiz(text: str, num_questions: int = 5,
                  quiz_type: str = MIXED, seed: int | None = None) -> list[dict]:
    """문서에서 최대 num_questions개의 문제를 생성합니다.

    quiz_type: "객관식", "빈칸형", "혼합"(번갈아 출제) 중 하나.
    핵심 용어나 후보 문장이 부족하면 만들 수 있는 만큼만 돌려줍니다.
    """
    if quiz_type not in (MC, CLOZE, MIXED):
        raise ValueError(f"알 수 없는 문제 유형입니다: {quiz_type}")
    rng = random.Random(seed)
    keywords = extract_keywords(text, top_n=30)
    candidates = _candidate_sentences(text, keywords)
    rng.shuffle(candidates)

    questions: list[dict] = []
    used_sentences: set[str] = set()
    for sentence, keyword in candidates:
        if len(questions) >= num_questions:
            break
        if sentence in used_sentences:
            continue
        if quiz_type == MIXED:
            qtype = MC if len(questions) % 2 == 0 else CLOZE
        else:
            qtype = quiz_type
        question = _make_question(sentence, keyword, qtype, keywords, rng)
        if question is None:
            # 객관식을 만들 수 없으면 빈칸형으로 대체합니다.
            question = _make_question(sentence, keyword, CLOZE, keywords, rng)
        used_sentences.add(sentence)
        questions.append(question)
    return questions
