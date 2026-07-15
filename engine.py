import asyncio
import sys
import os
import json
import logging
import statistics
import math
import csv
from collections import deque
import pandas as pd
import numpy as np
import re  
from aiohttp import web        
import aiohttp_cors 
import io  # Added for safe text wrapping

# ==============================================================================
# 1. CRITICAL: Stable Event Loop Policy for Windows Executables
# ==============================================================================
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==============================================================================
# 2. FRESH BOOT FILE INITIALIZATION (Pops up files cleanly next to your .exe)
# ==============================================================================
# Wipes old files entirely on a brand new boot so your folder stays pristine
for log_file in ["bot_log.txt", "bot_error.txt"]:
    if os.path.exists(log_file):
        try: os.remove(log_file)
        except Exception: pass

# Pre-create fresh, empty files side-by-side with the running executable
with open("bot_log.txt", "w", encoding="utf-8") as f: f.write("")
with open("bot_error.txt", "w", encoding="utf-8") as f: f.write("")

# ==============================================================================
# 3. BUNDLE-SAFE PATHS & CONDITIONAL TERMINAL SWITCH
# ==============================================================================
is_exe = getattr(sys, 'frozen', False)

if is_exe:
    base_path = os.path.join(sys._MEIPASS, "pocketoptionapi_async")
    
    # EXE MODE: Safely sink raw/unhandled terminal text into a UTF-8 compliant void
    # This prevents the background 'charmap' codec crash entirely when libraries bypass logging.
    sys.stdout = open(os.devnull, 'w', encoding='utf-8', errors='replace')
    sys.stderr = open(os.devnull, 'w', encoding='utf-8', errors='replace')
else:
    base_path = os.path.join(os.getcwd(), "pocketoptionapi_async")

    # TERMINAL MODE: Standard stdout/stderr are preserved so you see direct data!

if base_path not in sys.path:
    sys.path.append(base_path)

from pocketoptionapi_async import AsyncPocketOptionClient, OrderDirection
from pocketoptionapi_async.constants import ASSETS

