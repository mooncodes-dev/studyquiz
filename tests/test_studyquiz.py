"""StudyQuiz 단위 테스트 (표준 라이브러리 unittest 사용).

실행:  python -m unittest discover -s tests -v
"""
import importlib.util
import threading
import unittest
from unittest import mock

from studyquiz import extract as extract_mod
from studyquiz.extract import (
    split_sentences, extract_text_from_bytes, needs_ocr, ScannedDocumentError,
)
from studyquiz.summarize import summarize, extract_keywords, tokenize, kiwi_available
from studyquiz.quizgen import generate_quiz, BLANK, MC, CLOZE, OX
from studyquiz.grade import grade
from studyquiz.gemini import pick_model
from studyquiz.webapp import parse_multipart

TEXT = (
    "프로세스는 실행 중인 프로그램이다. "
    "프로세스는 독립된 메모리 공간을 가진다. "
    "스레드는 프로세스 안의 실행 단위이다. "
    "스레드는 프로세스의 메모리를 공유한다. "
    "스케줄링은 프로세스의 실행 순서를 정하는 정책이다. "
    "커널은 운영체제의 핵심 부분이다. "
    "파일 시스템은 파일을 관리하는 체계이다. "
    "가상 메모리는 프로세스에게 큰 주소 공간을 제공한다."
)


class TestSummarize(unittest.TestCase):
    def test_returns_requested_number_of_sentences(self):
        result = summarize(TEXT, 3)
        self.assertEqual(len(result), 3)

    def test_sentences_come_from_source(self):
        source = split_sentences(TEXT)
        for sentence in summarize(TEXT, 4):
            self.assertIn(sentence, source)

    def test_keeps_original_order(self):
        source = split_sentences(TEXT)
        result = summarize(TEXT, 3)
        positions = [source.index(s) for s in result]
        self.assertEqual(positions, sorted(positions))

    def test_more_sentences_than_source_returns_all(self):
        result = summarize(TEXT, 100)
        self.assertEqual(len(result), len(split_sentences(TEXT)))

    def test_keywords_found(self):
        keywords = extract_keywords(TEXT, 10)
        self.assertIn("프로세스", keywords)
        self.assertIn("스레드", keywords)


class TestQuizGen(unittest.TestCase):
    def test_question_count(self):
        quiz = generate_quiz(TEXT, 5, seed=42)
        self.assertEqual(len(quiz), 5)

    def test_multiple_choice_has_exactly_one_correct(self):
        quiz = generate_quiz(TEXT, 5, quiz_type=MC, seed=42)
        self.assertTrue(quiz)
        for q in quiz:
            self.assertEqual(q["type"], MC)
            self.assertEqual(len(q["options"]), 4)
            self.assertEqual(q["options"].count(q["answer"]), 1)
            self.assertEqual(q["options"][q["answer_index"]], q["answer"])

    def test_distractors_differ_from_answer(self):
        quiz = generate_quiz(TEXT, 5, quiz_type=MC, seed=7)
        for q in quiz:
            distractors = [o for o in q["options"] if o != q["answer"]]
            self.assertEqual(len(distractors), 3)
            self.assertEqual(len(set(q["options"])), 4)

    def test_cloze_blanks_out_answer(self):
        quiz = generate_quiz(TEXT, 3, quiz_type=CLOZE, seed=42)
        self.assertTrue(quiz)
        for q in quiz:
            self.assertEqual(q["type"], CLOZE)
            self.assertIn(BLANK, q["question"])


