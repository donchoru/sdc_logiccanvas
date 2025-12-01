@echo off
echo ========================================
echo SDC LogicCanvas EXE 빌드 스크립트
echo ========================================
echo.

REM PyInstaller 설치 확인
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller가 설치되어 있지 않습니다. 설치 중...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller 설치 실패!
        pause
        exit /b 1
    )
)

echo.
echo EXE 파일 빌드 중...
echo.

REM PyInstaller 실행
REM JSON 파일들은 EXE와 같은 폴더에 두어 사용자가 직접 수정할 수 있도록 함
python -m PyInstaller ^
    --name="SDC_LogicCanvas" ^
    --onefile ^
    --windowed ^
    --icon=icon.png ^
    --hidden-import=PySide2 ^
    --hidden-import=NodeGraphQt ^
    --hidden-import=ctypes.wintypes ^
    --collect-all=NodeGraphQt ^
    --collect-all=PySide2 ^
    main.py

if errorlevel 1 (
    echo.
    echo 빌드 실패!
    pause
    exit /b 1
)

echo.
echo ========================================
echo 빌드 완료!
echo ========================================
echo.
echo EXE 파일 위치: dist\SDC_LogicCanvas.exe
echo.
echo [중요] EXE와 같은 폴더에 다음 JSON 파일들을 복사하세요:
echo   - tables.json
echo   - situation_types.json
echo   - screens.json
echo   - logs.json
echo.
echo 이 파일들은 사용자가 직접 수정할 수 있으며,
echo 프로그램 실행 시 자동으로 로드됩니다.
echo.
pause

