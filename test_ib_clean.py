from ib_insync import IB
ib = IB()
try:
    print("🔄 尝试连接 IB Gateway (clientId=999)...")
    ib.connect('127.0.0.1', 4002, clientId=999, timeout=10)
    print("✅ 连接成功！端口通畅")
    ib.disconnect()
except Exception as e:
    print(f"❌ 连接失败: {e}")
    exit(1)
