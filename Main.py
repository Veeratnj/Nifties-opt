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
import base64

# --- Local Imports ---
from algo import HeikinAshiATRStrategy


# --- Constants ---
IST = pytz.timezone("Asia/Kolkata")

load_dotenv()

# --- API Database Client ---
class ApiDatabaseClient:
    def __init__(self):
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000/db")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def kill_trade_signal(self, token: str) -> bool:
        url = f"{self.base_url}/admin/kill-trade-signal"
        payload = {"token": token}
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("kill", False)
        except Exception as e:
            logger.error(f"Failed to fetch kill trade signal for token {token}: {e}")
            return False

    def get_nifties_token(self) -> list[str]:
        url = f"{self.base_url}/indices/nifty-tokens"
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tokens", [])
        except Exception as e:
            logger.error(f"Failed to fetch Nifty tokens: {e}")
            return []

    def fetch_ohlc(self, token, limit=1):
        url = f"{self.base_url}/current/ohlc"
        params = {"token": token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        response_data = resp.json()
        if response_data.get("status") != "success":
            return None
        data = response_data.get("data")
        if not data:
            return None
        return data["start_time"], data["open"], data["high"], data["low"], data["close"]

    def fetch_historical_ohlc(self, token, limit=500):
        url = f"{self.base_url}/historical/ohlc/load"
        params = {"token": token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        response_data = resp.json()
        data = response_data.get("data", [])
        if not data:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(data)
        df.rename(columns={"timestamp": "start_time"}, inplace=True)
        return df

    def fetch_latest_ltp(self, stock_token: str = '99926009'):
        url = f"{self.base_url}/indices/ltp"
        params = {"stock_token": stock_token}
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()["data"]
        return data["last_update"], data["ltp"]

    def send_entry_signal(self, token, signal, strike_price_token, strategy_code,
                          unique_id, strike_data, stop_loss, target, description) -> bool:
        url = f"{self.base_url}/signals/entry/v3"
        payload = {
            "token": token, "signal": signal, "unique_id": unique_id,
            "strike_price_token": strike_price_token, "strategy_code": strategy_code,
            "stop_loss": stop_loss, "target": target, "description": description,
            "strike_data": strike_data
        }
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"Entry signal sent successfully: {payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to send entry signal for token {token}: {e}")
            return True

    def send_exit_signal(self, token, signal, strike_price_token, strategy_code,
                         unique_id, strike_data, stop_loss, target, description) -> bool:
        url = f"{self.base_url}/signals/exit/v3"
        payload = {
            "token": token, "signal": signal, "unique_id": unique_id,
            "strike_price_token": strike_price_token, "strategy_code": strategy_code,
            "strike_data": strike_data, "stop_loss": stop_loss,
            "target": target, "description": description
        }
        try:
            resp = self.session.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"Exit signal sent successfully: {payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to send exit signal for token {token}: {e}")
            return True

    def get_stop_loss_target(self, unique_id: str):
        url = f"{self.base_url}/signals/get-stop-loss-target/v1/{unique_id}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data['stop_loss'], data['target']

    def update_stop_loss_target(self, unique_id: str, stop_loss: float = None, target: float = None):
        url = f"{self.base_url}/signals/update-stop-loss-target/v1"
        params = {"unique_id": unique_id}
        if stop_loss is not None:
            params["stop_loss"] = stop_loss
        if target is not None:
            params["target"] = target
        response = self.session.put(url, params=params)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")
        return response.json()

    def get_strike_pice_close_signal(self, unique_id: str):
        url = f"{self.base_url}/signals/get-strike-price-close-trade-signal/{unique_id}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data['data']

    def get_symbol_token_file(self, token: str):
        url = f"{self.base_url}/signals/get-symbol-token-file/{token}"
        resp = self.session.get(url)
        data = resp.json()
        base64_file = data.get("file")
        file_path = data.get("file_path")
        print('file_path :: ', file_path)
        if base64_file:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(base64_file))
            print("✅ File saved at:", file_path)
        else:
            print("❌ No file found for this token")
        return data.get("file"), data.get("file_path")


