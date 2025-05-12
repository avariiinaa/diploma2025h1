#!/bin/bash

echo "🔍 Использование памяти:"
free -h

echo "🖥️ Загрузка CPU:"
top -bn1 | grep "Cpu(s)"

echo "📦 Модель:"
ps aux | grep main | grep -v grep
