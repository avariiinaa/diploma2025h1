import subprocess
import json
import os
from datetime import datetime

def log_interaction(prompt, response):
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "response": response
    }
    os.makedirs("logs", exist_ok=True)
    with open("logs/llama_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")

def run_llama(model_path, prompt):
    # Запуск llama.cpp (пример команды)
    cmd = [
        "./../llama.cpp/llama/bin/llama-cli",  # Путь к llama.cpp (main)
        "-m", model_path,
        "--prompt", prompt,
        "--temp", "1",
        "--n-predict", "64"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True,timeout=20)
    print("STDOUT:", result.stdout)  # Дебаг
    print("STDERR:", result.stderr)  # Дебаг
    return result.stdout.strip()

if __name__ == "__main__":
    model_path = "models/Qwen3-0.6B-Q4_K_M.gguf"  # Укажите путь к модели
    print("Llama.cpp CLI (type 'exit' to quit)")

    while True:
        prompt = input("> ")+'/no_think'
        print(prompt)
        if prompt.lower() == "exit/no_think":
            break

        response = run_llama(model_path, prompt)
        print("Response:", response)

        log_interaction(prompt, response)  # Запись в лог