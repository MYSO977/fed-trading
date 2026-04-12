# 📦 Fed-Trading v2.0-stable Release Notes

## 🚀 核心能力
- **联邦学习**：LoRA 微调 + FedAvg 聚合 + 热更新
- **交易执行**：IB Gateway 实时行情 + 模拟/实盘下单 + Dry-Run 保护
- **实时监控**：Telegram Loss/聚合/信号推送 + 错误告警
- **自动化**：Cron 每日 16:30(美东) 自动 训练→聚合→归档
- **高可用**：全链路降级兜底 + 日志轮转 + 幂等设计

## 🔐 安全基线
- `dry_run=True` 默认开启，实盘需显式关闭
- 敏感配置 (`telegram.yaml`) 严格 `.gitignore`
- 推理防 NaN/防溢出/超时熔断

## 🛠️ 快速启动
\`\`\`bash
git clone git@github.com:MYSO977/fed-trading.git
cd fed-trading && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/telegram.example.yaml config/telegram.yaml  # 填入 Token
python3 scripts/test_dry_run.py  # 验证链路
bash scripts/run_daily_pipeline.sh  # 手动触发流水线
\`\`\`

## 📅 发布时间
2026-04-11 | Maintainer: @MYSO977
