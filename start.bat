@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   音流 (VoiceFlow Studio) - 多引擎并发 AI 语音识别工作台
echo ========================================================
echo.
echo  [1] 启动桌面客户端 (默认3秒后自动进入)
echo  [2] 启动 Web 独立服务 (FastAPI 后端 + 前端页面)
echo.

choice /c 12 /d 1 /t 3 /m "请选择启动模式"
if errorlevel 2 goto start_web
goto start_gui

:start_gui
echo.
echo 正在启动音流桌面客户端...
if exist "%~dp0runtime\python.exe" goto gui_runtime
if exist "C:\Python314\python.exe" goto gui_py314
goto gui_system

:gui_runtime
set "PY=%~dp0runtime\python.exe"
goto gui_launch

:gui_py314
set "PY=C:\Python314\python.exe"
goto gui_launch

:gui_system
set "PY=python"
goto gui_launch

:gui_launch
if exist "%~dp0app\desktop_app.py" (
    cd /d "%~dp0app"
    start "" "%PY%" desktop_app.py
    exit /b 0
)

if exist "%~dp0desktop_app.py" (
    start "" "%PY%" desktop_app.py
    exit /b 0
)

echo [错误] 未找到 desktop_app.py 入口文件
pause
exit /b 1

:start_web
echo.
echo [1/2] 正在启动 FastAPI 后端服务 (端口: 5637)...

if exist "%~dp0runtime\python.exe" (
    set "PY=%~dp0runtime\python.exe"
) else (
    set "PY=python"
)

if exist "%~dp0app\server.py" (
    start "VoiceFlow Backend" cmd /c "cd /d %~dp0app && "%PY%" server.py"
) else (
    start "VoiceFlow Backend" cmd /c "cd /d %~dp0 && "%PY%" server.py"
)

echo [2/2] 正在启动前端开发服务...
if exist "%~dp0frontend" (
    cd /d "%~dp0frontend"
    start "VoiceFlow Frontend" cmd /c "npm run dev -- --host"
) else if exist "%~dp0app\frontend" (
    cd /d "%~dp0app\frontend"
    start "VoiceFlow Frontend" cmd /c "npm run dev -- --host"
)

echo.
echo 服务启动完成，请在浏览器中访问: http://localhost:5173
timeout /t 5 >nul
exit /b 0
