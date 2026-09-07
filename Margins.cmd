@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Install from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
:menu
cls
echo MARGINS - Dokaz Industries
echo.
echo 1. One-time setup
echo 2. Configuration check
echo 3. Build fictional demo
echo 4. Run one cycle
echo 5. Status
echo 6. Verify Stripe configuration
echo 7. Send owner test email
echo 8. Enable launch after setup and testing
echo 9. Install background schedule
echo 0. Exit
choice /c 1234567890 /n /m "Choose: "
set "selection=%errorlevel%"
if "%selection%"==10 exit /b
if "%selection%"==9 powershell -NoProfile -File "%~dp0scripts\schedule.ps1"
if "%selection%"==8 py -3 -m margins launch
if "%selection%"==7 py -3 -m margins self-test
if "%selection%"==6 py -3 -m margins verify
if "%selection%"==5 py -3 -m margins status
if "%selection%"==4 py -3 -m margins run
if "%selection%"==3 (
  py -3 -m margins demo
  start "Margins demo" "%~dp0demo-output\index.html"
)
if "%selection%"==2 py -3 -m margins doctor
if "%selection%"==1 py -3 -m margins setup
pause
goto menu
