

# --- Standard Library Imports ---
import time
from datetime import datetime, timedelta, time as time_c, date
from uuid import uuid4
from typing import Dict, Any, List
from strike_price_websocket import start_strike_ltp_stream
import threading

# Configure logging for Main.py
import logging
from logging.handlers import RotatingFileHandler

# Create a named logger for main
logger = logging.getLogger('main')
logger.setLevel(logging.INFO)

# Create rotating file handler for main.log (1MB max, keep 1 backup file)
file_handler = RotatingFileHandler('main.log', maxBytes=1*1024*1024, backupCount=1)
file_handler.setLevel(logging.INFO)

# Create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
file_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(file_handler)

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


load_dotenv()

# --- API Database Client ---
class ApiDatabaseClient:
    def __init__(self):
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
            logger.error(f"Failed to fetch kill trade signal for token {token}: {e}")
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
            logger.error(f"Failed to fetch Nifty tokens: {e}")
            return []
        
        
    def fetch_ohlc(self, token, limit=1):
        """Fetch current OHLC data for a token."""
        url = f"{self.base_url}/current/ohlc"
        params = {"token": token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        response_data = resp.json()
        # Response: {"status": "success", "data": {...}} - data is a single object, not a list
        if response_data.get("status") != "success":
            return None
        data = response_data.get("data")
        if not data:
            return None
        # Values are returned as floats in API
        return data["start_time"], data["open"], data["high"], data["low"], data["close"]

    def fetch_historical_ohlc(self, token, limit=500):
        """Fetch historical OHLC data for a token (last 3 days of 3-min candles)."""
        url = f"{self.base_url}/historical/ohlc/load"
        params = {"token": token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        response_data = resp.json()
        # Response: {"symbol": "...", "rows": N, "data": [...]}
        data = response_data.get("data", [])
        if not data:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(data)
        # Rename timestamp to start_time for compatibility
        df.rename(columns={"timestamp": "start_time"}, inplace=True)
        # Values are already floats from API
        return df

    def fetch_latest_ltp(self, stock_token: str = '99926009'):
        url = f"{self.base_url}/indices/ltp"
        params = {"stock_token": stock_token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()["data"]
        return data["last_update"], data["ltp"]

    def send_entry_signal(self, token: str, signal: str, strike_price_token: str, strategy_code: str,unique_id:str,strike_data:dict) -> bool:
        '''
        Send trading entry signal to the API.
        This is a POST API with no authentication required.
        
        Args:
            token (str): The token identifier (e.g., "23")
            signal (str): The signal type (e.g., "BUY_ENTRY", "SELL_ENTRY")
            strike_price_token (str): The strike price token
            strategy_code (str): Code of the strategy
            unique_id (str): Unique ID for this signal
            
        Returns:
            bool: True if signal sent successfully, False otherwise
        '''
        # url = f"{self.base_url}/signals/entry"
        # url = f"{self.base_url}/signals/v2/entry"
        url = f"{self.base_url}/signals/entry/v3"
        
        payload = {
            "token": token,
            "signal": signal,
            "unique_id": unique_id,
            "strike_price_token": strike_price_token,
            "strategy_code": strategy_code,
            "strike_data": strike_data
        }
        
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Entry signal sent successfully: {payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to send entry signal for token {token}: {e}")
            return True
            # return False

    def send_exit_signal(self, token: str, signal: str, strike_price_token: str, strategy_code: str, unique_id: str,strike_data:dict) -> bool:
        '''
        Send trading exit signal to the API.
        This is a POST API with no authentication required.
        
        Args:
            token (str): The token identifier (e.g., "23")
            signal (str): The signal type (e.g., "BUY_EXIT", "SELL_EXIT")
            strike_price_token (str): The strike price token
            strategy_code (str): Code of the strategy
            unique_id (str): Unique ID for this signal (should match the entry signal ID)
            
        Returns:
            bool: True if signal sent successfully, False otherwise
        '''
        # url = f"{self.base_url}/signals/exit"
        # url = f"{self.base_url}/signals/v2/exit"
        url = f"{self.base_url}/signals/exit/v3"
        
        payload = {
            "token": token,
            "signal": signal,
            "unique_id": unique_id,
            "strike_price_token": strike_price_token,
            "strategy_code": strategy_code,
            "strike_data": strike_data
        }
        
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Exit signal sent successfully: {payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to send exit signal for token {token}: {e}")
            return True
            # return False



# --- Strategy Orchestration Class ---
class StrategyTrader:
    def __init__(self, api_client):
        # Store the API client instance for data access
        self.api = api_client
        self.strategy_code = os.getenv("STRATEGY_CODE", "UNKNOWN")

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.
        Market hours: 9:30 AM to 2:00 PM (14:00) IST
        Returns True if market is open, False otherwise.
        """
        current_time = datetime.now(IST).time()
        market_open = time_c(9, 30)  # 9:30 AM
        market_close = time_c(15, 15)  # 2:00 PM (14:00)
        return market_open <= current_time <= market_close
        # return True

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
            logger.info(f"Starting trade_function for token: {token}")
            stock_token = token  # The token to trade

            # Fetch historical OHLC data for the token
            historical_df = self.api.fetch_historical_ohlc(token=stock_token, limit=500)
            if historical_df is None or historical_df.empty:
                # Abort if no historical data is available
                logger.error("No historical data found, aborting trade_function.")
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
            unique_id: str | None = None  # Unique ID for this trade
            strike_price_token: str | None = None  # Strike price token for exit signal
            strike_data: dict | None = None  # Strike data for exit signal

            while True:
                exit_flag = False  # Whether an exit condition is met

                # Skip loop if market is closed
                if not self.is_market_open():
                    time.sleep(60)  # Sleep when market is closed to avoid CPU spinning
                    continue

                try:
                    # Fetch the latest LTP (last traded price)
                    ltp_price = self.api.fetch_latest_ltp(stock_token=stock_token)[1]
                except Exception as e:
                    # Log and skip on LTP fetch error
                    print(e)
                    logger.error(f"Failed to fetch latest LTP: {e}")
                    traceback.print_exc()
                    time.sleep(10)
                    continue

                # Check for exit conditions if a position is open
                if previous_entry_exit_key is not None and stop_loss is not None and target is not None:
                    if previous_entry_exit_key == 'BUY_EXIT':
                        # Exit if LTP hits stop loss, target, or time is after 14:25
                        if ltp_price <= stop_loss or ltp_price >= target or datetime.now().time() >= time_c(14, 25):
                            exit_flag = True
                            print('exit flag is true')
                            logger.info(f"buy exit ltp_price={ltp_price} stop_loss={stop_loss} target={target} previous_entry_exit_key={previous_entry_exit_key} stock_token={stock_token} cond1{ltp_price <= stop_loss} cond2{ltp_price >= target}")
                        # Admin-triggered exit
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            print('admin exit signal received, exiting buy position')
                            logger.info(f"Admin exit signal for BUY_EXIT stock_token={stock_token}")
                    elif previous_entry_exit_key == 'SELL_EXIT':
                        # Exit if LTP hits stop loss, target, or time is after 14:25
                        if ltp_price >= stop_loss or ltp_price <= target or datetime.now().time() >= time_c(14, 25):
                            exit_flag = True
                            print('exit flag is true')
                            logger.info(f"sell exit ltp_price={ltp_price} stop_loss={stop_loss} target={target} previous_entry_exit_key={previous_entry_exit_key} stock_token={stock_token} cond1{ltp_price >= stop_loss} cond2{ltp_price <= target}")
                        # Admin-triggered exit
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            print('admin exit signal received, exiting sell position')
                            logger.info(f"Admin exit signal for SELL_EXIT stock_token={stock_token}")

                # Fetch the latest OHLC candle (use actual stock_token)
                try:
                    ohlc_result = self.api.fetch_ohlc(token=stock_token, limit=1)
                    if ohlc_result is None:
                        logger.error(f"OHLC fetch returned None for token {stock_token}")
                        time.sleep(5)
                        continue
                    start_time, open_, high, low, close = ohlc_result
                except Exception as e:
                    logger.error(f"Failed to fetch OHLC for token {stock_token}: {e}")
                    traceback.print_exc()
                    time.sleep(10)
                    continue
                # Skip if this candle was already processed
                if start_time == previous_candle_time:
                    time.sleep(2)  # Wait before checking again
                    continue
                previous_candle_time = start_time
                print('previous_candle_time is ==', open_,high,low,close)
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

                # Update stop_loss and target only if new values are provided
                if stop_loss_ is not None:
                    stop_loss = stop_loss_
                if target_ is not None:
                    target = target_
                logger.info(f"Signal generated: {signal}  strike price  {strike_price} ")

                if signal == 'BUY_ENTRY':
                    
                    if datetime.now().time() <= time_c(15, 30):
                        # Set up for a buy position
                        tokens_data_frame = pd.read_excel('strike-price.xlsx')  # Load strike price data
                        option_token_row = tokens_data_frame[
                            (tokens_data_frame['strike_price'] == int(strike_price)) &
                            (tokens_data_frame['position'] == 'CE')
                        ]
                        print('length is :: ', len(tokens_data_frame), "strike price is ::", strike_price)
                        if option_token_row.empty:
                            # No matching call option found
                            logger.error(f"No CE option found for strike_price {strike_price}")
                            strategy.reset_state() # Reset because we couldn't find the token
                            continue
                        print(f"BUY_ENTRY signal received token number is {option_token_row['token'].iloc[0]}")
                        temp_unique_id = str(uuid4())
                        temp_strike_price_token = str(option_token_row['token'].iloc[0])
                        threading.Thread(target=start_strike_ltp_stream, args=(str(option_token_row['token'].iloc[0]),str(option_token_row['symbol'].iloc[0]))).start()
                        strike_data = {
                            "token": str(option_token_row['token'].iloc[0]),
                            "exchange": str(option_token_row['exchange'].iloc[0]),
                            "index_name": str(option_token_row['index_name'].iloc[0]),
                            "DOE": str(option_token_row['DOE'].iloc[0]),
                            "strike_price": int(option_token_row['strike_price'].iloc[0]),
                            "position": str(option_token_row['position'].iloc[0]),
                            "symbol": str(option_token_row['symbol'].iloc[0])
                        }
                        # Only update state if API call succeeds
                        if self.api.send_entry_signal(
                            token=token, 
                            signal="BUY_ENTRY", 
                            strike_price_token=temp_strike_price_token, 
                            strategy_code=self.strategy_code, 
                            unique_id=temp_unique_id,
                            strike_data=strike_data,
                            ):
                            previous_entry_exit_key = 'BUY_EXIT'
                            unique_id = temp_unique_id
                            strike_price_token = temp_strike_price_token
                            open_order = True  # Mark order as open
                            logger.info(f"strike price token number is {temp_strike_price_token}")
                        else:
                            logger.error(f"Failed to send BUY_ENTRY signal, resetting strategy state")
                            strategy.reset_state()
                    else:
                        logger.info(f"BUY_ENTRY signal ignored due to time limit (> 11:30 AM). Resetting strategy state.")
                        strategy.reset_state()

                elif signal == 'SELL_ENTRY':
                    if datetime.now().time() <= time_c(15, 15):
                        # Set up for a sell position
                        print('SELL_ENTRY signal received')
                        tokens_data_frame = pd.read_excel('strike-price.xlsx')  # Load strike price data
                        print('length is :: ', len(tokens_data_frame), "strike price is ::", strike_price)
                        option_token_row = tokens_data_frame[
                            (tokens_data_frame['strike_price'] == int(strike_price)) &
                            (tokens_data_frame['position'] == 'PE')
                        ]

                        if option_token_row.empty:
                            # No matching put option found
                            logger.error(f"No PE option found for strike_price {strike_price}")
                            strategy.reset_state() 
                            continue

                        temp_unique_id = str(uuid4())
                        temp_strike_price_token = str(option_token_row['token'].iloc[0])
                        threading.Thread(target=start_strike_ltp_stream, args=(str(option_token_row['token'].iloc[0]),str(option_token_row['symbol'].iloc[0]))).start()

                        strike_data = {
                            "token": str(option_token_row['token'].iloc[0]),
                            "exchange": str(option_token_row['exchange'].iloc[0]),
                            "index_name": str(option_token_row['index_name'].iloc[0]),
                            "DOE": str(option_token_row['DOE'].iloc[0]),
                            "strike_price": int(option_token_row['strike_price'].iloc[0]),
                            "position": str(option_token_row['position'].iloc[0]),
                            "symbol": str(option_token_row['symbol'].iloc[0])
                        }
                        # Only update state if API call succeeds
                        if self.api.send_entry_signal(
                            token=token, 
                            signal="SELL_ENTRY", 
                            strike_price_token=temp_strike_price_token, 
                            strategy_code=self.strategy_code, 
                            unique_id=temp_unique_id,
                            strike_data=strike_data,

                            ):
                            previous_entry_exit_key = 'SELL_EXIT'
                            unique_id = temp_unique_id
                            strike_price_token = temp_strike_price_token
                            open_order = True  # Mark order as open
                            print(f"SELL_ENTRY signal received token number is {option_token_row['token'].iloc[0]}")
                            logger.info(f"strike price token number is {temp_strike_price_token}")
                        else:
                            logger.error(f"Failed to send SELL_ENTRY signal, resetting strategy state")
                            strategy.reset_state()
                    else:
                        logger.info(f"SELL_ENTRY signal ignored due to time limit (> 11:30 AM). Resetting strategy state.")
                        strategy.reset_state()

                # --- EXIT conditions ---
                if signal == 'BUY_EXIT' or (previous_entry_exit_key == 'BUY_EXIT' and exit_flag):
                    # Only execute exit if we actually have an active trade (unique_id check)
                    if unique_id is not None:
                        open_order = False  # Mark order as closed
                        print('BUY_EXIT: Closing buy position')
                        logger.info(f"BUY_EXIT executed for stock_token={stock_token}")
                        # Validate variables before sending exit signal
                        if strike_price_token is not None:
                            self.api.send_exit_signal(
                                token=token, 
                                signal="BUY_EXIT", 
                                strike_price_token=strike_price_token, 
                                strategy_code=self.strategy_code, 
                                unique_id=unique_id,
                                strike_data=strike_data
                                )
                        else:
                            logger.error(f"Cannot send BUY_EXIT: strike_price_token is None")
                        
                        # Reset all position-related state
                        unique_id = None
                        strike_price_token = None
                        previous_entry_exit_key = None
                        stop_loss = None
                        target = None
                        strike_data=None
                    else:
                        # This handles the case where strategy sends BUY_EXIT but we never entered
                        if signal == 'BUY_EXIT':
                            logger.info(f"Ignoring strategy BUY_EXIT signal as no local position exists.")
                        # If exit_flag was set but no position, we reset strategy just in case
                        strategy.reset_state()
                    continue
                
                if signal == 'SELL_EXIT' or (previous_entry_exit_key == 'SELL_EXIT' and exit_flag):
                    # Only execute exit if we actually have an active trade (unique_id check)
                    if unique_id is not None:
                        open_order = False  # Mark order as closed
                        print('SELL_EXIT: Closing sell position')
                        logger.info(f"SELL_EXIT executed for stock_token={stock_token}")
                        # Validate variables before sending exit signal
                        if strike_price_token is not None:
                            self.api.send_exit_signal(
                                token=token, 
                                signal="SELL_EXIT", 
                                strike_price_token=strike_price_token, 
                                strategy_code=self.strategy_code, 
                                unique_id=unique_id,
                                strike_data=strike_data
                                )
                        else:
                            logger.error(f"Cannot send SELL_EXIT: strike_price_token is None")

                        # Reset all position-related state
                        unique_id = None
                        strike_price_token = None
                        previous_entry_exit_key = None
                        stop_loss = None
                        target = None
                        strike_data=None
                    else:
                        # This handles the case where strategy sends SELL_EXIT but we never entered
                        if signal == 'SELL_EXIT':
                            logger.info(f"Ignoring strategy SELL_EXIT signal as no local position exists.")
                        # If exit_flag was set but no position, we reset strategy just in case
                        strategy.reset_state()
                    continue

                # Wait before next iteration (throttle loop)
                time.sleep(2)
        except Exception as e:
            # Log and print any unexpected errors
            print('error is :: ', e)
            logger.error(f"Error processing trade: {str(e)}", exc_info=True)
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
            logger.error("Error in run method", exc_info=True)
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
