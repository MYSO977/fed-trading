import logging, os, yaml, asyncio
from datetime import datetime
try:
    from telegram import Bot
    _HAS_TG = True
except ImportError:
    _HAS_TG = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class Notifier:
    def __init__(self, config_path="config/telegram.yaml"):
        self.enabled = False
        self.bot = None
        self.chat_id = None
        if not _HAS_TG: return
        if not os.path.exists(config_path): return
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            if not cfg.get("enabled"): return
            self.bot = Bot(token=cfg["bot_token"])
            self.chat_id = cfg["chat_id"]
            self.config = cfg.get("notify", {})
            self.bot.get_me()
            self.enabled = True
            logging.info("✅ Telegram 通知已启用")
        except Exception as e:
            logging.error(f"❌ 初始化失败: {e}")

    def _send(self, text):
        if not self.enabled or not self.bot: return
        try:
            asyncio.run(self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="Markdown"))
        except Exception as e:
            logging.warning(f"⚠️ 发送失败: {e}")

    def send_loss_update(self, node_id, epoch, loss, threshold=0.5):
        if not self.config.get("train_loss"): return
        st = "🟢 正常" if loss < threshold else "🔴 异常"
        t = datetime.now().strftime("%H:%M:%S")
        msg = f"*Loss 更新*\n节点: `{node_id}`\nEpoch: `{epoch}`\nLoss: `{loss:.4f}` {st}\n时间: `{t}`"
        self._send(msg)

    def send_aggregate_status(self, status, nodes_online=3, version="v1.0"):
        if not self.config.get("aggregate"): return
        icon = "✅" if status == "success" else "❌"
        t = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"{icon} *聚合完成*\n状态: `{status}`\n节点: `{nodes_online}`\n版本: `{version}`\n时间: `{t}`"
        self._send(msg)

    def send_trade_signal(self, symbol, action, price, vol_ratio, dry_run=True):
        if not self.config.get("trade_signal"): return
        icon = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
        mode = "🧪 模拟" if dry_run else "💰 实盘"
        t = datetime.now().strftime("%H:%M:%S")
        msg = f"{icon} *交易信号*\n标的: `{symbol}`\n动作: `{action}` {mode}\n价格: `${price:.2f}`\n量比: `{vol_ratio:.1f}x`\n时间: `{t}`"
        self._send(msg)

_notifier = None
def get_notifier():
    global _notifier
    if _notifier is None: _notifier = Notifier()
    return _notifier

if __name__ == "__main__":
    n = get_notifier()
    if n.enabled:
        print("🧪 发送测试消息...")
        n.send_trade_signal("TSLA", "BUY", 245.30, 1.5, True)
        n.send_loss_update("node-11", 5, 0.1234)
        n.send_aggregate_status("success")
        print("✅ 测试消息已发送")
    else:
        print("⚠️ 通知未启用，请检查 config/telegram.yaml 及依赖")
