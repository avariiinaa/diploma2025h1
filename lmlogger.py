import subprocess
import threading
import time
import psutil
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
import os
import sys
import queue
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class LLMEngine:
    def __init__(self):
        self.active_process = None
        self.responses = queue.Queue()
        self.running = True
        self.model_loaded = False
        
        # Запускаем мониторинг ресурсов
        threading.Thread(target=self.monitor_resources, daemon=True).start()
        
        # Проверяем наличие файлов
        self.verify_files()
        
    def verify_files(self):
        """Проверка наличия необходимых файлов"""
        if not os.path.exists(f'''./{sys.argv[1]}'''):
            print("ERROR: llama.cpp executable './llama-cli' not found!", file=sys.stderr)
            sys.exit(1)
            
        if not os.path.exists('./models/Qwen3-0.6B-Q4_K_M.gguf'):
            print("ERROR: Model file not found!", file=sys.stderr)
            sys.exit(1)
            
        self.model_loaded = True

    def generate_response(self, prompt):
        """Запуск нового процесса для каждого запроса"""
        if not self.model_loaded:
            return False
            
        try:
            # Запускаем процесс с таймаутом
            process = subprocess.Popen(
                [
                    f'''./{sys.argv[1]}''',
                    '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf',
                    '-p', prompt,
                    '-n', '256',  # Максимальное количество токенов
                    '--temp', '0.7',
                    '--ctx-size', '2048'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Читаем вывод построчно
            full_response = []
            for line in process.stdout:
                line = line.strip()
                if line:
                    full_response.append(line)
                    self.responses.put(line)
                    socketio.emit('llm_response', {'text': line})
            
            # Ждем завершения с таймаутом
            try:
                process.wait(timeout=120)  # 2 минуты таймаут
            except subprocess.TimeoutExpired:
                process.kill()
                print("Процесс завершен по таймауту", file=sys.stderr)
                
            return True
            
        except Exception as e:
            print(f"Ошибка генерации: {str(e)}", file=sys.stderr)
            return False

    def monitor_resources(self):
        """Мониторинг использования ресурсов"""
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            socketio.emit('system_metrics', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': time.strftime("%H:%M:%S"),
                'status': 'ready' if self.model_loaded else 'error'
            })
            time.sleep(1)

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
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                #chat { border: 1px solid #ddd; padding: 15px; height: 400px; overflow-y: auto; margin-bottom: 15px; }
                .user { color: #1a73e8; margin-bottom: 10px; padding: 8px; background: #f0f7ff; border-radius: 4px; }
                .llm { color: #0d652d; margin-bottom: 10px; padding: 8px; background: #f0fff4; border-radius: 4px; }
                #metrics { margin-bottom: 15px; padding: 10px; background: #f5f5f5; border-radius: 4px; }
                textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; resize: vertical; min-height: 80px; }
                button { background: #1a73e8; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0d5bcd; }
                #status { font-weight: bold; }
                .status-ready { color: #0d652d; }
                .status-error { color: #d32f2f; }
                .loading { color: #666; }
            </style>
        </head>
        <body>
            <h1>LLM Chat</h1>
            <div id="metrics">
                CPU: <span id="cpu">0</span>% | 
                Memory: <span id="memory">0</span>% |
                Status: <span id="status" class="loading">Loading...</span>
            </div>
            <div id="chat"></div>
            <textarea id="prompt" placeholder="Type your message here..."></textarea>
            <button onclick="sendMessage()">Send</button>
            
            <script>
                const socket = io();
                const chatDiv = document.getElementById('chat');
                const statusEl = document.getElementById('status');
                let isProcessing = false;
                
                // Обработка ответов от LLM
                socket.on('llm_response', function(data) {
                    addMessage('llm', data.text);
                });
                
                // Обновление метрик системы
                socket.on('system_metrics', function(data) {
                    document.getElementById('cpu').textContent = data.cpu.toFixed(1);
                    document.getElementById('memory').textContent = data.memory.toFixed(1);
                    
                    if (data.status === 'ready') {
                        statusEl.textContent = "Ready";
                        statusEl.className = "status-ready";
                    } else {
                        statusEl.textContent = "Error (check server)";
                        statusEl.className = "status-error";
                    }
                });
                
                // Добавление сообщения в чат
                function addMessage(role, content) {
                    const msgDiv = document.createElement('div');
                    msgDiv.className = role;
                    msgDiv.innerHTML = `<strong>${role === 'user' ? 'You:' : 'AI:'}</strong> ${content}`;
                    chatDiv.appendChild(msgDiv);
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                }
                
                // Отправка сообщения
                function sendMessage() {
                    const prompt = document.getElementById('prompt').value.trim();
                    if (prompt && !isProcessing) {
                        isProcessing = true;
                        addMessage('user', prompt);
                        document.getElementById('prompt').value = '';
                        
                        fetch('/api/chat', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({prompt: prompt})
                        })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('Network error');
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.status !== 'success') {
                                addMessage('system', 'Error: ' + (data.message || 'Request failed'));
                            }
                        })
                        .catch(error => {
                            addMessage('system', 'Error sending request');
                            console.error('Error:', error);
                        })
                        .finally(() => {
                            isProcessing = false;
                        });
                    }
                }
                
                // Отправка по Enter (без Shift)
                document.getElementById('prompt').addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    data = request.get_json()
    prompt = data.get('prompt', '')
    
    if not prompt:
        return jsonify({'status': 'error', 'message': 'Empty prompt'}), 400
        
    # Запускаем генерацию в отдельном потоке
    threading.Thread(
        target=llm.generate_response,
        args=(prompt,),
        daemon=True
    ).start()
    
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    print("Starting server at http://localhost:8000")
    print("Make sure:")
    print("1. llama.cpp is compiled as './llama-cli'")
    print("2. Model file exists at 'models/Qwen3-0.6B-Q4_K_M.gguf'")
    
    try:
        socketio.run(app, host='0.0.0.0', port=8000)
    except KeyboardInterrupt:
        print("\nShutting down...")
        llm.running = False
        sys.exit(0)