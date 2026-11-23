"""텍스트 추출 모듈.

파일이나 바이트에서 본문 텍스트를 읽어 오고, 텍스트를 문장 단위로 나눕니다.
- .txt 등 일반 텍스트 파일: 표준 라이브러리로 바로 읽습니다.
- .pdf 파일: pypdf가 설치되어 있을 때만 읽습니다(선택적 의존성).
- 스캔본 PDF(텍스트 층이 거의 없는 PDF): OCR 패키지(pypdfium2 또는 PyMuPDF +
  rapidocr-onnxruntime)가 설치되어 있으면 OCR로 폴백합니다. 패키지가 없으면
  ScannedDocumentError로 이유를 알립니다.
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

_PDF_HELP = (
    "PDF 파일을 읽으려면 pypdf 패키지가 필요합니다.\n"
    "다음 명령으로 설치한 뒤 다시 실행해 주세요:  pip install pypdf"
)

_OCR_HELP = (
    "이 PDF는 텍스트가 거의 없는 스캔본으로 보입니다.\n"
    "스캔본을 읽으려면 OCR 패키지가 필요합니다. 다음 명령으로 설치한 뒤 "
    "다시 실행해 주세요:  pip install pypdfium2 rapidocr-onnxruntime"
)


class ScannedDocumentError(RuntimeError):
    """스캔본 PDF인데 OCR 패키지가 없어 읽을 수 없을 때 발생합니다."""


def needs_ocr(text: str, page_count: int | None = None) -> bool:
    """PDF에서 뽑은 텍스트가 너무 적어 스캔본으로 보이면 True를 돌려줍니다.

    기준: 텍스트가 비어 있거나, 페이지당 평균 글자 수가 30자 미만이거나,
    페이지 수를 모를 경우 전체가 50자 미만이면 스캔본으로 판단합니다.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True
    if page_count:
        return len(stripped) / page_count < 30
    return len(stripped) < 50


# ---------------------------------------------------------------------------
# PDF 텍스트 층 추출
# ---------------------------------------------------------------------------

def _pdf_text_from_bytes(data: bytes) -> tuple[str, int]:
    """pypdf로 PDF 바이트에서 (본문 텍스트, 페이지 수)를 추출합니다."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages), len(reader.pages)


def read_pdf(path: Path) -> str:
    """pypdf로 PDF의 모든 페이지 텍스트를 추출합니다(스캔본이면 OCR 폴백)."""
    return extract_text_from_bytes(Path(path).read_bytes(), Path(path).name)


def read_text(path) -> str:
    """파일 경로를 받아 본문 텍스트(문자열)를 돌려줍니다."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"파일을 찾을 수 없습니다: {p}")
    if p.suffix.lower() == ".pdf":
        return read_pdf(p)
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# OCR 폴백 (전부 선택적 의존성, 지연 임포트)
# ---------------------------------------------------------------------------

def _ocr_available() -> bool:
    """OCR에 필요한 패키지(페이지 렌더러 + RapidOCR)가 모두 있는지 확인합니다."""
    import importlib.util

    has_renderer = any(
        importlib.util.find_spec(name) is not None
        for name in ("pypdfium2", "fitz")
    )
    has_engine = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    return has_renderer and has_engine


def _render_pages(data: bytes):
    """PDF 페이지를 이미지(numpy 배열) 리스트로 렌더링합니다."""
    import importlib.util

    if importlib.util.find_spec("pypdfium2") is not None:
        import numpy as np
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        images = []
        for page in pdf:
            pil_image = page.render(scale=2.0).to_pil()
            images.append(np.array(pil_image))
        return images

    import fitz  # PyMuPDF
    import numpy as np

    doc = fitz.open(stream=data, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        channels = 4 if pix.alpha else 3
        images.append(
            np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, channels)
        )
    return images


def _ocr_pdf(data: bytes) -> str:
    """스캔본 PDF 바이트를 OCR로 읽어 텍스트를 돌려줍니다.

    OCR 패키지가 없으면 ScannedDocumentError를 발생시킵니다.
    """
    if not _ocr_available():
        raise ScannedDocumentError(_OCR_HELP)
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    page_texts = []
    for image in _render_pages(data):
        result, _ = engine(image)
        if result:
            page_texts.append("\n".join(item[1] for item in result))
    return "\n".join(page_texts)


def _extract_pdf(data: bytes) -> str:
    """PDF 바이트에서 텍스트를 추출하고, 스캔본이면 OCR로 폴백합니다."""
    import importlib.util

    if importlib.util.find_spec("pypdf") is None:
        # 텍스트 층을 읽을 방법이 없으면 OCR이라도 시도하고, 그것도 안 되면 안내합니다.
        if _ocr_available():
            return _ocr_pdf(data)
        raise SystemExit(_PDF_HELP)
    text, page_count = _pdf_text_from_bytes(data)
    if needs_ocr(text, page_count):
        return _ocr_pdf(data)
    return text


# ---------------------------------------------------------------------------
# 바이트 입력 (웹 업로드 등)
# ---------------------------------------------------------------------------

def extract_text_from_bytes(data: bytes, filename: str) -> str:
    """업로드된 바이트와 파일 이름으로 본문 텍스트를 추출합니다.

    - .pdf: pypdf로 텍스트를 뽑고, 스캔본이면 OCR로 폴백합니다.
    - 그 외(.txt 등): UTF-8로 디코딩하고, 실패하면 CP949로 다시 시도합니다.
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp949", errors="replace")


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
