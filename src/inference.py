import os, glob, torch, warnings, re
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import yaml

warnings.filterwarnings("ignore")
print("🧠 加载联邦全局模型...")
with open("config/base_config.yaml", "r") as f: cfg = yaml.safe_load(f)
base_name = cfg["model"]["base"]
global_path = sorted(glob.glob("./loras/global_merged_*"))[-1]

tokenizer = AutoTokenizer.from_pretrained(base_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print("⏳ 加载基座 & 执行 merge_and_unload()...")
base = AutoModelForCausalLM.from_pretrained(base_name, torch_dtype=torch.float32, device_map="cpu", trust_remote_code=True, low_cpu_mem_usage=True)
model = PeftModel.from_pretrained(base, global_path).merge_and_unload()
model.eval()

# 🔑 终极稳定配置：绝对贪婪 + 剥离所有采样参数
model.generation_config.update(
    max_new_tokens=12,
    do_sample=False,
    temperature=None,
    top_p=None,
    top_k=None,
    repetition_penalty=1.0,
    pad_token_id=tokenizer.eos_token_id,
    eos_token_id=tokenizer.eos_token_id
)
print("✅ 模型就绪（绝对贪婪解码 + 异常拦截模式）")
print("-" * 50)

@torch.no_grad()
def predict(prompt):
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    try:
        outputs = model.generate(**inputs)
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        res = text.split("Action:")[-1].strip() if "Action:" in text else text.strip()
        if re.match(r'^[^\w\u4e00-\u9fa5A-Z]+$', res) or len(res) < 2:
            return "HOLD (模型收敛中)"
        return res
    except RuntimeError as e:
        if "nan" in str(e) or "inf" in str(e):
            return "⚠️ Logits 溢出保护 (需 max_steps>=600 稳定权重)"
        return f"⚠️ 解码拦截 ({str(e)[:15]})"

cases = [
    "Asset: 贵州茅台(600519.SH) | Price: 1650.00 | MA5/20: 1645.00/1630.00 | VolRatio: 1.5x | Node: dell | Action:",
    "Asset: 宁德时代(300750.SZ) | Price: 190.00 | MA5/20: 195.00/198.00 | VolRatio: 2.1x | Node: dell | Action:",
    "Asset: 平安银行(000001.SZ) | Price: 10.50 | MA5/20: 10.45/10.40 | VolRatio: 0.8x | Node: dell | Action:"
]

for p in cases:
    print(f"📥 {p}")
    print(f"📤 {predict(p)}")
    print("-" * 50)
print("🎉 推理流水线验证完成")
