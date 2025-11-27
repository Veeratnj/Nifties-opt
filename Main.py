

# --- Standard Library Imports ---
import time
from datetime import datetime, timedelta, time as time_c, date
from uuid import uuid4
from typing import Dict, Any, List

# Configure logging for Main.py
import logging
logging.basicConfig(
    filename='main.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv
import os

# --- Local Imports ---
# import psql
from heikin_ashi_atr_strike import HeikinAshiATRStrategy

# --- Constants ---
IST = pytz.timezone("Asia/Kolkata")



# --- API Database Client ---
class ApiDatabaseClient:
    def __init__(self):
        load_dotenv()
        # Base URL includes /db, so endpoints are relative to http://localhost:8000/db
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000/db")
        # No authentication required - /db endpoints are public
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def kill_trade_signal(self, token: str) -> bool:
        """Call the admin API to check if a trade should be force-exited for a token."""
        url = f"{self.base_url}/admin/kill-trade-signal"
        payload = {"token": token}
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Expecting: {"kill": true/false}
            return data.get("kill", False)
        except Exception as e:
            logging.error(f"Failed to fetch kill trade signal for token {token}: {e}")
            return False
        
        
    def get_nifties_token(self) -> list[str]:
        """Fetch the list of Nifty tokens from the API server."""
        url = f"{self.base_url}/indices/nifty-tokens"
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            # Expecting: {"tokens": ["23", "45", "12", ...]}
            return data.get("tokens", [])
        except Exception as e:
            logging.error(f"Failed to fetch Nifty tokens: {e}")
            return []
        
        
    def fetch_ohlc(self, token, limit=1):
        """Fetch OHLC data for a token."""
        url = f"{self.base_url}/ohlc"
        payload = {"token": token, "limit": limit}
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        response_data = resp.json()
        # Response: {"data": [...]}
        data = response_data.get("data", [])
        if not data:
            return None
        row = data[-1]
        # Values are returned as strings in API, need to convert
        return row["start_time"], row["open"], row["high"], row["low"], row["close"]

    def fetch_historical_ohlc(self, token, limit=500):
        """Fetch historical OHLC data for a token."""
        url = f"{self.base_url}/ohlc"
        payload = {"token": token, "limit": limit}
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        response_data = resp.json()
        # Response: {"data": [...]}
        data = response_data.get("data", [])
        if not data:
            return pd.DataFrame(columns=["start_time", "open", "high", "low", "close"])
        df = pd.DataFrame(data)
        df = df[["start_time", "open", "high", "low", "close"]].copy()
        # Ensure values are floats
        df = df.astype({"open": float, "high": float, "low": float, "close": float})
        return df

    def fetch_latest_ltp(self, stock_token: str = '99926009'):
        url = f"{self.base_url}/indices/ltp"
        params = {"stock_token": stock_token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()["data"]
        return data["last_update"], data["ltp"]


# --- Strategy Orchestration Class ---
class StrategyTrader:
    def __init__(self, api_client):
        # Store the API client instance for data access
        self.api = api_client

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.
        Market hours: 9:30 AM to 2:00 PM (14:00) IST
        Returns True if market is open, False otherwise.
        """
        current_time = datetime.now(IST).time()
        market_open = time_c(9, 30)  # 9:30 AM
        market_close = time_c(14, 0)  # 2:00 PM (14:00)
        # return market_open <= current_time <= market_close
        return True

    def admin_trade_exit_signal(self, token: str) -> bool:
        """
        Checks with the admin API if a trade should be force-exited for a given token.
        Returns True if an admin-triggered exit is required, else False.
        """
        return self.api.kill_trade_signal(token=token)
         


    def trade_function(self, token: str) -> None:
        """
        Main trading loop for a single token. Handles data fetching, signal generation,
        entry/exit logic, and admin-triggered exits. Runs in its own thread per token.
        """
        import traceback  # For detailed error tracebacks
        try:
            # Log the start of trading for this token
            logging.info(f"Starting trade_function for token: {token}")
            stock_token = token  # The token to trade

            # Fetch historical OHLC data for the token
            historical_df = self.api.fetch_historical_ohlc(token=stock_token, limit=500)
            if historical_df is None or historical_df.empty:
                # Abort if no historical data is available
                logging.error("No historical data found, aborting trade_function.")
                return

            # Initialize the trading strategy with the token
            strategy = HeikinAshiATRStrategy(token=stock_token)
            temp_csv = f"_temp_{stock_token}_ohlc.csv"  # Temporary CSV for strategy
            historical_df.to_csv(temp_csv, index=False)  # Save historical data
            strategy.load_historical_data(temp_csv)  # Load into strategy

            open_order: bool = False  # Tracks if an order is currently open
            previous_candle_time: str | None = None  # Last processed candle time
            stop_loss: float | None = None  # Current stop loss
            target: float | None = None  # Current target
            previous_entry_exit_key: str | None = None  # Last entry/exit signal

            while True:
                exit_flag = False  # Whether an exit condition is met

                # Check for exit conditions if a position is open
                if previous_entry_exit_key is not None and stop_loss is not None and target is not None:
                    if previous_entry_exit_key == 'BUY_EXIT':
                        # Exit if LTP hits stop loss, target, or time is after 14:25
                        if ltp_price <= stop_loss or ltp_price >= target or datetime.now().time() >= time_c(14, 25):
                            exit_flag = True
                            print('exit flag is true')
                            logging.info(f"buy exit ltp_price={ltp_price} stop_loss={stop_loss} target={target} previous_entry_exit_key={previous_entry_exit_key} stock_token={stock_token} cond1{ltp_price <= stop_loss} cond2{ltp_price >= target}")
                        # Admin-triggered exit
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            print('admin exit signal received, exiting buy position')
                            logging.info(f"Admin exit signal for BUY_EXIT stock_token={stock_token}")
                    elif previous_entry_exit_key == 'SELL_EXIT':
                        # Exit if LTP hits stop loss, target, or time is after 14:25
                        if ltp_price >= stop_loss or ltp_price <= target or datetime.now().time() >= time_c(14, 25):
                            exit_flag = True
                            print('exit flag is true')
                            logging.info(f"sell exit ltp_price={ltp_price} stop_loss={stop_loss} target={target} previous_entry_exit_key={previous_entry_exit_key} stock_token={stock_token} cond1{ltp_price >= stop_loss} cond2{ltp_price <= target}")
                        # Admin-triggered exit
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            print('admin exit signal received, exiting sell position')
                            logging.info(f"Admin exit signal for SELL_EXIT stock_token={stock_token}")

                # Skip loop if market is closed
                if not self.is_market_open():
                    continue

                try:
                    # Fetch the latest LTP (last traded price)
                    ltp_price = self.api.fetch_latest_ltp(stock_token=stock_token)[1]
                except Exception as e:
                    # Log and skip on LTP fetch error
                    print(e)
                    logging.error(f"Failed to fetch latest LTP: {e}")
                    traceback.print_exc()
                    time.sleep(10)
                    continue

                # Fetch the latest OHLC candle (using token '25' as example)
                start_time, open_, high, low, close = self.api.fetch_ohlc(token='25', limit=1)
                # Skip if this candle was already processed
                if start_time == previous_candle_time:
                    previous_candle_time = start_time
                    continue
                previous_candle_time = start_time
                print('start time is ==', start_time)

                # Prepare live data for the strategy
                live_data = {
                    'open': open_,
                    'close': close,
                    'high': high,
                    'low': low,
                    'volume': 0,  # Volume not used
                    'timestamp': start_time
                }
                strategy.add_live_data(live_data)  # Add to strategy

                # Generate trading signal from strategy
                signal_result = strategy.generate_signal()
                if isinstance(signal_result, tuple):
                    signal, stop_loss_, target_, strike_price = signal_result
                else:
                    signal, stop_loss_, target_, strike_price = signal_result, None, None, None

                # Always update stop_loss and target with latest values
                stop_loss = stop_loss_
                target = target_
                logging.info(f"Signal generated: {signal}  strike price  {strike_price} ")

                # --- ENTRY conditions ---
                if signal == 'BUY_ENTRY' and datetime.now().time() <= time_c(11, 30):
                    # Set up for a buy position
                    previous_entry_exit_key = 'BUY_EXIT'
                    tokens_data_frame = pd.read_excel('strike-price.xlsx')  # Load strike price data
                    option_token_row = tokens_data_frame[
                        (tokens_data_frame['strike_price'] == int(strike_price)) &
                        (tokens_data_frame['position'] == 'CE')
                    ]
                    print('length is :: ', len(tokens_data_frame), "strike price is ::", strike_price)
                    if option_token_row.empty:
                        # No matching call option found
                        logging.error(f"No CE option found for strike_price {strike_price}")
                        continue
                    print(f"BUY_ENTRY signal received token number is {option_token_row['token'].iloc[0]}")
                    open_order = True  # Mark order as open
                    trade_count -= 1  # Decrement trade count (if used)
                    logging.info(f"strike price token number is {str(option_token_row['token'].iloc[0])}")
                    # symbol = option_token_row['symbol'].iloc[0]  # Optionally use symbol
                    historical_df = self.api.fetch_historical_ohlc(token='25', limit=500)
                    strategy.load_historical_data(historical_df)

                elif signal == 'SELL_ENTRY' and datetime.now().time() <= time_c(11, 30):
                    # Set up for a sell position
                    previous_entry_exit_key = 'SELL_EXIT'
                    print('SELL_ENTRY signal received')
                    tokens_data_frame = pd.read_excel('strike-price.xlsx')  # Load strike price data
                    print('length is :: ', len(tokens_data_frame), "strike price is ::", strike_price)
                    option_token_row = tokens_data_frame[
                        (tokens_data_frame['strike_price'] == int(strike_price)) &
                        (tokens_data_frame['position'] == 'PE')
                    ]
                    if option_token_row.empty:
                        # No matching put option found
                        logging.error(f"No PE option found for strike_price {strike_price}")
                        continue
                    print(f"SELL_ENTRY signal received token number is {option_token_row['token'].iloc[0]}")
                    open_order = True  # Mark order as open
                    logging.info(f"strike price token number is {str(option_token_row['token'].iloc[0])}")
                    symbol = option_token_row['symbol'].iloc[0]
                    historical_df = self.api.fetch_historical_ohlc(token='25', limit=500)
                    strategy.load_historical_data(historical_df)

                # --- EXIT conditions ---
                if signal == 'BUY_EXIT' or (previous_entry_exit_key == 'BUY_EXIT' and exit_flag):
                    open_order = False  # Mark order as closed
                    print('BUY_EXIT: Closing buy position')
                    logging.info(f"BUY_EXIT executed for stock_token={stock_token}")
                    # Place your buy exit order logic here
                    continue
                if signal == 'SELL_EXIT' or (previous_entry_exit_key == 'SELL_EXIT' and exit_flag):
                    open_order = False  # Mark order as closed
                    print('SELL_EXIT: Closing sell position')
                    logging.info(f"SELL_EXIT executed for stock_token={stock_token}")
                    # Place your sell exit order logic here
                    continue

                # Wait before next iteration (throttle loop)
                time.sleep(2)
        except Exception as e:
            # Log and print any unexpected errors
            print('error is :: ', e)
            logging.error(f"Error processing trade: {str(e)}", exc_info=True)
            traceback.print_exc()

    def run(self):
        import threading
        import traceback
        try:
            tokens = ApiDatabaseClient().get_nifties_token()  # List of tokens to trade
            print('tokens are :: ', tokens)
            threads = []
            for token in tokens:
                t = threading.Thread(target=self.trade_function, args=(token,))
                t.start()
                print(f"Started thread for token={token}")
                threads.append(t)
            for t in threads:
                t.join()
        except Exception as e:
            logging.error("Error in run method", exc_info=True)
            traceback.print_exc()


# --- Entry Point ---
if __name__ == "__main__":
    print('main function started')
    api_client = ApiDatabaseClient()
    api_client.fetch_latest_ltp(stock_token='25')
    print('api client created')
    trader = StrategyTrader(api_client)
    print('trader created')
    trader.run()
    print('trader run')
