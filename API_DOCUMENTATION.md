# Nifties API Documentation

This document outlines all the API endpoints required by the `Main.py` trading application.

**Base URL**: `http://localhost:8000/db` (configurable via `API_BASE_URL` environment variable)

**Authentication**: Bearer Token (configured via `API_KEY` environment variable)

---

## 1. Admin Kill Trade Signal

Check if a trade should be force-exited for a specific token.

### Endpoint

```
POST /admin/kill-trade-signal
```

### Headers

```
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

### Request Payload

```json
{
  "token": "99926009"
}
```

### Response

```json
{
  "kill": true
}
```

**Response Fields**:

- `kill` (boolean): `true` if the trade should be force-exited, `false` otherwise

---

## 2. Get Nifty Tokens

Fetch the list of Nifty tokens available for trading.

### Endpoint

```
GET /nifty-tokens
```

### Headers

```
Authorization: Bearer {API_KEY}
```

### Request Payload

None (GET request)

### Response

```json
{
  "tokens": ["99926009", "99926000", "99926037"]
}
```

**Response Fields**:

- `tokens` (array of strings): List of token identifiers

---

## 3. Fetch OHLC Data

Retrieve OHLC (Open, High, Low, Close) candlestick data for a specific token.

### Endpoint

```
POST /ohlc
```

### Headers

```
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

### Request Payload

```json
{
  "token": "99926009",
  "limit": 1
}
```

**Payload Fields**:

- `token` (string, required): The token identifier
- `limit` (integer, required): Number of candles to fetch (1 for latest, 500 for historical)

### Response

```json
{
  "data": [
    {
      "start_time": "2025-11-25 09:15:00",
      "open": "24500.50",
      "high": "24525.75",
      "low": "24490.25",
      "close": "24510.00"
    },
    {
      "start_time": "2025-11-25 09:16:00",
      "open": "24510.00",
      "high": "24535.50",
      "low": "24505.00",
      "close": "24520.25"
    }
  ]
}
```

**Response Fields**:

- `data` (array): List of OHLC candles
  - `start_time` (string): Candle start timestamp
  - `open` (string): Opening price
  - `high` (string): Highest price
  - `low` (string): Lowest price
  - `close` (string): Closing price

**Usage**:

- Latest candle: `limit=1`
- Historical data: `limit=500`

---

## 4. Fetch Latest LTP

Get the Latest Traded Price (LTP) for a specific stock token.

### Endpoint

```
POST /ltp
```

### Headers

```
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

### Request Payload

```json
{
  "stock_token": "99926009"
}
```

**Payload Fields**:

- `stock_token` (string, required): The stock token identifier

### Response

```json
{
  "data": {
    "last_update": "2025-11-25 14:30:45",
    "ltp": 24515.75
  }
}
```

**Response Fields**:

- `data` (object):
  - `last_update` (string): Timestamp of the last price update
  - `ltp` (float): Latest traded price

---

## 5. Fetch Stock Trend

Retrieve the current trend type for a stock.

### Endpoint

```
POST /trend
```

### Headers

```
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

### Request Payload

```json
{
  "stock_token": "99926009"
}
```

**Payload Fields**:

- `stock_token` (string, required): The stock token identifier

### Response

```json
{
  "data": {
    "trend_type": "BULLISH"
  }
}
```

**Response Fields**:

- `data` (object):
  - `trend_type` (string): Current trend type (e.g., "BULLISH", "BEARISH", "NEUTRAL")

---

## Environment Variables

The following environment variables must be configured in your `.env` file:

```env
API_BASE_URL=http://localhost:8000/db
API_KEY=your_api_key_here
```

---

## Error Handling

All API endpoints may return the following error responses:

### 401 Unauthorized

```json
{
  "error": "Invalid or missing API key"
}
```

### 500 Internal Server Error

```json
{
  "error": "Internal server error",
  "message": "Detailed error message"
}
```

### 404 Not Found

```json
{
  "error": "Endpoint not found"
}
```

---

## API Client Implementation

The `ApiDatabaseClient` class in `Main.py` implements these API calls using the `requests` library with session-based authentication.

**Example Usage**:

```python
from dotenv import load_dotenv
import os

# Initialize client
api_client = ApiDatabaseClient()

# Fetch tokens
tokens = api_client.get_nifties_token()

# Fetch OHLC data
ohlc_data = api_client.fetch_ohlc(token="99926009", limit=1)

# Fetch latest LTP
timestamp, ltp = api_client.fetch_latest_ltp(stock_token="99926009")

# Check kill trade signal
should_exit = api_client.kill_trade_signal(token="99926009")

# Fetch stock trend
trend = api_client.fetch_stock_trend(stock_token="99926009")
```


sample_payload = {
  "token": "string",
  "signal": "string",
  "unique_id": "string",
  "strategy_code": "string",
  "strike_data": {
      "token": 35000, # Automatically converted to "35000"
      "exchange": "OPTIDX",
      "index_name": "BANKNIFTY",
      "DOE": "2025-12-30 00:00:00",
      "strike_price": 69700.0,
      "position": "CE",
      "symbol": "BANKNIFTY-Dec2025-69700-CE"
  }
}