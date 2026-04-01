# TurboQuant+ Benchmark Guide

## KV Cache Memory Comparison

Benchmarked on **Apple M2, 16GB unified memory** with **Qwen3.5-2B-Q4_K_M** at **16384 (16K) context length**.

All runs use the same prompt, model, and settings — only the KV cache type varies.

### Results

| Configuration | Key Cache | Value Cache | KV Context (MiB) | vs Baseline |
|---|---|---|---:|---:|
| **Baseline (f16/f16)** | f16 | f16 | **211** | — |
| **Symmetric q8 (q8_0/q8_0)** | q8_0 | q8_0 | **121** | −43% |
| **TurboQuant (q8_0/turbo4)** ⭐ | q8_0 | turbo4 | **95** | **−55%** |
| **TurboQuant (q8_0/turbo3)** | q8_0 | turbo3 | **89** | **−58%** |
| **Symmetric q4 (q4_0/q4_0)** | q4_0 | q4_0 | **73** | −65% |

### Memory Breakdown (GPU)

```
┌──────────────────────────────────────────────────────────────────────────┐
│              KV Cache Memory at 16384 Context Length                    │
│                                                                        │
│  f16/f16      ████████████████████████████████████ 211 MiB (baseline)  │
│  q8_0/q8_0    ████████████████████                 121 MiB (−43%)      │
│  q8_0/turbo4  ███████████████                       95 MiB (−55%) ⭐    │
│  q8_0/turbo3  ██████████████                        89 MiB (−58%)      │
│  q4_0/q4_0    ████████████                          73 MiB (−65%)      │
│                                                                        │
│  Model: 1211 MiB │ Compute: 489 MiB │ Host: 413 MiB (all configs)    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Analysis

- **TurboQuant asymmetric (q8_0/turbo4)** saves **55% KV memory** vs f16 baseline while preserving quality through higher-precision keys
- **Symmetric q4_0** saves the most memory (65%) but risks quality degradation on small models — the asymmetric approach avoids this
- **Generation speed** is comparable across all configs (~36-40 t/s), meaning the memory savings come essentially for free
- At larger context lengths (16K, 32K+), the savings compound dramatically since KV cache grows linearly with context

### Why Asymmetric Matters for Small Models

The documentation warns that small low-bit models suffer **catastrophic quality drops** with symmetric compression (e.g., q4_0/q4_0). The asymmetric approach rescues quality by:

1. Keeping **Keys at q8_0** — attention patterns depend heavily on key precision
2. Compressing **Values with turbo4** — value vectors are more tolerant of quantization
3. This gives most of the memory savings of q4 while maintaining near-f16 quality

---

## Reproduce the Comparison

```bash
# Baseline: f16/f16
./build/bin/llama-cli -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 16384 -fa on --cache-type-k f16 --cache-type-v f16 \
  -n 100 -p "Write a quick Python script to calculate the Fibonacci sequence." --jinja

# Symmetric q8: q8_0/q8_0
./build/bin/llama-cli -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 16384 -fa on --cache-type-k q8_0 --cache-type-v q8_0 \
  -n 100 -p "Write a quick Python script to calculate the Fibonacci sequence." --jinja

# TurboQuant: q8_0/turbo4 (recommended)
./build/bin/llama-cli -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 16384 -fa on --cache-type-k q8_0 --cache-type-v turbo4 \
  -n 100 -p "Write a quick Python script to calculate the Fibonacci sequence." --jinja

# TurboQuant turbo3: q8_0/turbo3
./build/bin/llama-cli -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 16384 -fa on --cache-type-k q8_0 --cache-type-v turbo3 \
  -n 100 -p "Write a quick Python script to calculate the Fibonacci sequence." --jinja

# Symmetric q4: q4_0/q4_0
./build/bin/llama-cli -m models/Qwen3.5-2B-Q4_K_M.gguf \
  -ngl 99 -c 16384 -fa on --cache-type-k q4_0 --cache-type-v q4_0 \
  -n 100 -p "Write a quick Python script to calculate the Fibonacci sequence." --jinja
```

Memory breakdown is printed on exit. Look for the `context` column in `llama_memory_breakdown_print`.
