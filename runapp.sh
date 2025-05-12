#!/bin/bash
mkdir -p logs
CONFIG_FILE="config.yaml"

MODEL_PATH=$(grep 'model_path:' $CONFIG_FILE | awk '{print $2}' | tr -d '"')
LLAMA_PATH=$(grep 'llama_path:' $CONFIG_FILE | awk '{print $2}')
THREADS=$(grep 'threads:' $CONFIG_FILE | awk '{print $2}')
CTX_SIZE=$(grep 'ctx_size:' $CONFIG_FILE | awk '{print $2}')
PREDICT=$(grep 'predict:' $CONFIG_FILE | awk '{print $2}')
TEMP=$(grep 'temp:' $CONFIG_FILE | awk '{print $2}')
TOP_K=$(grep 'topk:' $CONFIG_FILE | awk '{print $2}')
TOP_P=$(grep 'topp:' $CONFIG_FILE | awk '{print $2}')
PENALTY=$(grep 'pen:' $CONFIG_FILE | awk '{print $2}')
MIN_P=$(grep 'minp:' $CONFIG_FILE | awk '{print $2}')

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
  
  RESPONSE=$(.$LLAMA_PATH \
      -m "$MODEL_PATH" \
      -t "$THREADS" \
      -c "$CTX_SIZE" \
      -n "$PREDICT" \
      --temp "$TEMP" \
      --top_k "$TOP_K" \
      --top_p "$TOP_P" \
      --min_p "$MIN_P" \
      --repeat_penalty "$PENALTY" \
      -p "$PROMPT./no_think" 2>&1 | tee /dev/tty)
  echo $RESPONSE
  ESCAPED_RESPONSE=$(echo "$RESPONSE" | \
  sed -e 's/"/\\"/g' \
      -e 's/\\/\\\\/g' \
      -e 's/\n/\\n/g' \
      -e 's/\r/\\r/g' \
      -e 's/\t/\\t/g')
  # Формируем JSON-запись и пишем в лог
  JSON_ENTRY="{\"prompt\":\"$PROMPT\",\"response\":\"$ESCAPED_RESPONSE\"}"
  echo "$JSON_ENTRY" >> "logs/qwen_log.jsonl"

done
