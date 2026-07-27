@echo off
echo ============================
echo  DouyinMind 前端启动
echo ============================
cd /d %~dp0frontend

echo.
echo [1/2] 安装依赖...
call npm install

echo [2/2] 启动 Vite 开发服务器...
echo.
echo 前端地址: http://localhost:5173
echo.
call npm run dev
