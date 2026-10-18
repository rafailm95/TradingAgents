@echo off
setlocal
cd /d "%~dp0"
echo BYBIT PUBLIC DATA: BTC ETH LTC SOL XRP. No API key or login.
echo Historical download first, then about72hours of market sampling.
echo Keep this window open, laptop plugged in, Internet connected, lid open.
echo Final file to send: BYBIT_SEND_THIS.zip
where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 -S scripts\verify_bybit_packet_026.py
if errorlevel 1 goto DONE
py -3 -S scripts\collect_bybit_packet_026.py
goto DONE
:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
python -S scripts\verify_bybit_packet_026.py
if errorlevel 1 goto DONE
python -S scripts\collect_bybit_packet_026.py
goto DONE
:NO_PYTHON
echo Python3 is required. Use the PC where the earlier Bybit collector worked.
echo Official installer: https://www.python.org/downloads/windows/
:DONE
echo.
echo If BYBIT_SEND_THIS.zip exists, send only that ZIP, including any gap report.
echo To resume an interrupted capture, run this same START_ALL.cmd again.
pause
endlocal
