def start_strike_ltp_stream(token: str):
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
    CLIENT_ID = '1100465668'
    ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3MzI1MjY1LCJpYXQiOjE3NjcyMzg4NjUsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAwNDY1NjY4In0.ut8FQnXZQh-tJkdBKHfx6T6yTyIwo6oAcN3AWSdgshxj0tprWS2ovzBryK9Vbv7FI4v3dPmDUciRXryy3PbAdA"

    # if not BASE_URL or not CLIENT_ID or not ACCESS_TOKEN:
    #     raise RuntimeError("❌ Missing BASE_URL / CLIENT_ID / ACCESS_TOKEN in .env")

    # ================== CONFIG ==================
    ist = pytz.timezone("Asia/Kolkata")
    VERSION = "v2"
    STRIKE_LTP_ENDPOINT = "/signals/strike-ltp"

    instruments = [
        (MarketFeed.NSE_FNO, token, MarketFeed.Ticker),
    ]

    dhan_context = DhanContext(CLIENT_ID, ACCESS_TOKEN)

    # ================== API CALL ==================
    def insert_strike_ltp_api(token: str, price: float,symbol:str):
        url = f"{BASE_URL}{STRIKE_LTP_ENDPOINT}"
        payload = {
            "token": token,
            "ltp": price,
            "symbol": symbol
        }
        response = requests.post(url, json=payload, timeout=3)
        response.raise_for_status()

    # ================== RETRY CONFIG ==================
    retry_delay = 5
    max_retry_delay = 60

    print(f"📡 Starting Strike LTP Stream for token: {token}")

    # ================== MAIN LOOP ==================
    while True:
        try:
            data = MarketFeed(dhan_context, instruments, VERSION)
            retry_delay = 20

            while True:
                print("🚀 Starting Market Feed...")
                now_ist = datetime.now(ist)

                market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
                market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

                if not (market_start <= now_ist <= market_end):
                    print("⏸ Market closed. Waiting...")
                    time.sleep(60)
                    continue

                data.run_forever()
                response = data.get_data()
                print(response)
                if 'LTP' not in response:
                    continue

                ltp = response['LTP']

                try:
                    insert_strike_ltp_api(token=token, price=ltp)
                    print(f"📍 LTP Sent | Token: {token} | Price: {ltp}")

                except Exception as e:
                    print(f"❌ API Insert Error: {e}")

        except KeyboardInterrupt:
            print("\n🛑 Stream stopped by user")
            break

        except Exception as e:
            print(f"❌ WebSocket Error: {e}")
            print(f"🔁 Reconnecting in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)


if __name__ == "__main__":
    start_strike_ltp_stream(token="74400",symbol='BANKNIFTY-Jan2026-74400-CE')