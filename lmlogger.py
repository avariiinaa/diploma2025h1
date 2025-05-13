from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO
import psutil
import threading
import subprocess
from datetime import datetime
from collections import deque
import time
import signal
import os
import queue

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class LLMService:
    def __init__(self):
        self.llm_process = None
        self.response_queue = queue.Queue()
        self.running = False
        self.monitor_thread = None
        self.cpu_history = deque(maxlen=100)
        self.mem_history = deque(maxlen=100)
        self.timestamps = deque(maxlen=100)
        self.conversation = []
        
        # Запуск мониторинга ресурсов
        self.start_monitoring()
    
    def start_llm_process(self):
        """Запуск llama.cpp в фоновом режиме с STDIN"""
        if self.llm_process is None or self.llm_process.poll() is not None:
            self.llm_process = subprocess.Popen(
                ['./../llama.cpp/llama/bin/llama-cli', '-m', 'models/Qwen3-0.6B-Q4_K_M.gguf', '-n', '64', '--temp', '1', '--n-threads','4'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            # Поток для чтения вывода
            threading.Thread(target=self.read_output, daemon=True).start()
    
    def read_output(self):
        """Чтение вывода процесса"""
        while True:
            line = self.llm_process.stdout.readline()
            if not line:
                break
            self.response_queue.put(line.strip())
            socketio.emit('llm_output', {'text': line.strip()})
    
    def generate(self, prompt):
        """Отправка промпта в запущенный процесс"""
        if self.llm_process is None or self.llm_process.poll() is not None:
            self.start_llm_process()
            time.sleep(1)  # Даем процессу время на запуск
        
        self.llm_process.stdin.write(prompt + "/no_think")
        self.llm_process.stdin.flush()
        
        # Сохраняем в историю
        self.conversation.append({'role': 'user', 'content': prompt})
        socketio.emit('conversation_update', {'role': 'user', 'content': prompt})
    
    def start_monitoring(self):
        """Мониторинг ресурсов системы"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self.monitor_resources, daemon=True)
            self.monitor_thread.start()
    
    def monitor_resources(self):
        """Сбор метрик системы"""
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            self.cpu_history.append(cpu)
            self.mem_history.append(mem)
            self.timestamps.append(timestamp)
            
            socketio.emit('system_metrics', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': timestamp,
                'history': {
                    'timestamps': list(self.timestamps),
                    'cpu': list(self.cpu_history),
                    'memory': list(self.mem_history)
                }
            })
            
            time.sleep(1)
    
    def get_status(self):
        """Текущее состояние системы"""
        return {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent,
            'conversation': self.conversation,
            'running': self.running
        }

llm_service = LLMService()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/generate', methods=['POST'])
def api_generate():
    prompt = request.json.get('prompt', '')
    if prompt:
        llm_service.generate(prompt)
    return jsonify({'status': 'processing'})

@app.route('/api/status')
def api_status():
    return jsonify(llm_service.get_status())

@socketio.on('connect')
def handle_connect():
    socketio.emit('init', llm_service.get_status())

if __name__ == '__main__':
    llm_service.start_llm_process()  # Предварительный запуск
    socketio.run(app, host='0.0.0.0', port=8000)