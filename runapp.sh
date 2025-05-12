#!/bin/bash

# Настройки
MODEL_PATH="models/Qwen3-0.6B-Q4_K_M.gguf"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/qwen_log.jsonl"
LLAMA_CMD="./../llama.cpp/llama/llama-cli"  # Путь к бинарнику llama.cpp

# Создаем директорию для логов
mkdir -p "$LOG_DIR"

# Функция для экранирования JSON
escape_json() {
    local str="$1"
    str=${str//\\/\\\\}  # Экранируем обратные слеши первыми
    str=${str//\"/\\\"}  # Экранируем кавычки
    str=${str//$'\n'/\\n}  # Заменяем переносы строк
    str=${str//$'\r'/\\r}  # Заменяем возврат каретки
    str=${str//$'\t'/\\t}  # Заменяем табуляции
    echo "$str"
}

# Основной цикл
while true; do
    read -p "Введите промпт (или 'exit' для выхода): " PROMPT
    [[ "$PROMPT" == "exit" ]] && break

    # Запускаем llama.cpp с таймаутом (60 сек)
    echo "Генерация ответа..."
    RESPONSE=$(timeout 60s $LLAMA_CMD -m "$MODEL_PATH" -p "$PROMPT" 2>&1)
    EXIT_CODE=$?

    # Обработка ошибок
    if [ $EXIT_CODE -eq 124 ]; then
        RESPONSE="ОШИБКА: Превышено время ожидания ответа (60 сек)"
    elif [ $EXIT_CODE -ne 0 ]; then
        RESPONSE="ОШИБКА: Код выхода $EXIT_CODE - $RESPONSE"
    fi

    # Экранирование и логирование
    ESCAPED_PROMPT=$(escape_json "$PROMPT")
    ESCAPED_RESPONSE=$(escape_json "$RESPONSE")
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Формируем JSON запись
    JSON_ENTRY="{\"timestamp\":\"$TIMESTAMP\",\"prompt\":\"$ESCAPED_PROMPT\",\"response\":\"$ESCAPED_RESPONSE\"}"

    # Записываем в лог
    echo "$JSON_ENTRY" >> "$LOG_FILE"
    echo "===== Ответ сохранен ====="
    echo "Файл: $LOG_FILE"
    echo "--------------------------"
    echo "$RESPONSE"
    echo "=========================="
done

echo "Работа завершена. Логи доступны в $LOG_FILE"