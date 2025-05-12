#!/bin/bash

# Запуск Flask-монитора в фоне
echo "run server..."
python3 monitor_server.py > logs/flask.log 2>&1 &

# Ждём пару секунд, чтобы сервер стартанул
sleep 2

# Запуск основного приложения
echo "run Qwen..."
bash run_qwen.sh
