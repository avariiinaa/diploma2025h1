import subprocess
import threading
import time
import psutil
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
import os
import sys

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class LLMWrapper:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self.keep_alive = True
        self.start_process()
        
        # Мониторинг ресурсов
        threading.Thread(target=self.monitor_resources, daemon=True).start()

    def start_process(self):
        """Запуск llama.cpp с автоматическим восстановлением"""
        with self.lock:
            if self.process and self.process.poll() is None:
                return

            cmd = [
                './../llama.cpp/llama/bin/llama-cli',
                '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf',
                '--interactive-first',
                '--ctx-size', '2048',
                '--keep', '30',
                '--temp', '0.7',
                '-r', '### User:',
                '--color', '-i'
            ]
            
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                print("LLM процесс успешно запущен")
                
                # Поток для чтения вывода
                threading.Thread(target=self.read_output, daemon=True).start()
                
            except Exception as e:
                print(f"Ошибка запуска LLM: {e}", file=sys.stderr)
                self.process = None

    def read_output(self):
        """Чтение вывода процесса"""
        buffer = ""
        while self.keep_alive and self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                    
                buffer += line
                if "### User:" in buffer:
                    response = buffer.split("### User:")[0].strip()
                    if response:
                        socketio.emit('llm_response', {'text': response})
                    buffer = ""
                    
            except Exception as e:
                print(f"Ошибка чтения вывода: {e}", file=sys.stderr)
                break

    def send_prompt(self, prompt):
        """Отправка промпта с защитой от сбоев"""
        for attempt in range(3):  # 3 попытки
            with self.lock:
                if not self.process or self.process.poll() is not None:
                    self.start_process()
                    time.sleep(2)  # Даем время на инициализацию
                    continue
                    
                try:
                    self.process.stdin.write(f"{prompt}\n")
                    self.process.stdin.flush()
                    return True
                    
                except (BrokenPipeError, IOError) as e:
                    print(f"Ошибка отправки (попытка {attempt+1}): {e}", file=sys.stderr)
                    self.process = None
                    time.sleep(1)
                    
        print("Не удалось отправить промпт после 3 попыток")
        return False

    def monitor_resources(self):
        """Мониторинг использования ресурсов"""
        while self.keep_alive:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            socketio.emit('system_metrics', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': time.strftime("%H:%M:%S")
            })
            time.sleep(1)

    def shutdown(self):
        """Корректное завершение"""
        self.keep_alive = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

llm = LLMWrapper()

@app.route('/')
def home():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>LLM Chat</title>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
            <style>
                body { font-family: Arial; max-width: 800px; margin: 0 auto; padding: 20px; }
                #chat { border: 1px solid #ddd; padding: 10px; height: 400px; overflow-y: auto; }
                .user { color: blue; margin: 5px 0; }
                .llm { color: green; margin: 5px 0; }
                #metrics { margin: 10px 0; padding: 10px; background: #f5f5f5; }
                textarea { width: 100%; height: 80px; margin: 10px 0; }
                button { padding: 8px 15px; background: #4CAF50; color: white; border: none; cursor: pointer; }
                button:hover { background: #45a049; }
            </style>
        </head>
        <body>
            <h1>LLM Chat</h1>
            <div id="metrics">
                CPU: <span id="cpu">0</span>% | 
                Memory: <span id="memory">0</span>% | 
                <span id="status">Status: OK</span>
            </div>
            <div id="chat"></div>
            <textarea id="prompt" placeholder="Type your message..."></textarea>
            <button onclick="send()">Send</button>
            
            <script>
                const socket = io();
                const chatDiv = document.getElementById('chat');
                const statusSpan = document.getElementById('status');
                
                // Обработка ответов
                socket.on('llm_response', function(data) {
                    addMessage('llm', data.text);
                });
                
                // Метрики системы
                socket.on('system_metrics', function(data) {
                    document.getElementById('cpu').textContent = data.cpu.toFixed(1);
                    document.getElementById('memory').textContent = data.memory.toFixed(1);
                });
                
                function addMessage(role, text) {
                    const div = document.createElement('div');
                    div.className = role;
                    div.textContent = (role === 'user' ? 'You: ' : 'AI: ') + text;
                    chatDiv.appendChild(div);
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                }
                
                function send() {
                    const prompt = document.getElementById('prompt').value.trim();
                    if (prompt) {
                        addMessage('user', prompt);
                        
                        fetch('/api/chat', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({prompt: prompt})
                        }).then(response => {
                            if (!response.ok) {
                                statusSpan.textContent = "Status: Error sending message";
                                statusSpan.style.color = "red";
                            }
                        });
                        
                        document.getElementById('prompt').value = '';
                    }
                }
                
                // Отправка по Enter (без Shift)
                document.getElementById('prompt').addEventListener('keypress', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                    }
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    data = request.get_json()
    if llm.send_prompt(data['prompt']):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 500

def shutdown_handler(signum, frame):
    print("\nЗавершение работы...")
    llm.shutdown()
    sys.exit(0)

import signal
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

if __name__ == '__main__':
    print("Сервер запущен: http://localhost:8000")
    socketio.run(app, host='0.0.0.0', port=8000)