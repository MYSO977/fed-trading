#!/bin/bash
set -e
PROJECT_DIR="$HOME/fed-trading"; source "$PROJECT_DIR/venv/bin/activate"
LOG_DIR="$PROJECT_DIR/logs"; mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S"); LOG_FILE="$LOG_DIR/pipeline_$TIMESTAMP.log"
log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
log "🚀 开始每日流水线"; python3 "$PROJECT_DIR/src/train_local.py" 2>&1 | tee -a "$LOG_FILE"
python3 "$PROJECT_DIR/src/aggregate_global.py" 2>&1 | tee -a "$LOG_FILE"
find "$LOG_DIR" -name "pipeline_*.log" -mtime +7 -delete 2>/dev/null || true
log "🎉 每日流水线完成"