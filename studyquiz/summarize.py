"""추출 요약(extractive summarization) 모듈.

문장 점수를 TF-IDF 방식으로 매겨 핵심 문장을 고릅니다.

- TF-IDF 점수: 문장 안 단어의 (문장 내 빈도 × 역문장빈도)를 문장 길이로 나눈 값.
  문서 전체에 흔한 단어는 가중치가 낮아져, 긴 강의 자료에서도
  "어디에나 나오는 말"이 아니라 그 문단을 대표하는 문장이 뽑힙니다.
- 위치 보너스: 문단/섹션의 첫 문장에 작은 가산점을 줍니다.
- MMR 다양성: 이미 고른 문장과 단어가 많이 겹치는 문장은 감점해,
  거의 같은 문장이 나란히 뽑히지 않게 합니다.

토큰화는 두 경로가 있습니다.
- kiwipiepy가 설치되어 있으면 Kiwi 형태소 분석기로 명사·외래어 표기를 뽑습니다.
- 없으면 한글 덩어리에서 조사/어미를 단순 규칙으로 떼어 내는 간이 토큰화를 씁니다.
어느 경로든 표준 라이브러리만으로 동작하는 것이 기본이며, Kiwi는 선택 사항입니다.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .extract import split_sentences

# 의미 없는 고빈도 단어(불용어). 한국어는 한 글자 토큰이 길이 규칙으로도 걸러집니다.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "as", "at", "by", "from", "we", "you", "they", "can", "will",
    "것", "수", "등", "때", "더", "또", "및", "즉", "곧", "왜", "무엇",
    "때문", "경우", "정도", "자체", "통해", "대해", "위해", "여러", "모든",
    "이런", "그런", "저런", "어떤", "각", "뒤", "앞", "안", "밖", "중",
}

# 긴 것부터 검사해야 "에서는"이 "는"보다 먼저 떨어집니다.
_PARTICLES = (
    "에서는", "에서", "에게", "까지", "부터", "으로", "라고", "처럼", "보다",
    "입니다", "습니다", "합니다", "됩니다", "이다", "이며", "이고", "하는", "되는",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
    "요", "다",
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
_KOREAN_RE = re.compile(r"[가-힣]+")

# 문단의 첫 문장에 주는 가산점과 MMR 감점 강도(0~1, 클수록 중복을 강하게 피함).
_POSITION_BONUS = 0.15
_MMR_LAMBDA = 0.6


# ---------------------------------------------------------------------------
# Kiwi(선택) 토큰화
# ---------------------------------------------------------------------------

_KIWI = None
_KIWI_TRIED = False


def _get_kiwi():
    """kiwipiepy가 설치되어 있으면 Kiwi 인스턴스를, 아니면 None을 돌려줍니다."""
    global _KIWI, _KIWI_TRIED
    if _KIWI_TRIED:
        return _KIWI
    _KIWI_TRIED = True
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        _KIWI = None
    else:
        _KIWI = Kiwi()
    return _KIWI


def kiwi_available() -> bool:
    """Kiwi 형태소 분석기를 쓸 수 있는지 알려줍니다."""
    return _get_kiwi() is not None


def _tokenize_with_kiwi(text: str) -> list[str]:
    """Kiwi로 명사(NNG/NNP)와 외래어 표기(SL)만 핵심어 토큰으로 뽑습니다."""
    kiwi = _get_kiwi()
    tokens: list[str] = []
    for token in kiwi.tokenize(text or ""):
        if token.tag not in ("NNG", "NNP", "SL"):
            continue
        word = token.form.lower()
        if len(word) < 2 or word in _STOPWORDS:
            continue
        tokens.append(word)
    return tokens


# ---------------------------------------------------------------------------
# 간이 규칙 토큰화 (기본 경로)
# ---------------------------------------------------------------------------

def _strip_particle(word: str) -> str:
    """한국어 단어 끝의 조사를 단순 규칙으로 제거합니다(남는 길이가 2 이상일 때만)."""
    for particle in _PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def _tokenize_simple(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        word = raw.lower()
        if _KOREAN_RE.fullmatch(word):
            word = _strip_particle(word)
        if len(word) < 2 or word in _STOPWORDS:
            continue
        tokens.append(word)
    return tokens


def tokenize(text: str) -> list[str]:
    """텍스트를 핵심어 토큰 리스트로 바꿉니다.

    kiwipiepy가 설치되어 있으면 Kiwi 형태소 분석을, 아니면 간이 규칙을 씁니다.
    """
    if kiwi_available():
        return _tokenize_with_kiwi(text)
    return _tokenize_simple(text)


# ---------------------------------------------------------------------------
# 빈도/TF-IDF 용어 순위
# ---------------------------------------------------------------------------

def word_frequencies(text: str) -> Counter:
    """문서 전체의 토큰 빈도를 셉니다."""
    return Counter(tokenize(text))


def extract_keywords(text: str, top_n: int = 20) -> list[str]:
    """빈도가 높은 핵심 용어를 순서대로 돌려줍니다(동률이면 사전순)."""
    freq = word_frequencies(text)
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:top_n]]


def _inverse_sentence_frequencies(sentence_tokens: list[list[str]]) -> dict[str, float]:
    """단어별 역문장빈도(ISF)를 계산합니다. 여러 문장에 흔한 단어일수록 값이 작아집니다."""
    n = len(sentence_tokens)
    doc_freq: Counter = Counter()
    for toks in sentence_tokens:
        doc_freq.update(set(toks))
    return {
        term: math.log((n + 1) / (df + 1)) + 1.0
        for term, df in doc_freq.items()
    }


def extract_keywords_tfidf(text: str, top_n: int = 20) -> list[str]:
    """TF-IDF 점수가 높은 핵심 용어를 순서대로 돌려줍니다(동률이면 사전순).

    점수 = 문서 전체 등장 빈도 × 역문장빈도. 문서 곳곳에 퍼진 흔한 단어보다
    특정 부분에 집중해서 등장하는 개념어가 위로 올라옵니다.
    """
    sentences = split_sentences(text)
    if not sentences:
        return []
    sentence_tokens = [tokenize(s) for s in sentences]
    isf = _inverse_sentence_frequencies(sentence_tokens)
    total_freq = Counter()
    for toks in sentence_tokens:
        total_freq.update(toks)
    ranked = sorted(
        total_freq.items(),
        key=lambda kv: (-(kv[1] * isf[kv[0]]), kv[0]),
    )
    return [word for word, _ in ranked[:top_n]]


# ---------------------------------------------------------------------------
# 요약
# ---------------------------------------------------------------------------

def _paragraph_first_flags(text: str, sentences: list[str]) -> list[bool]:
    """각 문장이 문단(빈 줄로 구분)의 첫 문장인지 표시합니다."""
    flags = [False] * len(sentences)
    if not sentences:
        return flags
    flags[0] = True
    index = 0
    for paragraph in re.split(r"\n\s*\n", text or ""):
        count = len(split_sentences(paragraph))
        if count and index < len(sentences):
            flags[index] = True
        index += count
    return flags


def summarize(text: str, num_sentences: int = 3) -> list[str]:
    """핵심 문장 num_sentences개를 골라 원문 순서의 리스트로 돌려줍니다.

    문장 점수 = TF-IDF 평균(문장 길이로 나눔) + 문단 첫 문장 보너스.
    문장을 하나씩 고를 때마다 이미 고른 문장과 단어 겹침이 큰 문장은
    MMR 방식으로 감점해, 서로 다른 주제의 문장이 골고루 뽑히게 합니다.
    """
    sentences = split_sentences(text)
    if num_sentences <= 0 or not sentences:
        return []
    if len(sentences) <= num_sentences:
        return list(sentences)

    sentence_tokens = [tokenize(s) for s in sentences]
    token_sets = [set(toks) for toks in sentence_tokens]
    isf = _inverse_sentence_frequencies(sentence_tokens)
    first_flags = _paragraph_first_flags(text, sentences)

    base_scores: list[float] = []
    for idx, toks in enumerate(sentence_tokens):
        if toks:
            tf = Counter(toks)
            score = sum(count * isf[term] for term, count in tf.items()) / len(toks)
        else:
            score = 0.0
        if first_flags[idx]:
            score *= 1.0 + _POSITION_BONUS
        base_scores.append(score)

    # 점수 스케일을 0~1로 맞춰 MMR 감점과 비교할 수 있게 합니다.
    peak = max(base_scores) or 1.0
    norm_scores = [s / peak for s in base_scores]

    selected: list[int] = []
    remaining = set(range(len(sentences)))
    while len(selected) < num_sentences and remaining:
        best_idx, best_value = -1, -1.0
        for idx in sorted(remaining):
            penalty = 0.0
            if selected and token_sets[idx]:
                penalty = max(
                    len(token_sets[idx] & token_sets[chosen]) /
                    max(1, len(token_sets[idx] | token_sets[chosen]))
                    for chosen in selected
                )
            value = norm_scores[idx] - _MMR_LAMBDA * penalty
            if value > best_value:
                best_idx, best_value = idx, value
        selected.append(best_idx)
        remaining.discard(best_idx)

    return [sentences[i] for i in sorted(selected)]
