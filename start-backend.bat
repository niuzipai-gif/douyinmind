@echo off
echo ============================
echo  DouyinMind 后端启动
echo ============================
cd /d %~dp0backend

echo.
echo [1/3] 检查虚拟环境...
if not exist ".venv" (
    echo 创建虚拟环境...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install uv
    uv sync --python 3.12
) else (
    call .venv\Scripts\activate.bat
)

echo [2/3] 安装 Playwright 浏览器...
playwright install chromium

echo [3/3] 启动 FastAPI...
echo.
echo 后端地址: http://127.0.0.1:8000
echo API 文档: http://127.0.0.1:8000/docs
echo.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
