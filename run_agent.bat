@echo off
setlocal

:: Load environment if needed, but the python script itself loads .env
if not exist ".env" (
    echo [ERROR] .env file not found. Please create one with GOOGLE_API_KEY.
    exit /b 1
)

:: Activate venv and run agent
call .venv\Scripts\activate.bat
python tools\agent\agent.py %*

endlocal
