import subprocess
import threading
import time
import psutil
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
import os
import sys
import queue

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class LLMEngine:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.running = True
        self.ready = False
        
        # Запускаем потоки
        threading.Thread(target=self.process_manager, daemon=True).start()
        threading.Thread(target=self.output_reader, daemon=True).start()
        threading.Thread(target=self.monitor_resources, daemon=True).start()
        threading.Thread(target=self.input_writer, daemon=True).start()

    def process_manager(self):
        """Управление жизненным циклом процесса"""
        while self.running:
            if not self.process or self.process.poll() is not None:
                self.start_process()
            time.sleep(1)

    def start_process(self):
        """Запуск llama.cpp с правильными параметрами"""
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()

            self.process = subprocess.Popen(
                [
                    './../llama.cpp/llama/bin/llama-cli',
                    '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf',
                    '--interactive',
                    '--ctx-size', '2048',
                    '--keep', '-1',
                    '--temp', '0.7',
                    '-r', '### User:',
                    '--color', '-i',
                    '-ins'  # Режим инструкций для лучшего диалога
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.ready = True
            print("Процесс LLM успешно запущен")
        except Exception as e:
            print(f"Ошибка запуска: {e}", file=sys.stderr)
            self.ready = False

    def input_writer(self):
        """Отправка промптов в процесс"""
        while self.running:
            if not self.ready:
                time.sleep(0.5)
                continue
                
            prompt = self.input_queue.get()
            try:
                self.process.stdin.write(prompt + "\n")
                self.process.stdin.flush()
                print(f"Отправлен промпт: {prompt[:50]}...")
            except Exception as e:
                print(f"Ошибка отправки: {e}", file=sys.stderr)
                self.ready = False

    def output_reader(self):
        """Чтение вывода процесса"""
        buffer = ""
        while self.running:
            if not self.ready or not self.process:
                time.sleep(0.5)
                continue
                
            try:
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                    
                buffer += line
                if "### User:" in buffer:
                    response = buffer.split("### User:")[0].strip()
                    if response:
                        self.output_queue.put(response)
                        socketio.emit('llm_response', {'text': response})
                    buffer = ""
            except Exception as e:
                print(f"Ошибка чтения: {e}", file=sys.stderr)
                self.ready = False

    def monitor_resources(self):
        """Мониторинг ресурсов системы"""
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            socketio.emit('system_metrics', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': time.strftime("%H:%M:%S"),
                'status': 'ready' if self.ready else 'error'
            })
            time.sleep(1)

    def generate(self, prompt):
        """Добавление промпта в очередь"""
        if self.ready:
            self.input_queue.put(prompt)
            return True
        return False

    def shutdown(self):
        """Корректное завершение"""
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

llm = LLMEngine()

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
                #status { font-weight: bold; }
                .error { color: red; }
            </style>
        </head>
        <body>
            <h1>LLM Chat</h1>
            <div id="metrics">
                CPU: <span id="cpu">0</span>% | 
                Memory: <span id="memory">0</span>% |
                Status: <span id="status">Loading...</span>
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
                
                // Обновление метрик
                socket.on('system_metrics', function(data) {
                    document.getElementById('cpu').textContent = data.cpu.toFixed(1);
                    document.getElementById('memory').textContent = data.memory.toFixed(1);
                    
                    if (data.status === 'ready') {
                        statusSpan.textContent = "Ready";
                        statusSpan.className = "";
                    } else {
                        statusSpan.textContent = "Error - retrying...";
                        statusSpan.className = "error";
                    }
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
                        }).catch(e => {
                            statusSpan.textContent = "Network error";
                            statusSpan.className = "error";
                        });
                        
                        document.getElementById('prompt').value = '';
                    }
                }
                
                // Отправка по Enter
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
    if llm.generate(data['prompt']):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'LLM not ready'}), 503

def shutdown_handler(signum, frame):
    print("\nЗавершение работы...")
    llm.shutdown()
    sys.exit(0)

import signal
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

if __name__ == '__main__':
    print("Сервер запущен: http://localhost:8000")
    print("Убедитесь что:")
    print("1. llama.cpp скомпилирован как './main'")
    print("2. Модель находится в './models/llama-2-7b.Q4_K_M.gguf'")
    socketio.run(app, host='0.0.0.0', port=8000)