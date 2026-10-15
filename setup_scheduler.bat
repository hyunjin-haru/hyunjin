@echo off
chcp 65001 >nul
echo ======================================================
echo  Second Brain 24시간 자율 레이더 스케줄러 등록 중...
echo ======================================================

set SCRIPT_DIR=%~dp0
set PYTHON_EXE=py
set RADAR_PATH=%SCRIPT_DIR%radar.py

:: 4시간마다 백그라운드에서 조용히 실행되는 작업 스케줄러 등록
schtasks /create /tn "SecondBrain_Radar" /tr "%PYTHON_EXE% \"%RADAR_PATH%\"" /sc hourly /mo 4 /f

echo.
echo [성공] Second Brain 자율 레이더가 4시간 주기로 자동 등록되었습니다!
echo 이제 PC가 켜져 있는 동안 알아서 최신 정보를 감시하고 리포트를 적재합니다.
echo.
pause