# ==============================================================================
# 4. IMMACULATE TABULAR LOGGING MATRIX (Dynamic Dev vs. Production)
# ==============================================================================
log_formatter = logging.Formatter('%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Wipe out any default chaotic logs that PyInstaller tries to attach
while root_logger.handlers:
    root_logger.removeHandler(root_logger.handlers)

if is_exe:
    # --- PRODUCTION EXE LOGGING SHIELD ---
    # A. Setup the Main Detailed Log Handler
    stdout_handler = logging.FileHandler("bot_log.txt", encoding="utf-8", delay=False)
    stdout_handler.setFormatter(log_formatter)
    stdout_handler.setLevel(logging.INFO)
    root_logger.addHandler(stdout_handler)

    # B. Setup the Tidy Error File (Stays 0 bytes until a real code failure occurs)
    stderr_handler = logging.FileHandler("bot_error.txt", encoding="utf-8", delay=False)
    stderr_handler.setFormatter(log_formatter)
    stderr_handler.setLevel(logging.WARNING)  
    root_logger.addHandler(stderr_handler)
else:
    # --- LIVE DEVELOPMENT TERMINAL MODE ---
    # Stream safely to console using an explicit UTF-8 wrapper to prevent charmap crashes
    safe_stdout = io.TextIOWrapper(sys.__stdout__.buffer, encoding='utf-8', errors='replace')
    console_handler = logging.StreamHandler(safe_stdout)  
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # Also write to bot_log.txt/bot_error.txt in terminal mode -- previously
    # only the exe build wrote to file, so this file stayed empty when run
    # via `python engine.py` even though the bot was clearly logging (to
    # the console). Both modes now get console output AND the same files,
    # so bot_log.txt can be pasted directly instead of copying from terminal.
    file_handler = logging.FileHandler("bot_log.txt", encoding="utf-8", delay=False)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    err_file_handler = logging.FileHandler("bot_error.txt", encoding="utf-8", delay=False)
    err_file_handler.setFormatter(log_formatter)
    err_file_handler.setLevel(logging.WARNING)
    root_logger.addHandler(err_file_handler)

# C. MUTE BACKGROUND NETWORK SPAM
logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# Suppress pocketoptionapi_async library internals from log files.
# The library logs every websocket message, send, receive, and process
# step at DEBUG/INFO level — useful for deep debugging but pure noise
# for normal operation. WARNING and above still comes through so genuine
# library errors are never hidden.
logging.getLogger("pocketoptionapi_async").setLevel(logging.WARNING)
logging.getLogger("pocketoptionapi_async.websocket_client").setLevel(logging.WARNING)
logging.getLogger("pocketoptionapi_async.client").setLevel(logging.WARNING)
logging.getLogger("pocketoptionapi_async.connection_keep_alive").setLevel(logging.WARNING)

logging.info("🚀 EXECUTIVE EXECUTABLE ENGINE ONLINE & IMMACULATELY FORMATTED.")

# --- 4. REPAIRED INITIAL STATE (Live Standby) ---
state = {
    "client": None, 
    "is_running": True,           # FIXED: Set to True so UI shows READY instead of BOT STOPPED
    "is_paused": False, 
    "manual_pause": False,        # Set by UI PAUSE button — never overridden by auto logic
    "multipliers": [1.0] * 10,    # Updated to 10 slots to match UI boxes
    "base_amount": 1.0, 
    "current_stake": 1.0, 
    "current_step": 0, 
    "duration": 5,                 # Trade expiry — always matches chart_tf, since the
                                    # spec calls for the same expiry as the active timeframe
    "chart_tf": 5,                 # The ONE active timeframe, set from the UI — any
                                    # positive number of seconds is accepted, no
                                    # restriction to a fixed list. Only this one is watched;
                                    # switching it is the same idea as switching asset.
    "is_trading": False,
    "daily_profit": 0.0, 
    "daily_goal": 50.0,
    "funds_to_risk": 400.0, 
    "last_bar_time": 0, 
    "ssid": "", 
    "alerts": [], 
    "payout": 0,                  # Block trading until WebSocket delivers real payout data
    "min_payout": 90,
    "content_payout": None,       # Content script's own scraped-vs-websocket decision
    "content_payout_time": 0,     # When content_payout was last reported, for freshness checks
    "active_asset": "EURUSD_otc",
    "last_trade": {"asset": "EURUSD_otc", "status": "WAITING"},
    
    # =========================================================================
    # REAL-TIME INFRASTRUCTURE STORAGE INJECTIONS
    # =========================================================================
    "bar_tracker": {},            # Per-asset bar aggregation for the ONE active
                                   # timeframe (chart_tf) — see on_live_tick()
    "last_processed_bar": {},     # Per asset — the start-time of the last bar
                                   # this engine already evaluated, so a closed
                                   # bar is only ever checked once, not
                                   # re-checked on every loop tick
    "last_clock_skip_log": 0,     # Track timestamp signatures for clock protection
    "consecutive_losses": 0,      # Live count of consecutive confirmed losses (reset on win)
    "last_trade_time": 0,         # Shared cooldown timer — set by both the automated
                                   # loop and the manual TRADE action so the two can't
                                   # fire overlapping trades within the same window
    # =========================================================================
}

# The only valid values chart_tf can be set to — matches the spec's list of
# timeframes this bot needs to support: 5s, 10s, 15s, 30s, 1min.
# The only valid values chart_tf can be set to — matches the FULL spec list:
# S5, S10, S15, S30, M1, M2, M3 (in seconds: 5, 10, 15, 30, 60, 120, 180).
# Previously only had 5 of these 7 — M2 and M3 were silently unsupported.
# No fixed list of "valid" timeframes — PocketOption's actual range (and
# any future changes to it) shouldn't need to be hand-maintained here.
# Any positive whole number of seconds is accepted; the only real check is
# that it's a sane positive number, not a specific enumerated set.
def is_valid_timeframe(tf):
    return isinstance(tf, int) and tf > 0



# --- 5. MASTER UNIVERSAL ASSET CLEANER ---
def format_asset(raw_asset):
    raw_str = str(raw_asset).upper().strip()
    is_otc = "OTC" in raw_str
    
    # Strip non-alphanumeric (removes /, spaces, brackets etc.)
    clean_key = re.sub(r'[^A-Z0-9]', '', raw_str.replace("OTC", ""))

    # THE DYNAMIC REGISTRY (Corrected for PO 2026)
    REGISTRY = {
        "KES": "KESUSD_otc",
        "KESUSD": "KESUSD_otc", 
        "NGN": "NGNUSD_otc",
        "NGNUSD": "NGNUSD_otc",
        "ZAR": "ZARUSD_otc",
        "ZARUSD": "ZARUSD_otc",
        "UAH": "UAHUSD_otc",
        "UAHUSD": "UAHUSD_otc",
        "CNY": "USDCNY_otc",
        "TRY": "USDTRY_otc",
        "RUB": "USDRUB_otc",
        "HUF": "EURHUF_otc",
        "NOK": "CHFNOK_otc",
        "GOLD": "XAUUSD_otc" if is_otc else "XAUUSD",
        "SILVER": "XAGUSD",
        "BTC": "BTCUSD",
        "BTCUSD": "BTCUSD_otc" if is_otc else "BTCUSD",
        "BITCOIN": "BTCUSD_otc",
        "US100": "US100_otc" if is_otc else "US100",
        "SP500": "SP500_otc" if is_otc else "SP500"
    }

    # 1. Check for specific registry match (Prevents AEDCNY -> USDCNY hijack)
    if clean_key in REGISTRY:
        return REGISTRY[clean_key]

    # 2. Fallback to standard PO suffix format
    if is_otc:
        return f"{clean_key}_otc"
    
    return clean_key

import time 

def detect_demo_from_ssid(raw_ssid: str) -> bool:
    """
    Reads the actual isDemo value out of the pasted SSID string itself —
    the same value the login handshake in client.py already honors —
    instead of engine.py using a fixed, disconnected value of its own.

    This is what closes the gap between "what account we're logged into"
    (decided by the pasted SSID) and "what mode we tell the client to use
    for trading" (previously always hardcoded True here, regardless of
    what was actually pasted).

    Defaults to True (demo) if the field can't be found at all, since
    that's the safer failure mode.
    """
    try:
        match = re.search(r'"isDemo"\s*:\s*(true|false|1|0)', str(raw_ssid), re.IGNORECASE)
        if match:
            val = match.group(1).lower()
            return val in ("1", "true")
    except Exception:
        pass
    return True  # Safe default when the field is missing/unparseable


async def connection_monitor():
    """Background task to ensure the API stays connected while running."""
    consecutive_dead_ticks = 0
    
    while True:
        try:
            if state.get("is_running") and state.get("client"):
                client = state["client"]
                
                # --- INJECTED CONCURRENCY SHIELD ---
                # Check if the library itself is already running its own automatic reconnect loop
                # This explicitly avoids knocking down a newly processing connection socket thread!
                is_reconnecting = getattr(client, '_reconnect_task', None) is not None
                if is_reconnecting:
                    consecutive_dead_ticks = 0
                    await asyncio.sleep(20)
                    continue
                # -----------------------------------

                # --- FIXED: Track stream time instead of market payout state ---
                # Check how many seconds have passed since the stream last updated us
                last_update = state.get("last_stream_time", time.time())
                stream_stalled = (time.time() - last_update) > 40  # Stalled if quiet for 40s
                
                if client.is_connected and stream_stalled:
                    consecutive_dead_ticks += 1
                else:
                    consecutive_dead_ticks = 0

                # Reconnect if library reports disconnected OR stream ticks drop hard
                if not client.is_connected or consecutive_dead_ticks >= 3:
                    logging.warning("📡 Connection lost or WebSocket stalled. Attempting reconnect...")
                    consecutive_dead_ticks = 0  
                    
                    await client.connect()
                    # Reset stream timer on fresh connection success
                    state["last_stream_time"] = time.time()
                    logging.info("✅ Reconnected successfully.")

                    # Wait for server to complete its own session setup after
                    # authentication. connect() returns as soon as auth is
                    # confirmed, but the server needs a moment to finish its
                    # internal handshake before it can process a changeSymbol
                    # subscription request. Firing immediately causes the
                    # changeSymbol to be silently ignored, leaving bar_tracker
                    # empty and the bot trading blind.
                    await asyncio.sleep(3.0)

                    # Item 13: Re-subscribe to the active asset stream after
                    # every reconnect. The library restores the raw connection
                    # but does NOT re-call subscribe_symbol_stream automatically,
                    # so bar_tracker stops updating until either a manual Sync
                    # from the UI or this auto-resubscribe fires.
                    active_asset = state.get("active_asset")
                    chart_tf     = state.get("chart_tf", 5)
                    if active_asset and state.get("is_running"):
                        for attempt in range(1, 3):  # try up to 2 times
                            try:
                                await client.subscribe_symbol_stream(active_asset, chart_tf, on_live_tick)
                                logging.info(f"📡 AUTO-RESUBSCRIBED: {active_asset} ({chart_tf}s) after reconnect (attempt {attempt}).")
                                break
                            except Exception as sub_err:
                                logging.error(f"⚠️ Auto-resubscribe attempt {attempt} failed: {sub_err}")
                                if attempt < 2:
                                    await asyncio.sleep(2.0)  # wait before retry
        except Exception as e:
            logging.error(f"❌ Connection monitor encountered error: {str(e)}")
        
        await asyncio.sleep(20)


async def payout_monitor():
    global state
    while True:
        try:
            if state.get("is_running") and state.get("client") and state["client"].is_connected:
                asset = state.get("active_asset", "")
                p_map = getattr(state["client"], 'payouts', {})
                
                # Update stream time watchdog since the library is actively writing to the map
                if p_map:
                    state["last_stream_time"] = time.time()
                
                # Direct, lightweight lookup from the clean library dictionary
                # — kept exactly as before, still fetched every cycle "as
                # usual". This is now used as the FALLBACK, not necessarily
                # the value the pause decision is based on.
                raw = (
                    p_map.get(asset) or
                    p_map.get(asset.lower()) or
                    p_map.get(asset.upper()) or
                    p_map.get(asset.replace("_otc", "")) or
                    p_map.get(asset.replace("_otc", "").lower()) or
                    p_map.get(asset.replace("_otc", "").upper())
                )
                ws_payout = int(float(raw)) if raw is not None else 0

                # state["payout"] always stays the RAW websocket number — the
                # content script reads this back to run its own
                # scraped-vs-websocket comparison, so this must never be
                # overwritten with a derived value or it'd create a feedback
                # loop with itself.
                state["payout"] = ws_payout

                # Defer to the content script's own final decision (scraped
                # vs websocket, chart-match aware) when it has reported
                # something within the last 5 seconds — it polls once a
                # second, so anything older than that means the extension
                # isn't actively reporting right now (tab closed, page
                # reloaded, etc). In that case, fall back to the raw
                # websocket read exactly as before.
                content_payout = state.get("content_payout")
                content_payout_time = state.get("content_payout_time", 0)
                content_is_fresh = (content_payout is not None) and (time.time() - content_payout_time <= 5)
                effective_payout = content_payout if content_is_fresh else ws_payout

                target_threshold = state.get("min_payout", 80)
                state["alerts"] = [a for a in state.get("alerts", []) if "LOW PAYOUT" not in a]
                was_paused = state.get("is_paused", False)

                if effective_payout > 0 and effective_payout < target_threshold:
                    state["is_paused"] = True
                    # NOTE: Never auto-resume if user manually paused
                    source = "content script" if content_is_fresh else "WebSocket"
                    state["alerts"].append(f"⚠️ LOW PAYOUT: {effective_payout}% (via {source})")
                    if not was_paused:  # Only log the actual transition, not every cycle while already paused
                        logging.warning(f"⏸️ AUTO-PAUSED: {asset} payout {effective_payout}% below {target_threshold}% minimum (source: {source})")
                elif effective_payout == 0 and not content_is_fresh:
                    # Only treat this as a hard data-feed-lagging case when we
                    # also have no fresh content-script number to fall back
                    # on — otherwise a momentary empty websocket map
                    # shouldn't force a pause the content script disagrees with.
                    state["is_paused"] = True
                    state["alerts"].append(f"⚠️ LOW PAYOUT: 0% (Data Feed Lagging for {asset})")
                    if not was_paused:
                        logging.warning(f"⏸️ AUTO-PAUSED: {asset} data feed lagging (no payout data from either source)")
        except Exception as e:
            logging.error(f"❌ Error in payout calculation loop: {str(e)}")
            
        await asyncio.sleep(3)

import asyncio
import time
import logging

def on_live_tick(data):
    """
    Persistent callback registered via client.subscribe_symbol_stream().

    Confirmed wire format from the library's _on_json_data dispatch is a flat
    dict per tick: {"asset": ..., "time": ..., "price": ...}.

    Unlike the tick-buffer approach in the z-score engines, this builds a
    real OHLC bar from the incoming tick stream, for whichever ONE timeframe
    is currently active (state["chart_tf"]) — set via the UI, same idea as
    switching asset. Only that single timeframe is tracked; switching it
    mid-session starts a fresh bar under the new interval. Each asset keeps
    its own current (still-forming) bar and a short history of CLOSED bars.
    A bar only ever gets added to that history once its time window has
    actually elapsed — nothing here is ever evaluated while still forming,
    which is what avoids the repainting problem discussed for ZigZag.
    """
    global state
    try:
        asset_name = str(data.get("asset", ""))
        price = float(data.get("price", 0))
        tick_time = float(data.get("time", time.time()))
        if not asset_name or price <= 0:
            return

        tf = state.get("chart_tf", 5)
        tf_state = state["bar_tracker"].setdefault(asset_name, {"tf": tf, "current": None, "closed": deque(maxlen=3)})

        # If the active timeframe changed since this asset's tracker was
        # created, reset it — bars built under the old interval aren't
        # valid under the new one.
        if tf_state.get("tf") != tf:
            tf_state["tf"] = tf
            tf_state["current"] = None
            tf_state["closed"].clear()

        bucket_start = int(tick_time // tf) * tf
        current = tf_state["current"]

        if current is None or current["start"] != bucket_start:
            # The previous bar's time window has elapsed — it's now closed
            # and safe to evaluate. Push it into history before starting
            # the new one.
            if current is not None:
                tf_state["closed"].append(current)
            tf_state["current"] = {
                "start": bucket_start,
                "open": price, "high": price, "low": price, "close": price,
            }
        else:
            current["high"]  = max(current["high"], price)
            current["low"]   = min(current["low"], price)
            current["close"] = price
    except Exception as e:
        logging.debug(f"on_live_tick parse failed: {e}")


def check_bar_pattern(asset_name):
    """
    Two-bar continuation pattern, evaluated only on CLOSED bars — bar[0] is
    the most recently closed bar, bar[1] is the one before it. Reads
    whichever timeframe is currently active for this asset in bar_tracker
    (set by on_live_tick from state["chart_tf"]).

        LONG:  High[0]>=High[1] AND Low[0]>=Low[1] AND Close[0]>Open[0] AND Close[1]>Open[1]
        SHORT: High[0]<=High[1] AND Low[0]<=Low[1] AND Close[0]<Open[0] AND Close[1]<Open[1]

    Not strict (>=/<=), matching the spec exactly as given — a tied high or
    low still counts. Returns "call", "put", or None. Also returns the
    start-time of bar[0], used by the caller to make sure each closed bar
    only ever gets evaluated once, not re-checked every loop tick.
    """
    tf_state = state.get("bar_tracker", {}).get(asset_name)
    if not tf_state:
        return None, None

    closed = tf_state["closed"]
    if len(closed) < 2:
        return None, None

    bar0, bar1 = closed[-1], closed[-2]   # bar0 = most recent closed, bar1 = one before

    is_long = (bar0["high"] >= bar1["high"] and bar0["low"] >= bar1["low"]
               and bar0["close"] > bar0["open"] and bar1["close"] > bar1["open"])
    is_short = (bar0["high"] <= bar1["high"] and bar0["low"] <= bar1["low"]
                and bar0["close"] < bar0["open"] and bar1["close"] < bar1["open"])

    if is_long:
        return "call", bar0["start"]
    if is_short:
        return "put", bar0["start"]
    return None, bar0["start"]



SIGNAL_LOG_PATH = "signal_log.csv"
_SIGNAL_LOG_FIELDS = [
    "timestamp", "asset", "timeframe", "direction", "stake", "trade_id",
    "outcome", "net_profit", "step",
    "bar0_open", "bar0_high", "bar0_low", "bar0_close",
    "bar1_open", "bar1_high", "bar1_low", "bar1_close",
]


def log_trade_csv(row: dict):
    """
    Append one resolved trade + the signal meta that triggered it to a
    flat CSV, for backtesting/calibration (e.g. real win rate by regime,
    by z-score bucket, signals-per-minute vs Z_THRESHOLD, etc).
    One row per trade, written at resolution time in
    background_order_watchdog -- not at signal time, so it always
    reflects an actual placed trade with a known outcome.
    """
    try:
        file_exists = os.path.exists(SIGNAL_LOG_PATH)
        with open(SIGNAL_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_SIGNAL_LOG_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in _SIGNAL_LOG_FIELDS})
    except Exception as e:
        logging.debug(f"log_trade_csv failed: {e}")


async def place_new_order(asset, stake, direction, meta=None):
    """An unblocked, production-grade execution hand.

    Launches a dedicated background watchdog for the trade outcome so the main
    loop can continue running.
    """
    global state
    
    # 1. Structural activity guardrail
    if state.get("is_paused") or not state.get("is_running"): 
        return "BLOCKED"
    
    target_asset = format_asset(asset)
    api_dir = "call" if str(direction).lower() in ["call", "buy", "up"] else "put"
    
    try:
        # 2. Extract account snapshot cleanly
        account_info = await state["client"].get_balance()
        if hasattr(account_info, 'balance'):
            state["pre_trade_balance"] = float(account_info.balance)
        elif isinstance(account_info, dict):
            state["pre_trade_balance"] = float(account_info.get("balance", 0) or account_info.get("data", {}).get("balance", 0))
        else:
            state["pre_trade_balance"] = float(account_info)

        logging.info(f"🎯 EXOTIC EXECUTION: {api_dir.upper()} | {target_asset} | ${stake:.2f}")

        # 2b. REAL FUNDS GUARDRAIL — checked against the actual account
        # balance just fetched above, not the bot's internal virtual
        # tracking. If the real account can't actually cover this stake,
        # refuse outright and never call place_order() at all. This is
        # what stops a trade from ever being sent when there's nothing
        # real behind it, regardless of what the virtual goal-tracking
        # thinks is available.
        if state["pre_trade_balance"] < stake:
            logging.warning(
                f"🚫 INSUFFICIENT REAL FUNDS: balance ${state['pre_trade_balance']:.2f} "
                f"< stake ${stake:.2f}. Trade refused, bot stopped."
            )
            state["alerts"].append(
                f"🚫 INSUFFICIENT REAL FUNDS: balance ${state['pre_trade_balance']:.2f} "
                f"is less than the ${stake:.2f} stake. Bot stopped."
            )
            state["is_running"] = False
            state["is_trading"] = False  # Safe unlock
            return "INSUFFICIENT_FUNDS"

        # 3. Fire the order instantly
        order = await state["client"].place_order(target_asset, stake, api_dir, state["duration"])
        
        if not order:
            logging.error(f"❌ ORDER REFUSED: {target_asset}")
            state["is_trading"] = False  # Safe unlock
            return "REFUSED"
            
        if isinstance(order, dict):
            trade_id = order.get('id') or order.get('order_id')
        else:
            trade_id = getattr(order, 'id', getattr(order, 'order_id', None))
            
        if not trade_id:
            logging.error(f"⚠️ ID ERROR: Order failed or missed by broker.")
            state["is_trading"] = False  # Safe unlock
            return "ID_MISSING"
            
        logging.info(f"✅ ORDER PLACED: ID {trade_id}. Tracking initialized in background...")

        # 4. CRITICAL: Spin up a non-blocking tracking worker task
        # This keeps the current execution task active for less than 500ms total!
        asyncio.create_task(background_order_watchdog(trade_id, stake, meta or {}))
        return "TRACKING"

    except Exception as e:
        logging.error(f"🚨 ORDER HAND EXCEPTION: {str(e)}")
        state["is_trading"] = False  # Safe unlock
        return "ERROR"

async def background_order_watchdog(trade_id, stake, meta=None):
    """Monitors an active trade in the background.

    Updates Martingale levels and unlocks the trading state upon completion.
    """
    global state
    max_wait = state.get("duration", 60) + 15
    start_time = asyncio.get_event_loop().time()
    last_outcome = None

    # Defined BEFORE the try block, not inside it. Previously these were
    # only set partway through the try block (after the timeout check),
    # so if check_win() never resolved in time, the TimeoutError raised
    # before reaching this line — jumping straight to the except block's
    # fallback logic, which then crashed referencing asset_name before it
    # had ever been assigned. Confirmed from a real crash log: the
    # fallback correctly determined and logged the LOSS outcome, then
    # crashed one line later on `if asset_name:`.
    meta = meta or {}
    asset_name = meta.get("asset", state.get("active_asset", ""))

    try:
        # Polling runs concurrently within this isolated background task wrapper
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            res = await state["client"].check_win(trade_id)
            if res and any(s in str(res.get('status','')).lower() for s in ["win", "loss", "lose", "draw", "equal", "closed"]):
                last_outcome = res
                break
            await asyncio.sleep(1.5)  # Safe delay to protect against network rate limits
            
        if not last_outcome:
            raise TimeoutError("Trade resolution message delayed past designated safety margins.")

        # Parse final outcome string attributes safely
        status_str = str(last_outcome.get('status', '')).lower()
        raw_payout = float(last_outcome.get('profit', 0))
        is_actually_tie = any(x in status_str for x in ["draw", "tie", "equal"]) or (raw_payout == 0.0 and "win" not in status_str and "loss" not in status_str)

        def _update_asset_stats(outcome_key):
            """Record win/loss for per-asset adaptive calibration."""
            if not asset_name:
                return
            s = state.setdefault("asset_stats", {}).setdefault(asset_name, {"wins": 0, "losses": 0, "draws": 0})
            s[outcome_key] = s.get(outcome_key, 0) + 1

        if is_actually_tie:
            logging.info(f"🔄 CONTRACT RESOLVED [DRAW] | ID: {trade_id}")
            _update_asset_stats("draws")
            # Stake was deducted when trade fired — add it back on a draw
            # since neither side won and the full stake should be returned.
            state["daily_profit"] += stake
            log_trade_csv({**meta, "timestamp": time.time(), "stake": stake,
                           "trade_id": trade_id, "outcome": "DRAW", "net_profit": 0})
            # Draw: leave consecutive_losses unchanged, don't reset it
        elif "win" in status_str or raw_payout > stake:
            state["last_raw_payout"] = raw_payout if raw_payout > stake else (raw_payout + stake)
            # Stake was already deducted when trade fired. Add back the full
            # payout (stake + profit), not just the profit portion.
            state["daily_profit"] += state["last_raw_payout"]
            net = state["last_raw_payout"] - stake
            logging.info(f"💰 CONTRACT RESOLVED [WIN] | ID: {trade_id} | Net: +${net:.2f}")
            _update_asset_stats("wins")
            log_trade_csv({**meta, "timestamp": time.time(), "stake": stake,
                           "trade_id": trade_id, "outcome": "WIN", "net_profit": net})
            state["current_step"] = 0
            state["consecutive_losses"] = 0   # reset streak on win
        else:
            # Stake already deducted when trade fired — do NOT deduct again here.
            # Only increment the step and streak counters.
            state["current_step"] += 1
            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
            logging.info(f"📉 CONTRACT RESOLVED [LOSS] | ID: {trade_id} | Net: -${stake:.2f} | Now on Step {state['current_step']} | Streak: {state['consecutive_losses']}")
            _update_asset_stats("losses")
            log_trade_csv({**meta, "timestamp": time.time(), "stake": stake,
                           "trade_id": trade_id, "outcome": "LOSS", "net_profit": -stake})
            
            # NEXT STEP BALANCE CHECK — only after loss confirmed
            virtual_balance = state.get("funds_to_risk", 0) + state.get("daily_profit", 0)
            current_step = state["current_step"]

            if current_step >= len(state["multipliers"]):
                # Max levels reached — alert and stop
                alert_msg = f"🛑 MAX LEVELS REACHED: Lost on Step {current_step}. Bot stopped. Balance remaining: ${virtual_balance:.2f}"
                state["alerts"].append(alert_msg)
                state["is_running"] = False
                logging.warning(alert_msg)
            else:
                # Calculate cumulative stake for next step
                next_stake = round(float(state["base_amount"]), 2)
                for i in range(current_step):
                    try:
                        mult = float(state["multipliers"][i]) if i < len(state["multipliers"]) else 1.0
                        if mult <= 0: break
                        next_stake = round(next_stake * mult, 2)
                    except:
                        pass
                if next_stake > virtual_balance:
                    alert_msg = (
                        f"🚨 INSUFFICIENT BALANCE: "
                        f"Lost on Step {current_step} (Stake was ${stake:.2f}). "
                        f"Next Step {current_step + 1} requires ${next_stake:.2f} "
                        f"but only ${virtual_balance:.2f} remaining. Bot stopped."
                    )
                    state["alerts"].append(alert_msg)
                    state["is_running"] = False
                    logging.warning(alert_msg)

    except Exception as err:
        logging.error(f"🚨 WATCHDOG ENCOUNTERED ERROR: {err}. Deploying account balance fallback updates...")
        try:
            # Fallback balance recovery mechanism
            account_data = await asyncio.wait_for(state["client"].get_balance(), timeout=5.0)
            if hasattr(account_data, 'balance'):
                remote_balance = float(account_data.balance)
            elif isinstance(account_data, dict):
                remote_balance = float(account_data.get("balance", 0) or account_data.get("data", {}).get("balance", 0))
            else:
                remote_balance = float(account_data)
                
            pre_balance = state.get("pre_trade_balance", remote_balance)
            
            if abs(remote_balance - pre_balance) < 0.01:
                logging.info(f"🔄 FALLBACK DETECTED: [DRAW] for ID {trade_id}")
                if asset_name:
                    state.setdefault("asset_stats", {}).setdefault(asset_name, {"wins":0,"losses":0,"draws":0})["draws"] = \
                        state["asset_stats"][asset_name].get("draws",0) + 1
            elif remote_balance > pre_balance:
                profit_delta = remote_balance - pre_balance
                state["daily_profit"] += profit_delta
                logging.info(f"💰 FALLBACK DETECTED: [WIN] for ID {trade_id} | Net: +${profit_delta:.2f}")
                state["current_step"] = 0
                state["consecutive_losses"] = 0
                if asset_name:
                    state.setdefault("asset_stats", {}).setdefault(asset_name, {"wins":0,"losses":0,"draws":0})["wins"] = \
                        state["asset_stats"][asset_name].get("wins",0) + 1
            else:
                state["daily_profit"] -= stake
                state["current_step"] += 1
                state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                logging.info(f"📉 FALLBACK DETECTED: [LOSS] for ID {trade_id} | Net: -${stake:.2f} | Now on Step {state['current_step']} | Streak: {state['consecutive_losses']}")
                if asset_name:
                    state.setdefault("asset_stats", {}).setdefault(asset_name, {"wins":0,"losses":0,"draws":0})["losses"] = \
                        state["asset_stats"][asset_name].get("losses",0) + 1
                
                # NEXT STEP BALANCE CHECK — only after loss confirmed
                virtual_balance = state.get("funds_to_risk", 0) + state.get("daily_profit", 0)
                current_step = state["current_step"]

                if current_step >= len(state["multipliers"]):
                    alert_msg = f"🛑 MAX LEVELS REACHED: Lost on Step {current_step}. Bot stopped. Balance remaining: ${virtual_balance:.2f}"
                    state["alerts"].append(alert_msg)
                    state["is_running"] = False
                    logging.warning(alert_msg)
                else:
                    next_stake = round(float(state["base_amount"]), 2)
                    for i in range(current_step):
                        try:
                            mult = float(state["multipliers"][i]) if i < len(state["multipliers"]) else 1.0
                            if mult <= 0: break
                            next_stake = round(next_stake * mult, 2)
                        except:
                            pass
                    if next_stake > virtual_balance:
                        alert_msg = (
                            f"🚨 INSUFFICIENT BALANCE: "
                            f"Lost on Step {current_step} (Stake was ${stake:.2f}). "
                            f"Next Step {current_step + 1} requires ${next_stake:.2f} "
                            f"but only ${virtual_balance:.2f} remaining. Bot stopped."
                        )
                        state["alerts"].append(alert_msg)
                        state["is_running"] = False
                        logging.warning(alert_msg)
        except Exception as fallback_err:
            logging.critical(f"❌ RECOVERY SHIELD CRITICAL FAILURE: {fallback_err}")
            
    finally:
        # ALWAYS RELEASE LOCK: Ensure your system state is reset regardless of how the trade concludes
        state["is_trading"] = False

import json
import logging

async def strategy_loop():
    global state
    last_requested_asset = None
    last_requested_tf = None

    while True:
        if state["daily_profit"] >= state["daily_goal"]:
            state["is_running"] = False
            logging.info("🎯 TARGET REACHED: Stopping bot.")
            await asyncio.sleep(1)
            continue

        if (state.get("is_running") and 
            not state.get("is_paused") and 
            state.get("client") and 
            state["client"].is_connected and 
            not state.get("is_trading")):
            
            try:
                asset_str = format_asset(state["active_asset"])
                chart_tf = state.get("chart_tf", 5)
                if not is_valid_timeframe(chart_tf):
                    chart_tf = 5
                    state["chart_tf"] = 5

                # --- SINGLE SOURCE OF TRUTH — same deference rule as
                # payout_monitor(): trust the content script's own scraped-
                # vs-websocket decision when it's been reported within the
                # last 5 seconds, otherwise fall back to the raw websocket
                # read.
                content_payout = state.get("content_payout")
                content_payout_time = state.get("content_payout_time", 0)
                content_is_fresh = (content_payout is not None) and (time.time() - content_payout_time <= 5)
                checked_payout = content_payout if content_is_fresh else state.get("payout", 0)

                min_payout = state.get("min_payout", 80) 

                if checked_payout < min_payout:
                    if int(asyncio.get_event_loop().time()) % 10 == 0:
                        source = "content script" if content_is_fresh else "WebSocket"
                        logging.warning(f"⏸️ PAYOUT PAUSE: {asset_str} at {checked_payout}% (Requires {min_payout}%, source: {source})")
                    await asyncio.sleep(1)
                    continue

                # ASSET/TIMEFRAME SWITCH: resubscribe whenever either the
                # active asset OR the active timeframe changes — same idea
                # as asset-switching in the other engines, just now also
                # covering a mid-session timeframe change. on_live_tick()
                # resets its own bar tracker for this asset automatically
                # when it notices chart_tf has changed.
                if asset_str != last_requested_asset or chart_tf != last_requested_tf:
                    try:
                        if last_requested_asset:
                            state["client"].unsubscribe_symbol_stream(last_requested_asset, on_live_tick)
                        await state["client"].subscribe_symbol_stream(asset_str, chart_tf, on_live_tick)
                        last_requested_asset = asset_str
                        last_requested_tf = chart_tf
                        logging.info(f"📡 SUBSCRIBED: {asset_str} ({chart_tf}s bars)")
                    except Exception as e:
                        logging.error(f"⚠️ Subscription Failed: {e}")
                        last_requested_asset = None  # Retry next loop

                    state["last_bar_time"] = 0
                    await asyncio.sleep(1.5)

                try:
                    current_time = asyncio.get_event_loop().time()

                    # --- BRAIN CENTER: SHIFT-BY-1 MARTINGALE ARITHMETIC ---
                    if state["current_step"] == 0:
                        stake = round(state["base_amount"], 2)
                    else:
                        stake = round(float(state["base_amount"]), 2)
                        for i in range(state["current_step"]):
                            try:
                                mult = float(state["multipliers"][i]) if i < len(state["multipliers"]) else 1.0
                                if mult <= 0:
                                    state["is_running"] = False
                                    logging.warning(f"🛑 STOP: Multiplier at level {i+1} is 0. Killing Engine.")
                                    break
                                stake = round(stake * mult, 2)
                            except:
                                pass

                    state["current_stake"] = stake

                    # -----------------------------------------------------------
                    # 3-LOSS PAUSE: after 3 consecutive losses, pause 60 seconds
                    # then resume at the EXACT same step — no reset, no ladder
                    # change.
                    # -----------------------------------------------------------
                    if state.get("consecutive_losses", 0) >= 3:
                        logging.warning(f"⏸️ 3 CONSECUTIVE LOSSES: Pausing 60s. Resuming at Step {state['current_step']} (no reset)...")
                        state["consecutive_losses"] = 0
                        await asyncio.sleep(60)
                        logging.info(f"▶️ RESUMING: Back at Step {state['current_step']} | Stake: ${stake}")
                        continue

                    in_cooldown = (current_time - state.get("last_trade_time", 0)) <= 15

                    # -----------------------------------------------------------
                    # BAR PATTERN CHECK — the single active asset/timeframe
                    # only. Tracks the start-time of the last bar already
                    # evaluated, so a closed bar is only ever checked once —
                    # but if the pattern is still true on the NEXT closed
                    # bar (a genuinely new event), it fires again.
                    # -----------------------------------------------------------
                    if not in_cooldown and not state.get("is_paused"):
                        signal, bar0_start = check_bar_pattern(asset_str)
                        last_seen = state["last_processed_bar"].get(asset_str)

                        if bar0_start is not None and bar0_start != last_seen:
                            state["last_processed_bar"][asset_str] = bar0_start

                            if signal:
                                tf_state = state["bar_tracker"][asset_str]
                                bar0, bar1 = tf_state["closed"][-1], tf_state["closed"][-2]

                                state["last_trade_time"] = current_time
                                state["is_trading"] = True
                                state["duration"] = chart_tf  # expiry matches the active timeframe

                                logging.info(f"🎯 SIGNAL: {signal.upper()} | {chart_tf}s bar | Level: {state['current_step'] + 1} | Stake: ${stake}")

                                state["daily_profit"] -= stake

                                trade_meta = {
                                    "asset": asset_str, "timeframe": chart_tf, "direction": signal,
                                    "step": state["current_step"],
                                    "bar0_open": bar0["open"], "bar0_high": bar0["high"],
                                    "bar0_low": bar0["low"],   "bar0_close": bar0["close"],
                                    "bar1_open": bar1["open"], "bar1_high": bar1["high"],
                                    "bar1_low": bar1["low"],   "bar1_close": bar1["close"],
                                }

                                await place_new_order(asset_str, stake, signal, meta=trade_meta)

                                state["is_trading"] = False

                # Handle timeout blocks safely without force-breaking token alignments
                except (asyncio.TimeoutError, AttributeError):
                    pass
            
            except Exception as e:
                logging.error(f"⚠️ Loop Error: {e}")
                state["is_trading"] = False  
                await asyncio.sleep(1)
                    
        await asyncio.sleep(0.05) # Stabilized to 50ms polling to avoid overloading local CPU threads


async def handle_request(request):
    global state
    try:
        data = await request.json()
        action = data.get('action')
        
        # Helper to prevent 'NoneType' crashes
        def safe_int(val, default=0):
            try:
                if val is None or val == "": return default
                return int(float(val))
            except Exception: return default

        if action != 'STATUS':
            logging.info(f"📥 UI ACTION: {action} | Asset: {data.get('asset')} | Min Payout: {data.get('min_payout')}")

        # --- 1. SYNC & START ACTION ---
        if action == 'SYNC':
            new_min = safe_int(data.get('min_payout'), 90)
            target_asset = format_asset(data.get('asset', 'EURUSD_otc'))

            # --- DEMO-ONLY GATE ---
            # Reads the real value straight out of the pasted SSID (same
            # check used later to configure the client) and refuses to
            # proceed at all if it isn't clearly demo. No client is created,
            # no connection is attempted — this engine simply never accepts
            # a live session, full stop.
            incoming_ssid = data.get('ssid', '')
            if not detect_demo_from_ssid(incoming_ssid):
                logging.warning("🚫 LIVE SSID REJECTED: this engine only runs demo sessions.")
                return web.json_response({
                    "status": "error",
                    "message": "This bot only runs on demo accounts. Live sessions are not accepted."
                }, status=403)

            # Reject an invalid timeframe outright rather than silently
            # Reject a nonsensical value (zero, negative) outright, but
            # otherwise accept any timeframe — no hardcoded list to fall
            # out of sync with what PocketOption actually offers.
            requested_tf = int(data.get('chart_tf', 5))
            if not is_valid_timeframe(requested_tf):
                return web.json_response({
                    "status": "error",
                    "message": f"'{requested_tf}' isn't a valid timeframe — must be a positive number of seconds."
                }, status=400)

            state.update({
                "active_asset": target_asset,
                "base_amount": round(float(data.get('base_amount', 1.0)), 3),
                "multipliers": data.get('multipliers', [1.0] * 10),
                "chart_tf": requested_tf,
                "duration": requested_tf,  # Expiry always matches the active timeframe
                "daily_goal": float(data.get('daily_goal', 50.0)),
                "min_payout": new_min, 
                "funds_to_risk": float(data.get('funds_to_risk', 400.0)),
                "ssid": data.get('ssid'),
                "is_running": True, 
                "is_paused": False, 
                "manual_pause": False,
                "current_step": 0,
                "payout": 100,  # Let payout_monitor() take over immediately after WebSocket connects
                "alerts": []
            })
            state["current_stake"] = state["base_amount"]
            state["daily_profit"] = 0.0 
            state["last_bar_time"] = 0 
            # Wipe bar tracking on every fresh SYNC. Without this, a
            # same-asset restart shortly after a STOP left old, stale bars
            # in place, so the very first fresh tick could be evaluated
            # against bars that have nothing to do with the new session.
            state["bar_tracker"] = {}
            state["last_processed_bar"] = {}

            async def start_session():
                try:
                    if state.get("client"):
                        try: await state["client"].disconnect()
                        except Exception: pass

                    detected_is_demo = detect_demo_from_ssid(state["ssid"])
                    state["is_demo"] = detected_is_demo
                    logging.info(
                        f"🔎 SSID MODE DETECTED: {'DEMO' if detected_is_demo else 'LIVE'} "
                        f"(read directly from pasted SSID, not assumed)"
                    )

                    state["client"] = AsyncPocketOptionClient(state["ssid"], is_demo=detected_is_demo)
                    await state["client"].connect()
                    try:
                        await state["client"].subscribe_symbol_stream(
                            state["active_asset"], state["chart_tf"], on_live_tick
                        )
                    except Exception as e:
                        logging.error(f"⚠️ Stream subscription failed: {e}")
                    logging.info(f"✅ SYNC COMPLETE: Asset={state['active_asset']} | Payout={state['payout']}%")
                except Exception as e:
                    logging.error(f"❌ Background Connection Error: {e}")

            asyncio.create_task(start_session())
            return web.json_response({"status": "ok"})

        # --- 2. MANUAL TRADE ACTION ---
        if action == 'TRADE':
            user_asset = data.get("asset", state["active_asset"])
            direction = data.get("direction") 
            amount = float(data.get("amount", state["current_stake"]))
            
            # FIXED: Encapsulated into a protected task container to prevent overlapping automated trades
            async def manual_trade_worker():
                state["is_trading"] = True
                # Set the shared cooldown timer BEFORE firing, same as the
                # automated loop does. Without this, the automated loop had
                # no way to know a trade just went out manually, and could
                # fire its own trade on top of this one within the same
                # martingale window.
                state["last_trade_time"] = asyncio.get_event_loop().time()
                try:
                    await place_new_order(user_asset, amount, direction)
                finally:
                    state["is_trading"] = False
                    
            asyncio.create_task(manual_trade_worker())
            return web.json_response({"status": "ok"})

        # --- 3. STATUS POLLING ACTION ---
        if action == 'STATUS':
            ui_asset = data.get('asset')
            if ui_asset:
                state["active_asset"] = format_asset(ui_asset)

            # The content script sends its OWN final payout decision here —
            # the result of comparing scraped-vs-websocket with the
            # chart-match rule already applied on its end. We store it
            # separately (not into state["payout"]) because the content
            # script's own next comparison depends on reading back the pure
            # websocket value via state["payout"] — overwriting it here
            # would create a feedback loop. payout_monitor() is what
            # actually decides whether to trust this value or fall back.
            final_payout = safe_int(data.get('final_payout'), 0)
            if final_payout > 0:
                state["content_payout"] = final_payout
                state["content_payout_time"] = time.time()

            if 'min_payout' in data:
                state["min_payout"] = safe_int(data.get('min_payout'), 90)

            target_min = state.get("min_payout", 90)
            
            # THE CONNECTION & SYNC FLAG
            is_successfully_synced = False
            if state.get("client") and state["client"].is_connected:
                is_successfully_synced = True
                # --- SINGLE SOURCE OF TRUTH INJECTION ---
                # Payout lookup code block has been cleanly stripped out of here.
                # This worker reads straight from the global state tracking memory map
                # populated continuously by your asynchronous payout_monitor loop.
                pass
            else:
                # Fallback to zero out memory parameters when the socket connection drops off entirely
                state["payout"] = 0

            # REMOVED: Auto-pause/resume logic here was conflicting with payout_monitor()
            # payout_monitor() is the single source of truth for pause/resume decisions

            current_alerts = list(state.get("alerts", []))
            if 0 < state["payout"] < target_min:
                msg = f"⚠️ LOW PAYOUT: {state['payout']}%"
                if msg not in current_alerts:
                    current_alerts.append(msg)
                    state["alerts"] = current_alerts
            else:
                state["alerts"] = [a for a in current_alerts if "LOW PAYOUT" not in a]

            return web.json_response({
                "status": "ok", 
                "daily_profit": state["daily_profit"],
                "daily_goal": state.get("daily_goal", 50.0),
                "current_stake": float(state.get("current_stake", 0)),
                "current_step": state.get("current_step", 0),
                "is_running": state["is_running"],
                "is_connected": is_successfully_synced, # UI turns green based on this
                "is_paused": state.get("is_paused", False),
                "payout": state.get("payout", 0),  # Instantly streams the single source of truth
                "scraped_payout": 0, # Kept structural key placeholder intact for UI payload parity
                "min_payout": state["min_payout"],
                "alerts": state["alerts"],
                "last_trade": {"asset": state["active_asset"]}
            })

        # --- 3b. MANUAL ASSET SWITCH (mid-martingale, no reset) ---
        # Lets the user swap the active asset while the bot is paused
        # (e.g. waiting out a low-payout window) without touching
        # current_step, current_stake, daily_profit, or consecutive_losses.
        # Those fields are asset-agnostic already, so a switch here is a
        # pure re-target: strategy_loop() will unsubscribe the old symbol
        # and subscribe the new one on its own the next time it runs
        # (it compares state["active_asset"] against last_requested_asset),
        # then continue the martingale sequence exactly where it left off.
        if action == 'SWITCH_ASSET':
            if not state.get("is_paused"):
                return web.json_response({
                    "status": "error",
                    "message": "Pause the bot before switching assets."
                }, status=400)

            new_asset_raw = data.get("asset")
            if not new_asset_raw:
                return web.json_response({
                    "status": "error",
                    "message": "No asset provided."
                }, status=400)

            new_asset = format_asset(new_asset_raw)
            old_asset = state.get("active_asset")

            # Reject anything that isn't a real, tradeable PocketOption
            # asset — reusing the exact same canonical list client.py
            # itself trusts before subscribing or placing an order, so
            # this can't drift out of sync with what's actually valid.
            # A typo here would previously sail through silently and only
            # fail later, quietly, when the engine tried to subscribe.
            if new_asset not in ASSETS:
                return web.json_response({
                    "status": "error",
                    "message": f"'{new_asset_raw}' is not a recognized asset. Check the spelling and try again."
                }, status=400)

            if new_asset == old_asset:
                return web.json_response({"status": "ok", "active_asset": new_asset, "message": "Already active."})

            state["active_asset"] = new_asset
            # Force a fresh bar tracker for the new symbol rather than
            # reusing stale bars left over from a previous session on it.
            state.get("bar_tracker", {}).pop(new_asset, None)
            state.get("last_processed_bar", {}).pop(new_asset, None)
            state["last_bar_time"] = 0

            logging.info(
                f"🔀 MANUAL ASSET SWITCH: {old_asset} → {new_asset} "
                f"(Step {state.get('current_step', 0)} preserved, "
                f"Stake ${state.get('current_stake', 0):.2f} preserved, "
                f"Profit ${state.get('daily_profit', 0):.2f} preserved)"
            )

            return web.json_response({
                "status": "ok",
                "active_asset": new_asset,
                "current_step": state.get("current_step", 0),
                "current_stake": state.get("current_stake", 0),
                "daily_profit": state.get("daily_profit", 0),
            })

        # --- 4. STANDARD ACTIONS ---
        if action == 'STOP': 
            state["is_running"] = False 
            return web.json_response({"status": "ok"})
            
        if action == 'RESET': 
            state.update({"current_step": 0, "daily_profit": 0.0})
            state["current_stake"] = state.get("base_amount", 1.0)
            return web.json_response({"status": "ok"})

        if action == 'PAUSE': 
            state["is_paused"] = True
            state["manual_pause"] = True  # Manual override — auto resume will not clear this
            logging.info(f"⏸️ MANUAL PAUSE: {state.get('active_asset', '?')}")
            return web.json_response({"status": "ok"})

        if action == 'AUTO_PAUSE':
            # Fired by the content script's own client-side low-payout
            # detection — NOT a real human click. Deliberately does not
            # touch manual_pause, so AUTO_RESUME can still clear this once
            # payout genuinely recovers. Previously this shared the 'PAUSE'
            # action with real manual clicks, which incorrectly set
            # manual_pause=True and left the bot stuck until someone
            # manually hit Resume, even after payout was fine again.
            was_paused = state.get("is_paused", False)
            state["is_paused"] = True
            if not was_paused:
                logging.warning(f"⏸️ AUTO-PAUSED (content script): {state.get('active_asset', '?')}")
            return web.json_response({"status": "ok"})
        
        if action == 'RESUME':
            # Manual RESUME — always works regardless of manual_pause flag
            state["is_paused"] = False
            state["manual_pause"] = False
            logging.info(f"▶️ MANUAL RESUME: {state.get('active_asset', '?')}")
            return web.json_response({"status": "ok"})

        if action == 'AUTO_RESUME':
            # Auto RESUME from payout recovery — only works if not manually paused
            if not state.get("manual_pause", False):
                if state.get("is_paused"):
                    logging.info(f"▶️ AUTO-RESUME: {state.get('active_asset', '?')} payout recovered and stable")
                state["is_paused"] = False
            return web.json_response({"status": "ok"})

        if action == 'TOGGLE_PAUSE': 
            state["is_paused"] = not state["is_paused"]
            state["manual_pause"] = state["is_paused"]  # Sync manual_pause with toggled state
            logging.info(f"{'⏸️ MANUAL PAUSE' if state['is_paused'] else '▶️ MANUAL RESUME'} (toggle): {state.get('active_asset', '?')}")
            return web.json_response({"status": "ok"})

        return web.json_response({"status": "unknown"})

    except Exception as e:
        logging.error(f"❌ Backend Request Error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def main():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
    cors.add(app.router.add_post('/control', handle_request))
    asyncio.create_task(strategy_loop())
    asyncio.create_task(connection_monitor())
    asyncio.create_task(payout_monitor())
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, '127.0.0.1', 5005).start()
    
    # FIXED: Replaced raw print with structured logging to keep text logs perfectly aligned
    logging.info("🚀 Engine ONLINE on Port 5005")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try: 
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): 
        sys.exit(0)
