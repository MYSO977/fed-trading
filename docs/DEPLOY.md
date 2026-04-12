# Fed-Trading 2.0 部署手册
## 快速开始
1. `git clone git@github.com:MYSO977/fed-trading.git`
2. `python3 -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp config/telegram.example.yaml config/telegram.yaml` (填入 Token)
5. `python3 scripts/test_dry_run.py` 验证链路
## 生产配置
- dry_run=True 默认开启，实盘需显式关闭
- 敏感配置严格 .gitignore
- Cron: 30 20 * * 1-5 ~/fed-trading/scripts/run_daily_pipeline.sh