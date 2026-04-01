import subprocess
import re
import sys
import time

LLAMA_CLI = "./llama-cpp-turboquant/build/bin/llama-cli"
MODEL = "models/Qwen3.5-2B-Q4_K_M.gguf"
CONTEXT_LENGTH = 16384
PROMPT = "Write a quick Python script to calculate the Fibonacci sequence."

CONFIGS = [
    {"name": "Baseline (f16/f16)", "k": "f16", "v": "f16"},
    {"name": "Symmetric q8 (q8_0/q8_0)", "k": "q8_0", "v": "q8_0"},
    {"name": "TurboQuant (q8_0/turbo4)", "k": "q8_0", "v": "turbo4"},
    {"name": "TurboQuant (q8_0/turbo3)", "k": "q8_0", "v": "turbo3"},
    {"name": "Symmetric q4 (q4_0/q4_0)", "k": "q4_0", "v": "q4_0"},
]

def run_benchmark(config):
    print(f"Running benchmark for {config['name']} with context length {CONTEXT_LENGTH}...")
    
    cmd = [
        LLAMA_CLI,
        "-m", MODEL,
        "-ngl", "99",
        "-c", str(CONTEXT_LENGTH),
        "-fa", "on",
        "--cache-type-k", config["k"],
        "--cache-type-v", config["v"],
        "-n", "50",
        "-p", PROMPT,
        "--jinja"
    ]
    
    try:
        # We pass /exit to stdin so that interactive mode aborts cleanly and prints stats
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit then output /exit
        stdout, stderr = process.communicate(input="/exit\n", timeout=120)
        output = stdout + stderr
        
        # Parse metrics
        context_mem = "N/A"
        prompt_ts = "N/A"
        gen_ts = "N/A"
        
        # Parse memory
        mem_pattern = r"\|\s*-\s*[^|]+\s*\|\s*\d+\s*=\s*\d+\s*\+\s*\(\s*\d+\s*=\s*\d+\s*\+\s*(\d+)\s*\+\s*\d+\)"
        mem_match = re.search(mem_pattern, output)
        if mem_match:
            context_mem = mem_match.group(1)
            
        # Parse speed (e.g. [ Prompt: 191.5 t/s | Generation: 39.6 t/s ])
        speed_pattern = r"\[ Prompt: ([\d.]+) t/s \| Generation: ([\d.]+) t/s \]"
        speed_match = re.search(speed_pattern, output)
        if speed_match:
            prompt_ts = speed_match.group(1)
            gen_ts = speed_match.group(2)
            
        return {
            "name": config["name"],
            "k": config["k"],
            "v": config["v"],
            "context_mem": context_mem,
            "prompt_ts": prompt_ts,
            "gen_ts": gen_ts
        }
    except Exception as e:
        print(f"Error running {config['name']}: {e}")
        return None

results = []
for config in CONFIGS:
    res = run_benchmark(config)
    if res:
        results.append(res)
    time.sleep(2)  # brief pause between runs

# Print results table
print("\n" + "="*80)
print(f"BENCHMARK RESULTS (Context Length: {CONTEXT_LENGTH})")
print("="*80)
print(f"{'Configuration':<28} | {'Key C.':<8} | {'Val C.':<8} | {'KV Mem (MiB)':<12} | {'Prompt (t/s)':<12} | {'Gen (t/s)':<10}")
print("-" * 80)

for r in results:
    print(f"{r['name']:<28} | {r['k']:<8} | {r['v']:<8} | {r['context_mem']:<12} | {r['prompt_ts']:<12} | {r['gen_ts']:<10}")
print("="*80)
