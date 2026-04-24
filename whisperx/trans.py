import os
import re
import glob
import time
import subprocess
import requests
from datetime import datetime
from tqdm import tqdm
from openai import OpenAI 

# ================= 配置区域 =================
OUTPUT_SUFFIX = ".translated" 

LM_STUDIO_URL = "http://localhost:18818/v1"
LM_STUDIO_API_KEY = "sk-lm-uGgSijqd:60nCbHMd77K33VZmV1AY"

# 务必保持这里的拼写与 lms ls 显示的精确名称完全一致
MODEL_NAME = "huihui-hy-mt1.5-7b-abliterated"
TARGET_LANG = "Simplified Chinese"

client = OpenAI(base_url=LM_STUDIO_URL, api_key=LM_STUDIO_API_KEY)
# ===========================================

def ensure_server_and_model_ready():
    """确保服务器开启，并强制提前加载模型到显存"""
    print("Checking LM Studio server status...")
    
    # 1. 检查服务器是否在线
    server_online = False
    try:
        response = requests.get(f"{LM_STUDIO_URL}/models", headers={"Authorization": f"Bearer {LM_STUDIO_API_KEY}"}, timeout=2)
        if response.status_code == 200:
            print("Server is already running.")
            server_online = True
    except requests.exceptions.RequestException:
        pass

    # 2. 如果不在线，启动服务器
    if not server_online:
        print("Server not responding. Starting headless LM Studio server via CLI...")
        try:
            subprocess.Popen(["lms", "server", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError("lms command not found. Please install LM Studio CLI.")

        # 等待服务器启动
        for _ in range(15):
            time.sleep(2)
            try:
                res = requests.get(f"{LM_STUDIO_URL}/models", headers={"Authorization": f"Bearer {LM_STUDIO_API_KEY}"}, timeout=2)
                if res.status_code == 200:
                    print("Server successfully started.")
                    server_online = True
                    break
            except requests.exceptions.RequestException:
                pass
        
        if not server_online:
            raise RuntimeError("Server startup timeout.")

    # 3. 强制预加载模型 (方法二核心逻辑)
    print(f"Ensuring model '{MODEL_NAME}' is loaded into memory...")
    print("Please wait a moment if it's loading for the first time...")
    try:
        # lms load 会阻塞等待，直到模型真的加载完才会继续往下走
        subprocess.run(["lms", "load", MODEL_NAME], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Model is fully loaded and ready!")
    except Exception as e:
        print(f"Warning: Failed to pre-load model via CLI. Proceeding anyway. Error: {e}")
        # 如果预加载失败（比如命令不对），依然放行，依靠方法一的按需加载兜底

def parse_srt(content):
    blocks = re.split(r'\n\s*\n', content.strip())
    parsed_blocks = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3: continue
        
        index = lines[0]
        timestamp = lines[1]
        text = " ".join(lines[2:]) 
        
        parsed_blocks.append({
            "index": index,
            "timestamp": timestamp,
            "text": text
        })
    return parsed_blocks

def translate_line(text, model, target_lang):
    system_prompt = (
        f"You are a professional JAV (Japanese Adult Video) subtitle translator. "
        f"Translate the given text into {target_lang}. "
        f"Keep the tone natural, intimate, and authentically uncensored. "
        f"Fix obvious AI transcription errors based on context, but do not invent dialogue. "
        f"Output ONLY the translated text. Do not add explanations or notes."
    )
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.0, 
            max_tokens=1000  
        )
        
        result = response.choices[0].message.content
        return result.strip().replace('\n', ' ')
        
    except Exception as e:
        tqdm.write(f" -> [Error]: {e}")
        return text 

def read_file_with_encoding(filepath):
    encodings = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别文件编码: {filepath}")

def process_file(input_file):
    base, ext = os.path.splitext(input_file)
    output_path = f"{base}{OUTPUT_SUFFIX}{ext}"
    
    print(f"\n========================================")
    print(f"File:  {input_file}")
    print(f"Save:  {output_path}")
    print(f"Model: {MODEL_NAME}")
    print(f"========================================")

    try:
        content = read_file_with_encoding(input_file)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    blocks = parse_srt(content)
    total_blocks = len(blocks)
    
    if total_blocks == 0:
        print("No subtitles found. Skipping.")
        return

    with open(output_path, 'w', encoding='utf-8') as f:
        pass

    start_time = datetime.now()
    
    for block in tqdm(blocks, desc=f"Trans: {input_file}", unit="line", ncols=100):
        
        original_text = block['text']
        translated_text = translate_line(original_text, MODEL_NAME, TARGET_LANG)
        final_text = f"{translated_text}\n{original_text}"
        new_block = f"{block['index']}\n{block['timestamp']}\n{final_text}\n\n"
        
        with open(output_path, 'a', encoding='utf-8') as f:
            f.write(new_block)

    duration = datetime.now() - start_time
    print(f"Done! Cost: {duration}")

def main():
    # 强制进行前置检查和模型预热
    ensure_server_and_model_ready()

    all_srt_files = glob.glob("*.srt")
    files_to_process = [f for f in all_srt_files if OUTPUT_SUFFIX not in f]

    if not files_to_process:
        print("当前目录下没有找到需要翻译的 .srt 文件。")
        return

    print(f"\nFound {len(files_to_process)} files to process.")
    
    for idx, srt_file in enumerate(files_to_process):
        print(f"\nProcessing [{idx+1}/{len(files_to_process)}]: {srt_file}")
        process_file(srt_file)
        
    print("\n\nAll tasks completed!")

    print("Unloading model to free up VRAM...")
    import subprocess
    subprocess.run(["lms", "unload", "--all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("VRAM cleared!")

if __name__ == "__main__":
    main()