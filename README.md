# StudyQuiz — 강의 자료 요약 + 자동 퀴즈 생성기

가천대학교 오픈소스SW 수업 팀 프로젝트 (Group 46)입니다.
강의 자료 텍스트를 넣으면 핵심 문장을 골라 요약하고, 그 내용으로 객관식·빈칸형 퀴즈를 만들어 채점까지 해 주는 프로그램입니다.

## 만든 이유

시험 기간에 강의 자료를 처음부터 다시 읽는 게 번거로워서, 요약과 문제 풀이를 자동으로 해 주는 도구를 만들어 봤습니다.

- 기본 기능은 파이썬 표준 라이브러리만으로 동작합니다. (외부 API 불필요)
- PDF도 읽을 수 있습니다. (`pypdf` 설치 시)

## 기능

- 텍스트 추출: `.txt` 파일과 PDF에서 본문을 뽑고 문장 단위로 나눕니다. 스캔본 PDF는 OCR 패키지가 있으면 읽어 냅니다.
- 요약: TF-IDF로 문장 점수를 매기고, 문단 첫 문장 가산점과 중복 감점(MMR)을 적용해 핵심 문장을 원문 순서대로 뽑습니다. `kiwipiepy`가 있으면 형태소 분석으로 용어를 뽑습니다.
- 퀴즈 생성: 핵심 용어를 정답으로 객관식(보기 4개)과 빈칸형 문제를 만듭니다. 오답 보기는 문서 안의 다른 핵심 용어에서 가져옵니다.
- Gemini 연동 (선택): API 키를 넣으면 Gemini로 요약·퀴즈를 만들 수 있습니다. 모델은 키로 쓸 수 있는 것 중 자동으로 선택됩니다.
- 채점: 점수와 문항별 정답·해설을 보여줍니다.
- 웹 데모: 브라우저에서 텍스트를 붙여넣거나 PDF를 올리면 요약과 퀴즈를 카드 형태로 보여줍니다. Gemini 방식도 고를 수 있습니다.

## 빠른 시작

```bash
git clone https://github.com/mooncodes-dev/studyquiz.git
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

필요한 패키지는 아래 명령 한 번으로 전부 설치됩니다. (PDF 입력, 한국어 형태소 분석, 스캔본 OCR 포함)

```bash
pip install -r requirements.txt
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
├── requirements.txt         # 필요 패키지 한 번에 설치
└── LICENSE                  # MIT
```

## 동작 원리

요약은 문장마다 TF-IDF 점수를 매기는 방식입니다. 문서 곳곳에 흔한 단어는 가중치가 낮아지고, 문단의 첫 문장은 가산점을 받습니다. 이미 고른 문장과 내용이 겹치면 감점(MMR)을 해서 한쪽 주제에만 몰리지 않게 했습니다. 고른 문장은 원문에 나온 순서대로 배열합니다.

퀴즈는 요약 문장에서 핵심 용어를 빈칸으로 바꾸고, 나머지 핵심 용어 중 3개를 오답 보기로 넣습니다. 정답이 하나만 되도록 만들 때 확인합니다.

## 테스트

```bash
python -m unittest discover -s tests
# Ran 33 tests — OK
```

요약(문장 수·출처·순서, 긴 문서 핵심 문장·중복 방지), 퀴즈(문항 수·정답 유일성·보기 구성),
채점(점수 계산·보기 번호 답안), Gemini 모델 자동 선택, 바이트 추출·OCR 판단,
웹 멀티파트 파싱까지 검증합니다.

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
