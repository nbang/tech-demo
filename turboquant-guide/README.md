# TurboQuant+ Demo — Local LLM with Asymmetric KV Cache on Apple Silicon

This demo runs a **Qwen3.5-2B** model locally on Mac (Apple Silicon) using the **TurboQuant+** fork of llama.cpp with optimized Metal GPU kernels and an asymmetric KV cache configuration.

## What is TurboQuant+?

TurboQuant+ extends llama.cpp with novel quantization methods for the KV cache that significantly reduce memory usage while maintaining quality. The key innovation is **asymmetric cache compression**:

- **Key cache (`q8_0`)**: Higher precision to preserve attention accuracy
- **Value cache (`turbo4`)**: More aggressive compression that saves memory with minimal quality loss

This is especially important for smaller models (like 2B), where symmetric compression can cause catastrophic quality drops.

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4)
- Xcode Command Line Tools
- cmake
- Python 3.12+ (via pyenv)

```bash
xcode-select --install
brew install cmake
```

## Setup

### 1. Clone & Build

```bash
git clone https://github.com/TheTom/llama-cpp-turboquant.git turboquant
cd turboquant
git checkout feature/turboquant-kv-cache

# Build with Metal support
cmake -B build -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

### 2. Download Model

```bash
mkdir -p models
python3.12 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='unsloth/Qwen3.5-2B-GGUF',
    filename='Qwen3.5-2B-Q4_K_M.gguf',
    local_dir='models'
)
"
```

## Run the Demo

```bash
./build/bin/llama-cli \
  -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 \
  -c 4096 \
  -fa on \
  --cache-type-k q8_0 \
  --cache-type-v turbo4 \
  -n 200 \
  -p "Write a quick Python script to calculate the Fibonacci sequence." \
  --jinja
```

### Key Flags

| Flag | Description |
|------|-------------|
| `-ngl 99` | Offload all layers to Metal GPU |
| `-c 4096` | Context window (can push higher with compressed KV cache) |
| `-fa on` | Enable Flash Attention |
| `--cache-type-k q8_0` | Key cache: 8-bit quantization (higher precision) |
| `--cache-type-v turbo4` | Value cache: TurboQuant 4-bit (aggressive compression) |
| `-n 200` | Max tokens to generate |
| `--jinja` | Enable Jinja chat template |

---

## KV Cache Memory Comparison

For a detailed analysis of memory savings and performance at various context lengths (including the massive 16K benchmarks) and instructions on how to replicate the tests, please see our dedicated [KV Cache Benchmark Guide](benchmark.md).

## Interactive Mode

```bash
./build/bin/llama-cli \
  -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 4096 -fa on \
  --cache-type-k q8_0 --cache-type-v turbo4 \
  --jinja
```

Commands: `/exit`, `/regen`, `/clear`, `/read`