class TestGrade(unittest.TestCase):
    def setUp(self):
        self.quiz = generate_quiz(TEXT, 4, seed=42)
        self.assertEqual(len(self.quiz), 4)

    def test_all_correct_scores_100(self):
        answers = [q["answer"] for q in self.quiz]
        result = grade(self.quiz, answers)
        self.assertEqual(result["correct"], 4)
        self.assertEqual(result["score"], 100.0)

    def test_all_wrong_scores_0(self):
        answers = ["전혀관계없는답"] * len(self.quiz)
        result = grade(self.quiz, answers)
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["score"], 0.0)

    def test_partial_score_math(self):
        answers = [q["answer"] for q in self.quiz]
        answers[0] = "오답"
        answers[1] = "오답"
        result = grade(self.quiz, answers)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["score"], 50.0)

    def test_feedback_marks_each_question(self):
        answers = [q["answer"] for q in self.quiz]
        answers[0] = "오답"
        result = grade(self.quiz, answers)
        self.assertFalse(result["results"][0]["is_correct"])
        self.assertTrue(result["results"][1]["is_correct"])
        self.assertIn(self.quiz[0]["answer"], result["results"][0]["feedback"])

    def test_multiple_choice_accepts_option_number(self):
        mc_quiz = generate_quiz(TEXT, 3, quiz_type=MC, seed=42)
        answers = [str(q["answer_index"] + 1) for q in mc_quiz]
        result = grade(mc_quiz, answers)
        self.assertEqual(result["score"], 100.0)


# ---------------------------------------------------------------------------
# OX형 퀴즈
# ---------------------------------------------------------------------------

class TestOXQuiz(unittest.TestCase):
    def setUp(self):
        self.quiz = generate_quiz(TEXT, 6, quiz_type=OX, seed=3)

    def test_ox_question_format(self):
        self.assertTrue(self.quiz)
        for q in self.quiz:
            self.assertEqual(q["type"], OX)
            self.assertEqual(q["options"], ["O", "X"])
            self.assertIn(q["answer"], ("O", "X"))
            self.assertEqual(q["options"][q["answer_index"]], q["answer"])

    def test_true_statement_is_original_sentence(self):
        sentences = split_sentences(TEXT)
        for q in self.quiz:
            if q["answer"] == "O":
                self.assertIn(q["question"], sentences)

    def test_false_statement_is_altered(self):
        sentences = split_sentences(TEXT)
        for q in self.quiz:
            if q["answer"] == "X":
                self.assertNotIn(q["question"], sentences)

    def test_both_answers_appear_over_many_seeds(self):
        answers = set()
        for seed in range(20):
            for q in generate_quiz(TEXT, 4, quiz_type=OX, seed=seed):
                answers.add(q["answer"])
        self.assertEqual(answers, {"O", "X"})

    def test_ox_grading_accepts_aliases(self):
        q_o = {"type": OX, "question": "s", "options": ["O", "X"],
               "answer": "O", "answer_index": 0}
        q_x = {"type": OX, "question": "s", "options": ["O", "X"],
               "answer": "X", "answer_index": 1, "explanation": "설명"}
        for o_ans, x_ans in [("o", "x"), ("1", "2"), ("참", "거짓"), ("O", "X")]:
            result = grade([q_o, q_x], [o_ans, x_ans])
            self.assertEqual(result["score"], 100.0, (o_ans, x_ans))

    def test_wrong_x_answer_shows_explanation(self):
        q_x = {"type": OX, "question": "s", "options": ["O", "X"],
               "answer": "X", "answer_index": 1, "explanation": "원래 용어 안내"}
        result = grade([q_x], ["O"])
        self.assertIn("원래 용어 안내", result["results"][0]["feedback"])

    def test_mixed_includes_ox(self):
        quiz = generate_quiz(TEXT, 6, seed=42)
        self.assertIn(OX, {q["type"] for q in quiz})


# ---------------------------------------------------------------------------
# 긴 문서 요약 (TF-IDF + 위치 보너스 + MMR)
# ---------------------------------------------------------------------------

_FILLER = "이 내용은 강의에서 매우 중요하게 다루어지는 부분이다."
_CORE1 = "프로세스는 실행 중인 프로그램이며 운영체제로부터 독립된 메모리 공간을 할당받는다."
_CORE2 = "가상 메모리는 실제 메모리보다 큰 주소 공간을 프로세스에게 제공하는 기술이다."
_CORE3 = "세마포어는 공유 자원에 대한 접근을 조절하는 정수 변수와 대기 큐로 이루어진 동기화 도구이다."
_DUP_A = "뮤텍스는 한 번에 하나의 스레드만 임계 구역에 들어가도록 보장하는 잠금 장치이다."
_DUP_B = "뮤텍스는 한 번에 하나의 스레드만 임계 구역에 들어가도록 보장하는 잠금 도구이다."

