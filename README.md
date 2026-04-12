# Fed-Trading 2.0 🚀
分布式联邦量化交易系统 | 3 机协同 | 纯开源栈 | 零云服务

## 核心能力
- 🧠 联邦学习: LoRA 微调 + FedAvg 聚合
- 💹 IB 交易: 实时行情 + Dry-Run 安全拦截  
- 📱 实时监控: Telegram Loss/信号推送
- 🕐 自动流水线: Cron 每日训练→聚合→归档

## 快速开始
\`\`\`bash
git clone git@github.com:MYSO977/fed-trading.git
cd fed-trading && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 scripts/test_dry_run.py  # 验证链路
\`\`\`

## 安全基线
- `dry_run=True` 默认开启
- 敏感配置通过 `config/telegram.yaml` 管理（已 .gitignore）
- 推理防崩溃/防溢出/自动降级

📦 版本: v2.0-stable | 📅 2026-04 | 🔐 生产级就绪