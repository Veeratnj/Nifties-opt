
# Configure logging for this strategy file
import math  # For mathematical operations
import pandas as pd  # For data manipulation
import pandas_ta as ta  # For technical analysis indicators

# Set up logging to a separate file for this script
import logging

# Create a named logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create file handler for this logger
file_handler = logging.FileHandler('heikin_ashi_atr_strike.log')
file_handler.setLevel(logging.INFO)

# Create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
file_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(file_handler)

class HeikinAshiATRStrategy:
    def __init__(self,
                 atr_len=14, atr_mult=2.5,
                 rsi_len=14,
                 strike_roundup_value=100,
                 risk_reward=2.0,
                 etf='3min', ltf='5min', htf='15min',
                 token='token None',
                 stock_symbol='symbol None',
                 round_off_diff=100):
        # Initialize strategy parameters
        self.atr_len = atr_len  # ATR window length
        self.atr_mult = atr_mult  # ATR multiplier for stop loss
        self.rsi_len = rsi_len  # RSI window length
        self.risk_reward = risk_reward  # Risk-reward ratio
        self.etf = etf  # Extra time frame (e.g., 3min)
        self.ltf = ltf  # Lower time frame (e.g., 5min)
        self.htf = htf  # Higher time frame (e.g., 15min)
        self.token = token  # Token identifier
        self.stock_symbol = stock_symbol  # Stock symbol
        self.round_off_diff = round_off_diff  # Rounding difference for strike
        self.df = pd.DataFrame()  # DataFrame to hold OHLCV and indicators
        self.last_signal = None  # Last trading signal
        self.last_position = None  # Last position ('long' or 'short')
        self.entry_price = None  # Entry price for current position
        self.stop_loss = None  # Stop loss for current position
        self.take_profit = None  # Take profit for current position
        self.trailing_sl = None  # Trailing stop loss
        self.highest_since_entry = None  # Highest price since entry (for long)
        self.lowest_since_entry = None  # Lowest price since entry (for short)
        self.strike_roundup_value = strike_roundup_value

    def reset_state(self):
        """Reset all position-related state variables to effectively 'cancel' a trade."""
        self.last_position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.trailing_sl = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        logger.info(f"Strategy state reset manually.")

    def update_trailing_stop_loss(self):
        # Update the trailing stop loss based on the latest Heikin-Ashi values
        if self.last_position is None:
            return  # No position, nothing to update

        last = self.df.iloc[-1]  # Get the latest row

        if self.last_position == 'long':
            # For long, trail stop below HA high minus ATR
            new_stop = last['ha_high'] - self.atr_mult * last['atr']
            self.stop_loss = max(self.stop_loss, new_stop)

        elif self.last_position == 'short':
            # For short, trail stop above HA close plus ATR
            new_stop = last['ha_close'] + self.atr_mult * last['atr']
            self.stop_loss = min(self.stop_loss, new_stop)

    def calculate_to_60_minute(self):
        # Calculate rolling 60-minute OHLCV and RSI values
        rolling = self.df.rolling(window=12, min_periods=12)
        self.df['60_min_open']   = rolling['open'].apply(lambda x: x.iloc[0])  # First open in window
        self.df['60_min_high']   = rolling['high'].max()  # Max high in window
        self.df['60_min_low']    = rolling['low'].min()  # Min low in window
        self.df['60_min_close']  = rolling['close'].apply(lambda x: x.iloc[-1])  # Last close in window
        self.df['60_min_volume'] = rolling['volume'].sum()  # Sum of volume
        self.df['60_min_rsi_14'] = ta.rsi(self.df['60_min_close'], length=14).round(2)  # RSI on 60-min close

    def load_historical_data(self, csv_file):
        # Load historical OHLCV data from CSV
        self.df = pd.read_csv(csv_file)
        self.df.rename(columns={"start_time": "timestamp"}, inplace=True)  # Standardize timestamp column
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])  # Parse timestamps
        self.df['timestamp'] = self.df['timestamp'].dt.tz_convert('Asia/Kolkata')  # Convert to IST

        self.df.sort_values(by='timestamp', inplace=True)  # Sort by time
        self.df.reset_index(drop=True, inplace=True)  # Reset index

        # Calculate Heikin Ashi candles
        ha = ta.ha(self.df['open'], self.df['high'], self.df['low'], self.df['close'])
        self.df['ha_open'] = ha['HA_open']
        self.df['ha_high'] = ha['HA_high']
        self.df['ha_low'] = ha['HA_low']
        self.df['ha_close'] = ha['HA_close']

        # ATR computed on Heikin-Ashi candles
        self.df['atr'] = ta.atr(self.df['ha_high'], self.df['ha_low'], self.df['ha_close'], length=self.atr_len).round(6)

        # RSI for LTF (base) computed on HA close
        self.df['rsi_ltf'] = ta.rsi(self.df['ha_close'], length=self.rsi_len).round(2)

        # For HTF and ETF, resample to higher/lower timeframes
        df_temp = self.df.set_index('timestamp')

        # HTF RSI computed on HA close
        rsi_htf = df_temp['ha_close'].resample(self.htf).last()
        rsi_htf = ta.rsi(rsi_htf, length=self.rsi_len)
        rsi_htf = rsi_htf.reindex(self.df['timestamp'], method='ffill')
        self.df['rsi_htf'] = rsi_htf.values

        # ETF RSI computed on HA close
        rsi_etf = df_temp['ha_close'].resample(self.etf).last()
        rsi_etf = ta.rsi(rsi_etf, length=self.rsi_len)
        rsi_etf = rsi_etf.reindex(self.df['timestamp'], method='ffill')
        self.df['rsi_etf'] = rsi_etf.values

        # Mark if each row is within the trading session
        self.df['in_session'] = self.df['timestamp'].dt.time.between(
            pd.to_datetime("09:15").time(),
            pd.to_datetime("15:15").time()
        )

        # Save processed DataFrame for reference
        self.df.to_csv(f'{self.token.replace("|", "_")}.csv', index=False)

    def add_live_data(self, new_data):
        # Add a new live data row to the DataFrame and update indicators
        ts = pd.to_datetime(new_data['timestamp'])  # Parse timestamp
        if ts.tzinfo is None:
            ts = ts.tz_localize('Asia/Kolkata')  # Localize if not already
        else:
            ts = ts.tz_convert('Asia/Kolkata')  # Convert to IST if needed

        # Prepare new row for DataFrame
        new_row = {
            'timestamp': ts,
            'open': new_data['open'],
            'high': new_data['high'],
            'low': new_data['low'],
            'close': new_data['close'],
            'volume': new_data['volume']
        }

        # Append new row
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
        idx = self.df.index[-1]  # Index of new row

        # Update Heikin Ashi candles for all data
        ha = ta.ha(self.df['open'], self.df['high'], self.df['low'], self.df['close'])
        self.df['ha_open'] = ha['HA_open']
        self.df['ha_high'] = ha['HA_high']
        self.df['ha_low'] = ha['HA_low']
        self.df['ha_close'] = ha['HA_close']

        # ATR on HA candles (update only last row)
        atr_series = ta.atr(self.df['ha_high'], self.df['ha_low'], self.df['ha_close'], length=self.atr_len)
        self.df.at[idx, 'atr'] = atr_series.iloc[-1]

        # RSI LTF on HA close (update only last row)
        rsi_series = ta.rsi(self.df['ha_close'], length=self.rsi_len)
        self.df.at[idx, 'rsi_ltf'] = rsi_series.iloc[-1]

        # Update HTF and ETF RSI for last row
        df_temp = self.df.set_index('timestamp')
        rsi_htf = df_temp['ha_close'].resample(self.htf).last()
        rsi_htf = ta.rsi(rsi_htf, length=self.rsi_len)
        rsi_htf_val = rsi_htf.reindex([ts], method='ffill').iloc[0]
        self.df.at[idx, 'rsi_htf'] = rsi_htf_val

        rsi_etf = df_temp['ha_close'].resample(self.etf).last()
        rsi_etf = ta.rsi(rsi_etf, length=self.rsi_len)
        rsi_etf_val = rsi_etf.reindex([ts], method='ffill').iloc[0]
        self.df.at[idx, 'rsi_etf'] = rsi_etf_val

        # Mark if this row is within the trading session
        ts_time = ts.timetz()
        in_session = pd.to_datetime("09:15").time() <= ts_time <= pd.to_datetime("15:15").time()
        self.df.at[idx, 'in_session'] = in_session

    def detect_bos_choch(df: pd.DataFrame, lookback=60):
        # Detect Break of Structure (BOS) and Change of Character (CHOCH) in price action
        df = df.copy()
        df['prev_swing_high'] = df['high'].shift(1).rolling(lookback).max()  # Previous swing high
        df['prev_swing_low'] = df['low'].shift(1).rolling(lookback).min()  # Previous swing low

        df['bos'] = False  # Break of Structure flag
        df['choch'] = False  # Change of Character flag

        trend = None  # Track current trend

        for i in range(lookback + 1, len(df)):
            curr_high = df.at[i, 'high']
            curr_low = df.at[i, 'low']
            prev_high = df.at[i, 'prev_swing_high']
            prev_low = df.at[i, 'prev_swing_low']

            if trend is None:
                # Initialize trend
                if curr_high > prev_high:
                    trend = 'bullish'
                    df.at[i, 'bos'] = True
                elif curr_low < prev_low:
                    trend = 'bearish'
                    df.at[i, 'bos'] = True
            elif trend == 'bullish':
                # Bullish trend: look for BOS or CHOCH
                if curr_high > prev_high:
                    df.at[i, 'bos'] = True 
                elif curr_low < prev_low:
                    df.at[i, 'choch'] = True  
                    trend = 'bearish'
            elif trend == 'bearish':
                # Bearish trend: look for BOS or CHOCH
                if curr_low < prev_low:
                    df.at[i, 'bos'] = True  
                elif curr_high > prev_high:
                    df.at[i, 'choch'] = True  
                    trend = 'bullish'

        return df
    def generate_signal(self):
        # Generate trading signal based on latest data and strategy rules
        if len(self.df) < 2:
            return None  # Not enough data

        last = self.df.iloc[-1]  # Latest row
        prev = self.df.iloc[-2]  # Previous row

        # Update trailing stop and check for exit if in a position
        if self.last_position == 'long':
            # For long, update highest and trailing stop
            self.highest_since_entry = max(self.highest_since_entry, last['ha_high'])
            self.trailing_sl = self.highest_since_entry - self.atr_mult * last['atr']
            exit_long = (
                last['ha_close'] <= self.trailing_sl or  # Price hits trailing stop
                last['ha_close'] >= self.take_profit or  # Price hits target
                last['rsi_ltf'] < 50  # RSI drops below threshold
            )
            if exit_long:
                # Reset all state on exit
                self.last_position = None
                self.entry_price = None
                self.stop_loss = None
                self.take_profit = None
                self.trailing_sl = None
                self.highest_since_entry = None
                logger.info(f"SIGNAL: BUY_EXIT | Time: {last['timestamp']} | Open: {last['open']} | High: {last['high']} | Low: {last['low']} | Close: {last['close']} | HA_Close: {last['ha_close']}")
                return 'BUY_EXIT'

        elif self.last_position == 'short':
            # For short, update lowest and trailing stop
            self.lowest_since_entry = min(self.lowest_since_entry, last['ha_low'])
            self.trailing_sl = self.lowest_since_entry + self.atr_mult * last['atr']
            exit_short = (
                last['ha_close'] >= self.trailing_sl or  # Price hits trailing stop
                last['ha_close'] <= self.take_profit or  # Price hits target
                last['rsi_ltf'] > 50  # RSI rises above threshold
            )
            if exit_short:
                # Reset all state on exit
                self.last_position = None
                self.entry_price = None
                self.stop_loss = None
                self.take_profit = None
                self.trailing_sl = None
                self.lowest_since_entry = None
                logger.info(f"SIGNAL: SELL_EXIT | Time: {last['timestamp']} | Open: {last['open']} | High: {last['high']} | Low: {last['low']} | Close: {last['close']} | HA_Close: {last['ha_close']}")
                return 'SELL_EXIT'

        # --- ENTRY conditions ---
        long_entry = (
            last['ha_close'] > last['ha_open'] and  # Bullish HA candle
            last['rsi_ltf'] > 50 and  # RSI above threshold
            last['rsi_htf'] > 50 and  # HTF RSI above threshold
            last['rsi_etf'] < 58 and  # ETF RSI below upper bound
            self.last_position is None  # Only if flat
        )

        short_entry = (
            last['ha_close'] < last['ha_open'] and  # Bearish HA candle
            last['rsi_ltf'] < 50 and  # RSI below threshold
            last['rsi_htf'] < 50 and  # HTF RSI below threshold
            last['rsi_etf'] > 34 and  # ETF RSI above lower bound
            self.last_position is None  # Only if flat
        )

        if long_entry:
            # Enter long position
            self.last_position = 'long'
            self.entry_price = last['ha_close']
            self.highest_since_entry = last['ha_high']
            self.stop_loss = last['ha_close'] - self.atr_mult * last['atr']
            self.take_profit = last['ha_close'] + self.risk_reward * (last['ha_close'] - self.stop_loss)
            option_strike = ((last['ha_close'] - self.round_off_diff) // 100) * 100  # Round down to nearest strike_value
            print('long',last['ha_close'],option_strike)
            logger.info(f"SIGNAL: BUY_ENTRY | Time: {last['timestamp']} | Open: {last['open']} | High: {last['high']} | Low: {last['low']} | Close: {last['close']} | HA_Close: {last['ha_close']} | SL: {self.stop_loss} | TP: {self.take_profit} | Strike: {option_strike}")
            return 'BUY_ENTRY', self.stop_loss, self.take_profit, option_strike

        elif short_entry:
            # Enter short position
            self.last_position = 'short'
            self.entry_price = last['ha_close']
            self.lowest_since_entry = last['ha_low']
            self.stop_loss = last['ha_close'] + self.atr_mult * last['atr']
            self.take_profit = last['ha_close'] - self.risk_reward * (self.stop_loss - last['ha_close'])
            option_strike = math.ceil((last['ha_close'] + self.round_off_diff) / 100) * 100  # Round up to nearest strike_roundup_value
            print('short',last['ha_close'],option_strike)
            logger.info(f"SIGNAL: SELL_ENTRY | Time: {last['timestamp']} | Open: {last['open']} | High: {last['high']} | Low: {last['low']} | Close: {last['close']} | HA_Close: {last['ha_close']} | SL: {self.stop_loss} | TP: {self.take_profit} | Strike: {option_strike}")
            return 'SELL_ENTRY', self.stop_loss, self.take_profit, option_strike

        return None  # No signal


if __name__ == "__main__":
    # Example usage: run strategy on historical and simulated live data
    strategy = HeikinAshiATRStrategy(token="Nifty", stock_symbol="Nifty50")  # Initialize strategy
    # strategy.load_historical_data('old_3min.csv')  # Load historical data
    strategy.load_historical_data(r'split_output/output_part_1.csv')  # Load historical data

    signals_data = []  # Store signals for later analysis

    # Simulate live data addition from new_3min.csv
    live_data = pd.read_csv(r'split_output/output_part_2.csv')
    for index, row in live_data.iterrows():
        # Prepare new data row for each tick
        new_data = {
            'timestamp': row['start_time'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': 1  # Dummy volume
        }
        strategy.add_live_data(new_data)  # Add to strategy
        signal = strategy.generate_signal()  # Generate signal
        if signal:
            # Store signal and row data
            row_dict = strategy.df.iloc[-1].to_dict()
            row_dict['signal'] = signal
            signals_data.append(row_dict)
            print(f"Signal: {signal}")

    # Save all signals to CSV if any were generated
    if signals_data:
        pd.DataFrame(signals_data).to_csv('signals.csv', index=False)

