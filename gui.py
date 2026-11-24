"""StudyQuiz 데스크톱 실행기 (tkinter).

명령어를 외우지 않아도 창 하나에서 요약 → 퀴즈 풀기 → 채점까지 할 수 있습니다.
파이썬 표준 라이브러리(tkinter)만 사용합니다.

실행:  python gui.py   (Windows는 run.bat 더블클릭)
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from studyquiz.extract import read_text, ScannedDocumentError
from studyquiz.grade import grade
from studyquiz.quizgen import generate_quiz, MC, CLOZE, OX, MIXED
from studyquiz.summarize import summarize

APP_TITLE = "StudyQuiz — 강의 자료 요약 + 자동 퀴즈"
EXAMPLE_FILE = Path(__file__).resolve().parent / "examples" / "sample_lecture.txt"
QUIZ_TYPES = [MIXED, MC, CLOZE, OX]
COLOR_OK = "#1a7f37"
COLOR_NO = "#c62828"
COLOR_CARD = "#f6f8fa"


def build_quiz(text: str, num: int, snum: int, quiz_type: str = MIXED,
               seed: int | None = None) -> tuple[list[str], list[dict]]:
    """입력 텍스트로 (요약 문장 목록, 문제 목록)을 만듭니다. 화면과 분리해 테스트할 수 있습니다."""
    text = (text or "").strip()
    if not text:
        raise ValueError("강의 자료 텍스트를 입력하거나 파일을 열어 주세요.")
    summary = summarize(text, snum)
    questions = generate_quiz(text, num, quiz_type, seed=seed)
    if not questions:
        raise ValueError("문제를 만들 수 없습니다. 텍스트를 더 길게 입력해 주세요.")
    return summary, questions


class StudyQuizApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.questions: list[dict] = []
        self.answer_vars: list[tk.StringVar] = []
        self.feedback_labels: list[tk.Label] = []
        self.wrap_labels: list[tk.Label] = []

        root.title(APP_TITLE)
        root.geometry("900x780")
        root.minsize(700, 560)
        self._setup_fonts()
        self._build_input_area()
        self._build_options_row()
        self._build_result_area()

    # ------------------------------------------------------------------ 화면 구성
    def _setup_fonts(self) -> None:
        families = set(tkfont.families(self.root))
        for name in ("Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo",
                     "Noto Sans CJK KR", "NanumGothic"):
            if name in families:
                for fname in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
                    tkfont.nametofont(fname).configure(family=name, size=10)
                break
        self.bold = tkfont.nametofont("TkDefaultFont").copy()
        self.bold.configure(weight="bold")
        self.big = tkfont.nametofont("TkDefaultFont").copy()
        self.big.configure(size=12, weight="bold")

    def _build_input_area(self) -> None:
        top = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        top.pack(fill="x")
        ttk.Label(top, text="강의 자료", font=self.big).pack(side="left")
        ttk.Button(top, text="예제 불러오기", command=self.load_example).pack(side="right")
        ttk.Button(top, text="파일 열기 (txt/pdf)", command=self.open_file).pack(
            side="right", padx=6)
        self.file_label = ttk.Label(top, text="텍스트를 붙여넣거나 파일을 여세요.",
                                    foreground="#57606a")
        self.file_label.pack(side="left", padx=10)

        self.input_text = ScrolledText(self.root, height=8, wrap="word")
        self.input_text.pack(fill="x", padx=10, pady=6)

    def _build_options_row(self) -> None:
        row = ttk.Frame(self.root, padding=(10, 0))
        row.pack(fill="x")
        ttk.Label(row, text="요약 문장 수").pack(side="left")
        self.snum = tk.IntVar(value=3)
        ttk.Spinbox(row, from_=1, to=10, width=4, textvariable=self.snum).pack(
            side="left", padx=(4, 14))
        ttk.Label(row, text="문제 수").pack(side="left")
        self.num = tk.IntVar(value=5)
        ttk.Spinbox(row, from_=1, to=20, width=4, textvariable=self.num).pack(
            side="left", padx=(4, 14))
        ttk.Label(row, text="문제 유형").pack(side="left")
        self.qtype = tk.StringVar(value=MIXED)
        ttk.Combobox(row, values=QUIZ_TYPES, textvariable=self.qtype, width=8,
                     state="readonly").pack(side="left", padx=(4, 14))
        ttk.Button(row, text="요약 + 퀴즈 만들기", command=self.make_quiz).pack(side="right")

    def _build_result_area(self) -> None:
        ttk.Separator(self.root).pack(fill="x", padx=10, pady=8)

        ttk.Label(self.root, text="핵심 요약", font=self.big).pack(anchor="w", padx=10)
        self.summary_box = ScrolledText(self.root, height=5, wrap="word",
                                        state="disabled", background=COLOR_CARD)
        self.summary_box.pack(fill="x", padx=10, pady=(4, 8))

        head = ttk.Frame(self.root, padding=(10, 0))
        head.pack(fill="x")
        ttk.Label(head, text="퀴즈", font=self.big).pack(side="left")
        self.grade_button = ttk.Button(head, text="채점하기", command=self.grade_quiz,
                                       state="disabled")
        self.grade_button.pack(side="right")
        self.score_label = ttk.Label(head, text="", font=self.big)
        self.score_label.pack(side="right", padx=12)

        # 문제가 많아도 볼 수 있도록 스크롤 가능한 영역을 만듭니다.
        holder = ttk.Frame(self.root)
        holder.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.canvas = tk.Canvas(holder, highlightthickness=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.quiz_frame = ttk.Frame(self.canvas)
        self.quiz_frame.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self._quiz_window = self.canvas.create_window((0, 0), window=self.quiz_frame,
                                                      anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        # 마우스가 퀴즈 영역 위에 있을 때만 휠로 스크롤합니다.
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))

    def _on_canvas_resize(self, event) -> None:
        self.canvas.itemconfigure(self._quiz_window, width=event.width)
        for label in self.wrap_labels:
            label.configure(wraplength=max(200, event.width - 40))

    def _bind_wheel(self, on: bool) -> None:
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows/mac
            self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
            self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(seq)

    def _on_mousewheel(self, event) -> None:
        step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * max(1, abs(event.delta) // 120), "units")

    # ------------------------------------------------------------------ 동작
    def _set_input(self, text: str, label: str) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)
        self.file_label.configure(text=label)

    def load_example(self) -> None:
        try:
            self._set_input(read_text(EXAMPLE_FILE), f"예제: {EXAMPLE_FILE.name}")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"예제 파일을 읽을 수 없습니다.\n{exc}")

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="강의 자료 열기",
            filetypes=[("강의 자료", "*.txt *.pdf"), ("텍스트", "*.txt"), ("PDF", "*.pdf"),
                       ("모든 파일", "*.*")])
        if not path:
            return
        try:
            text = read_text(path)
        except ScannedDocumentError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        except SystemExit as exc:  # pypdf 미설치 등 안내 메시지
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"파일을 읽을 수 없습니다.\n{exc}")
            return
        self._set_input(text, f"파일: {Path(path).name}")

    def make_quiz(self) -> None:
        try:
            summary, questions = build_quiz(
                self.input_text.get("1.0", "end"), int(self.num.get()),
                int(self.snum.get()), self.qtype.get())
        except (ValueError, tk.TclError) as exc:
            messagebox.showinfo(APP_TITLE, str(exc))
            return
        self._show_summary(summary)
        self._show_questions(questions)

    def _show_summary(self, summary: list[str]) -> None:
        self.summary_box.configure(state="normal")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", "\n".join(f"• {s}" for s in summary))
        self.summary_box.configure(state="disabled")

    def _show_questions(self, questions: list[dict]) -> None:
        for child in self.quiz_frame.winfo_children():
            child.destroy()
        self.questions = questions
        self.answer_vars, self.feedback_labels, self.wrap_labels = [], [], []
        self.score_label.configure(text="")
        wrap = max(200, self.canvas.winfo_width() - 40)

        for i, q in enumerate(questions):
            card = tk.Frame(self.quiz_frame, background=COLOR_CARD, padx=10, pady=8)
            card.pack(fill="x", pady=4)
            title = tk.Label(card, text=f"[{i + 1}] ({q['type']}) {q['question']}",
                             background=COLOR_CARD, font=self.bold, justify="left",
                             anchor="w", wraplength=wrap)
            title.pack(fill="x")
            self.wrap_labels.append(title)

            var = tk.StringVar(value="")
            self.answer_vars.append(var)
            if q["type"] == OX:
                self._ox_buttons(card, var)
            elif q.get("options"):
                for option in q["options"]:
                    tk.Radiobutton(card, text=option, value=option, variable=var,
                                   background=COLOR_CARD, activebackground=COLOR_CARD,
                                   highlightthickness=0, borderwidth=0,
                                   anchor="w").pack(fill="x", pady=1)
            else:
                row = tk.Frame(card, background=COLOR_CARD)
                row.pack(fill="x", pady=(4, 0))
                tk.Label(row, text="빈칸에 들어갈 용어:", background=COLOR_CARD).pack(side="left")
                ttk.Entry(row, textvariable=var, width=24).pack(side="left", padx=6)

            feedback = tk.Label(card, text="", background=COLOR_CARD, justify="left",
                                anchor="w", wraplength=wrap)
            feedback.pack(fill="x", pady=(4, 0))
            self.feedback_labels.append(feedback)
            self.wrap_labels.append(feedback)

        self.grade_button.configure(state="normal")
        self.canvas.yview_moveto(0)

    def _ox_buttons(self, parent: tk.Widget, var: tk.StringVar) -> None:
        """OX형은 큼직한 O / X 토글 버튼으로 답합니다."""
        row = tk.Frame(parent, background=COLOR_CARD)
        row.pack(anchor="w", pady=(6, 0))
        for value, color in (("O", "#1565c0"), ("X", COLOR_NO)):
            tk.Radiobutton(row, text=value, value=value, variable=var, indicatoron=False,
                           width=5, font=self.big, foreground=color,
                           selectcolor="#ffe08a", relief="raised",
                           offrelief="raised").pack(side="left", padx=(0, 8))

    def grade_quiz(self) -> None:
        if not self.questions:
            return
        answers = [var.get() for var in self.answer_vars]
        result = grade(self.questions, answers)
        for label, r in zip(self.feedback_labels, result["results"]):
            mark = "✔" if r["is_correct"] else "✘"
            label.configure(text=f"{mark} {r['feedback']}",
                            foreground=COLOR_OK if r["is_correct"] else COLOR_NO)
        color = COLOR_OK if result["score"] >= 60 else COLOR_NO
        self.score_label.configure(
            text=f"{result['score']}점 ({result['correct']}/{result['total']})",
            foreground=color)


def main() -> None:
    root = tk.Tk()
    StudyQuizApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
