@echo off
echo Installing Music Manager dependencies...
python -m pip install -r requirements.txt
echo.
echo Done! Usage:
echo   python main.py scan   "C:\Path\To\Music"
echo   python main.py report
echo   python main.py organise "C:\Path\To\Organised"
echo.
pause
