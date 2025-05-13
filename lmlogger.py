from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO
import subprocess
import threading
import psutil
import time
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class SimpleLLMServer:
    def __init__(self):
        self.llm_process = None
        self.conversation = []
        self.running = True
        self.start_llm()
        threading.Thread(target=self.monitor_resources, daemon=True).start()

    def start_llm(self):
        """Запуск llama.cpp в режиме диалога"""
        if not os.path.exists('./../llama.cpp/llama/bin/llama-cli'):
            print("Error: llama.cpp executable './main' not found!")
            return

        if not os.path.exists('models/Qwen3-0.6B-Q4_K_M.gguf'):
            print("Error: Model file not found!")
            return

        # Запускаем процесс с поддержкой диалога
        self.llm_process = subprocess.Popen(
            ['./../llama.cpp/llama/bin/llama-cli', 
             '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf',
             '--interactive',  # Режим интерактивного диалога
             '--ctx-size', '2048',
             '--keep', '-1',  # Бесконечный диалог
             '--temp', '0.7',
             '--color', '-i',
             '-r', 'User:',
             '-f', 'prompts/chat-with-bob.txt'],  # Файл с промптом
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Поток для чтения ответов
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self):
        """Чтение вывода модели"""
        buffer = ""
        while self.running and self.llm_process.poll() is None:
            line = self.llm_process.stdout.readline()
            if not line:
                break
                
            buffer += line
            if "User:" in buffer:  # Конец ответа модели
                response = buffer.split("User:")[0].strip()
                if response:
                    self.conversation.append(('llm', response))
                    socketio.emit('llm_response', {'text': response})
                buffer = ""

    def send_prompt(self, prompt):
        """Отправка промпта модели"""
        if not self.llm_process or self.llm_process.poll() is not None:
            self.start_llm()
            time.sleep(1)  # Даем время на запуск
            
        try:
            self.conversation.append(('user', prompt))
            self.llm_process.stdin.write(f"{prompt}\n")
            self.llm_process.stdin.flush()
        except Exception as e:
            print(f"Error sending prompt: {e}")

    def monitor_resources(self):
        """Мониторинг CPU и памяти"""
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            socketio.emit('system_metrics', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': time.strftime("%H:%M:%S")
            })
            time.sleep(1)

llm_server = SimpleLLMServer()

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
            </style>
        </head>
        <body>
            <h1>LLM Chat</h1>
            <div id="metrics">
                CPU: <span id="cpu">0</span>% | 
                Memory: <span id="memory">0</span>%
            </div>
            <div id="chat"></div>
            <textarea id="prompt" placeholder="Type your message..."></textarea>
            <button onclick="send()">Send</button>
            
            <script>
                const socket = io();
                const chatDiv = document.getElementById('chat');
                
                // Обработка ответов от LLM
                socket.on('llm_response', function(data) {
                    const div = document.createElement('div');
                    div.className = 'llm';
                    div.textContent = 'LLM: ' + data.text;
                    chatDiv.appendChild(div);
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                });
                
                // Обновление метрик системы
                socket.on('system_metrics', function(data) {
                    document.getElementById('cpu').textContent = data.cpu.toFixed(1);
                    document.getElementById('memory').textContent = data.memory.toFixed(1);
                });
                
                // Отправка промпта
                function send() {
                    const prompt = document.getElementById('prompt').value;
                    if (prompt.trim()) {
                        const div = document.createElement('div');
                        div.className = 'user';
                        div.textContent = 'You: ' + prompt;
                        chatDiv.appendChild(div);
                        
                        fetch('/api/chat', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({prompt: prompt})
                        });
                        
                        document.getElementById('prompt').value = '';
                        chatDiv.scrollTop = chatDiv.scrollHeight;
                    }
                }
            </script>
        </body>
        </html>
    ''')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    llm_server.send_prompt(data['prompt'])
    return jsonify({'status': 'sent'})

if __name__ == '__main__':
    print("Starting server at http://localhost:8000")
    socketio.run(app, host='0.0.0.0', port=8000)