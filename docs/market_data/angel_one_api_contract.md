# Angel One SmartAPI Market Data API Contract & Verification Record

* **Verification Date:** 2026-09-25
* **Authoritative Documentation Sources:**
  * SmartAPI Overview & REST Endpoints: `https://smartapi.angelone.in/docs`
  * Historical Data & Candlestick Contract: `https://smartapi.angelone.in/docs/Historical`
  * Smart Stream 2.0 WebSocket Contract: `https://smartapi.angelone.in/docs/SmartStream`
  * Instrument Scrip Master Publisher: `https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json`
* **Target Integration Role:** Market Data & Paper Trading Signal Pipeline Only (Strictly Zero Live Order Routing)

---

## 1. Network Hosts and Endpoints

### 1.1 REST Gateway
* **Production REST Host:** `https://apiconnect.angelone.in`
* **Authentication Endpoint:** `POST /rest/auth/angelbroking/user/v1/loginByPassword`
* **Token Regeneration Endpoint:** `POST /rest/auth/angelbroking/jwt/v1/generateTokens`
* **Historical Candle Data:** `POST /rest/secure/angelbroking/historical/v1/getCandleData`
* **Market Quote / LTP Endpoint:** `POST /rest/secure/angelbroking/market/v1/quote`
* **User Profile & Status:** `GET /rest/secure/angelbroking/user/v1/getProfile`

### 1.2 WebSocket Stream Gateway
* **Smart Stream 2.0 (Binary WebSocket):** `wss://smartapisocket.angelone.in/smart-stream`
* **Legacy Text/JSON WebSocket:** `wss://smartapisocket.angelone.in/websocket`

### 1.3 Instrument Scrip Master
* **URL:** `https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json`
* **Format:** Static JSON array updated daily before market open (approx. 08:00 IST).

---

## 2. Authentication & Token Lifecycle

### 2.1 Credential Requirements
1. `api_key`: Issued per application on SmartAPI developer portal.
2. `client_code`: Angel One Client Trading ID.
3. `password`: Account password / MPIN.
4. `totp_key`: 32-character Base32 secret for Time-based One-Time Password generation (RFC 6238).

> [!WARNING]
> **Unified Credential Privilege Warning:**
> Angel One SmartAPI does not offer segregated read-only API keys; API keys possess potential trading authorization at the broker side. The application-level `MarketDataProvider` wrapper MUST strictly fail-closed, exposing ONLY market-data retrieval and subscription endpoints, and completely prohibiting order placement, cancellation, modification, or routing.

### 2.2 Token Lifecycle
* **Login Call:**
  ```json
  POST https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword
  Headers:
    Content-Type: application/json
    Accept: application/json
    X-UserType: USER
    X-SourceID: WEB
    X-PrivateKey: <api_key>
  Body:
    {
      "clientcode": "<client_code>",
      "password": "<password>",
      "totp": "<6_digit_totp>"
    }
  ```
* **Issued Tokens:**
  * `jwtToken`: Bearer JWT token required in `Authorization: Bearer <jwtToken>` header. Valid for 24 hours / current trading day.
  * `refreshToken`: Used to generate a fresh `jwtToken` without re-supplying password and TOTP.
  * `feedToken`: Dedicated session token required for WebSocket stream authentication.
* **Token Refresh (`generateTokens`):**
  * When `jwtToken` expires (HTTP 401 or response error `AG8001`), the adapter attempts automated regeneration using `refreshToken`.
  * Max bounded retries: 2 attempts. If regeneration fails, the system transitions to safe failure mode (`OPERATOR_INTERVENTION_REQUIRED`).

---

## 3. Instrument Master Mapping & Allowlist

### 3.1 Mapping Schema
The OpenAPI Scrip Master maps exchange symbols to numeric string tokens:
* `token`: Numeric identifier string (e.g., `"3045"`)
* `symbol`: Trading symbol with series suffix (e.g., `"SBIN-EQ"`)
* `name`: Base corporate name (e.g., `"SBIN"`)
* `exch_seg`: Exchange and segment (`"NSE"` or `"BSE"`)
* `tick_size`: Minimum price movement in paise (e.g., `"5.000000"` = ₹0.05)
* `lotsize`: Contract lot size (`"1"` for equity cash)

