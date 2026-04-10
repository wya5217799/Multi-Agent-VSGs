#!/bin/bash
source ~/andes_venv/bin/activate
cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
nohup python3 scenarios/new_england/train_andes.py --episodes 2000 --seed 42 > /tmp/ne_train.log 2>&1 &
echo "NE PID: $!"
