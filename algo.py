"""
Heikin Ashi + ATR + RSI + Expansion Candle Strategy

Features
--------
1. Heikin Ashi trend detection
2. ATR based stop loss
3. Multi timeframe RSI filter
4. Expansion candle body rule (0.68 factor)
5. Strike calculation for options
6. Logging for entries and exits
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
        body_expansion_factor=0.68
    ):

        # Strategy parameters
        self.atr_len = atr_len
        self.atr_mult = atr_mult
        self.rsi_len = rsi_len
        self.risk_reward = risk_reward
        self.strike_roundup_value = strike_roundup_value
        self.round_off_diff = round_off_diff

        # Timeframes
        self.etf = etf
        self.htf = htf

        # Body expansion rule
        self.body_expansion_factor = body_expansion_factor

        # DataFrame storage
        self.df = pd.DataFrame()

        # Position state variables
        self.last_position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.trailing_sl = None

        self.highest_since_entry = None
        self.lowest_since_entry = None


    # -------------------------------------------------------
    # Load historical OHLC data
    # -------------------------------------------------------

    def load_historical_data(self, csv_file):

        self.df = pd.read_csv(csv_file)

        self.df.rename(columns={"start_time": "timestamp"}, inplace=True)

        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])
        self.df.sort_values("timestamp", inplace=True)

        # -------- Heikin Ashi Calculation --------

        ha = ta.ha(
            self.df["open"],
            self.df["high"],
            self.df["low"],
            self.df["close"]
        )

        self.df["ha_open"] = ha["HA_open"]
        self.df["ha_high"] = ha["HA_high"]
        self.df["ha_low"] = ha["HA_low"]
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

        df_temp = self.df.set_index("timestamp")

        rsi_htf = df_temp["ha_close"].resample(self.htf).last()
        rsi_htf = ta.rsi(rsi_htf, length=self.rsi_len)

        rsi_htf = rsi_htf.reindex(self.df["timestamp"], method="ffill")

        self.df["rsi_htf"] = rsi_htf.values


    # -------------------------------------------------------
    # Add new candle (Live data simulation)
    # -------------------------------------------------------

    def add_live_data(self, new_data):

        new_row = pd.DataFrame([new_data])

        self.df = pd.concat([self.df, new_row], ignore_index=True)

        # Recalculate indicators only when new row arrives
        ha = ta.ha(
            self.df["open"],
            self.df["high"],
            self.df["low"],
            self.df["close"]
        )

        self.df["ha_open"] = ha["HA_open"]
        self.df["ha_high"] = ha["HA_high"]
        self.df["ha_low"] = ha["HA_low"]
        self.df["ha_close"] = ha["HA_close"]

        self.df["atr"] = ta.atr(
            self.df["ha_high"],
            self.df["ha_low"],
            self.df["ha_close"],
            length=self.atr_len
        )

        self.df["rsi_ltf"] = ta.rsi(
            self.df["ha_close"],
            length=self.rsi_len
        )


    # -------------------------------------------------------
    # Expansion Body Rule (Your rule)
    # -------------------------------------------------------

    def expansion_body_signal(self):

        if len(self.df) < 4:
            return False, False

        last = self.df.iloc[-1]

        # Candle bodies
        bullish_body = max(last["close"] - last["open"], 0)
        bearish_body = max(last["open"] - last["close"], 0)

        # Range from your formula
        bullish_range = self.df["high"].iloc[-3] - self.df["low"].iloc[-1]
        bearish_range = self.df["high"].iloc[-1] - self.df["low"].iloc[-3]

        bullish_signal = bullish_body > self.body_expansion_factor * bullish_range
        bearish_signal = bearish_body > self.body_expansion_factor * bearish_range

        return bullish_signal, bearish_signal


    # -------------------------------------------------------
    # Generate Trading Signal
    # -------------------------------------------------------

    def generate_signal(self):

        if len(self.df) < 4:
            return None

        last = self.df.iloc[-1]

        bullish_expansion, bearish_expansion = self.expansion_body_signal()

        # ---------------------------------------------------
        # Exit Logic
        # ---------------------------------------------------

        if self.last_position == "long":

            self.highest_since_entry = max(
                self.highest_since_entry,
                last["ha_high"]
            )

            self.trailing_sl = self.highest_since_entry - (
                self.atr_mult * last["atr"]
            )

            if last["ha_close"] <= self.trailing_sl:

                logger.info("BUY EXIT")
                self.last_position = None
                return "BUY_EXIT"

        if self.last_position == "short":

            self.lowest_since_entry = min(
                self.lowest_since_entry,
                last["ha_low"]
            )

            self.trailing_sl = self.lowest_since_entry + (
                self.atr_mult * last["atr"]
            )

            if last["ha_close"] >= self.trailing_sl:

                logger.info("SELL EXIT")
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

            self.stop_loss = (
                last["ha_close"] -
                self.atr_mult * last["atr"]
            )

            self.take_profit = (
                last["ha_close"] +
                self.risk_reward *
                (last["ha_close"] - self.stop_loss)
            )

            option_strike = (
                (last["ha_close"] - self.round_off_diff)
                // self.strike_roundup_value
            ) * self.strike_roundup_value

            logger.info(
                f"CALL BUY ENTRY | price={last['close']} strike={option_strike}"
            )

            return "BUY_ENTRY", self.stop_loss, self.take_profit, option_strike

        # ---------------------------------------------------
        # PUT BUY
        # ---------------------------------------------------

        if short_entry:

            self.last_position = "short"

            self.entry_price = last["ha_close"]

            self.lowest_since_entry = last["ha_low"]

            self.stop_loss = (
                last["ha_close"] +
                self.atr_mult * last["atr"]
            )

            self.take_profit = (
                last["ha_close"] -
                self.risk_reward *
                (self.stop_loss - last["ha_close"])
            )

            option_strike = math.ceil(
                (last["ha_close"] + self.round_off_diff)
                / self.strike_roundup_value
            ) * self.strike_roundup_value

            logger.info(
                f"PUT BUY ENTRY | price={last['close']} strike={option_strike}"
            )

            return "SELL_ENTRY", self.stop_loss, self.take_profit, option_strike

        return None


# -----------------------------------------------------------
# Example Backtest Runner
# -----------------------------------------------------------

if __name__ == "__main__":

    strategy = HeikinAshiATRStrategy()

    # df=pd.read_csv("historical_data_202601091034.csv")

    # # Find midpoint
    # mid = len(df) // 2

    # # Split into two DataFrames
    # df1 = df.iloc[:mid].to_csv("historical_data_1.csv", index=False)
    # df2 = df.iloc[mid:].to_csv("historical_data_2.csv", index=False)

    # Load historical data
    strategy.load_historical_data("historical_data_1.csv")

    # Load simulated live candles
    live_data = pd.read_csv("historical_data_2.csv")

    signals = []

    for _, row in live_data.iterrows():
        # print('row')

        new_data = {
            "timestamp": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row.get("volume", 0)
        }

        # Add new candle
        strategy.add_live_data(new_data)

        # Generate signal
        signal = strategy.generate_signal()
        print('signal', signal)

        if signal:
            print("Signal:", signal)

            row_dict = strategy.df.iloc[-1].to_dict()
            row_dict["signal"] = signal

            signals.append(row_dict)

    if signals:
        pd.DataFrame(signals).to_csv("signals.csv", index=False)