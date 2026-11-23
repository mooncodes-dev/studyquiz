"""텍스트 추출 모듈.

파일에서 본문 텍스트를 읽어 오고, 텍스트를 문장 단위로 나눕니다.
- .txt 등 일반 텍스트 파일: 표준 라이브러리로 바로 읽습니다.
- .pdf 파일: pypdf가 설치되어 있을 때만 읽습니다(선택적 의존성).
"""
from __future__ import annotations

import re
from pathlib import Path

_PDF_HELP = (
    "PDF 파일을 읽으려면 pypdf 패키지가 필요합니다.\n"
    "다음 명령으로 설치한 뒤 다시 실행해 주세요:  pip install pypdf"
)


def read_pdf(path: Path) -> str:
    """pypdf로 PDF의 모든 페이지 텍스트를 추출합니다."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit(_PDF_HELP)
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def read_text(path) -> str:
    """파일 경로를 받아 본문 텍스트(문자열)를 돌려줍니다."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"파일을 찾을 수 없습니다: {p}")
    if p.suffix.lower() == ".pdf":
        return read_pdf(p)
    return p.read_text(encoding="utf-8")


def split_sentences(text: str) -> list[str]:
    """텍스트를 문장 리스트로 나눕니다.

    마침표/물음표/느낌표 뒤의 공백을 기준으로 나누며,
    줄바꿈과 연속 공백은 하나의 공백으로 정리합니다.
    """
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]
