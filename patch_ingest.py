import re

with open("live_market_daemon.py", "r") as f:
    content = f.read()

# We need to add candle status, completeness, freshness logic
ingest_block_old = """
                self.cached_market_data[sym] = {
                    "price": current_price,
                    "high": high_price,
                    "atr14": atr14,
                    "ema5": ema5,
                    "ema8": ema8,
                    "ema13": ema13,
                    "prev_ema5": prev_ema5,
                    "prev_ema13": prev_ema13,
                    "signal": signal_val,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
"""

ingest_block_new = """
                # Candle freshness & completeness validation
                now_ist = get_ist_now()
                candle_time = df.index[-1]
                # If market hasn't closed (15:30 IST), today's candle is developing
                is_developing = now_ist.time() < datetime.time(15, 30) and candle_time.date() == now_ist.date()
                candle_status = "developing" if is_developing else "completed"

                self.cached_market_data[sym] = {
                    "price": current_price,
                    "high": high_price,
                    "atr14": atr14,
                    "ema5": ema5,
                    "ema8": ema8,
                    "ema13": ema13,
                    "prev_ema5": prev_ema5,
                    "prev_ema13": prev_ema13,
                    "signal": signal_val,
                    "candle_status": candle_status,
                    "candle_timestamp": candle_time.isoformat(),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
"""

content = content.replace(ingest_block_old, ingest_block_new)

with open("live_market_daemon.py", "w") as f:
    f.write(content)
