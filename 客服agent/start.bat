@echo off
echo ====================================
echo Neowow 客服 Agent 启动脚本
echo ====================================
echo.

echo [1/2] 启动后端 (端口 8001)...
start "Neowow-Backend" cmd /k "cd /d D:\privateforyge\客服agent\backend && python main.py"

timeout /t 3 /nobreak >nul

echo [2/2] 启动前端 (端口 5173)...
start "Neowow-Frontend" cmd /k "cd /d D:\privateforyge\客服agent\frontend && npm run dev"

echo.
echo ====================================
echo 启动完成！
echo 后端：http://localhost:8001
echo 前端：http://localhost:5173
echo 局域网：http://192.168.10.209:5173
echo ====================================
echo.
echo 按任意键关闭此窗口（不影响已启动的服务）
pause >nul
