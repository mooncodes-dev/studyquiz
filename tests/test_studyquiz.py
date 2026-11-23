"""StudyQuiz 단위 테스트 (표준 라이브러리 unittest 사용).

실행:  python -m unittest discover -s tests -v
"""
import unittest

from studyquiz.extract import split_sentences
from studyquiz.summarize import summarize, extract_keywords
from studyquiz.quizgen import generate_quiz, BLANK, MC, CLOZE
from studyquiz.grade import grade

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


if __name__ == "__main__":
    unittest.main()
