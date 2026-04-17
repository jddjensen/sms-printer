@echo off
setlocal

set PYTHON=C:\Users\jddje\AppData\Local\Programs\Python\Python312\python.exe
set NGROK=C:\Users\jddje\sms-printer\ngrok.exe
for /f "usebackq tokens=1,2 delims==" %%A in (".env") do set %%A=%%B

cd /d %~dp0

echo Starting ngrok...
start "ngrok" /B "%NGROK%" http 5000
timeout /t 3 /nobreak >nul

echo Configuring Twilio webhook...
%PYTHON% setup_webhook.py

echo Starting SMS printer server...
timeout /t 1 /nobreak >nul
start "" http://localhost:5000
%PYTHON% app.py
