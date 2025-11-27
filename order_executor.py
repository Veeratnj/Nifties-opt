import json
import time
import requests
from datetime import datetime
from dhanhq import dhanhq, DhanContext
import os
from dotenv import load_dotenv
load_dotenv()
# --- Load credentials ---
def load_credentials(path='creds.json'):
    with open(path, 'r') as file:
        return json.load(file)

user_creds = load_credentials()
user_ids = [2,11,12,13,14,]


# API_BASE = os.getenv('API_URL') 
# print(f"API_BASE: {API_BASE}")
time.sleep(5)
API_BASE = 'https://localhost:8000'  

# --- Generate custom order ID ---
def generate_order_id(user_id: int, token: str, side: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{user_id}_{token}_{side.upper()}_{timestamp}"

# --- Call /trade/open API ---
def post_to_open_trade_api(order_data: dict):
    try:
        res = requests.post(f"{API_BASE}/standalone/option/trade/open", json=order_data)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# --- Call /trade/close API ---
def post_to_close_trade_api(order_data: dict):
    try:
        res = requests.post(f"{API_BASE}/standalone/option/trade/close", json=order_data)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# --- Main Order Function ---
def order_function(transaction_type: str, token: str, ltp: float = 0.0, option_symbol: str = 'BANKNIFTYXXX',position:str=None):
    """
    Places Dhan orders and logs trades to FastAPI backend.

    Args:
        transaction_type (str): 'entry' for BUY, anything else for SELL
        token (str): Security token for the option
        ltp (float): Last traded price to be saved in trade log
        option_symbol (str): Option symbol like BANKNIFTY24AUG48000CE

    Returns:
        list: Response log for each user
    """
    results = []

    for user_id in user_ids:
        user_dict = user_creds[str(user_id)]
        dhan_context = DhanContext(
            user_dict['dhan_creds']['client_id'],
            user_dict['dhan_creds']['access_token']
        )
        dhan = dhanhq(dhan_context)

        custom_order_id = generate_order_id(user_id, token, transaction_type)

        try:
            # --- Place order with Dhan ---
            res = dhan.place_order(
                security_id=token,
                exchange_segment=dhan.NSE_FNO,
                transaction_type=dhan.BUY if transaction_type.lower() == 'entry' else dhan.SELL,
                quantity=35,
                order_type=dhan.MARKET,
                product_type=dhan.INTRA,
                price=0,
            )

            # --- Send to local trade API ---
            now = datetime.now().isoformat()

            if transaction_type.lower() == 'entry':
                open_payload = {
                    "order_id": custom_order_id,
                    "option_symbol": option_symbol,
                    "option_type": "CE" if "CE" == position.upper() else "PE",
                    "trade_type": "BUY",
                    "quantity": 35,
                    "entry_ltp": ltp,
                    "trade_entry_time": now
                }
                api_res = post_to_open_trade_api(open_payload)
            else:
                close_payload = {
                    "user_id": user_id,
                    "exit_ltp": ltp,
                    "trade_exit_time": now,
                }
                print(close_payload)
                api_res = post_to_close_trade_api(close_payload)

            log_entry = {
                "user_id": user_id,
                "status": "success",
                "custom_order_id": custom_order_id,
                "dhan_response": res,
                "trade_api": api_res,
            }

        except Exception as e:
            log_entry = {
                "user_id": user_id,
                "status": "failed",
                "custom_order_id": custom_order_id,
                "error": str(e)
            }

        results.append(log_entry)
        with open('dhan_response.txt', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    return results

# --- Script Entry Point ---
if __name__ == '__main__':
    response = order_function(
        transaction_type='entry',
        token='54033',
        ltp=500.0,
        option_symbol='BANKNIFTY24AUG48000CE',
        position='CE'
    )
    print(json.dumps(response, indent=2))
