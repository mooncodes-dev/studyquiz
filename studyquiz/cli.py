"""StudyQuiz 명령줄 인터페이스(CLI).

사용법:
    python -m studyquiz.cli summarize <파일> [--num 3]
    python -m studyquiz.cli quiz <파일> [--num 5] [--type 혼합] [--out quiz.json] [--interactive]
    python -m studyquiz.cli grade <quiz.json> <answers.json>

quiz --out 으로 저장한 JSON에는 정답이 포함됩니다(답안지).
grade의 answers.json은 답 문자열의 JSON 배열입니다. 예: ["프로세스", "2", ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extract import read_text
from .summarize import summarize
from .quizgen import generate_quiz, MC, CLOZE, MIXED
from .grade import grade


def _print_questions(questions: list[dict], show_answers: bool = False) -> None:
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}] ({q['type']}) {q['question']}")
        if q["type"] == MC:
            for j, option in enumerate(q["options"], 1):
                print(f"    {j}. {option}")
        if show_answers:
            print(f"    -> 정답: {q['answer']}")


def _print_grade(result: dict) -> None:
    print("\n===== 채점 결과 =====")
    for i, r in enumerate(result["results"], 1):
        mark = "O" if r["is_correct"] else "X"
        print(f"[{i}] {mark} {r['feedback']} (내 답: {r['user_answer']})")
    print(f"\n총 {result['total']}문제 중 {result['correct']}문제 정답 "
          f"-> {result['score']}점")


def cmd_summarize(args) -> int:
    text = read_text(args.file)
    summary = summarize(text, args.num)
    if not summary:
        print("요약할 문장이 없습니다. 입력 텍스트를 확인해 주세요.")
        return 1
    print(f"===== 요약 (상위 {len(summary)}문장) =====")
    for sentence in summary:
        print(f"- {sentence}")
    return 0


def cmd_quiz(args) -> int:
    text = read_text(args.file)
    questions = generate_quiz(text, args.num, args.type, seed=args.seed)
    if not questions:
        print("문제를 만들 수 없습니다. 텍스트가 너무 짧거나 핵심 용어가 부족합니다.")
        return 1
    _print_questions(questions, show_answers=args.show_answers)
    if args.out:
        payload = {"source": str(args.file), "questions": questions}
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n문제와 정답을 {args.out} 파일로 저장했습니다.")
    if args.interactive:
        print("\n===== 바로 풀기 =====")
        answers = []
        for i, q in enumerate(questions, 1):
            prompt = f"[{i}] 답을 입력하세요"
            if q["type"] == MC:
                prompt += " (보기 번호 또는 보기 내용)"
            answers.append(input(prompt + ": "))
        _print_grade(grade(questions, answers))
    return 0


def cmd_grade(args) -> int:
    quiz_data = json.loads(Path(args.quiz_json).read_text(encoding="utf-8"))
    questions = quiz_data["questions"] if isinstance(quiz_data, dict) else quiz_data
    answers = json.loads(Path(args.answers_json).read_text(encoding="utf-8"))
    _print_grade(grade(questions, answers))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studyquiz", description="강의 자료 요약 + 자동 퀴즈 생성기")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="강의 자료를 요약합니다")
    p_sum.add_argument("file", help="입력 파일(.txt 또는 pypdf 설치 시 .pdf)")
    p_sum.add_argument("--num", type=int, default=3, help="요약 문장 수 (기본 3)")
    p_sum.set_defaults(func=cmd_summarize)

    p_quiz = sub.add_parser("quiz", help="퀴즈를 생성합니다")
    p_quiz.add_argument("file", help="입력 파일(.txt 또는 pypdf 설치 시 .pdf)")
    p_quiz.add_argument("--num", type=int, default=5, help="문제 수 (기본 5)")
    p_quiz.add_argument("--type", choices=[MC, CLOZE, MIXED], default=MIXED,
                        help="문제 유형 (기본 혼합)")
    p_quiz.add_argument("--seed", type=int, default=None,
                        help="무작위 시드 (같은 값을 주면 같은 문제가 나옵니다)")
    p_quiz.add_argument("--out", help="문제+정답 JSON 저장 경로")
    p_quiz.add_argument("--show-answers", action="store_true", help="정답도 함께 출력")
    p_quiz.add_argument("--interactive", action="store_true",
                        help="문제를 바로 풀고 채점까지 받습니다")
    p_quiz.set_defaults(func=cmd_quiz)

    p_grade = sub.add_parser("grade", help="저장된 퀴즈 JSON과 답안 JSON으로 채점합니다")
    p_grade.add_argument("quiz_json", help="quiz --out 으로 저장한 파일")
    p_grade.add_argument("answers_json", help="답 문자열 배열 JSON 파일")
    p_grade.set_defaults(func=cmd_grade)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
