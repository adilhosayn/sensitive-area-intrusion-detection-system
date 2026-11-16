@echo off
setlocal enabledelayedexpansion
title Eagle Eye AI - Live Camera Surveillance

echo =====================================================================
echo           EAGLE EYE AI - LIVE CAMERA SURVEILLANCE LAUNCHER
echo =====================================================================
echo.

set "PROJECT_DIR=E:\Project\sentinel-vision-main"
if not exist "!PROJECT_DIR!" (
    set "PROJECT_DIR=%~dp0..\sentinel-vision-main"
)
if not exist "!PROJECT_DIR!" (
    set "PROJECT_DIR=%~dp0"
)

if not exist "!PROJECT_DIR!\src\main.py" (
    echo [ERROR] Could not find Eagle Eye project directory at:
    echo         !PROJECT_DIR!
    echo.
    echo Please make sure sentinel-vision-main is located at:
    echo E:\Project\sentinel-vision-main
    echo.
    goto fail
)

echo [1/4] Project directory located: !PROJECT_DIR!

set "VENV_PYTHON=!PROJECT_DIR!\.venv\Scripts\python.exe"
if not exist "!VENV_PYTHON!" (
    set "VENV_PYTHON=%~dp0backend\.venv\Scripts\python.exe"
)

if not exist "!VENV_PYTHON!" (
    echo [ERROR] Virtual environment python.exe not found.
    echo Checked: !PROJECT_DIR!\.venv\Scripts\python.exe
    echo Checked: %~dp0backend\.venv\Scripts\python.exe
    echo.
    goto fail
)
echo [2/4] Python environment verified: !VENV_PYTHON!

set "MODEL_PATH=!PROJECT_DIR!\models\rik_best_best.pt"
if not exist "!MODEL_PATH!" (
    echo [ERROR] Weapon detection model not found at:
    echo         !MODEL_PATH!
    echo.
    goto fail
)
echo [3/4] Weapon model verified: !MODEL_PATH!

set "CONFIG_PATH=configs/default.yaml"
if not exist "!PROJECT_DIR!\!CONFIG_PATH!" (
    echo [ERROR] Configuration file not found at:
    echo         !PROJECT_DIR!\!CONFIG_PATH!
    echo.
    goto fail
)
echo [4/4] Configuration verified: !CONFIG_PATH!

echo.
echo =====================================================================
echo Starting Live Camera Surveillance...
echo - Camera: Laptop Webcam (index 0)
echo - Models: YOLO11n + YOLO Weapon Detector (rik_best_best.pt)
echo - Audio: Emergency Siren + Security Beeps enabled
echo.
echo Press 'q' inside the camera window to stop surveillance.
echo =====================================================================
echo.

cd /d "!PROJECT_DIR!"
"!VENV_PYTHON!" -m src.main --config "!CONFIG_PATH!" --profile eagle_eye_cpu
if errorlevel 1 (
    echo.
    echo [ERROR] Surveillance pipeline exited with an error code: %errorlevel%
    echo If your laptop webcam was busy or not found, try testing with the sample video:
    echo "!VENV_PYTHON!" -m src.main --config "!CONFIG_PATH!" --profile eagle_eye_cpu --source data/samples/test_video.mp4
    echo.
    goto fail
)

echo.
echo [INFO] Surveillance ended cleanly.
goto end

:fail
echo.
echo =====================================================================
echo Launch failed. Please review the error message above.
echo =====================================================================

:end
echo Press any key to close this window...
pause >nul
endlocal
