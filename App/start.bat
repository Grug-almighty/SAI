@echo off
title SAI
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting SAI...
python app.py
pause
