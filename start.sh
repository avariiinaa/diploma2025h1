#!/bin/bash

# Запуск Flask-монитора в фоне
echo "🚀 Запуск Flask-сервера мониторинга..."
nohup python3 monitor_server.py > logs/flask.log 2>&1 &

# Ждём пару секунд, чтобы сервер стартанул
sleep 2

# Запуск основного приложения в фоне
echo "🧠 Запуск инференса Qwen..."
nohup bash run_qwen.sh > logs/qwen.log 2>&1 &
