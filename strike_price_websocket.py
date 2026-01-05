def start_strike_ltp_stream(token: str, symbol: str):
    # ================== THREAD EVENT LOOP (MANDATORY) ==================
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # ================== IMPORTS ==================
    import os
    import time
    import requests
    import pytz
    from datetime import datetime
    from dotenv import load_dotenv
    from dhanhq import DhanContext, MarketFeed

    # ================== LOAD ENV ==================
    load_dotenv()
    BASE_URL = os.getenv("API_BASE_URL")

    CLIENT_ID = "1100465668"
    ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3NjY1MTU5LCJpYXQiOjE3Njc1Nzg3NTksInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAwNDY1NjY4In0.mqIdNumndRSjgedlS_hojTzqeA-tgRN7ldKlbQhUF-eeEnZgmnbceimjT9LkcWC1LdY_-3doU-iJgrFGBtrPKQ"
    VERSION = "v2"

    ist = pytz.timezone("Asia/Kolkata")
    STRIKE_LTP_ENDPOINT = "/signals/strike-ltp"

    instruments = [
        (MarketFeed.NSE_FNO, token, MarketFeed.Ticker),
    ]

    dhan_context = DhanContext(CLIENT_ID, ACCESS_TOKEN)

    # ================== API CALL ==================
    def insert_strike_ltp_api(token: str, price: float, symbol: str):
        try:
            url = f"{BASE_URL}{STRIKE_LTP_ENDPOINT}"
            # price(url)
            payload = {
                "token": str(token),
                "ltp": float(price),   # ✅ convert numpy → python
                "symbol": str(symbol),
            }
            print(payload)
            r = requests.post(url, json=payload, timeout=3)
            r.raise_for_status()
            print(f"📍 API CALLED | {symbol} → {price}")
        except Exception as e:
            print(f"❌ API Insert Error: {e}")

    print(f"📡 Starting Strike LTP Stream | {symbol}")

    retry_delay = 5
    max_retry_delay = 60

    # ================== MAIN LOOP ==================
    while True:
        try:
            data = MarketFeed(dhan_context, instruments, VERSION)
            print("🚀 MarketFeed connected")
            data.run_forever()  # start websocket (non-blocking internally)
            print('flag one')
            # ================== DATA LOOP ==================
            while True:
                print('loop started')
                now = datetime.now(ist)

                market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
                market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)

                if not (market_start <= now <= market_end):
                    print("⏸ Market closed. Sleeping 60s...")
                    time.sleep(60)
                    continue

                response = data.get_data()
                print(response)
                if not response:
                    continue

                if "LTP" in response:
                    insert_strike_ltp_api(
                        token=token,
                        price=response["LTP"],
                        symbol=symbol
                    )

        except KeyboardInterrupt:
            print("🛑 Stream stopped by user")
            break

        except Exception as e:
            print(f"❌ WebSocket Error: {e}")
            print(f"🔁 Reconnecting in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)



# if __name__ == "__main__":
#     import threading
#     t = threading.Thread(
#         target=start_strike_ltp_stream,
#         args=("35011", "BANKNIFTY-Jan2026-74400-CE"),
#         daemon=True
#     )
#     t.start()
#     t.join()

