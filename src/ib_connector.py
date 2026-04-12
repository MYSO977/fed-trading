import logging, re, pandas as pd
from ib_insync import IB, Stock, MarketOrder
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class IBTrader:
    def __init__(self, host='127.0.0.1', port=4002, client_id=100, paper=True):
        self.ib, self.connected = IB(), False
        self.host, self.port, self.client_id = host, port, client_id
        self.paper, self.daily_trades = paper, 0

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=False, timeout=10)
            self.connected = True
            logging.info(f"✅ 连接 IB {'模拟' if self.paper else '实盘'} | {self.host}:{self.port}")
            return True
        except Exception as e:
            logging.error(f"❌ 连接失败: {e}"); return False

    def disconnect(self):
        if self.connected: self.ib.disconnect(); self.connected = False

    def fetch_market_prompt(self, symbol, duration='3 D', bar_size='1 hour'):
        if not self.connected: return None
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            bars = self.ib.reqHistoricalData(contract, endDateTime='', durationStr=duration, barSizeSetting=bar_size, whatToShow='TRADES', useRTH=True, formatDate=1)
            df = pd.DataFrame([{'close':b.close, 'volume':b.volume} for b in bars])
            if len(df) < 10: return None
            df['MA5'], df['MA20'] = df['close'].rolling(5).mean(), df['close'].rolling(20).mean()
            df['VolRatio'] = df['volume'] / df['volume'].rolling(20).mean()
            r = df.iloc[-1]
            return f"Asset: {symbol} | Price: {r['close']:.2f} | MA5/20: {r['MA5']:.2f}/{r['MA20']:.2f} | VolRatio: {r['VolRatio']:.1f}x | Node: ib | Action:"
        except Exception as e:
            logging.warning(f"⚠️ 获取 {symbol} 数据失败: {e}"); return None

    def parse_and_place_order(self, symbol, output, dry_run=True):
        m = re.search(r'\b(BUY|SELL|HOLD)\b', output, re.I)
        if not m or m.group(1).upper() == 'HOLD': return None
        action, qty = m.group(1).upper(), 10
        logging.info(f"📤 [{symbol}] {action} x{qty} | DryRun:{dry_run}")
        if dry_run: return {"status":"DRY_RUN", "symbol":symbol, "action":action, "qty":qty}
        try:
            order = MarketOrder(action, qty)
            trade = self.ib.placeOrder(Stock(symbol,'SMART','USD'), order)
            return {"status": trade.orderStatus.status, "symbol":symbol, "action":action}
        except Exception as e:
            logging.error(f"❌ 下单失败: {e}"); return None
