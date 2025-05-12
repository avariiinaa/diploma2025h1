from flask import Flask, jsonify, render_template_string
import json

app = Flask(__name__)
LOG_FILE = "logs/qwen_log.jsonl"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>LLM Монитор</title>
  <meta http-equiv="refresh" content="5">
  <style>body { font-family: sans-serif; padding: 2em; }</style>
</head>
<body>
  <h1>🧠 Мониторинг Qwen</h1>
  {% for entry in logs %}
    <div style="margin-bottom: 1em;">
      <b>📝 Prompt:</b> {{ entry["prompt"] }}<br>
      <b>💬 Response:</b> {{ entry["response"] }}
    </div>
  {% endfor %}
</body>
</html>
"""

@app.route("/")
def index():
    logs = []
    try:
        with open(LOG_FILE) as f:
            for line in f:
                logs.append(json.loads(line))
    except FileNotFoundError:
        pass
    return render_template_string(HTML_TEMPLATE, logs=logs[-10:])  # последние 10

@app.route("/api/logs")
def api_logs():
    logs = []
    try:
        with open(LOG_FILE) as f:
            for line in f:
                logs.append(json.loads(line))
    except FileNotFoundError:
        pass
    return jsonify(logs[-10:])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