LONG_TEXT = "\n\n".join([
    " ".join([
        _CORE1,
        "스케줄링은 준비 상태의 프로세스들 가운데 다음에 실행할 프로세스를 고르는 정책이다.",
        "선입선출 스케줄링은 도착한 순서대로 프로세스를 실행하는 단순한 방식이다.",
        "라운드 로빈 스케줄링은 각 프로세스에 시간 할당량을 번갈아 부여한다.",
        _FILLER,
    ]),
    " ".join([
        _CORE2,
        "페이징은 가상 메모리를 고정된 크기의 페이지로 나누어 관리하는 방식이다.",
        "페이지 테이블은 가상 페이지와 물리 프레임의 대응 관계를 기록한다.",
        "페이지 폴트는 접근한 페이지가 메모리에 없을 때 발생하는 예외이다.",
        _FILLER,
    ]),
    " ".join([
        _CORE3,
        _DUP_A,
        _DUP_B,
        "임계 구역은 공유 자원을 사용하는 코드 구간이다.",
        _FILLER,
    ]),
])


class TestLongDocumentSummarize(unittest.TestCase):
    def test_core_sentence_is_selected(self):
        result = summarize(LONG_TEXT, 3)
        cores = {_CORE1, _CORE2, _CORE3}
        self.assertTrue(any(s in cores for s in result),
                        f"핵심 문장이 하나도 뽑히지 않았습니다: {result}")

    def test_no_near_duplicate_pair(self):
        result = summarize(LONG_TEXT, 3)
        self.assertFalse(_DUP_A in result and _DUP_B in result,
                         "거의 같은 문장이 함께 뽑혔습니다")

    def test_repeated_filler_not_selected(self):
        # 문서 전체에 반복되는 문장은 TF-IDF 가중치가 낮아 뽑히지 않아야 합니다.
        result = summarize(LONG_TEXT, 3)
        self.assertNotIn(_FILLER, result)


class TestTokenizerFallback(unittest.TestCase):
    def test_tokenize_works_without_kiwi(self):
        # kiwipiepy가 없어도(간이 규칙 경로) 토큰화가 동작해야 합니다.
        tokens = tokenize("프로세스는 실행 중인 프로그램이다.")
        self.assertIn("프로세스", tokens)
        self.assertTrue(all(isinstance(t, str) for t in tokens))

    def test_kiwi_available_returns_bool(self):
        self.assertIsInstance(kiwi_available(), bool)


class TestPickModel(unittest.TestCase):
    def test_prefers_newest_flash(self):
        names = ["models/gemini-2.5-flash", "models/gemini-3.8-flash",
                 "models/gemini-3-pro"]
        self.assertEqual(pick_model(names), "gemini-3.8-flash")

    def test_gemini3_beats_older_flash(self):
        names = ["models/gemini-2.5-flash", "models/gemini-3-pro"]
        self.assertEqual(pick_model(names), "gemini-3-pro")

    def test_any_flash_beats_plain_gemini(self):
        names = ["models/gemini-1.5-pro", "models/gemini-2.0-flash"]
        self.assertEqual(pick_model(names), "gemini-2.0-flash")

    def test_accepts_names_without_prefix(self):
        self.assertEqual(pick_model(["gemini-2.5-flash"]), "gemini-2.5-flash")

    def test_empty_list_returns_none(self):
        self.assertIsNone(pick_model([]))

    def test_no_gemini_returns_none(self):
        self.assertIsNone(pick_model(["models/text-embedding-004"]))


class TestExtractFromBytes(unittest.TestCase):
    def test_txt_utf8(self):
        data = "프로세스는 실행 중인 프로그램이다.".encode("utf-8")
        self.assertEqual(extract_text_from_bytes(data, "lecture.txt"),
                         "프로세스는 실행 중인 프로그램이다.")

    def test_txt_cp949_fallback(self):
        data = "가상 메모리는 기술이다.".encode("cp949")
        self.assertEqual(extract_text_from_bytes(data, "lecture.txt"),
                         "가상 메모리는 기술이다.")


