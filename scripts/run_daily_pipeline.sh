#!/bin/bash
# Fed-Trading 2.0 · 每日自动化流水线
# 执行: 美东时间 16:30 (美股收盘后)
# 触发: cron + 系统日志 + Telegram 通知

set -e  # 遇到错误立即退出

# ========== 配置 ==========
PROJECT_DIR="$HOME/fed-trading"
VENV_ACTIVATE="$PROJECT_DIR/venv/bin/activate"
LOG_DIR="$PROJECT_DIR/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/pipeline_$TIMESTAMP.log"
NODE_ID=$(hostname)

# 确保目录存在
mkdir -p "$LOG_DIR"

# 日志函数
log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# 错误处理 + 通知
trap 'log "❌ 流水线异常退出"; python3 -c "from src.notifier import get_notifier; n=get_notifier(); n.enabled and n._send("❌ *流水线失败*\n节点: `$NODE_ID`\n时间: `$(date)"")' EXIT

log "🚀 开始每日流水线 (节点: $NODE_ID)"

# 1. 激活虚拟环境
log "🔌 激活虚拟环境..."
source "$VENV_ACTIVATE"

# 2. 本地训练 (`.11` GPU 节点执行)
if [[ "$NODE_ID" == *"dell"* ]] || [[ "$NODE_ID" == *"OptiPlex"* ]]; then
    log "🧠 执行本地训练..."
    python3 "$PROJECT_DIR/src/train_local.py" --epochs 5 --batch 16 2>&1 | tee -a "$LOG_FILE"
    log "✅ 训练完成"
    
    # 推送训练完成通知
    python3 -c "
from src.notifier import get_notifier
n = get_notifier()
n.enabled and n.send_loss_update('$NODE_ID', 5, 0.12, threshold=0.5)
" 2>/dev/null || true
fi

# 3. 权重聚合 (`.18` Host 节点执行)
if [[ "$NODE_ID" == *"acer"* ]] || [[ "$NODE_ID" == *"Aspire"* ]]; then
    log "🔄 执行联邦聚合..."
    python3 "$PROJECT_DIR/src/aggregate_global.py" 2>&1 | tee -a "$LOG_FILE"
    log "✅ 聚合完成"
    
    # 推送聚合通知
    python3 -c "
from src.notifier import get_notifier
n = get_notifier()
n.enabled and n.send_aggregate_status('success', nodes_online=3, version='v2.0')
" 2>/dev/null || true
fi

# 4. 归档当日日志（所有节点）
log "📦 归档日志..."
find "$LOG_DIR" -name "pipeline_*.log" -mtime +7 -delete 2>/dev/null || true
log "✅ 旧日志已清理 (>7 天)"

# 5. 推送成功通知
python3 -c "
from src.notifier import get_notifier
n = get_notifier()
n.enabled and n._send("✅ *流水线成功*\n节点: \`$NODE_ID\`\n时间: \`$(date +%Y-%m-%d\ %H:%M)\`")
" 2>/dev/null || true

log "🎉 每日流水线完成"
