# API Documentation: Nifties-opt Trading Bot

This document describes all API endpoints used by the Nifties-opt trading system, including request/response formats, authentication, and usage notes.

---

## Authentication
- All endpoints require an API key.
- Pass the API key in the `Authorization` header as: `Bearer <API_KEY>`

---

## Endpoints

### 1. Get Nifty Tokens
- **Endpoint:** `/db/nifty-tokens`
- **Method:** `GET`
- **Description:** Fetches the list of available Nifty tokens for trading.
- **Sample Response:**
  ```json
  {
    "tokens": ["23", "45", "12", ...]
  }
  ```

---

### 2. Fetch OHLC Data
- **Endpoint:** `/db/ohlc`
- **Method:** `POST`
- **Description:** Fetches OHLC (Open, High, Low, Close) data for a given token.
- **Request Body:**
  ```json
  {
    "token": "25",
    "limit": 500
  }
  ```
- **Sample Response:**
  ```json
  {
    "status": "success",
    "data": [
      {
        "start_time": "2025-11-21T09:15:00",
        "open": 48000.0,
        "high": 48100.0,
        "low": 47900.0,
        "close": 48050.0
      }
      // ... more rows ...
    ]
  }
  ```

---

### 3. Fetch Latest LTP
- **Endpoint:** `/db/ltp`
- **Method:** `POST`
- **Description:** Fetches the latest Last Traded Price (LTP) for a given stock token.
- **Request Body:**
  ```json
  {
    "stock_token": "99926009"
  }
  ```
- **Sample Response:**
  ```json
  {
    "data": {
      "last_update": "2025-11-21T14:30:00",
      "ltp": 48055.0
    }
  }
  ```

---

### 4. Fetch Stock Trend
- **Endpoint:** `/db/trend`
- **Method:** `POST`
- **Description:** Fetches the current trend type for a given stock token.
- **Request Body:**
  ```json
  {
    "stock_token": "99926009"
  }
  ```
- **Sample Response:**
  ```json
  {
    "data": {
      "trend_type": "bullish"
    }
  }
  ```

---

### 5. Admin Kill Trade Signal
- **Endpoint:** `/db/admin/kill-trade-signal`
- **Method:** `POST`
- **Description:** Checks if an admin-triggered exit is required for a given token. Used for force-closing trades.
- **Request Body:**
  ```json
  {
    "token": "<token_id>"
  }
  ```
- **Sample Response:**
  ```json
  {
    "kill": true
  }
  ```

---

## Error Handling
- All endpoints return standard HTTP status codes.
- On error, the response will include an error message:
  ```json
  {
    "status": "error",
    "message": "Description of the error."
  }
  ```

---

## Notes
- All timestamps are in ISO 8601 format and IST timezone unless specified.
- Ensure your `.env` file contains the correct `API_BASE_URL` and `API_KEY`.
- For more usage examples, see `README.md`.
