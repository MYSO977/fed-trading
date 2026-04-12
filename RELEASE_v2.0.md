# 📦 Fed-Trading v2.0-stable Release
## ✅ 交付清单
- 7 大核心模块 (src/)
- 2 自动化脚本 (scripts/)
- 安全配置模板 (config/)
- 部署文档 (docs/)

## 🔐 安全基线  
- dry_run=True 默认 | 敏感配置隔离 | 推理防崩溃

## 🚀 一键启动
\`\`\`bash
git clone git@github.com:MYSO977/fed-trading.git && cd fed-trading
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python3 scripts/test_dry_run.py
\`\`\`