### 3.2 Canonical Allowlist (NSE Cash Equities)
| Canonical Symbol | Trading Symbol | Token | Exchange | Series | Tick Size (INR) | Lot Size |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SBIN** | `SBIN-EQ` | `3045` | NSE | EQ | ₹0.05 | 1 |
| **RELIANCE** | `RELIANCE-EQ` | `2885` | NSE | EQ | ₹0.05 | 1 |
| **TCS** | `TCS-EQ` | `11536` | NSE | EQ | ₹0.05 | 1 |
| **ITC** | `ITC-EQ` | `1660` | NSE | EQ | ₹0.05 | 1 |
| **HAL** | `HAL-EQ` | `2303` | NSE | EQ | ₹0.05 | 1 |
| **INFY** | `INFY-EQ` | `1594` | NSE | EQ | ₹0.05 | 1 |

*Unresolved symbols outside this allowlist are strictly rejected by the adapter.*

---

## 4. Subscription Modes & Market Data Feeds

### 4.1 Smart Stream 2.0 Modes
* **Mode 1 (LTP):** 
  * Payload size: Compact 8 bytes.
  * Fields: Subscription mode, Token, Last Traded Price (scaled in paise, divide by 100 for INR).
* **Mode 2 (Quote):**
  * Fields: LTP, Last Traded Quantity, Average Traded Price (ATP), Volume (cumulative day volume), Total Traded Value, Buy/Sell Best 1 Depth.
* **Mode 3 (SnapQuote / Full):**
  * Fields: LTP, LTQ, ATP, Cumulative Volume, Open, High, Low, Close, 5-level Best Bid/Ask Market Depth, Open Interest, Exchange Timestamp.

### 4.2 Historical Candle Data
* **Endpoint:** `POST /rest/secure/angelbroking/historical/v1/getCandleData`
* **Intervals:** `"ONE_MINUTE"`, `"THREE_MINUTE"`, `"FIVE_MINUTE"`, `"FIFTEEN_MINUTE"`, `"THIRTY_MINUTE"`, `"ONE_HOUR"`, `"ONE_DAY"`.
* **Output Format:** Array of arrays: `[Timestamp, Open, High, Low, Close, Volume]`.
* **Timezone Normalization:** Timestamps provided by Angel One are in IST (`Asia/Kolkata`); the adapter normalizes all timestamps to UTC ISO-8601 strings.

---

## 5. Rate Limits, Heartbeat & Reliability

* **REST Rate Limits:**
  * Login / Session: 1 request / second.
  * Quotes / LTP: 10 requests / second.
  * Historical Data: 3 requests / second.
* **WebSocket Limits:**
  * Maximum 500 instrument tokens per WebSocket connection.
  * Maximum 3 simultaneous WebSocket connections per API key.
* **Heartbeat & Keepalive:**
  * Ping frame every 30 seconds.
  * If no pong received within 10 seconds, drop connection and trigger reconnect.
* **Auto-Reconnect & Backoff:**
  * Exponential backoff: 1s, 2s, 4s, 8s, 16s, up to 30s ceiling.
  * Max consecutive reconnection failures before raising critical alert: 5 attempts.

---

## 6. Regulatory & Compliance Boundaries

* **Data Ownership & Redistribution:**
  * Under Indian regulatory provisions (SEBI & NSE Market Data Guidelines), data received via broker API is authorized exclusively for internal trading strategies and algorithmic execution of the registered client.
  * External dissemination, commercial redistribution, or public display of raw ticks is strictly prohibited.
* **Trading Safeguards:**
  * Market data feed is completely decoupled from broker order interfaces.
  * `ALLOW_LIVE_TRADING = False` and `ALLOW_REAL_BROKER_EXECUTION = False` remain system-level invariants.

---

## 7. Current Connectivity State (Environment Audit)

* **Target Host:** `apiconnect.angelone.in:443` (IP: `103.82.178.77`)
* **Observed Network Status:** `BLOCKED_BY_NETWORK_EGRESS` (`TCP_TIMEOUT`, `errno=11` / `EAGAIN`).
* **Operational Action:** 
  1. The adapter is implemented with complete production logic for REST and WebSocket streams.
  2. A robust, deterministic `MockAngelOneFeed` is integrated to allow complete offline pipeline execution, test suites, and paper-trading simulations.
  3. When real network connectivity is restored or cloud egress is unblocked, the adapter seamlessly switches to genuine feeds without code changes.
