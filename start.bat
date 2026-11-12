@echo off
rem DailyLumen Web 看板启动脚本
rem 默认只读 + 127.0.0.1；写操作请自行在最后一行加 --enable-write
rem 用法：start.bat [端口]（默认 8765）

setlocal
set PORT=%1
if "%PORT%"=="" set PORT=8765

if not exist "local\.env" (
  echo [!] 缺少 local\.env，未配置访问密钥，serve 会拒绝启动。
  echo     生成密钥： python -c "import secrets; print(secrets.token_urlsafe(32))"
  pause
  exit /b 1
)

echo DailyLumen: http://127.0.0.1:%PORT%/ （只读模式，Ctrl+C 退出）
uv run --extra web python -m review_tool serve --port %PORT%
endlocal
