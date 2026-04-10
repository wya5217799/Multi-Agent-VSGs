@echo off
cd /d "C:\Users\27443\Desktop\Multi-Agent  VSGs"
echo ================================================
echo   Profiling 1 Kundur Simulink Episode
echo   (takes ~30-60s, please wait)
echo ================================================
echo.
"C:\Users\27443\miniconda3\envs\andes_env\python.exe" -u scripts\profile_one_episode.py
echo.
echo ================================================
echo   Done! Results saved to results\sim_kundur\logs\profile_1ep.json
echo ================================================
pause
