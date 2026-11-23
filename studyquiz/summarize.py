"""추출 요약(extractive summarization) 모듈.

문서 전체의 단어 빈도를 세어, 핵심 단어를 많이 담은 문장에 높은 점수를 주고
상위 N개 문장을 원문 순서대로 돌려줍니다. 별도 모델이나 외부 라이브러리 없이
표준 라이브러리만으로 동작합니다.

토큰화 규칙
- 영문/숫자: 소문자로 통일한 단어 단위
- 한국어: 한글 덩어리를 뽑은 뒤, 자주 붙는 조사/어미를 단순 규칙으로 떼어 냅니다.
  (예: "프로세스는" -> "프로세스") 형태소 분석기를 쓰지 않는 간이 처리입니다.
"""
from __future__ import annotations

import re
from collections import Counter

from .extract import split_sentences

# 의미 없는 고빈도 단어(불용어). 한국어는 한 글자 토큰이 길이 규칙으로도 걸러집니다.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "as", "at", "by", "from", "we", "you", "they", "can", "will",
    "것", "수", "등", "때", "더", "또", "및", "즉", "곧", "왜", "무엇",
}

# 긴 것부터 검사해야 "에서는"이 "는"보다 먼저 떨어집니다.
_PARTICLES = (
    "에서는", "에서", "에게", "까지", "부터", "으로",
    "입니다", "합니다", "됩니다", "이다",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
_KOREAN_RE = re.compile(r"[가-힣]+")


def _strip_particle(word: str) -> str:
    """한국어 단어 끝의 조사를 단순 규칙으로 제거합니다(남는 길이가 2 이상일 때만)."""
    for particle in _PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def tokenize(text: str) -> list[str]:
    """텍스트를 핵심어 토큰 리스트로 바꿉니다."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        word = raw.lower()
        if _KOREAN_RE.fullmatch(word):
            word = _strip_particle(word)
        if len(word) < 2 or word in _STOPWORDS:
            continue
        tokens.append(word)
    return tokens


def word_frequencies(text: str) -> Counter:
    """문서 전체의 토큰 빈도를 셉니다."""
    return Counter(tokenize(text))


def extract_keywords(text: str, top_n: int = 20) -> list[str]:
    """빈도가 높은 핵심 용어를 순서대로 돌려줍니다(동률이면 사전순)."""
    freq = word_frequencies(text)
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:top_n]]


def summarize(text: str, num_sentences: int = 3) -> list[str]:
    """핵심 문장 num_sentences개를 골라 원문 순서의 리스트로 돌려줍니다.

    문장 점수 = 문장 안 토큰들의 (문서 전체 빈도) 평균.
    긴 문장이 무조건 유리해지지 않도록 합이 아닌 평균을 씁니다.
    """
    sentences = split_sentences(text)
    if num_sentences <= 0 or not sentences:
        return []
    if len(sentences) <= num_sentences:
        return list(sentences)

    freq = word_frequencies(text)
    scored: list[tuple[int, float]] = []
    for idx, sentence in enumerate(sentences):
        toks = tokenize(sentence)
        score = sum(freq[t] for t in toks) / len(toks) if toks else 0.0
        scored.append((idx, score))

    top = sorted(scored, key=lambda x: (-x[1], x[0]))[:num_sentences]
    return [sentences[i] for i, _ in sorted(top)]
