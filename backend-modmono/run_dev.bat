@echo off
REM Development server startup script for Windows

REM Load environment variables from .env file
if exist .env (
    for /f "usebackq tokens=*" %%a in (".env") do (
        echo %%a | findstr /v "^#" > nul
        if not errorlevel 1 set %%a
    )
)

REM Default values
if not defined HOST set HOST=0.0.0.0
if not defined PORT set PORT=8000
if not defined RELOAD set RELOAD=true

echo Starting FHIR RAG API Development Server...
echo Host: %HOST%
echo Port: %PORT%
echo Reload: %RELOAD%
echo.

REM Run uvicorn with reload for development
if "%RELOAD%"=="true" (
    uvicorn app.app:app --host %HOST% --port %PORT% --reload --reload-dir app --log-level debug
) else (
    uvicorn app.app:app --host %HOST% --port %PORT% --log-level info
)
