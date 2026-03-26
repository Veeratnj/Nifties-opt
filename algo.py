"""
Heikin Ashi + ATR + RSI + Expansion Candle Strategy

Fixes Applied
-------------
1. rsi_htf now recalculated in add_live_data (was never updated → NaN → signals blocked)
2. expansion_body_signal now uses ha_open/ha_close/ha_high/ha_low consistently
3. Zero/negative range guard added in expansion_body_signal
4. ffill + bfill applied to rsi_htf reindex to eliminate NaN on edge rows
5. Diagnostic logging added per candle to aid debugging
"""

import math
import pandas as pd
import pandas_ta as ta
import logging


# -----------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("heikin_ashi_strategy.log")
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)


# -----------------------------------------------------------
# Strategy Class
# -----------------------------------------------------------

class HeikinAshiATRStrategy:

    def __init__(
        self,
        atr_len=14,
        atr_mult=2.5,
        rsi_len=14,
        risk_reward=2.0,
        strike_roundup_value=100,
        round_off_diff=100,
        etf="3min",
        htf="15min",
        body_expansion_factor=0.68,
        token=None
    ):
        self.atr_len = atr_len
        self.atr_mult = atr_mult
        self.rsi_len = rsi_len
        self.risk_reward = risk_reward
        self.strike_roundup_value = strike_roundup_value
        self.round_off_diff = round_off_diff
        self.token = token

        self.etf = etf
        self.htf = htf

        self.body_expansion_factor = body_expansion_factor

        self.df = pd.DataFrame()

        self.last_position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.trailing_sl = None

        self.highest_since_entry = None
        self.lowest_since_entry = None


    # -------------------------------------------------------
    # Internal: Recalculate all indicators on self.df
    # -------------------------------------------------------

    def _recalculate_indicators(self):
        """Recalculates HA, ATR, RSI LTF and RSI HTF on the full DataFrame."""

        # -------- Heikin Ashi --------
        ha = ta.ha(
            self.df["open"],
            self.df["high"],
            self.df["low"],
            self.df["close"]
        )

        self.df["ha_open"]  = ha["HA_open"]
        self.df["ha_high"]  = ha["HA_high"]
        self.df["ha_low"]   = ha["HA_low"]
        self.df["ha_close"] = ha["HA_close"]

        # -------- ATR --------
        self.df["atr"] = ta.atr(
            self.df["ha_high"],
            self.df["ha_low"],
            self.df["ha_close"],
            length=self.atr_len
        )

        # -------- RSI LTF --------
        self.df["rsi_ltf"] = ta.rsi(
            self.df["ha_close"],
            length=self.rsi_len
        )

        # -------- RSI HTF --------
        # FIX: was only calculated in load_historical_data, never in add_live_data
        df_temp = self.df.set_index("timestamp")

        rsi_htf_series = df_temp["ha_close"].resample(self.htf).last()
        rsi_htf_series = ta.rsi(rsi_htf_series, length=self.rsi_len)

        rsi_htf_reindexed = rsi_htf_series.reindex(
            self.df["timestamp"], method="ffill"
        ).ffill().bfill()  # FIX: bfill handles NaN on leading rows after reindex

        self.df["rsi_htf"] = rsi_htf_reindexed.values


    # -------------------------------------------------------
    # Load historical OHLC data
    # -------------------------------------------------------

    def load_historical_data(self, csv_file):

        self.df = pd.read_csv(csv_file)

        # Support both column name conventions
        if "start_time" in self.df.columns:
            self.df.rename(columns={"start_time": "timestamp"}, inplace=True)

        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], infer_datetime_format=True)
        self.df.sort_values("timestamp", inplace=True)
        self.df.reset_index(drop=True, inplace=True)

        self._recalculate_indicators()

        logger.info(f"Loaded {len(self.df)} historical candles.")


    # -------------------------------------------------------
    # Add new candle (live data simulation)
    # -------------------------------------------------------

    def add_live_data(self, new_data):

        # FIX: ensure timestamp is always a Timestamp object before concat
        new_data["timestamp"] = pd.to_datetime(new_data["timestamp"])

        new_row = pd.DataFrame([new_data])
        self.df = pd.concat([self.df, new_row], ignore_index=True)

        # Ensure the entire column is datetime after every concat
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])

        self._recalculate_indicators()


    # -------------------------------------------------------
    # Expansion Body Rule
    # -------------------------------------------------------

    def expansion_body_signal(self):

        if len(self.df) < 4:
            return False, False

        last = self.df.iloc[-1]

        # FIX: use ha_open/ha_close/ha_high/ha_low instead of raw OHLC
        bullish_body = max(last["ha_close"] - last["ha_open"], 0)
        bearish_body = max(last["ha_open"] - last["ha_close"], 0)

        bullish_range = self.df["ha_high"].iloc[-3] - self.df["ha_low"].iloc[-1]
        bearish_range = self.df["ha_high"].iloc[-1] - self.df["ha_low"].iloc[-3]

        # FIX: guard against zero or negative range to avoid false signals
        bullish_signal = (
            bullish_range > 0 and
            bullish_body > self.body_expansion_factor * bullish_range
        )
        bearish_signal = (
            bearish_range > 0 and
            bearish_body > self.body_expansion_factor * bearish_range
        )

        return bullish_signal, bearish_signal


    # -------------------------------------------------------
    # Generate Trading Signal
    # -------------------------------------------------------

    def generate_signal(self):

        if len(self.df) < self.atr_len + 2:
            return None

        last = self.df.iloc[-1]

        # Skip if any key indicator is NaN
        if pd.isna(last["atr"]) or pd.isna(last["rsi_ltf"]) or pd.isna(last["rsi_htf"]):
            logger.debug(
                f"NaN indicators at {last['timestamp']} — "
                f"atr={last['atr']} rsi_ltf={last['rsi_ltf']} rsi_htf={last['rsi_htf']}"
            )
            return None

        bullish_expansion, bearish_expansion = self.expansion_body_signal()

        # ---------------------------------------------------
        # Diagnostic log per candle
        # ---------------------------------------------------
        logger.debug(
            f"ts={last['timestamp']} | "
            f"ha_close={last['ha_close']:.2f} | "
            f"rsi_ltf={last['rsi_ltf']:.2f} | "
            f"rsi_htf={last['rsi_htf']:.2f} | "
            f"bull_exp={bullish_expansion} | "
            f"bear_exp={bearish_expansion} | "
            f"position={self.last_position}"
        )

        # ---------------------------------------------------
        # Exit Logic
        # ---------------------------------------------------

        if self.last_position == "long":

            self.highest_since_entry = max(
                self.highest_since_entry,
                last["ha_high"]
            )

            self.trailing_sl = (
                self.highest_since_entry - self.atr_mult * last["atr"]
            )

            if last["ha_close"] <= self.trailing_sl:
                logger.info(
                    f"BUY EXIT | ts={last['timestamp']} "
                    f"ha_close={last['ha_close']:.2f} trailing_sl={self.trailing_sl:.2f}"
                )
                self.last_position = None
                return "BUY_EXIT"

        if self.last_position == "short":

            self.lowest_since_entry = min(
                self.lowest_since_entry,
                last["ha_low"]
            )

            self.trailing_sl = (
                self.lowest_since_entry + self.atr_mult * last["atr"]
            )

            if last["ha_close"] >= self.trailing_sl:
                logger.info(
                    f"SELL EXIT | ts={last['timestamp']} "
                    f"ha_close={last['ha_close']:.2f} trailing_sl={self.trailing_sl:.2f}"
                )
                self.last_position = None
                return "SELL_EXIT"

        # ---------------------------------------------------
        # Entry Logic
        # ---------------------------------------------------

        long_entry = (
            bullish_expansion and
            last["rsi_ltf"] > 50 and
            last["rsi_htf"] > 50 and
            self.last_position is None
        )

        short_entry = (
            bearish_expansion and
            last["rsi_ltf"] < 50 and
            last["rsi_htf"] < 50 and
            self.last_position is None
        )

        # ---------------------------------------------------
        # CALL BUY
        # ---------------------------------------------------

        if long_entry:

            self.last_position = "long"
            self.entry_price = last["ha_close"]
            self.highest_since_entry = last["ha_high"]

            self.stop_loss = last["ha_close"] - self.atr_mult * last["atr"]

            self.take_profit = (
                last["ha_close"] +
                self.risk_reward * (last["ha_close"] - self.stop_loss)
            )

            option_strike = (
                (last["ha_close"] - self.round_off_diff)
                // self.strike_roundup_value
            ) * self.strike_roundup_value

            logger.info(
                f"CALL BUY ENTRY | ts={last['timestamp']} "
                f"price={last['close']:.2f} strike={option_strike} "
                f"sl={self.stop_loss:.2f} tp={self.take_profit:.2f}"
            )

            return "BUY_ENTRY", self.stop_loss, self.take_profit, option_strike

        # ---------------------------------------------------
        # PUT BUY
        # ---------------------------------------------------

        if short_entry:

            self.last_position = "short"
            self.entry_price = last["ha_close"]
            self.lowest_since_entry = last["ha_low"]

            self.stop_loss = last["ha_close"] + self.atr_mult * last["atr"]

            self.take_profit = (
                last["ha_close"] -
                self.risk_reward * (self.stop_loss - last["ha_close"])
            )

            option_strike = math.ceil(
                (last["ha_close"] + self.round_off_diff)
                / self.strike_roundup_value
            ) * self.strike_roundup_value

            logger.info(
                f"PUT BUY ENTRY | ts={last['timestamp']} "
                f"price={last['close']:.2f} strike={option_strike} "
                f"sl={self.stop_loss:.2f} tp={self.take_profit:.2f}"
            )

            return "SELL_ENTRY", self.stop_loss, self.take_profit, option_strike

        return None


