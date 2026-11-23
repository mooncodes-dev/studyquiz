"""StudyQuiz - 강의 자료 요약 + 자동 퀴즈 생성기.

파이썬 표준 라이브러리만으로 동작하는 학습 도구입니다.
(PDF 입력만 선택적 의존성 pypdf를 사용합니다.)
"""

__version__ = "1.0.0"

from .summarize import summarize, extract_keywords
from .quizgen import generate_quiz
from .grade import grade

__all__ = ["summarize", "extract_keywords", "generate_quiz", "grade", "__version__"]
