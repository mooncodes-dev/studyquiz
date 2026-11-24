"""StudyQuiz 학습 통계 대시보드 (외부 패키지 불필요).

시험 결과를 개인정보/문제 본문 없이 JSONL에 기록하고 통계를 보여준다.
이전에 생성한 오답노트 TXT도 읽는다. 단, 예전 오답노트만으로는
100점 시험이나 유형별 전체 문제 수를 알 수 없어 부분 통계가 된다.

저장소 루트에서 실행:
    python -m studyquiz.studyStats
    python -m studyquiz.studyStats --summary
    python -m studyquiz.studyStats --export results.csv
    python -m studyquiz.studyStats --import-grade graded.json
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import uuid

DEFAULT_ROOT = Path.home() / "StudyQuiz"
DEFAULT_LOG = DEFAULT_ROOT / "study_results.jsonl"
DEFAULT_NOTES_DIR = DEFAULT_ROOT / "wrong_notes"

# 오답노트 TXT는 wrongAnswer.py가 저장하는 형식이다.
_NOTE_SUMMARY = re.compile(
    r"시험 결과:\s*([\d.]+)점\s*/\s*전체\s*(\d+)문제\s*/\s*정답\s*(\d+)개\s*/\s*오답\s*(\d+)개"
)
_NOTE_TYPE = re.compile(r"^\[\d+번\]\s*(.+?)\s*$", re.MULTILINE)


def record_result(grade_result: dict, log_path: str | Path = DEFAULT_LOG, *,
                  duration_seconds: float | None = None,
                  timed_out: bool = False, when: datetime | None = None) -> Path:
    """grade() 결과를 JSONL에 기록한다. 정답/문항 텍스트는 저장하지 않는다."""
    results = grade_result.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("유효한 채점 결과(results)가 필요합니다.")
    total = len(results)
    if not all(isinstance(item, dict) and type(item.get("is_correct")) is bool
               for item in results):
        raise ValueError("각 문제에 is_correct(True/False)가 필요합니다.")
    correct = sum(item["is_correct"] for item in results)
    types = defaultdict(lambda: {"correct": 0, "total": 0})
    for item in results:
        label = str(item.get("type") or "기타")
        types[label]["total"] += 1
        types[label]["correct"] += int(item["is_correct"])
    if duration_seconds is not None and duration_seconds < 0:
        raise ValueError("소요시간은 음수가 될 수 없습니다.")
    created_at = when or datetime.now().astimezone()
    row = {
        "version": 1,
        "id": uuid.uuid4().hex,
        "timestamp": created_at.isoformat(timespec="seconds"),
        "score": round(correct / total * 100, 1),
        "total": total,
        "correct": correct,
        "types": dict(types),
        "timed_out": bool(timed_out),
        "duration_seconds": None if duration_seconds is None else round(duration_seconds, 1),
    }
    file = Path(log_path).expanduser()
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return file


def _parse_timestamp(raw: str) -> datetime:
    stamp = datetime.fromisoformat(raw)
    # 혼합된 시간대 데이터도 정렬 가능하도록 통일된 로컬 naive datetime 사용
    return stamp.astimezone().replace(tzinfo=None) if stamp.tzinfo else stamp


def _load_log(log_path: str | Path) -> tuple[list[dict], list[str]]:
    file = Path(log_path).expanduser()
    if not file.exists():
        return [], []
    sessions, warnings = [], []
    try:
        with file.open(encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    total, correct = int(row["total"]), int(row["correct"])
                    if total <= 0 or not 0 <= correct <= total:
                        raise ValueError("문제 수/정답 수 오류")
                    stamp = _parse_timestamp(row["timestamp"])
                    raw_types = row.get("types", {})
                    type_map = {}
                    for name, val in raw_types.items():
                        n, c = int(val["total"]), int(val["correct"])
                        if not 0 <= c <= n:
                            raise ValueError("유형별 정답 수 오류")
                        type_map[str(name)] = {"total": n, "correct": c}
                    sessions.append({
                        "timestamp": stamp, "total": total, "correct": correct,
                        "score": round(correct / total * 100, 1),
                        "types": type_map, "source": "전체 기록",
                        "wrong_types": {}, "timed_out": bool(row.get("timed_out", False)),
                        "duration_seconds": row.get("duration_seconds"),
                        "id": str(row.get("id") or f"line-{number}"),
                    })
                except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as e:
                    warnings.append(f"학습 기록 {number}번째 줄을 건너뜀: {e}")
    except OSError as e:
        warnings.append(f"학습 기록을 열 수 없음: {e}")
    return sessions, warnings


def parse_wrong_note(text: str, file: Path | None = None) -> dict | None:
    """기존 오답노트의 헤더를 읽는다. 100점 기록은 원래 파일이 없을 수 있다."""
    match = _NOTE_SUMMARY.search(text)
    if not match:
        return None
    score, total, correct, wrong = match.groups()
    total, correct, wrong = int(total), int(correct), int(wrong)
    if total <= 0 or correct + wrong != total:
        return None
    stamp_match = re.search(r"^작성 일시:\s*(.+)$", text, re.MULTILINE)
    if stamp_match:
        try:
            when = datetime.strptime(stamp_match.group(1).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            when = datetime.fromtimestamp(file.stat().st_mtime) if file else datetime.now()
    else:
        when = datetime.fromtimestamp(file.stat().st_mtime) if file else datetime.now()
    wrong_types: dict[str, int] = {}
    for label in _NOTE_TYPE.findall(text):
        wrong_types[label] = wrong_types.get(label, 0) + 1
    return {
        "timestamp": when, "total": total, "correct": correct,
        "score": round(100 * correct / total, 1),
        "types": {}, "source": "오답노트(부분 기록)",
        "wrong_types": wrong_types, "timed_out": False,
        "duration_seconds": None,
        "id": str(file) if file else "pasted-note",
    }


def load_sessions(log_path: str | Path = DEFAULT_LOG,
                  notes_dir: str | Path = DEFAULT_NOTES_DIR) -> tuple[list[dict], list[str]]:
    """전체 기록과 이전 오답노트를 병합하며 중복 시험은 1번만 계산."""
    sessions, warnings = _load_log(log_path)
    folder = Path(notes_dir).expanduser()
    if folder.exists():
        for file in sorted(folder.glob("wrong_notes_*.txt")):
            try:
                legacy = parse_wrong_note(file.read_text(encoding="utf-8"), file)
                if legacy is None:
                    warnings.append(f"오답노트 형식을 인식하지 못함: {file.name}")
                    continue
                # 새 로거와 오답노트는 동일 제출에서 1~2초 사이에 기록된다.
                # 문제 수와 정답 수, 작성 시각이 모두 일치할 때만 중복으로 판단.
                duplicate = any(
                    s["source"] == "전체 기록"
                    and s["total"] == legacy["total"]
                    and s["correct"] == legacy["correct"]
                    and abs((s["timestamp"] - legacy["timestamp"]).total_seconds()) <= 5
                    for s in sessions
                )
                if not duplicate:
                    sessions.append(legacy)
            except (OSError, UnicodeError) as e:
                warnings.append(f"오답노트 읽기 실패 ({file.name}): {e}")
    sessions.sort(key=lambda s: (s["timestamp"], s["id"]))
    return sessions, warnings


def calculate_statistics(sessions: list[dict]) -> dict:
    if not sessions:
        return {"count": 0, "avg_score": 0.0, "best": 0.0, "last": 0.0,
                "accuracy": 0.0, "questions": 0, "correct": 0, "types": {},
                "wrong_types": {}, "partial": False, "recent_avg": 0.0}
    total = sum(s["total"] for s in sessions)
    correct = sum(s["correct"] for s in sessions)
    typed = defaultdict(lambda: {"total": 0, "correct": 0})
    legacy_wrong = defaultdict(int)
    for s in sessions:
        for name, info in s.get("types", {}).items():
            typed[name]["total"] += info["total"]
            typed[name]["correct"] += info["correct"]
        for name, count in s.get("wrong_types", {}).items():
            legacy_wrong[name] += count
    tail = sessions[-5:]
    return {
        "count": len(sessions),
        "avg_score": round(sum(s["score"] for s in sessions) / len(sessions), 1),
        "recent_avg": round(sum(s["score"] for s in tail) / len(tail), 1),
        "best": max(s["score"] for s in sessions),
        "last": sessions[-1]["score"],
        "questions": total, "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "types": dict(typed), "wrong_types": dict(legacy_wrong),
        "partial": any(s["source"] != "전체 기록" for s in sessions),
    }


def format_summary(sessions: list[dict], warnings: list[str] | None = None) -> str:
    s = calculate_statistics(sessions)
    if s["count"] == 0:
        return "분석할 학습 기록이 없습니다. 퀴즈를 풀거나 채점 JSON을 가져오세요."
    out = [
        "StudyQuiz 학습 통계", "=" * 36,
        f"시험 횟수(기록된 시험): {s['count']}회",
        f"평균 점수: {s['avg_score']:.1f}점 / 최근 5회 평균: {s['recent_avg']:.1f}점",
        f"최고 점수: {s['best']:.1f}점 / 최근 점수: {s['last']:.1f}점",
        f"문항 누적 정답률: {s['accuracy']:.1f}% ({s['correct']}/{s['questions']})",
    ]
    if s["types"]:
        out.append("유형별 정답률 (전체 기록이 있는 시험만):")
        for name, v in sorted(s["types"].items()):
            rate = v["correct"] / v["total"] * 100 if v["total"] else 0
            out.append(f"  {name}: {rate:.1f}% ({v['correct']}/{v['total']})")
    if s["wrong_types"]:
        out.append("예전 오답노트 유형별 오답 건수 (정답률 아님):")
        out.extend(f"  {name}: {count}건" for name, count in sorted(s["wrong_types"].items()))
    if s["partial"]:
        out.append("※ 일부 점수는 예전 오답노트에서 복원됨. 오답이 없는 시험은 누락될 수 있습니다.")
    if warnings:
        out.append(f"읽기 경고: {len(warnings)}건")
    return "\n".join(out)


def export_csv(sessions: list[dict], output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["일시", "점수", "정답수", "전체문제수", "정답률(%)", "기록 종류", "시간초과", "소요시간(초)"])
        for s in sessions:
            writer.writerow([
                s["timestamp"].strftime("%Y-%m-%d %H:%M:%S"), s["score"],
                s["correct"], s["total"], round(s["correct"]/s["total"]*100,1),
                s["source"], "예" if s["timed_out"] else "아니요",
                "" if s["duration_seconds"] is None else s["duration_seconds"],
            ])
    return path


class StudyStatsApp:
    """표준 tkinter 기반 학습 통계 그래프/표 화면."""

    def __init__(self, root, log_path: str | Path = DEFAULT_LOG,
                 notes_dir: str | Path = DEFAULT_NOTES_DIR) -> None:
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.root = root
        self.log_path = Path(log_path)
        self.notes_dir = Path(notes_dir)
        self.sessions: list[dict] = []
        self.root.title("StudyQuiz — 학습 결과 통계")
        self.root.geometry("960x760")
        self.root.minsize(740, 580)
        layout = ttk.Frame(root, padding=14)
        layout.pack(fill="both", expand=True)
        title = ttk.Frame(layout)
        title.pack(fill="x")
        ttk.Label(title, text="학습 결과 통계", font=("Malgun Gothic", 17, "bold")).pack(side="left")
        ttk.Button(title, text="CSV 내보내기", command=self.on_export).pack(side="right", padx=(6, 0))
        ttk.Button(title, text="새로고침", command=self.refresh).pack(side="right")
        self.summary_var = tk.StringVar()
        ttk.Label(layout, textvariable=self.summary_var, font=("Malgun Gothic", 11),
                  justify="left").pack(fill="x", pady=(14, 5))
        ttk.Label(layout, text="최근 점수 추이 (최대 15회)").pack(anchor="w", pady=(12, 3))
        self.chart = tk.Canvas(layout, height=220, background="white", highlightthickness=1)
        self.chart.pack(fill="x")
        self.chart.bind("<Configure>", lambda _e: self.draw_chart())
        ttk.Label(layout, text="문제 유형별 성적 (전체 기록이 있는 시험만 집계)").pack(anchor="w", pady=(13, 4))
        self.type_table = ttk.Treeview(layout, columns=("type", "correct", "total", "rate"),
                                       show="headings", height=4)
        for col, head, width in [("type", "문제 유형", 140), ("correct", "정답", 100),
                                  ("total", "전체", 100), ("rate", "정답률", 130)]:
            self.type_table.heading(col, text=head)
            self.type_table.column(col, width=width, anchor="center")
        self.type_table.pack(fill="x")
        ttk.Label(layout, text="시험 기록").pack(anchor="w", pady=(13, 4))
        wrapper = ttk.Frame(layout)
        wrapper.pack(fill="both", expand=True)
        self.table = ttk.Treeview(wrapper, columns=("date", "score", "correct", "origin"), show="headings")
        for col, name, width in [("date", "일시", 175), ("score", "점수", 70),
                                 ("correct", "정답 / 전체", 110), ("origin", "기록 종류", 210)]:
            self.table.heading(col, text=name)
            self.table.column(col, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.notice_var = tk.StringVar()
        ttk.Label(layout, textvariable=self.notice_var, foreground="#8a5c19",
                  wraplength=900).pack(fill="x", pady=(10, 0))
        self.refresh()

    def refresh(self):
        self.sessions, warnings = load_sessions(self.log_path, self.notes_dir)
        s = calculate_statistics(self.sessions)
        self.summary_var.set(
            f"기록된 시험 {s['count']}회     평균 {s['avg_score']:.1f}점     최고 {s['best']:.1f}점\n"
            f"누적 정답률 {s['accuracy']:.1f}% ({s['correct']}/{s['questions']})     "
            f"최근 5회 평균 {s['recent_avg']:.1f}점"
        )
        for x in self.type_table.get_children():
            self.type_table.delete(x)
        for name, v in sorted(s["types"].items()):
            rate = v["correct"] / v["total"]*100 if v["total"] else 0
            self.type_table.insert("", "end", values=(name, v["correct"], v["total"], f"{rate:.1f}%"))
        for x in self.table.get_children():
            self.table.delete(x)
        for item in reversed(self.sessions):
            self.table.insert("", "end", values=(
                item["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                f"{item['score']:.1f}", f"{item['correct']} / {item['total']}", item["source"]))
        notes = []
        if s["partial"]:
            notes.append("기존 오답노트 기반 통계는 100점 시험이 누락될 수 있어 전체 학습 기록이 아닙니다.")
        if s["wrong_types"]:
            parts = ", ".join(f"{k}: {v}건" for k,v in sorted(s["wrong_types"].items()))
            notes.append("과거 오답노트의 유형별 오답: " + parts)
        if warnings:
            notes.append(f"인식하지 못한 기록 {len(warnings)}건")
        if not self.sessions:
            notes.append("아직 기록이 없습니다. 타이머 퀴즈를 풀거나 --import-grade 옵션으로 기록을 추가하세요.")
        self.notice_var.set("\n".join(notes))
        self.draw_chart()

    def draw_chart(self):
        c = self.chart
        c.delete("all")
        width = c.winfo_width()
        height = c.winfo_height()
        if width < 80 or height < 80:
            return
        last = self.sessions[-15:]
        if not last:
            c.create_text(width/2, height/2, text="점수 기록이 없습니다", fill="#777777")
            return
        left, right, top, bottom = 43, width - 14, 18, height - 29
        for value in (0, 50, 100):
            y = bottom - value/100*(bottom-top)
            c.create_line(left, y, right, y, fill="#e6e9ee")
            c.create_text(left - 7, y, text=str(value), anchor="e", fill="#777777")
        w = (right-left)/len(last)
        for i, s in enumerate(last):
            x0 = left + i*w + max(2, w*.15)
            x1 = left + (i+1)*w - max(2, w*.15)
            y = bottom - s["score"] / 100 * (bottom-top)
            color = "#2979c9" if s["source"] == "전체 기록" else "#a3aab6"
            c.create_rectangle(x0, y, x1, bottom, fill=color, outline="")
            c.create_text((x0+x1)/2, max(10,y-9), text=f"{s['score']:.0f}",
                          font=("Arial", 9), fill="#303b49")
            c.create_text((x0+x1)/2, bottom+13, text=str(i+1), fill="#777777", font=("Arial", 9))
        c.create_text(right, 9, text="파랑: 전체 기록 / 회색: 과거 오답노트",
                      anchor="e", fill="#777777", font=("Arial", 8))

    def on_export(self):
        from tkinter import filedialog, messagebox
        if not self.sessions:
            messagebox.showinfo("내보내기", "저장할 시험 기록이 없습니다.")
            return
        filename = filedialog.asksaveasfilename(
            title="CSV 저장", defaultextension=".csv", initialfile="studyquiz_stats.csv",
            filetypes=[("CSV 파일", "*.csv")])
        if not filename:
            return
        try:
            export_csv(self.sessions, filename)
        except OSError as e:
            messagebox.showerror("저장 실패", str(e))
        else:
            messagebox.showinfo("저장 완료", f"CSV 저장 완료:\n{filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="StudyQuiz 학습 결과 통계 분석")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="전체 학습 JSONL 기록")
    parser.add_argument("--notes-dir", type=Path, default=DEFAULT_NOTES_DIR, help="기존 오답노트 폴더")
    parser.add_argument("--summary", action="store_true", help="터미널에 통계 출력")
    parser.add_argument("--export", type=Path, help="시험 기록 CSV 내보내기")
    parser.add_argument("--import-grade", type=Path, help="기존 grade() 결과 JSON을 한 회차로 추가")
    args = parser.parse_args()
    if args.import_grade:
        try:
            grade_result = json.loads(args.import_grade.read_text(encoding="utf-8"))
            output = record_result(grade_result, args.log)
            print(f"학습 기록 추가됨: {output}")
        except (OSError, ValueError, TypeError, KeyError) as e:
            parser.exit(1, f"가져오기 실패: {e}\n")
    if args.summary or args.export:
        sessions, warnings = load_sessions(args.log, args.notes_dir)
        if args.summary:
            print(format_summary(sessions, warnings))
        if args.export:
            print("CSV 저장:", export_csv(sessions, args.export))
        return
    if args.import_grade:
        return
    import tkinter as tk
    root = tk.Tk()
    StudyStatsApp(root, args.log, args.notes_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
