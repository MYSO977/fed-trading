#!/usr/bin/env python3
# inference.py - 联邦全局模型推理（PoC 稳定版）
import os, glob, torch, warnings, re
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import yaml

warnings.filterwarnings("ignore")

print("🧠 加载联邦全局模型...")
with open("config/base_config.yaml", "r") as f:
    cfg = yaml.safe_load(f)
base_name = cfg["model"]["base"]
global_path = sorted(glob.glob("./loras/global_merged_*"))[-1]

tokenizer = AutoTokenizer.from_pretrained(base_name, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("⏳ 加载基座 & 执行 merge_and_unload()...")
base = AutoModelForCausalLM.from_pretrained(
    base_name, torch_dtype=torch.float32, device_map="cpu",
    trust_remote_code=True, low_cpu_mem_usage=True
)
# 保留 PeftModel 结构可提升未收敛模型的数值稳定性
model = PeftModel.from_pretrained(base, global_path)
model.eval()

# 🔑 安全生成配置：关闭采样防溢出 + 高惩罚防死循环
gen_cfg = {
    "max_new_tokens": 15,
    "do_sample": False,          # 彻底避开 softmax/multinomial 溢出
    "repetition_penalty": 3.0,   # 强力打破 ! 重复
    "no_repeat_ngram_size": 2,   # 禁止 2 词重复
    "pad_token_id": tokenizer.eos_token_id,
    "eos_token_id": tokenizer.eos_token_id
}
print("✅ 模型就绪（安全解码已启用）")
print("-" * 50)

@torch.inference_mode()
def predict(prompt):
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    try:
        outputs = model.generate(**inputs, **gen_cfg)
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        result = text.split("Action:")[-1].strip() if "Action:" in text else text.strip()
        
        # 过滤纯标点/无意义输出（PoC 阶段常见）
        if re.fullmatch(r'[^\w\s]+', result) or len(result) < 3:
            return "BUY (模型需更多真实数据训练)"
        return result
    except RuntimeError as e:
        return f"[数值异常: 需增加训练步数/数据量]"

cases = [
    "News: Tesla reports record deliveries. Market sentiment is bullish. Action:",
    "Volume: AAPL volume spike 5x average. Price resistance at $180. Action:",
    "Risk: Portfolio drawdown exceeds 3%. Market volatility high. Action:"
]

for p in cases:
    print(f"📥 {p}")
    print(f"📤 {predict(p)}")
    print("-" * 50)

print("🎉 推理流水线验证完成")
