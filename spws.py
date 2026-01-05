import asyncio
import os
import pandas as pd
import aiohttp
from dotenv import load_dotenv
from dhanhq import DhanContext, MarketFeed
from collections import deque
import time

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL")
CLIENT_ID = "1100465668"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3NjY1MTU5LCJpYXQiOjE3Njc1Nzg3NTksInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAwNDY1NjY4In0.mqIdNumndRSjgedlS_hojTzqeA-tgRN7ldKlbQhUF-eeEnZgmnbceimjT9LkcWC1LdY_-3doU-iJgrFGBtrPKQ"
VERSION = "v2"

# ===== CONFIG =====
MAX_WORKERS = 20  # Reduced workers to avoid overwhelming API
MAX_QUEUE_SIZE = 10000  # Prevent memory overflow
RATE_LIMIT_SECONDS = 1.5  # Min time between updates for same token


class HighPerformanceStreamer:
    def __init__(self):
        # Load strike data once
        df = pd.read_excel("strike-price.xlsx")
        df["token"] = df["token"].astype(str)
        self.token_symbol = dict(zip(df["token"], df["symbol"]))
        
        # Create instruments list
        self.instruments = [
            (MarketFeed.NSE_FNO, token, MarketFeed.Ticker)
            for token in self.token_symbol.keys()
        ]
        
        self.dhan_context = DhanContext(CLIENT_ID, ACCESS_TOKEN)
        self.last_ltp = {}
        self.last_sent_time = {}  # Track last send time per token
        
        # High-performance queue
        self.update_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        
        # Connection pool with optimizations
        self.session = None
        
        # Metrics
        self.ticks_received = 0
        self.ticks_sent = 0
        self.api_calls = 0
        self.last_metric_time = time.time()
    
    async def init_session(self):
        """Initialize aiohttp session with connection pooling"""
        connector = aiohttp.TCPConnector(
            limit=100,  # Max 100 concurrent connections
            limit_per_host=50,
            ttl_dns_cache=300,
            force_close=False,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=5,  # Increased to 5 seconds
            connect=2,
            sock_read=3
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
    
    async def send_single(self, item):
        """Send single update to API with per-token rate limiting"""
        token = item["token"]
        now = time.time()
        
        # Check if we sent this token recently (within 1.5 seconds)
        last_sent = self.last_sent_time.get(token, 0)
        if now - last_sent < RATE_LIMIT_SECONDS:
            return  # Skip - too soon for this token
        
        try:
            payload = {
                "token": token,
                "ltp": item["ltp"],
                "symbol": item["symbol"]
            }
            
            async with self.session.post(
                f"{BASE_URL}/signals/strike-ltp",
                json=payload
            ) as resp:
                if resp.status == 200:
                    self.ticks_sent += 1
                    self.api_calls += 1
                    self.last_sent_time[token] = now  # Record send time
                elif resp.status == 404:
                    print(f"⚠️ API endpoint not found: {BASE_URL}/signals/strike-ltp")
                elif resp.status >= 500:
                    print(f"⚠️ Server error {resp.status}")
                else:
                    text = await resp.text()
                    print(f"⚠️ API returned {resp.status}: {text[:100]}")
            
        except asyncio.TimeoutError:
            print(f"⚠️ API timeout (>{5}s) - Check if {BASE_URL} is reachable")
        except aiohttp.ClientConnectorError as e:
            print(f"⚠️ Cannot connect to {BASE_URL}: {e}")
        except aiohttp.ClientError as e:
            print(f"⚠️ Connection error: {e}")
        except Exception as e:
            print(f"⚠️ API error: {type(e).__name__}: {e}")
    
    async def api_worker(self):
        """Worker that sends individual API calls"""
        while True:
            try:
                item = await self.update_queue.get()
                await self.send_single(item)
                self.update_queue.task_done()
                
            except Exception as e:
                print(f"⚠️ Worker error: {e}")
                await asyncio.sleep(0.1)
    
    async def process_tick(self, response):
        """Fast tick processing"""
        if not response or "LTP" not in response:
            return
        
        token = str(response["security_id"])
        ltp = float(response["LTP"])
        
        if ltp <= 0:
            return
        
        # DEDUP check
        if self.last_ltp.get(token) == ltp:
            return
        
        self.last_ltp[token] = ltp
        
        symbol = self.token_symbol.get(token)
        if not symbol:
            return
        
        self.ticks_received += 1
        
        # Non-blocking queue put
        try:
            self.update_queue.put_nowait({
                "token": token,
                "ltp": ltp,
                "symbol": symbol
            })
        except asyncio.QueueFull:
            print("⚠️ Queue full - dropping tick")
    
    async def print_metrics(self):
        """Print performance metrics"""
        while True:
            await asyncio.sleep(5)
            
            now = time.time()
            elapsed = now - self.last_metric_time
            
            ticks_per_sec = self.ticks_received / elapsed if elapsed > 0 else 0
            sent_per_sec = self.ticks_sent / elapsed if elapsed > 0 else 0
            api_per_sec = self.api_calls / elapsed if elapsed > 0 else 0
            
            print(f"\n📊 METRICS (last 5s):")
            print(f"   Ticks received: {self.ticks_received} ({ticks_per_sec:.0f}/s)")
            print(f"   Ticks sent: {self.ticks_sent} ({sent_per_sec:.0f}/s)")
            print(f"   API calls: {self.api_calls} ({api_per_sec:.1f}/s)")
            print(f"   Queue size: {self.update_queue.qsize()}")
            print(f"   Dedup cache: {len(self.last_ltp)}")
            print(f"   Rate limit cache: {len(self.last_sent_time)}")
            
            # Reset counters
            self.ticks_received = 0
            self.ticks_sent = 0
            self.api_calls = 0
            self.last_metric_time = now
    
    async def run(self):
        """Main streaming loop"""
        await self.init_session()
        
        data = MarketFeed(self.dhan_context, self.instruments, VERSION)
        
        try:
            await data.connect()
            print("✅ WebSocket connected")
            print(f"📈 Monitoring {len(self.instruments)} instruments")
            print(f"⚙️ Workers: {MAX_WORKERS}")
            
            # Start API workers
            workers = [
                asyncio.create_task(self.api_worker())
                for _ in range(MAX_WORKERS)
            ]
            
            # Start metrics printer
            metrics_task = asyncio.create_task(self.print_metrics())
            
            # Main tick processing loop (no artificial delays!)
            while True:
                response = await data.get_instrument_data()
                await self.process_tick(response)
            
        finally:
            await self.session.close()
            await data.disconnect()
            print("🔌 Stream closed")


def start_strike_ltp_stream():
    """Entry point"""
    streamer = HighPerformanceStreamer()
    
    try:
        asyncio.run(streamer.run())
    except KeyboardInterrupt:
        print("\n🛑 Stream stopped")


if __name__ == "__main__":
    try:
        start_strike_ltp_stream()
    except KeyboardInterrupt:
        print("\n🛑 Stopping stream...")