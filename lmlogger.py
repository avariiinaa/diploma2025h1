import os
import sys
import time
import signal
import threading
import subprocess
import queue
import psutil
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

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
        self.process_lock = threading.Lock()
        self.model_path = 'models/Qwen3-0.6B-Q4_K_M.gguf'  # Убедитесь в правильности пути
        
        # Проверка существования файлов
        self.check_files()
        
        self.start_monitoring()
        self.start_llm_process()

    def check_files(self):
        """Проверка наличия необходимых файлов"""
        required_files = {
            'llama.cpp': './../llama.cpp/llama/bin/llama-cli',
            'model': self.model_path
        }
        
        for name, path in required_files.items():
            if not os.path.exists(path):
                print(f"Error: {name} not found at {path}", file=sys.stderr)
                print("Please ensure:")
                print("1. llama.cpp is compiled and named 'main' in current directory")
                print(f"2. Model file exists at {self.model_path}")
                sys.exit(1)

    def start_llm_process(self):
        """Запуск llama.cpp с улучшенной обработкой ошибок"""
        with self.process_lock:
            if self.llm_process is not None and self.llm_process.poll() is None:
                return
            
            try:
                # Убедимся, что старый процесс завершён
                if self.llm_process is not None:
                    self.llm_process.terminate()
                    try:
                        self.llm_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.llm_process.kill()
                
                # Запускаем новый процесс
                self.llm_process = subprocess.Popen(
                    ['./main', 
                     '-m', self.model_path,
                     '-n', '256',
                     '--temp', '0.7',
                     '--ctx-size', '2048',
                     '--keep', '30'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    start_new_session=True  # Важно для корректного завершения
                )
                
                # Запускаем поток чтения вывода
                threading.Thread(target=self.read_output, daemon=True).start()
                print("LLM process started successfully")
                
                # Мониторинг stderr для диагностики
                threading.Thread(target=self.read_stderr, daemon=True).start()
                
            except Exception as e:
                print(f"Failed to start LLM process: {str(e)}", file=sys.stderr)
                self.llm_process = None

    def read_output(self):
        """Чтение stdout процесса"""
        while self.llm_process and self.llm_process.poll() is None:
            try:
                line = self.llm_process.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                if line:  # Игнорируем пустые строки
                    self.response_queue.put(line)
                    socketio.emit('llm_output', {'text': line})
                    
            except (ValueError, IOError) as e:
                print(f"Output read error: {str(e)}", file=sys.stderr)
                break

    def read_stderr(self):
        """Чтение stderr для диагностики"""
        while self.llm_process and self.llm_process.poll() is None:
            try:
                line = self.llm_process.stderr.readline()
                if not line:
                    break
                    
                line = line.strip()
                if line:  # Выводим ошибки в консоль
                    print(f"LLM stderr: {line}", file=sys.stderr)
                    
            except (ValueError, IOError) as e:
                print(f"Error reading stderr: {str(e)}", file=sys.stderr)
                break

    def generate(self, prompt):
        """Отправка промпта с обработкой ошибок"""
        if not prompt.strip():
            return
            
        with self.process_lock:
            # Проверяем состояние процесса
            if self.llm_process is None or self.llm_process.poll() is not None:
                print("LLM process not running, attempting to restart...")
                self.start_llm_process()
                time.sleep(2)  # Даём время на инициализацию
                
            if self.llm_process is None or self.llm_process.poll() is not None:
                print("Failed to start LLM process")
                socketio.emit('llm_error', {'text': 'LLM process is not running'})
                return
                
            try:
                # Добавляем завершающий символ новой строки
                full_prompt = f"{prompt}\n"
                
                # Пишем в stdin
                self.llm_process.stdin.write(full_prompt)
                self.llm_process.stdin.flush()
                
                # Логируем запрос
                self.conversation.append({'role': 'user', 'content': prompt})
                socketio.emit('conversation_update', {'role': 'user', 'content': prompt})
                
            except (BrokenPipeError, IOError) as e:
                print(f"Write error: {str(e)}", file=sys.stderr)
                self.llm_process = None
                socketio.emit('llm_error', {'text': 'Connection to LLM lost, reconnecting...'})
                self.generate(prompt)  # Повторная попытка
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
    # Обработка Ctrl+C для корректного завершения
    def signal_handler(sig, frame):
        print("\nShutting down...")
        llm_service.running = False
        if llm_service.llm_process:
            llm_service.llm_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("Starting server...")
    print(f"Web interface: http://localhost:8000")
    socketio.run(app, host='0.0.0.0', port=8000)