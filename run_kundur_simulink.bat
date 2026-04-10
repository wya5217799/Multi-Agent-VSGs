@echo off
cd /d "C:\Users\27443\Desktop\Multi-Agent  VSGs"
"C:\Users\27443\miniconda3\envs\andes_env\python.exe" -u scenarios\kundur\train_simulink.py --mode simulink >> results\sim_kundur\logs\train_simulink_run4.log 2>&1
