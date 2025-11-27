# Nifties-opt API Integration

This project uses an external API for database operations instead of direct PostgreSQL access.

## Environment Variables

Set your API endpoint and credentials in the `.env` file:

```
API_BASE_URL=https://api.example.com/db
API_KEY=your_api_key_here
```

## Sample API Usage

### Example Endpoint

- **URL:** `https://api.example.com/db/ohlc`
- **Method:** `POST`

#### Request Payload
```json
{
  "token": "25",
  "limit": 500
}
```

#### Response Schema
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


### Other Endpoints
- `/db/ltp` for latest price
- `/db/trend` for trend type
- `/db/nifty-tokens` for fetching the list of Nifty tokens
- `/db/admin/kill-trade-signal` for admin-triggered trade exit signal

#### Example: Admin Trade Exit Signal

- **URL:** `https://api.example.com/db/admin/kill-trade-signal`
- **Method:** `POST`

##### Request Payload
```json
{
  "token": "<token_id>"
}
```

##### Response Schema
```json
{
  "kill": true
}
```

This endpoint is used by the `admin_trade_exit_signal` method in `StrategyTrader` to check if an admin-triggered exit is required for a given token.

#### Example: Fetching Nifty Tokens

- **URL:** `https://api.example.com/db/nifty-tokens`
- **Method:** `GET`

##### Response Schema
```json
{
  "tokens": ["23", "45", "12", ...]
}
```

Use this endpoint to dynamically retrieve the list of tokens for trading.

Adjust the payload and endpoint as needed for your use case.
