import time
import psutil
import threading
import subprocess
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import json
import os
import signal

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

class LLMService:
    def __init__(self, llama_path, model_path, log_file="llm_conversation.log", 
                 max_history=100, refresh_interval=1.0, host='0.0.0.0', port=5000):
        """
        Инициализация LLM сервиса с веб-интерфейсом
        
        Args:
            llama_path (str): Путь к исполняемому файлу llama.cpp
            model_path (str): Путь к модели GGUF
            log_file (str): Путь к файлу логов
            max_history (int): Максимальное количество записей в истории метрик
            refresh_interval (float): Интервал обновления метрик (секунды)
            host (str): Хост для веб-сервера
            port (int): Порт для веб-сервера
        """
        self.llama_path = llama_path
        self.model_path = model_path
        self.log_file = log_file
        self.refresh_interval = refresh_interval
        self.running = False
        self.monitor_thread = None
        self.llm_process = None
        self.host = host
        self.port = port
        
        # Очереди для хранения истории
        self.cpu_history = deque(maxlen=max_history)
        self.mem_history = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)
        self.conversation = deque(maxlen=50)
        
        # Инициализация файла лога
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n\n=== New Session [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===\n")
        
        # Запуск мониторинга
        self.start_monitoring()
        
        # Запуск веб-сервера в отдельном потоке
        self.server_thread = threading.Thread(
            target=lambda: socketio.run(app, host=self.host, port=self.port),
            daemon=True
        )
        self.server_thread.start()
    
    def _monitor_resources(self):
        """Мониторинг использования ресурсов"""
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            timestamp = time.time()
            
            self.cpu_history.append(cpu)
            self.mem_history.append(mem)
            self.timestamps.append(timestamp)
            
            # Отправка данных через WebSocket
            socketio.emit('metrics_update', {
                'cpu': cpu,
                'memory': mem,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
            
            time.sleep(self.refresh_interval)
    
    def start_monitoring(self):
        """Запуск мониторинга ресурсов"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
            self.monitor_thread.start()
            print("Resource monitoring started...")
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        print("Resource monitoring stopped.")
    
    def generate_response(self, prompt, max_tokens=128, temp=0.7):
        """
        Генерация ответа с помощью llama.cpp
        
        Args:
            prompt (str): Входной промпт
            max_tokens (int): Максимальное количество токенов
            temp (float): Температура генерации
            
        Returns:
            str: Сгенерированный ответ
        """
        if not os.path.exists(self.llama_path):
            raise FileNotFoundError(f"llama.cpp not found at {self.llama_path}")
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        
        # Формирование команды
        cmd = [
            self.llama_path,
            "-m", self.model_path,
            "-p", prompt,
            "-n", str(max_tokens),
            "--temp", str(temp)
        ]
        
        # Запуск процесса
        self.llm_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Чтение вывода в реальном времени
        response = []
        for line in iter(self.llm_process.stdout.readline, ''):
            cleaned_line = line.strip()
            if cleaned_line:
                response.append(cleaned_line)
                # Отправка частичного ответа через WebSocket
                socketio.emit('partial_response', {'text': cleaned_line})
        
        full_response = "\n".join(response)
        
        # Логирование диалога
        self._log_conversation(prompt, full_response)
        
        return full_response
    
    def _log_conversation(self, prompt, response):
        """Логирование диалога"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'prompt': prompt,
            'response': response
        }
        
        self.conversation.append(log_entry)
        
        # Сохранение в файл
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}]\nUser: {prompt}\nLLM: {response}\n{'-'*40}\n")
        
        # Отправка через WebSocket
        socketio.emit('conversation_update', log_entry)
    
    def stop_llm(self):
        """Остановка генерации"""
        if self.llm_process and self.llm_process.poll() is None:
            self.llm_process.terminate()
            try:
                self.llm_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.llm_process.kill()
            print("LLM process stopped")
    
    def get_current_state(self):
        """Получение текущего состояния для API"""
        return {
            'metrics': {
                'cpu': psutil.cpu_percent(),
                'memory': psutil.virtual_memory().percent,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            },
            'conversation': list(self.conversation),
            'system': {
                'running': self.running,
                'llm_active': self.llm_process is not None and self.llm_process.poll() is None
            }
        }

# Веб-роуты
@app.route('/')
def index():
    """Главная страница с мониторингом"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """API для получения текущего статуса"""
    return jsonify(llm_service.get_current_state())

@app.route('/api/generate', methods=['POST'])
def generate_text():
    """API для генерации текста"""
    data = request.json
    prompt = data.get('prompt', '')
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    # Запуск генерации в отдельном потоке
    threading.Thread(
        target=llm_service.generate_response,
        args=(prompt,)
    ).start()
    
    return jsonify({'status': 'generation_started'})

@app.route('/api/stop', methods=['POST'])
def stop_generation():
    """API для остановки генерации"""
    llm_service.stop_llm()
    return jsonify({'status': 'stopped'})

# WebSocket события
@socketio.on('connect')
def handle_connect():
    """Обработчик подключения WebSocket"""
    print('Client connected')
    socketio.emit('initial_data', llm_service.get_current_state())


if __name__ == "__main__":
    # Конфигурация (замените на свои пути)
    config = {
        'llama_path': './../llama.cpp/llama/llama-cli',  # путь к llama.cpp
        'model_path': 'models/Qwen3-0.6B-Q4_K_M.gguf',  # путь к модели
        'log_file': 'llm_conversation.log',
        'host': '0.0.0.0',  # для доступа с других устройств
        'port': 5000
    }
    
    # Инициализация сервиса
    llm_service = LLMService(**config)
    
    print(f"Web interface available at http://{config['host']}:{config['port']}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        llm_service.stop_monitoring()
        llm_service.stop_llm()
        print("Service stopped")