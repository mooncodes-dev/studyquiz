# StudyQuiz — 강의 자료 요약 + 자동 퀴즈 생성기

> 강의 자료를 넣으면 **핵심 요약**과 **복습용 퀴즈**가 자동으로 만들어집니다.
> 설치 없이, 파이썬만 있으면 바로 실행됩니다.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

가천대학교 **오픈소스SW** 수업 팀 프로젝트 (Group 46)

---

## 왜 만들었나요?

시험 기간마다 강의 자료를 처음부터 다시 읽는 것은 비효율적입니다.
StudyQuiz는 긴 강의 텍스트에서 중요한 문장을 골라 요약하고, 그 내용으로
객관식·빈칸형 퀴즈를 자동 생성해 **읽기 → 요약 → 문제 풀이 → 채점**까지의
복습 흐름을 한 번에 제공합니다.

- 외부 API나 유료 서비스가 필요 없습니다. **파이썬 표준 라이브러리만으로 동작**합니다.
- PDF 강의 자료도 읽을 수 있습니다 (`pypdf` 설치 시).

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 📄 텍스트 추출 | `.txt` 파일과 PDF에서 본문을 추출하고 문장 단위로 분리합니다. 스캔본 PDF는 OCR 패키지가 있으면 읽어 냅니다. |
| ✂️ 추출 요약 | TF-IDF 문장 점수와 문단 첫 문장 보너스, 중복 감점(MMR)으로 핵심 문장만 골라 원문 순서대로 요약합니다. `kiwipiepy`가 있으면 형태소 분석으로 용어를 더 정확히 뽑습니다. |
| ❓ 퀴즈 자동 생성 | TF-IDF 핵심 용어를 정답으로 하는 객관식(보기 4개)과 빈칸형 문제를 만듭니다. 오답 보기도 문서 안의 다른 핵심 용어에서 뽑아 그럴듯하게 구성합니다. |
| 🤖 Gemini 연동 (선택) | API 키를 넣으면 Gemini AI 요약·퀴즈를 사용할 수 있습니다. 모델은 키로 쓸 수 있는 것 중 자동으로 선택됩니다. |
| ✅ 자동 채점 | 점수와 문항별 피드백(정답·해설)을 바로 보여줍니다. |
| 🌐 웹 데모 | 브라우저에서 텍스트를 붙여넣거나 PDF를 업로드하면 요약과 퀴즈를 카드 형태로 보여줍니다. Gemini 방식도 선택할 수 있습니다. |

## 빠른 시작

별도 설치가 필요 없습니다. 저장소를 내려받고 바로 실행하세요.

```bash
git clone https://github.com/<계정>/studyquiz.git
cd studyquiz

# 1) 요약하기
python -m studyquiz.cli summarize examples/sample_lecture.txt --num 3

# 2) 퀴즈 만들기 (5문제, 파일로 저장)
python -m studyquiz.cli quiz examples/sample_lecture.txt --num 5 --out quiz.json

# 3) 퀴즈 풀고 채점하기
python -m studyquiz.cli quiz examples/sample_lecture.txt --num 5 --interactive

# 4) Gemini로 요약/퀴즈 만들기 (선택, 모델 자동 선택)
export GEMINI_API_KEY=<본인의 Gemini API 키>
python -m studyquiz.cli summarize examples/sample_lecture.txt --ai
python -m studyquiz.cli quiz examples/sample_lecture.txt --ai
```

PDF를 읽으려면 선택 의존성 하나만 설치하면 됩니다.

```bash
pip install -r requirements.txt   # pypdf
```

## 실행 예시

예제 강의 자료(운영체제 개요, 48문장)로 실행한 실제 결과입니다.

**요약 (3문장)**

```text
운영체제는 각 프로세스를 관리하기 위해 프로세스 제어 블록, 즉 PCB에 …
```

**퀴즈 (객관식)**

```text
Q. 디렉터리는 ____들을 묶어 계층 구조로 …
   1. 프로세스   2. 파일   3. 스레드   4. 교체
```

**채점**

```text
총 5문제 중 4문제 정답 -> 80.0점
- 오답입니다. 정답은 '메모리'입니다.
```

## 웹 데모

```bash
python -m studyquiz.webapp
# 브라우저에서 http://localhost:8000 접속
```

