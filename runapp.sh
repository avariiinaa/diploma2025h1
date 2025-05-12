#!/bin/bash

CONFIG_FILE="config.yaml"

MODEL_PATH=$(grep 'model_path:' $CONFIG_FILE | awk '{print $2}' | tr -d '"')
THREADS=$(grep 'threads:' $CONFIG_FILE | awk '{print $2}')
CTX_SIZE=$(grep 'ctx_size:' $CONFIG_FILE | awk '{print $2}')
PREDICT=$(grep 'predict:' $CONFIG_FILE | awk '{print $2}')

echo "model: $MODEL_PATH"
echo "threads: $THREADS | ctx: $CTX_SIZE | tokens: $PREDICT"
echo "type exit to close"
echo

while true; do
  read -p "type> " PROMPT

  if [[ "$PROMPT" == "exit" ]]; then
    echo "exit"
    break
  fi

  ./llama.cpp/llama/bin/llama-cli \
      -m "$MODEL_PATH" \
      -t "$THREADS" \
      -c "$CTX_SIZE" \
      -n "$PREDICT" \
      -p "$PROMPT"

  echo
done
