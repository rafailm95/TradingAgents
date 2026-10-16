@echo off
cd /d "%~dp0"
echo ONE BYBIT PUBLIC DATA COLLECTION - no API key or login.
echo First: historical download. Then: about 72 hours of market sampling.
echo Keep this window open, the laptop plugged in, and the lid open.
echo If interrupted, run this same START_ALL.cmd again to resume.
echo Final upload file: BYBIT_SEND_THIS.zip
where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 -S scripts\collect_bybit_complete.py
goto DONE
:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python -S scripts\collect_bybit_complete.py
goto DONE
:NO_PYTHON
echo Python 3 is required. Use the computer where the earlier collector ran.
:DONE
echo.
echo Upload BYBIT_SEND_THIS.zip when it is created, including error/gap reports.
pause
