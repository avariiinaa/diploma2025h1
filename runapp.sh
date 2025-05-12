#!/bin/bash

CONFIG_FILE="config.yaml"

MODEL_PATH=$(grep 'model_path:' $CONFIG_FILE | awk '{print $2}' | tr -d '"')
THREADS=$(grep 'threads:' $CONFIG_FILE | awk '{print $2}')
CTX_SIZE=$(grep 'ctx_size:' $CONFIG_FILE | awk '{print $2}')
PREDICT=$(grep 'predict:' $CONFIG_FILE | awk '{print $2}')

echo "📦 Qwen-инференс CLI (интерактивный режим)"
echo "  🧠 Модель: $MODEL_PATH"
echo "  🔧 Потоки: $THREADS | Контекст: $CTX_SIZE | Токены: $PREDICT"
echo "  💡 Напечатай 'exit' чтобы выйти."
echo

while true; do
  read -p "📝 Ввод> " PROMPT

  if [[ "$PROMPT" == "exit" ]]; then
    echo "👋 Выход."
    break
  fi

  ./llama.cpp/build/bin/main \
      -m "$MODEL_PATH" \
      -t "$THREADS" \
      -c "$CTX_SIZE" \
      -n "$PREDICT" \
      -p "$PROMPT"

  echo
done