텍스트를 붙여넣거나 PDF 파일을 업로드하고 버튼을 누르면 요약과 퀴즈가 생성되고,
브라우저에서 바로 답을 고르고 채점할 수 있습니다.
방식은 기본(내장 알고리즘)과 Gemini(AI) 중에서 고를 수 있고,
Gemini 키는 서버에 저장되지 않고 그 요청에만 사용됩니다.
서버는 파이썬 표준 라이브러리(`http.server`)만으로 구현되어 있습니다.

## 프로젝트 구조

```text
studyquiz/
├── studyquiz/
│   ├── __init__.py    # 공개 API (summarize, generate_quiz, grade)
│   ├── extract.py     # 텍스트/PDF 추출(스캔본 OCR 폴백), 문장 분리
│   ├── summarize.py   # TF-IDF 기반 추출 요약, 핵심 용어 추출
│   ├── quizgen.py     # 객관식·빈칸형 퀴즈 생성
│   ├── grade.py       # 채점과 문항별 피드백
│   ├── gemini.py      # Gemini 연동 (선택, 모델 자동 선택)
│   ├── cli.py         # 명령줄 인터페이스
│   └── webapp.py      # 웹 데모 서버
├── tests/
│   └── test_studyquiz.py
├── examples/
│   └── sample_lecture.txt   # 자체 제작 예제 (운영체제 개요)
├── docs/
│   └── 발표개요.md
├── requirements.txt         # pypdf (선택)
└── LICENSE                  # MIT
```

## 동작 원리

**추출 요약** — 문장을 형태 단위로 나누고(한국어 조사를 간단히 제거하거나,
`kiwipiepy`가 있으면 형태소 분석으로 명사를 뽑고), 문장 점수를 TF-IDF로 매깁니다.
문서 곳곳에 흔한 단어는 가중치가 낮아져 긴 자료에서도 주제를 대표하는 문장이 뽑히고,
문단의 첫 문장에는 가산점을, 이미 고른 문장과 겹치는 문장에는 감점(MMR)을 줘서
서로 다른 주제가 골고루 들어가게 합니다. 고른 문장은 **원문에 등장한 순서대로**
배열하므로 요약만 읽어도 글의 흐름이 유지됩니다.

**퀴즈 생성** — 요약 문장에서 핵심 용어를 정답으로 삼아 그 자리를
빈칸으로 바꾸고, 나머지 핵심 용어들 중에서 오답 보기 3개를 뽑습니다.
정답이 항상 하나만 존재하도록 생성 단계에서 검증합니다.

## 테스트

```bash
python -m unittest discover -s tests
# Ran 33 tests — OK
```

요약(문장 수·출처·순서, 긴 문서 핵심 문장·중복 방지), 퀴즈(문항 수·정답 유일성·보기 구성),
채점(점수 계산·보기 번호 답안), Gemini 모델 자동 선택, 바이트 추출·OCR 판단,
웹 멀티파트 파싱까지 전 구간을 검증합니다.

## 팀 역할 분담

| 역할 | 담당 내용 |
| --- | --- |
| 요약 모듈 | `extract.py`, `summarize.py` — 추출과 요약 알고리즘 |
| 퀴즈 생성 | `quizgen.py`, `grade.py` — 문제 생성과 채점 |
| 웹 UI | `webapp.py`, `cli.py` — 웹 데모와 명령줄 인터페이스 |
| 테스트·문서 | `tests/`, README, 발표 자료 |

## 한계와 개선 방향

- 기본 요약 품질이 아쉬워서, Gemini를 따로 연결해 AI 요약·퀴즈를 쓸 수 있게 해 두었습니다.
- 현재 요약은 추출 방식이라 문장을 새로 쓰지 않습니다.
  향후 오픈소스 생성 모델을 붙이면 생성 요약으로 확장할 수 있습니다.
- 한국어 형태소 분석은 간이 규칙 기반입니다.
  오픈소스 형태소 분석기를 연동하면 핵심 용어 추출 정확도를 높일 수 있습니다.
- 퀴즈 유형(빈칸형·객관식)에 OX형과 단답형을 추가할 계획입니다.

## 라이선스

MIT License — 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.

이 프로젝트는 파이썬 표준 라이브러리만으로 동작하며,
PDF 추출에만 오픈소스 라이브러리 `pypdf`(BSD)를 선택적으로 사용합니다.
