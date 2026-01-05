def start_strike_ltp_stream():
    import asyncio
    import os
    import pandas as pd
    import aiohttp
    from dotenv import load_dotenv
    from dhanhq import DhanContext, MarketFeed

    load_dotenv()
    BASE_URL = os.getenv("API_BASE_URL")

    CLIENT_ID = "1100465668"
    ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3NjY1MTU5LCJpYXQiOjE3Njc1Nzg3NTksInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAwNDY1NjY4In0.mqIdNumndRSjgedlS_hojTzqeA-tgRN7ldKlbQhUF-eeEnZgmnbceimjT9LkcWC1LdY_-3doU-iJgrFGBtrPKQ"
    VERSION = "v2"

    # ===== LOAD STRIKE DATA =====
    df = pd.read_excel("strike-price.xlsx")
    df["token"] = df["token"].astype(str)

    TOKEN_SYMBOL = dict(zip(df["token"], df["symbol"]))

    instruments = [
        (MarketFeed.NSE_FNO, token, MarketFeed.Ticker)
        for token in TOKEN_SYMBOL.keys()
    ]

    dhan_context = DhanContext(CLIENT_ID, ACCESS_TOKEN)

    # ===== LAST LTP CACHE (DEDUP) =====
    last_ltp = {}

    async def call_api(session, payload):
        try:
            async with session.post(
                f"{BASE_URL}/signals/strike-ltp",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=2)
            ):
                pass
        except Exception as e:
            print("⚠️ API error:", e)

    async def run_stream():
        data = MarketFeed(dhan_context, instruments, VERSION)
        session = aiohttp.ClientSession()

        try:
            await data.connect()
            print("✅ WebSocket connected")

            while True:
                response = await data.get_instrument_data()

                if not response or "LTP" not in response:
                    await asyncio.sleep(0)
                    continue

                token = str(response["security_id"])
                ltp = float(response["LTP"])

                if ltp <= 0:
                    continue

                # 🔒 DEDUP
                if last_ltp.get(token) == ltp:
                    continue
                last_ltp[token] = ltp

                symbol = TOKEN_SYMBOL.get(token)
                if not symbol:
                    continue

                payload = {
                    "token": token,
                    "ltp": ltp,
                    "symbol": symbol,
                }

                print(payload)

                # 🔥 FIRE & FORGET (CRITICAL)
                asyncio.create_task(call_api(session, payload))

                await asyncio.sleep(0.1)  # yield control

        finally:
            await session.close()
            await data.disconnect()
            print("🔌 Stream closed")

    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        print("\n🛑 Stream stopped")


if __name__ == "__main__":
    
    
    try:
        start_strike_ltp_stream()
    except KeyboardInterrupt:
        print("\n🛑 Stopping stream...")