class TestNeedsOcr(unittest.TestCase):
    def test_empty_text_needs_ocr(self):
        self.assertTrue(needs_ocr(""))
        self.assertTrue(needs_ocr("   \n  "))

    def test_sparse_text_per_page_needs_ocr(self):
        self.assertTrue(needs_ocr("짧은 텍스트", page_count=10))

    def test_dense_text_does_not_need_ocr(self):
        long_text = "프로세스는 실행 중인 프로그램이다. " * 40
        self.assertFalse(needs_ocr(long_text, page_count=2))
        self.assertFalse(needs_ocr(long_text))


class TestScannedPdfGraceful(unittest.TestCase):
    def test_ocr_pdf_raises_clear_error_without_packages(self):
        with mock.patch.object(extract_mod, "_ocr_available", return_value=False):
            with self.assertRaises(ScannedDocumentError) as ctx:
                extract_mod._ocr_pdf(b"%PDF-1.4 dummy")
        self.assertIn("OCR", str(ctx.exception))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"),
                         "pypdf가 없어 빈 PDF를 만들 수 없습니다")
    def test_blank_pdf_upload_raises_scanned_error(self):
        from io import BytesIO
        from pypdf import PdfWriter

        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(buffer)
        with mock.patch.object(extract_mod, "_ocr_available", return_value=False):
            with self.assertRaises(ScannedDocumentError):
                extract_text_from_bytes(buffer.getvalue(), "scan.pdf")


class TestMultipartParsing(unittest.TestCase):
    def test_fields_and_file(self):
        boundary = "----studyquiztest"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="text"\r\n\r\n'
            "안녕하세요\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "파일 내용\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        fields, files = parse_multipart(
            body, f"multipart/form-data; boundary={boundary}")
        self.assertEqual(fields["text"], ["안녕하세요"])
        self.assertEqual(files["file"][0], "a.txt")
        self.assertEqual(files["file"][1], "파일 내용".encode("utf-8"))


class TestWebPdfUpload(unittest.TestCase):
    """웹 데모에 PDF를 올렸을 때 빈 응답이 오지 않는지 확인합니다."""

    def _post_pdf(self, pdf_bytes: bytes) -> tuple[int, str]:
        import urllib.request
        from http.server import ThreadingHTTPServer
        from studyquiz.webapp import StudyQuizHandler

        server = ThreadingHTTPServer(("127.0.0.1", 0), StudyQuizHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            boundary = "----studyquizwebtest"
            body = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="text"\r\n\r\n'
                "\r\n"
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="lec.pdf"\r\n'
                "Content-Type: application/pdf\r\n\r\n"
            ).encode("utf-8") + pdf_bytes + (
                f"\r\n--{boundary}\r\n"
                'Content-Disposition: form-data; name="mode"\r\n\r\n'
                "local\r\n"
                f"--{boundary}--\r\n"
            ).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/quiz",
                data=body, method="POST",
                headers={"Content-Type":
                         f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()

    @staticmethod
    def _make_text_pdf() -> bytes:
        from io import BytesIO
        from pypdf import PdfWriter

        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(buffer)
        return buffer.getvalue()

    def test_missing_pypdf_shows_guide_not_empty_response(self):
        # pypdf가 없는 환경을 흉내 내면, 연결이 끊기는 대신 설치 안내가 떠야 합니다.
        real_find_spec = importlib.util.find_spec

        def fake_find_spec(name, package=None):
            if name == "pypdf":
                return None
            return real_find_spec(name, package)

        with mock.patch.object(importlib.util, "find_spec", fake_find_spec), \
                mock.patch.object(extract_mod, "_ocr_available",
                                  return_value=False):
            status, page = self._post_pdf(b"%PDF-1.4 dummy")
        self.assertEqual(status, 200)
        self.assertIn("pip install pypdf", page)


if __name__ == "__main__":
    unittest.main()
