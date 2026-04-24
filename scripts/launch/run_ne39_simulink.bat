@echo off
cd /d "C:\Users\27443\Desktop\Multi-Agent  VSGs"
"C:\Users\27443\miniconda3\envs\andes_env\python.exe" -u scenarios\new_england\train_simulink.py --mode simulink --episodes 500 >> results\sim_ne39\logs\train_simulink_run3.log 2>&1
