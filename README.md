# diploma2025h1
для запуска нужно запустить qemu примерно с такими параметрами 
./qemu-system-riscv64.exe     -machine virt  -m 2048 -smp 4     -kernel uboot.elf     -device virtio-net-device,netdev=eth0 -netdev user,id=eth0,hostfwd=tcp::8000-:8000     -device virtio-rng-pci     -drive file=ubuntu-24.04.2-preinstalled-server-riscv64.img,format=raw,if=virtio -cpu rv64,v=true,vlen=256
находясь в репозитории:
скачать модель 

wget https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf?download=true

mv Qwen3-0.6B-Q4_K_M.gguf models/

собрать llama.cpp где нибудь

запустить скрипт python3 lmlogger.py [вставить локацию llama-cli](например: ../llama.cpp/llama/bin/llama-cli)

открыть бразуер в локальной сети на localhost:8000