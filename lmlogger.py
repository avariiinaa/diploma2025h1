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

# HTML шаблон (сохранить в templates/index.html)
"""
<!DOCTYPE html>
<html>
<head>
    <title>LLM Monitoring</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { display: flex; flex-wrap: wrap; gap: 20px; }
        .panel { flex: 1; min-width: 300px; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }
        #metrics-chart { height: 300px; }
        #conversation { height: 400px; overflow-y: auto; }
        .message { margin-bottom: 10px; padding: 8px; border-radius: 4px; }
        .user { background-color: #e3f2fd; }
        .llm { background-color: #f1f8e9; }
        #generation-controls { margin-top: 20px; }
    </style>
</head>
<body>
    <h1>LLM Monitoring Dashboard</h1>
    
    <div class="container">
        <div class="panel">
            <h2>System Metrics</h2>
            <canvas id="metrics-chart"></canvas>
            <div id="current-metrics">
                <p>CPU: <span id="cpu-value">0</span>%</p>
                <p>Memory: <span id="mem-value">0</span>%</p>
            </div>
        </div>
        
        <div class="panel">
            <h2>Conversation</h2>
            <div id="conversation"></div>
            <div id="generation-controls">
                <textarea id="prompt-input" rows="3" style="width: 100%;"></textarea>
                <button onclick="generate()">Generate</button>
                <button onclick="stopGeneration()">Stop</button>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        const conversationDiv = document.getElementById('conversation');
        const cpuValue = document.getElementById('cpu-value');
        const memValue = document.getElementById('mem-value');
        
        // Инициализация графиков
        const ctx = document.getElementById('metrics-chart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU Usage (%)',
                        data: [],
                        borderColor: 'rgb(255, 99, 132)',
                        tension: 0.1
                    },
                    {
                        label: 'Memory Usage (%)',
                        data: [],
                        borderColor: 'rgb(54, 162, 235)',
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    x: { title: { display: true, text: 'Time' } },
                    y: { min: 0, max: 100 }
                }
            }
        });
        
        // Обработчики WebSocket
        socket.on('metrics_update', data => {
            cpuValue.textContent = data.cpu.toFixed(1);
            memValue.textContent = data.memory.toFixed(1);
            
            // Обновление графика
            if (chart.data.labels.length > 30) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
                chart.data.datasets[1].data.shift();
            }
            
            chart.data.labels.push(data.timestamp);
            chart.data.datasets[0].data.push(data.cpu);
            chart.data.datasets[1].data.push(data.memory);
            chart.update();
        });
        
        socket.on('conversation_update', data => {
            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            userMsg.innerHTML = `<strong>[${data.timestamp}] User:</strong><p>${data.prompt}</p>`;
            
            const llmMsg = document.createElement('div');
            llmMsg.className = 'message llm';
            llmMsg.innerHTML = `<strong>[${data.timestamp}] LLM:</strong><p>${data.response}</p>`;
            
            conversationDiv.appendChild(userMsg);
            conversationDiv.appendChild(llmMsg);
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
        });
        
        socket.on('partial_response', data => {
            const lastLlmMsg = conversationDiv.querySelector('.llm:last-child');
            if (lastLlmMsg) {
                lastLlmMsg.querySelector('p').textContent += data.text + ' ';
                conversationDiv.scrollTop = conversationDiv.scrollHeight;
            }
        });
        
        socket.on('initial_data', data => {
            // Загрузка начальных данных
            data.conversation.forEach(msg => {
                const event = { 
                    timestamp: msg.timestamp,
                    prompt: msg.prompt,
                    response: msg.response
                };
                socket.emit('conversation_update', event);
            });
        });
        
        // Функции управления
        function generate() {
            const prompt = document.getElementById('prompt-input').value;
            if (prompt.trim()) {
                fetch('/api/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt })
                });
                document.getElementById('prompt-input').value = '';
            }
        }
        
        function stopGeneration() {
            fetch('/api/stop', { method: 'POST' });
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    # Конфигурация (замените на свои пути)
    config = {
        'llama_path': './main',  # путь к llama.cpp
        'model_path': './models/llama-2-7b.Q4_K_M.gguf',  # путь к модели
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