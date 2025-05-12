#!/bin/bash

mkdir -p logs

while true; do
  read -p "type> " PROMPT
  [[ "$PROMPT" == "exit" ]] && break

  RESPONSE=$(./../llama.cpp/llama/bin/llama-cli -m models/Qwen3-0.6B-Q4_K_M.gguf -p "$PROMPT")

  echo "===== RAW RESPONSE ====="
  echo "$RESPONSE"
  echo "========================"

  ESCAPED_RESPONSE=$(echo "$RESPONSE" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')

  echo "{\"prompt\": \"$PROMPT\", \"response\": \"$ESCAPED_RESPONSE\"}" >> logs/qwen_log.jsonl
done
