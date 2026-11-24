@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title StudyQuiz 실행기

rem ---- 파이썬 찾기 (python 또는 py 런처) ----
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
    echo [오류] 파이썬을 찾을 수 없습니다.
    echo https://www.python.org/downloads/ 에서 설치할 때 "Add python.exe to PATH"를 체크해 주세요.
    pause
    exit /b 1
)

:menu
cls
echo ==========================================
echo    StudyQuiz - 강의 자료 요약 + 자동 퀴즈
echo ==========================================
echo  1. 데스크톱 실행기 (창으로 열기)
echo  2. 웹 데모 (브라우저로 열기)
echo  3. 터미널에서 퀴즈 풀기 (예제, 혼합)
echo  4. 터미널에서 OX 퀴즈 풀기 (예제)
echo  5. 예제 요약 보기
echo  6. 테스트 실행
echo  7. 필요 패키지 설치 (PDF/형태소 분석/OCR)
echo  0. 종료
echo ------------------------------------------
set "CHOICE="
set /p CHOICE=번호를 입력하세요: 

if "%CHOICE%"=="1" goto gui
if "%CHOICE%"=="2" goto web
if "%CHOICE%"=="3" goto quiz
if "%CHOICE%"=="4" goto ox
if "%CHOICE%"=="5" goto summary
if "%CHOICE%"=="6" goto test
if "%CHOICE%"=="7" goto install
if "%CHOICE%"=="0" exit /b 0
goto menu

:gui
%PY% gui.py
goto done

:web
echo 브라우저가 열리지 않으면 http://localhost:8000 에 직접 접속하세요. (종료: Ctrl+C)
start "" http://localhost:8000
%PY% -m studyquiz.webapp
goto done

:quiz
%PY% -m studyquiz.cli quiz examples/sample_lecture.txt --num 6 --interactive
goto done

:ox
%PY% -m studyquiz.cli quiz examples/sample_lecture.txt --num 5 --type OX형 --interactive
goto done

:summary
%PY% -m studyquiz.cli summarize examples/sample_lecture.txt --num 3
goto done

:test
%PY% -m unittest discover -s tests
goto done

:install
%PY% -m pip install -r requirements.txt
goto done

:done
echo.
pause
goto menu
