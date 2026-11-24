"""StudyQuiz 오답노트 저장 모듈.

기존 studyquiz.grade.grade()의 결과 dict를 받아 오답만 TXT로 저장합니다.
기존 프로젝트의 다른 파일을 수정할 필요가 없습니다.

단독 사용 예시:
    python wrong_answer.py grade_result.json

코드에서 사용:
    from wrong_answer import save_wrong_answers
    path = save_wrong_answers(grade_result)
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import uuid


DEFAULT_OUTPUT_DIR = Path.home() / "StudyQuiz" / "wrong_notes"


def get_wrong_answers(grade_result: dict) -> list[dict]:
    """grade() 결과에서 실제 오답만 골라 원래 문제 번호와 함께 반환합니다."""
    if not isinstance(grade_result, dict):
        raise TypeError("채점 결과는 dict 형태여야 합니다.")
    results = grade_result.get("results")
    if not isinstance(results, list):
        raise ValueError("채점 결과에 'results' 리스트가 없습니다.")
    return [
        {"number": index, **item}
        for index, item in enumerate(results, start=1)
        if isinstance(item, dict) and item.get("is_correct") is False
    ]


def format_wrong_answers(
    grade_result: dict, *, title: str = "StudyQuiz 오답노트", created_at: datetime | None = None
) -> str:
    """오답노트를 사람이 읽기 쉬운 한글 텍스트로 변환합니다."""
    wrong = get_wrong_answers(grade_result)
    created_at = created_at or datetime.now()
    total = grade_result.get("total", len(grade_result["results"]))
    correct = grade_result.get("correct", total - len(wrong))
    score = grade_result.get("score", 0)

    lines = [
        f"{title}",
        "=" * 48,
        f"작성 일시: {created_at:%Y-%m-%d %H:%M:%S}",
        f"시험 결과: {score}점 / 전체 {total}문제 / 정답 {correct}개 / 오답 {len(wrong)}개",
        "=" * 48,
    ]
    if not wrong:
        lines.append("오답이 없습니다. 모든 문제를 맞혔습니다!")
    for item in wrong:
        lines.extend([
            "",
            f"[{item['number']}번] {item.get('type') or '문제'}",
            f"문제: {item.get('question') or '(문제 없음)'}",
            f"제출 답안: {item.get('user_answer') or '(미응답)'}",
            f"정답: {item.get('answer') or '(정답 정보 없음)'}",
            f"해설: {item.get('feedback') or '(해설 없음)'}",
            "-" * 48,
        ])
    return "\n".join(lines) + "\n"


def save_wrong_answers(
    grade_result: dict,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    title: str = "StudyQuiz 오답노트",
    save_when_perfect: bool = False,
) -> Path | None:
    """오답을 고유한 TXT 파일로 저장합니다. 오답이 없으면 기본적으로 저장하지 않습니다.

    반환값: 생성한 파일 Path, 오답이 없을 때는 None.
    """
    wrong = get_wrong_answers(grade_result)
    if not wrong and not save_when_perfect:
        return None
    folder = Path(output_dir).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now()
    content = format_wrong_answers(grade_result, title=title, created_at=created_at)

    # 동시에 여러 번 실행해도 기존 오답노트를 덮어쓰지 않습니다.
    for _ in range(5):
        suffix = uuid.uuid4().hex[:8]
        path = folder / f"wrong_notes_{created_at:%Y%m%d_%H%M%S}_{suffix}.txt"
        try:
            with path.open("x", encoding="utf-8") as f:
                f.write(content)
            return path
        except FileExistsError:
            continue
    raise FileExistsError("서로 다른 오답노트 파일 이름을 만들지 못했습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="StudyQuiz 채점 JSON을 오답노트 TXT로 저장")
    parser.add_argument("result_json", type=Path, help="grade()의 반환값을 저장한 JSON 파일")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="오답노트 출력 폴더")
    parser.add_argument("--save-perfect", action="store_true",
                        help="전부 맞혀도 결과 파일을 저장")
    args = parser.parse_args()
    try:
        data = json.loads(args.result_json.read_text(encoding="utf-8"))
        path = save_wrong_answers(
            data, output_dir=args.output_dir, save_when_perfect=args.save_perfect
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        parser.exit(1, f"오답노트 저장 실패: {exc}\n")
    if path is None:
        print("오답이 없으므로 오답노트를 저장하지 않았습니다.")
    else:
        print(f"오답노트 저장 완료: {path}")


if __name__ == "__main__":
    main()
