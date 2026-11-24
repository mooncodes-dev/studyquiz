"""퀴즈 생성 모듈.

문서에서 TF-IDF 기준 핵심 용어를 뽑아 세 가지 유형의 문제를 만듭니다.
단순 빈도가 아니라 문서 안에서 두드러지는 개념어가 정답이 되므로,
긴 강의 자료에서도 핵심 개념을 묻는 문제가 나옵니다.
- 빈칸형(cloze): 핵심 용어가 든 문장에서 그 용어를 ____ 로 가립니다.
- 객관식: 빈칸형 문항에 정답 용어 + 문서의 다른 핵심 용어 3개를 보기로 제시합니다.
- OX형: 원래 문장을 그대로 내거나(정답 O), 핵심 용어를 문서의 다른 핵심 용어로
  바꿔 틀린 문장으로 만들어(정답 X) 참/거짓을 묻습니다.

문제는 dict 형태로 표현합니다.
    {"type": "객관식", "question": "...", "options": ["...", ...],
     "answer": "정답 용어", "answer_index": 0}
    {"type": "빈칸형", "question": "...", "options": None,
     "answer": "정답 용어", "answer_index": None}
    {"type": "OX형", "question": "...", "options": ["O", "X"],
     "answer": "O" 또는 "X", "answer_index": 0 또는 1,
     "explanation": "X일 때 원래 용어 안내"}
"""
from __future__ import annotations

import random

from .extract import split_sentences
from .summarize import extract_keywords_tfidf

BLANK = "____"
MC = "객관식"
CLOZE = "빈칸형"
OX = "OX형"
MIXED = "혼합"
OX_OPTIONS = ["O", "X"]
# 혼합 출제 시 돌아가며 내는 순서
MIXED_ORDER = (MC, CLOZE, OX)


def _candidate_sentences(text: str, keywords: list[str]) -> list[tuple[str, str]]:
    """핵심 용어를 포함하는 (문장, 용어) 쌍을 모읍니다. 문장당 대표 용어 하나만 씁니다."""
    candidates: list[tuple[str, str]] = []
    for sentence in split_sentences(text):
        for keyword in keywords:
            if keyword in sentence:
                candidates.append((sentence, keyword))
                break
    return candidates


def _make_ox_question(sentence: str, keyword: str,
                      keywords: list[str], rng: random.Random) -> dict:
    """OX 문제를 만듭니다. 절반 정도는 핵심 용어를 다른 용어로 바꿔 틀린 문장을 냅니다."""
    # 바꿔 넣을 용어는 원래 용어와 겹치지 않고, 문장에 이미 들어 있지 않은 것만 씁니다.
    swaps = [k for k in keywords
             if k != keyword and k not in keyword and keyword not in k
             and k not in sentence]
    if swaps and rng.random() < 0.5:
        wrong = rng.choice(swaps)
        return {
            "type": OX,
            "question": sentence.replace(keyword, wrong, 1),
            "options": list(OX_OPTIONS),
            "answer": "X",
            "answer_index": 1,
            "explanation": f"'{wrong}'이(가) 아니라 '{keyword}'이(가) 맞습니다.",
        }
    return {
        "type": OX,
        "question": sentence,
        "options": list(OX_OPTIONS),
        "answer": "O",
        "answer_index": 0,
        "explanation": "원문에 나온 그대로의 문장입니다.",
    }


def _make_question(sentence: str, keyword: str, qtype: str,
                   keywords: list[str], rng: random.Random) -> dict | None:
    if qtype == OX:
        return _make_ox_question(sentence, keyword, keywords, rng)
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

    quiz_type: "객관식", "빈칸형", "OX형", "혼합"(객관식→빈칸형→OX형 순서로 번갈아 출제) 중 하나.
    핵심 용어나 후보 문장이 부족하면 만들 수 있는 만큼만 돌려줍니다.
    """
    if quiz_type not in (MC, CLOZE, OX, MIXED):
        raise ValueError(f"알 수 없는 문제 유형입니다: {quiz_type}")
    rng = random.Random(seed)
    keywords = extract_keywords_tfidf(text, top_n=30)
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
            qtype = MIXED_ORDER[len(questions) % len(MIXED_ORDER)]
        else:
            qtype = quiz_type
        question = _make_question(sentence, keyword, qtype, keywords, rng)
        if question is None:
            # 객관식을 만들 수 없으면 빈칸형으로 대체합니다.
            question = _make_question(sentence, keyword, CLOZE, keywords, rng)
        used_sentences.add(sentence)
        questions.append(question)
    return questions
