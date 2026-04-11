#!/usr/bin/env python3
# aggregate_global.py - 联邦权重聚合 (FedAvg)
import os, glob, torch
from safetensors.torch import load_file, save_file
from peft import LoraConfig, get_peft_model, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import yaml

print("🤖 启动联邦聚合任务...")

# 1. 加载配置
with open("config/base_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

base_model_name = cfg["model"]["base"]

# 2. 查找最新权重路径
dell_path = sorted(glob.glob("./loras/dell_*"))[-1] if glob.glob("./loras/dell_*") else None
xiaoxin_path = sorted(glob.glob("./loras/xiaoxin_*"))[-1] if glob.glob("./loras/xiaoxin_*") else None

if not dell_path or not xiaoxin_path:
    print("❌ 错误: 找不到 Dell 或 Xiaoxin 的权重目录！")
    exit(1)

print(f"📂 找到 Dell 权重: {dell_path}")
print(f"📂 找到 Xiaoxin 权重: {xiaoxin_path}")

# 3. 加载权重张量
print("⏳ 加载权重文件...")
sd_dell = load_file(os.path.join(dell_path, "adapter_model.safetensors"))
sd_xiaoxin = load_file(os.path.join(xiaoxin_path, "adapter_model.safetensors"))

# 4. 核心聚合算法 (简单平均)
# 假设两台机器权重 1:1 贡献
print("⚖️ 正在执行 FedAvg (平均权重)...")
sd_global = {}
for key in sd_dell.keys():
    # 检查权重是否一致
    if key in sd_xiaoxin:
        # (权重 A + 权重 B) / 2
        sd_global[key] = (sd_dell[key] + sd_xiaoxin[key]) / 2.0
    else:
        print(f"⚠️ 警告: 键 {key} 在 Xiaoxin 权重中不存在")

# 5. 保存聚合后的权重
output_path = f"./loras/global_merged_{len(sd_global)}params"
os.makedirs(output_path, exist_ok=True)

# 保存为 safetensors 格式
save_file(sd_global, os.path.join(output_path, "adapter_model.safetensors"))

# 复制配置和 readme
import shutil
shutil.copy(os.path.join(dell_path, "adapter_config.json"), os.path.join(output_path, "adapter_config.json"))
with open(os.path.join(output_path, "README.md"), "w") as f:
    f.write(f"Global Merged Model\nSources:\n- {os.path.basename(dell_path)}\n- {os.path.basename(xiaoxin_path)}\n")

print(f"✅ 聚合完成！已保存至: {output_path}")
print(f"📦 包含 {len(sd_global)} 个参数张量")

# 6. 验证加载
print("🧪 验证聚合权重...")
tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(base_model_name, torch_dtype=torch.float32) # 验证用 CPU 即可
merged_model = PeftModel.from_pretrained(base_model, output_path)
print("✅ 验证通过：聚合模型可正常加载！")
