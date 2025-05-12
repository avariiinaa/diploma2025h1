from flask import Flask, jsonify, render_template_string
import json
import os

app = Flask(__name__)
LOG_FILE = "logs/qwen_log.jsonl"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Qwen Monitor</title>
  <meta http-equiv="refresh" content="5">
  <style>
    body { font-family: sans-serif; padding: 2em; max-width: 800px; margin: auto; }
    .entry { margin-bottom: 2em; border-bottom: 1px solid #ccc; padding-bottom: 1em; }
    .prompt { font-weight: bold; color: #333; }
    .response { color: #555; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>🧠 Qwen Monitor</h1>
  {% if logs %}
    {% for entry in logs %}
      <div class="entry">
        <div class="prompt">Prompt:</div>
        <div>{{ entry["prompt"] }}</div>
        <div class="prompt">Response:</div>
        <div class="response">{{ entry["response"] }}</div>
      </div>
    {% endfor %}
  {% else %}
    <p>Логов пока нет.</p>
  {% endif %}
</body>
</html>
"""

def load_logs(max_lines=10):
    logs = []
    if not os.path.exists(LOG_FILE):
        return logs
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-max_lines:]
            for line in lines:
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Ошибка чтения логов: {e}")
    return logs

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, logs=load_logs())

@app.route("/api/logs")
def api_logs():
    return jsonify(load_logs())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