# -----------------------------------------------------------
# Backtest Runner
# -----------------------------------------------------------

if __name__ == "__main__":

    strategy = HeikinAshiATRStrategy()

    df = pd.read_csv("nifty50_202603262028.csv")

    # Split into historical and live simulation
    mid = len(df) // 2
    df.iloc[:mid].to_csv("historical_data_1.csv", index=False)
    df.iloc[mid:].to_csv("historical_data_2.csv", index=False)

    # Load historical data
    strategy.load_historical_data("historical_data_1.csv")

    # Simulate live candles
    live_data = pd.read_csv("historical_data_2.csv")

    signals = []

    for _, row in live_data.iterrows():

        new_data = {
            "timestamp": row["timestamp"],
            "open":      row["open"],
            "high":      row["high"],
            "low":       row["low"],
            "close":     row["close"],
            "volume":    row.get("volume", 0)
        }

        strategy.add_live_data(new_data)

        # ---- Diagnostic print per candle ----
        last = strategy.df.iloc[-1]
        bull_exp, bear_exp = strategy.expansion_body_signal()
        print(
            f"ts={last['timestamp']} | "
            f"rsi_ltf={last['rsi_ltf']:.1f} | "
            f"rsi_htf={last['rsi_htf']:.1f} | "
            f"bull_exp={bull_exp} | "
            f"bear_exp={bear_exp}"
        )

        signal = strategy.generate_signal()

        if signal:
            print(">>> Signal:", signal)

            row_dict = strategy.df.iloc[-1].to_dict()
            row_dict["signal"] = signal
            signals.append(row_dict)

    if signals:
        pd.DataFrame(signals).to_csv("sensex_signals.csv", index=False)
        print(f"\nTotal signals generated: {len(signals)}")
    else:
        print("\nNo signals generated. Check the diagnostic output above.")