"""StudyQuiz 제한시간 퀴즈 — 별도 실행 가능한 Tkinter GUI.

새 파일로 추가하기만 하면 됩니다. 기존 팀원의 파일은 수정하지 않습니다.
실행 (프로젝트 루트에서): python -m studyquiz.Timer

필요한 파일: studyquiz/wrongAnswer.py, studyquiz/studyStats.py
"""
from __future__ import annotations

import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from studyquiz.extract import extract_text_from_bytes
from studyquiz.grade import grade
from studyquiz.quizgen import generate_quiz, MC, CLOZE, OX, MIXED
from .wrongAnswer import DEFAULT_OUTPUT_DIR, save_wrong_answers
from .studyStats import record_result


QUESTION_TYPES = (MIXED, MC, CLOZE, OX)


def remaining_seconds(deadline: float, now: float) -> int:
    """경과시간 오차가 누적되지 않도록 절대 종료시간을 기준으로 계산."""
    return max(0, math.ceil(deadline - now))


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class TimedQuizApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("StudyQuiz — 제한시간 퀴즈 + 오답노트")
        self.root.geometry("930x790")
        self.root.minsize(680, 590)

        self.questions: list[dict] = []
        self.answer_vars: list[tk.StringVar] = []
        self.answer_controls: list[tk.Widget] = []
        self.deadline: float | None = None
        self.started_at: float | None = None
        self.timer_job: str | None = None
        self.finished = True

        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="제한시간 퀴즈", font=("Malgun Gothic", 16, "bold")).pack(anchor="w")
        ttk.Label(top, text="강의 자료를 붙여넣거나 파일을 불러와 퀴즈를 생성합니다.").pack(anchor="w", pady=(3, 8))

        row = ttk.Frame(top)
        row.pack(fill="x")
        ttk.Button(row, text="TXT / PDF 열기", command=self.open_file).pack(side="left")
        self.source_label = ttk.Label(row, text="  파일을 선택하지 않았습니다.")
        self.source_label.pack(side="left")

        self.source_text = scrolledtext.ScrolledText(top, height=5, wrap="word")
        self.source_text.pack(fill="x", pady=(8, 8))

        options = ttk.Frame(top)
        options.pack(fill="x")
        ttk.Label(options, text="문제 수").pack(side="left")
        self.count_var = tk.IntVar(value=5)
        ttk.Spinbox(options, from_=1, to=20, width=5, textvariable=self.count_var).pack(side="left", padx=(5, 16))
        ttk.Label(options, text="시간(분)").pack(side="left")
        self.minutes_var = tk.IntVar(value=5)
        ttk.Spinbox(options, from_=1, to=120, width=5, textvariable=self.minutes_var).pack(side="left", padx=(5, 16))
        ttk.Label(options, text="문제 유형").pack(side="left")
        self.type_var = tk.StringVar(value=MIXED)
        ttk.Combobox(options, textvariable=self.type_var, values=QUESTION_TYPES,
                     width=9, state="readonly").pack(side="left", padx=5)

        actions = ttk.Frame(top)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="퀴즈 시작 / 새로 시작", command=self.start_quiz).pack(side="left")
        self.submit_button = ttk.Button(actions, text="제출 및 채점", command=self.submit_quiz, state="disabled")
        self.submit_button.pack(side="left", padx=8)
        self.timer_label = ttk.Label(actions, text="--:--", font=("Consolas", 20, "bold"))
        self.timer_label.pack(side="right")
        ttk.Label(actions, text="남은 시간").pack(side="right", padx=8)

        self.status_label = ttk.Label(top, text="시작 버튼을 눌러 주세요.")
        self.status_label.pack(fill="x", pady=(8, 0))
        ttk.Separator(self.root).pack(fill="x")

        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=12, pady=8)
        self.canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.question_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.question_frame, anchor="nw")
        self.question_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        bottom = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        ttk.Label(bottom, text="채점 및 오답노트 결과").pack(anchor="w")
        self.result_box = scrolledtext.ScrolledText(bottom, height=5, wrap="word", state="disabled")
        self.result_box.pack(fill="x", pady=(3, 0))

    def _set_result(self, content: str) -> None:
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", content)
        self.result_box.configure(state="disabled")

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="강의 자료 선택",
            filetypes=[("강의 자료", "*.txt *.pdf"), ("TXT", "*.txt"), ("PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            selected = Path(path)
            text = extract_text_from_bytes(selected.read_bytes(), selected.name)
        except (Exception, SystemExit) as exc:
            messagebox.showerror("파일 열기 실패", str(exc))
            return
        self.source_text.delete("1.0", "end")
        self.source_text.insert("1.0", text)
        self.source_label.configure(text=f"  {selected.name}")

    def _cancel_timer(self) -> None:
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def start_quiz(self) -> None:
        if not self.finished and not messagebox.askyesno(
            "진행 중인 퀴즈", "현재 퀴즈를 종료하고 새로운 퀴즈를 시작할까요?\n현재 답안은 저장되지 않습니다."
        ):
            return
        text = self.source_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("입력 필요", "강의 자료 텍스트를 입력하거나 파일을 열어 주세요.")
            return
        try:
            count = self.count_var.get()
            minutes = self.minutes_var.get()
            if not 1 <= count <= 20:
                raise ValueError("문제 수는 1~20개 사이여야 합니다.")
            if not 1 <= minutes <= 120:
                raise ValueError("제한시간은 1~120분 사이여야 합니다.")
            selected_type = self.type_var.get()
            if selected_type not in QUESTION_TYPES:
                raise ValueError("문제 유형을 다시 선택해 주세요.")
            questions = generate_quiz(text, num_questions=count, quiz_type=selected_type)
            if not questions:
                raise ValueError("문제를 생성하지 못했습니다. 강의 자료를 더 길게 입력해 주세요.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("퀴즈 생성 실패", str(exc))
            return

        self._cancel_timer()
        self.questions = questions
        self.finished = False
        self._build_questions()
        self.submit_button.configure(state="normal")
        self._set_result("")
        if len(questions) < count:
            self.status_label.configure(text=f"강의 자료에서 {len(questions)}개 문제만 생성되었습니다.")
        else:
            self.status_label.configure(text="퀴즈가 시작되었습니다. 제한시간 내에 답안을 제출하세요.")
        self.started_at = time.monotonic()
        self.deadline = self.started_at + (minutes * 60)
        self._update_timer()

    def _build_questions(self) -> None:
        for child in self.question_frame.winfo_children():
            child.destroy()
        self.answer_vars.clear()
        self.answer_controls.clear()
        for idx, question in enumerate(self.questions, start=1):
            block = ttk.LabelFrame(self.question_frame, text=f"{idx}번 · {question.get('type', '문제')}", padding=10)
            block.pack(fill="x", pady=(0, 8))
            ttk.Label(block, text=str(question.get("question", "")), wraplength=780,
                      justify="left").pack(anchor="w", fill="x", pady=(0, 5))
            answer_var = tk.StringVar(value="")
            self.answer_vars.append(answer_var)
            options = question.get("options")
            if options:
                for option in options:
                    button = ttk.Radiobutton(block, text=str(option), value=str(option), variable=answer_var)
                    button.pack(anchor="w", pady=1)
                    self.answer_controls.append(button)
            else:
                field = ttk.Entry(block, textvariable=answer_var, width=70)
                field.pack(anchor="w", fill="x", pady=(4, 0))
                self.answer_controls.append(field)
        self.canvas.yview_moveto(0)

    def _update_timer(self) -> None:
        if self.finished or self.deadline is None:
            return
        seconds = remaining_seconds(self.deadline, time.monotonic())
        self.timer_label.configure(text=format_duration(seconds))
        if seconds == 0:
            self.submit_quiz(timed_out=True)
            return
        self.timer_job = self.root.after(200, self._update_timer)

    def submit_quiz(self, timed_out: bool = False) -> None:
        if self.finished or not self.questions:
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            timed_out = True
        self.finished = True  # 중복 제출/타이머 재진입 방지
        self._cancel_timer()
        self.submit_button.configure(state="disabled")
        if timed_out:
            self.timer_label.configure(text="00:00")
        for control in self.answer_controls:
            control.configure(state="disabled")

        answers = [var.get() for var in self.answer_vars]
        result = grade(self.questions, answers)
        wrong_count = result["total"] - result["correct"]
        summary = (f"{'시간 종료 - 자동 제출' if timed_out else '제출 완료'}\n"
                   f"점수: {result['score']}점 | 정답 {result['correct']} / {result['total']} | "
                   f"오답 {wrong_count}\n")
        self.status_label.configure(text=f"채점 완료 · {result['score']}점")
        try:
            elapsed = time.monotonic() - self.started_at if self.started_at is not None else None
            record_result(result, duration_seconds=elapsed, timed_out=timed_out)
            summary += "학습 통계에 시험 기록을 저장했습니다.\n"
        except (OSError, ValueError, TypeError) as exc:
            summary += f"학습 통계 저장 실패: {exc}\n"
        details = []
        for idx, r in enumerate(result["results"], start=1):
            mark = "O" if r["is_correct"] else "X"
            details.append(f"{idx}번 [{mark}] {r['feedback']}")
        try:
            note_path = save_wrong_answers(result, output_dir=DEFAULT_OUTPUT_DIR)
            if note_path is not None:
                summary += f"오답노트 자동 저장: {note_path}\n"
            else:
                summary += "전부 정답! 저장할 오답이 없습니다.\n"
        except OSError as exc:
            summary += f"오답노트 저장 실패: {exc}\n"
        self._set_result(summary + "\n".join(details))

    def _on_close(self) -> None:
        self._cancel_timer()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TimedQuizApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