tokens_utils = {
    '25': {"file_name": r"Bank-Nifty.xlsx", "strike_roundup_value": 200, "lot_qty": 30, 'exchange': 'NSE_FNO'},
    "13": {"file_name": r"Nifty.xlsx",      "strike_roundup_value": 100, "lot_qty": 65, 'exchange': 'NSE_FNO'},
    "51": {"file_name": r"Sensex.xlsx",     "strike_roundup_value": 200, "lot_qty": 20, 'exchange': 'BSE_FNO'},
    "27": {"file_name": r"Nifty-fin.xlsx",  "strike_roundup_value": 100, "lot_qty": 60, 'exchange': 'NSE_FNO'},
    "442":{"file_name": r"Midcap-Nifty.xlsx","strike_roundup_value": 75, "lot_qty": 120,'exchange': 'NSE_FNO'}
}


# -----------------------------------------------------------
# Helper: reset all position state variables
# -----------------------------------------------------------

def _reset_position_state():
    """Returns a dict of cleared position variables."""
    return {
        "open_order": False,
        "stop_loss": None,
        "target": None,
        "previous_entry_exit_key": None,
        "unique_id": None,
        "strike_price_token": None,
        "strike_data": None,
    }


# --- Strategy Orchestration Class ---
class StrategyTrader:
    def __init__(self, api_client):
        self.api = api_client
        self.strategy_code = os.getenv("STRATEGY_CODE", "UNKNOWN")

    def is_market_open(self) -> bool:
        current_time = datetime.now(IST).time()
        market_open  = time_c(9, 27)
        market_close = time_c(13, 0)
        return market_open <= current_time <= market_close

    def is_new_entry_allowed(self) -> bool:
        """New entries allowed only between 9:27 AM and 1:30 PM."""
        current_time = datetime.now(IST).time()
        return time_c(9, 27) <= current_time <= time_c(13, 30)

    def admin_trade_exit_signal(self, token: str) -> bool:
        return self.api.kill_trade_signal(token=token)

    def trade_function(self, token: str, strike_roundup_value: int,
                       file_name: str, lot_qty: int, exchange: str) -> None:
        import traceback
        try:
            logger.info(f"Starting trade_function for token: {token}")
            stock_token = token

            historical_df = self.api.fetch_historical_ohlc(token=stock_token, limit=500)
            if historical_df is None or historical_df.empty:
                logger.error("No historical data found, aborting trade_function.")
                return

            strategy = HeikinAshiATRStrategy(token=stock_token, strike_roundup_value=strike_roundup_value)
            temp_csv = f"_temp_{stock_token}_ohlc.csv"
            historical_df.to_csv(temp_csv, index=False)
            strategy.load_historical_data(temp_csv)

            # --- Position state ---
            pos = _reset_position_state()
            previous_candle_time = None

            while True:
                # --------------------------------------------------
                # 1. Market hours gate
                #    - Loop runs until 1:30 PM to allow force close
                #    - After 1:30 PM and no open trade, sleep
                # --------------------------------------------------
                current_time = datetime.now(IST).time()
                if current_time < time_c(9, 27) or \
                        (current_time > time_c(13, 30) and pos["unique_id"] is None):
                    time.sleep(60)
                    continue

                # --------------------------------------------------
                # 2. Fetch LTP
                # --------------------------------------------------
                try:
                    ltp_price = self.api.fetch_latest_ltp(stock_token=stock_token)[1]
                except Exception as e:
                    logger.error(f"Failed to fetch latest LTP: {e}")
                    traceback.print_exc()
                    time.sleep(10)
                    continue

                # --------------------------------------------------
                # 3. Force close at 1:30 PM if trade is open
                # --------------------------------------------------
                if datetime.now(IST).time() >= time_c(13, 30) \
                        and pos["unique_id"] is not None:
                    exit_signal = pos["previous_entry_exit_key"]  # 'BUY_EXIT' or 'SELL_EXIT'
                    logger.info(f"Force close at 1:30 PM | signal={exit_signal} token={stock_token}")
                    print(f"Force close at 1:30 PM: sending {exit_signal} for token={stock_token}")

                    if pos["strike_price_token"] is not None:
                        self.api.send_exit_signal(
                            token=token,
                            signal=exit_signal,
                            strike_price_token=pos["strike_price_token"],
                            strategy_code=self.strategy_code,
                            unique_id=pos["unique_id"],
                            strike_data=pos["strike_data"],
                            stop_loss=pos["stop_loss"],
                            target=pos["target"],
                            description='force close at 1:30 PM'
                        )
                    else:
                        logger.error(f"Force close: strike_price_token is None for token={stock_token}")

                    strategy.reset_state()
                    pos = _reset_position_state()
                    time.sleep(2)
                    continue

                # --------------------------------------------------
                # 4. LTP-based exit check (runs every tick)
                # --------------------------------------------------
                exit_flag = False

                if pos["previous_entry_exit_key"] is not None \
                        and pos["stop_loss"] is not None \
                        and pos["target"] is not None \
                        and pos["unique_id"] is not None:

                    # Refresh SL/target from API
                    try:
                        temp_sl, temp_tp = self.api.get_stop_loss_target(pos["unique_id"])
                        if temp_sl is not None:
                            pos["stop_loss"] = temp_sl
                        if temp_tp is not None:
                            pos["target"] = temp_tp
                    except Exception as e:
                        logger.error(f"get_stop_loss_target failed: {e}")

                    if pos["previous_entry_exit_key"] == 'BUY_EXIT':
                        if ltp_price <= pos["stop_loss"] or ltp_price >= pos["target"]:
                            exit_flag = True
                            logger.info(
                                f"BUY LTP exit triggered | ltp={ltp_price} "
                                f"sl={pos['stop_loss']} tp={pos['target']}"
                            )
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            logger.info(f"Admin BUY exit for token={stock_token}")

                    elif pos["previous_entry_exit_key"] == 'SELL_EXIT':
                        if ltp_price >= pos["stop_loss"] or ltp_price <= pos["target"]:
                            exit_flag = True
                            logger.info(
                                f"SELL LTP exit triggered | ltp={ltp_price} "
                                f"sl={pos['stop_loss']} tp={pos['target']}"
                            )
                        elif self.admin_trade_exit_signal(token=stock_token):
                            exit_flag = True
                            logger.info(f"Admin SELL exit for token={stock_token}")

                    # Admin strike-price close
                    if not exit_flag:
                        try:
                            if self.api.get_strike_pice_close_signal(pos["unique_id"]):
                                exit_flag = True
                                logger.info(f"Strike price close signal for token={stock_token}")
                        except Exception as e:
                            logger.error(f"get_strike_pice_close_signal failed: {e}")

                # --------------------------------------------------
                # 4. If LTP exit triggered — send exit NOW without
                #    waiting for a new candle
                # --------------------------------------------------
                if exit_flag and pos["unique_id"] is not None:
                    exit_signal = pos["previous_entry_exit_key"]   # 'BUY_EXIT' or 'SELL_EXIT'
                    logger.info(f"{exit_signal} via exit_flag for token={stock_token}")
                    print(f"{exit_signal}: closing position via LTP/admin trigger")

                    if pos["strike_price_token"] is not None:
                        self.api.send_exit_signal(
                            token=token,
                            signal=exit_signal,
                            strike_price_token=pos["strike_price_token"],
                            strategy_code=self.strategy_code,
                            unique_id=pos["unique_id"],
                            strike_data=pos["strike_data"],
                            stop_loss=pos["stop_loss"],
                            target=pos["target"],
                            description='LTP/admin exit from 3mins strategy'
                        )
                    else:
                        logger.error(f"Cannot send {exit_signal}: strike_price_token is None")

                    # Reset everything
                    strategy.reset_state()
                    pos = _reset_position_state()
                    time.sleep(2)
                    continue

                # --------------------------------------------------
                # 5. Fetch latest OHLC candle
                # --------------------------------------------------
                try:
                    ohlc_result = self.api.fetch_ohlc(token=stock_token, limit=1)
                    if ohlc_result is None:
                        logger.error(f"OHLC fetch returned None for token {stock_token}")
                        time.sleep(5)
                        continue
                    start_time, open_, high, low, close = ohlc_result
                    print('ohlc =', ohlc_result)
                except Exception as e:
                    logger.error(f"Failed to fetch OHLC for token {stock_token}: {e}")
                    traceback.print_exc()
                    time.sleep(10)
                    continue

                # Skip duplicate candle
                if start_time == previous_candle_time:
                    time.sleep(2)
                    continue
                previous_candle_time = start_time
                print(f"New candle: open={open_} high={high} low={low} close={close} ts={start_time}")

                # --------------------------------------------------
                # 6. Feed candle to strategy and generate signal
                # --------------------------------------------------
                live_data = {
                    'open': open_, 'close': close,
                    'high': high,  'low': low,
                    'volume': 0,   'timestamp': start_time
                }
                strategy.add_live_data(live_data)
                signal_result = strategy.generate_signal()
                print('signal result =', signal_result)

                if isinstance(signal_result, tuple):
                    signal, stop_loss_, target_, strike_price = signal_result
                else:
                    signal, stop_loss_, target_, strike_price = signal_result, None, None, None

                # Update SL/target if new values came in
                if stop_loss_ is not None:
                    pos["stop_loss"] = stop_loss_
                if target_ is not None:
                    pos["target"] = target_

                # Push updated SL/target to API if trade is open
                if pos["stop_loss"] is not None and pos["target"] is not None \
                        and pos["unique_id"] is not None:
                    try:
                        self.api.update_stop_loss_target(
                            pos["unique_id"], pos["stop_loss"], pos["target"]
                        )
                    except Exception as e:
                        logger.error(f"update_stop_loss_target failed: {e}")

                logger.info(f"Signal: {signal} | strike_price: {strike_price}")

                # --------------------------------------------------
                # 7. Strategy-generated EXIT signals (candle close)
                # --------------------------------------------------
                if signal in ('BUY_EXIT', 'SELL_EXIT'):
                    if pos["unique_id"] is not None:
                        print(f"{signal}: closing position via strategy candle signal")
                        logger.info(f"{signal} via strategy for token={stock_token}")

                        if pos["strike_price_token"] is not None:
                            self.api.send_exit_signal(
                                token=token,
                                signal=signal,
                                strike_price_token=pos["strike_price_token"],
                                strategy_code=self.strategy_code,
                                unique_id=pos["unique_id"],
                                strike_data=pos["strike_data"],
                                stop_loss=pos["stop_loss"],
                                target=pos["target"],
                                description='strategy candle exit from 3mins strategy'
                            )
                        else:
                            logger.error(f"Cannot send {signal}: strike_price_token is None")

                        strategy.reset_state()
                        pos = _reset_position_state()
                    else:
                        logger.info(f"Ignoring {signal} — no active position.")
                        strategy.reset_state()

                    time.sleep(2)
                    continue

                # --------------------------------------------------
                # 8. ENTRY signals
                # --------------------------------------------------
                if signal == 'BUY_ENTRY' and self.is_new_entry_allowed():
                    tokens_data_frame = pd.read_excel(rf'strike_data/{file_name}')
                    option_token_row = tokens_data_frame[
                        (tokens_data_frame['strike_price'] == int(strike_price)) &
                        (tokens_data_frame['position'] == 'CE')
                    ]
                    print(f"BUY_ENTRY | df_len={len(tokens_data_frame)} strike={strike_price}")

                    if option_token_row.empty:
                        logger.error(f"No CE option found for strike_price {strike_price}")
                        strategy.reset_state()
                        time.sleep(2)
                        continue

                    temp_unique_id = str(uuid4())
                    temp_spt = str(option_token_row['token'].iloc[0])
                    temp_strike_data = {
                        "token":        str(option_token_row['token'].iloc[0]),
                        "exchange":     str(option_token_row['exchange'].iloc[0]),
                        "index_name":   str(option_token_row['index_name'].iloc[0]),
                        "DOE":          str(option_token_row['DOE'].iloc[0]),
                        "strike_price": int(option_token_row['strike_price'].iloc[0]),
                        "position":     str(option_token_row['position'].iloc[0]),
                        "symbol":       str(option_token_row['symbol'].iloc[0]),
                        "lot_qty":      lot_qty,
                        "exchange":     exchange
                    }

                    if self.api.send_entry_signal(
                        token=token, signal="BUY_ENTRY",
                        strike_price_token=temp_spt,
                        strategy_code=self.strategy_code,
                        unique_id=temp_unique_id,
                        strike_data=temp_strike_data,
                        stop_loss=pos["stop_loss"],
                        target=pos["target"],
                        description='natural entry signal from 3mins strategy'
                    ):
                        pos["previous_entry_exit_key"] = 'BUY_EXIT'
                        pos["unique_id"]               = temp_unique_id
                        pos["strike_price_token"]      = temp_spt
                        pos["strike_data"]             = temp_strike_data
                        pos["open_order"]              = True
                        logger.info(f"BUY_ENTRY confirmed | spt={temp_spt}")
                    else:
                        logger.error("Failed to send BUY_ENTRY signal, resetting strategy state")
                        strategy.reset_state()

                elif signal == 'BUY_ENTRY':
                    logger.info("BUY_ENTRY ignored — past time limit. Resetting strategy state.")
                    strategy.reset_state()

                elif signal == 'SELL_ENTRY' and self.is_new_entry_allowed():
                    tokens_data_frame = pd.read_excel(rf'strike_data/{file_name}')
                    option_token_row = tokens_data_frame[
                        (tokens_data_frame['strike_price'] == int(strike_price)) &
                        (tokens_data_frame['position'] == 'PE')
                    ]
                    print(f"SELL_ENTRY | df_len={len(tokens_data_frame)} strike={strike_price}")

                    if option_token_row.empty:
                        logger.error(f"No PE option found for strike_price {strike_price}")
                        strategy.reset_state()
                        time.sleep(2)
                        continue

                    temp_unique_id = str(uuid4())
                    temp_spt = str(option_token_row['token'].iloc[0])
                    temp_strike_data = {
                        "token":        str(option_token_row['token'].iloc[0]),
                        "exchange":     str(option_token_row['exchange'].iloc[0]),
                        "index_name":   str(option_token_row['index_name'].iloc[0]),
                        "DOE":          str(option_token_row['DOE'].iloc[0]),
                        "strike_price": int(option_token_row['strike_price'].iloc[0]),
                        "position":     str(option_token_row['position'].iloc[0]),
                        "symbol":       str(option_token_row['symbol'].iloc[0]),
                        "lot_qty":      lot_qty,
                        "exchange":     exchange
                    }

                    if self.api.send_entry_signal(
                        token=token, signal="SELL_ENTRY",
                        strike_price_token=temp_spt,
                        strategy_code=self.strategy_code,
                        unique_id=temp_unique_id,
                        strike_data=temp_strike_data,
                        stop_loss=pos["stop_loss"],
                        target=pos["target"],
                        description='natural entry signal from 3mins strategy'
                    ):
                        pos["previous_entry_exit_key"] = 'SELL_EXIT'
                        pos["unique_id"]               = temp_unique_id
                        pos["strike_price_token"]      = temp_spt
                        pos["strike_data"]             = temp_strike_data
                        pos["open_order"]              = True
                        logger.info(f"SELL_ENTRY confirmed | spt={temp_spt}")
                    else:
                        logger.error("Failed to send SELL_ENTRY signal, resetting strategy state")
                        strategy.reset_state()

                elif signal == 'SELL_ENTRY':
                    logger.info("SELL_ENTRY ignored — past time limit. Resetting strategy state.")
                    strategy.reset_state()

                time.sleep(2)

        except Exception as e:
            print('error is ::', e)
            logger.error(f"Error processing trade: {str(e)}", exc_info=True)
            import traceback
            traceback.print_exc()

    def run(self):
        import traceback
        try:
            tokens = ApiDatabaseClient().get_nifties_token()
            print('tokens are ::', tokens)
            threads = []
            for token in tokens:
                self.api.get_symbol_token_file(token)
                util_dict = tokens_utils[str(token)]
                t = threading.Thread(
                    target=self.trade_function,
                    args=(token, util_dict['strike_roundup_value'],
                          util_dict['file_name'], util_dict['lot_qty'], util_dict['exchange'])
                )
                t.start()
                print(f"Started thread for token={token}")
                threads.append(t)
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