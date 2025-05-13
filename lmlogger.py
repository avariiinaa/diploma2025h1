from flask import Flask, render_template_string, jsonify, request, Response
import threading
import subprocess
import json
import queue
import time

app = Flask(__name__)
response_queue = queue.Queue()

def stream_llm_response(prompt):
    """Функция для потоковой генерации через llama.cpp"""
    cmd = [
        './../llama.cpp/llama/bin/llama-cli',
        '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf',
        '-p', prompt+'/no_think',
        '-n', '64',
        '--temp', '0.7'
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    for line in iter(process.stdout.readline, ''):
        response_queue.put(line.strip())
    
    response_queue.put(None)  # Сигнал окончания

@app.route('/generate', methods=['POST'])
def generate():
    prompt = request.json.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    # Запуск генерации в отдельном потоке
    threading.Thread(
        target=stream_llm_response,
        args=(prompt,),
        daemon=True
    ).start()
    
    return jsonify({'status': 'generation_started'})

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            message = response_queue.get()
            if message is None:
                break
            yield f"data: {json.dumps({'text': message})}\n\n"
    
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <body>
            <textarea id="prompt" rows="4" cols="50"></textarea>
            <button onclick="generate()">Generate</button>
            <div id="output"></div>
            
            <script>
                const output = document.getElementById('output');
                const eventSource = new EventSource('/stream');
                
                eventSource.onmessage = function(e) {
                    const data = JSON.parse(e.data);
                    output.innerHTML += data.text + ' ';
                };
                
                function generate() {
                    const prompt = document.getElementById('prompt').value;
                    fetch('/generate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({prompt})
                    });
                }
            </script>
        </body>
        </html>
    ''')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)