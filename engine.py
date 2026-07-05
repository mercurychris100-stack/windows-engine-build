import asyncio
import sys
import os
import json
import logging
import statistics
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
    "duration": 5, 
    "chart_tf": 5, 
    "is_trading": False,
    "daily_profit": 0.0, 
    "daily_goal": 50.0,
    "funds_to_risk": 400.0, 
    "last_bar_time": 0, 
    "ssid": "", 
    "alerts": [], 
    "payout": 0,                  # Block trading until WebSocket delivers real payout data
    "min_payout": 90,
    "active_asset": "EURUSD_otc",
    "last_trade": {"asset": "EURUSD_otc", "status": "WAITING"},
    
    # =========================================================================
    # REAL-TIME INFRASTRUCTURE STORAGE INJECTIONS
    # =========================================================================
    "tick_tracker": {},           # Holds live sub-second price buffers per asset
    "last_clock_skip_log": 0,     # Track timestamp signatures for clock protection
    "consecutive_losses": 0,      # Live count of consecutive confirmed losses (reset on win)
    "_vol_blocked": False,        # Live volatility gate state per asset cycle
    "asset_stats": {},            # Per-asset W/L history for adaptive threshold calibration
    # =========================================================================
}

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
                    # changeSymbol to be silently ignored, leaving tick_tracker
                    # empty and the bot trading blind.
                    await asyncio.sleep(3.0)

                    # Item 13: Re-subscribe to the active asset stream after
                    # every reconnect. The library restores the raw connection
                    # but does NOT re-call subscribe_symbol_stream automatically,
                    # so tick_tracker stops updating until either a manual Sync
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
                raw = (
                    p_map.get(asset) or
                    p_map.get(asset.lower()) or
                    p_map.get(asset.upper()) or
                    p_map.get(asset.replace("_otc", "")) or
                    p_map.get(asset.replace("_otc", "").lower()) or
                    p_map.get(asset.replace("_otc", "").upper())
                )

                target_threshold = state.get("min_payout", 80)
                
                if raw is not None:
                    # Clean type casting: The library already scaled this to a clean float/int
                    state["payout"] = int(float(raw))
                    state["alerts"] = [a for a in state.get("alerts", []) if "LOW PAYOUT" not in a]
                    
                    if state["payout"] < target_threshold:
                        state["is_paused"] = True
                        # NOTE: Never auto-resume if user manually paused
                        state["alerts"].append(f"⚠️ LOW PAYOUT: {state['payout']}%")
                else:
                    # Treat an completely missing asset map key cleanly without dropping connection
                    state["payout"] = 0
                    state["is_paused"] = True  
                    state["alerts"] = [a for a in state.get("alerts", []) if "LOW PAYOUT" not in a]
                    state["alerts"].append(f"⚠️ LOW PAYOUT: 0% (Data Feed Lagging for {asset})")
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
    dict per tick: {"asset": ..., "time": ..., "price": ...}. Writes the
    current price into state["tick_tracker"] so get_signals_improved() /
    strategy_loop() can read it. Also maintains a short rolling buffer of
    recent prices per asset, used to compute volatility-normalized (z-score)
    signals instead of a fixed absolute threshold.
    """
    global state
    try:
        asset_name = str(data.get("asset", ""))
        price = float(data.get("price", 0))
        tick_time = float(data.get("time", time.time()))
        if not asset_name or price <= 0:
            return

        timeframe = state.get("chart_tf", 5) or 5
        bracket_epoch = int(tick_time // timeframe) * timeframe

        tracker = state["tick_tracker"].setdefault(
            asset_name, {"current_bracket": 0, "base_open": price, "buffer": deque(maxlen=150)}
        )
        if "buffer" not in tracker:
            tracker["buffer"] = deque(maxlen=150)

        # Real-Time Reset: anchor the Open on the first tick of a new bracket
        if tracker["current_bracket"] != bracket_epoch:
            tracker["current_bracket"] = bracket_epoch
            tracker["base_open"] = price

        tracker["last_price"] = price
        tracker["timestamp"] = tick_time
        tracker["buffer"].append(price)
    except Exception as e:
        logging.debug(f"on_live_tick parse failed: {e}")


def get_asset_z_adjustment(asset_str):
    """
    Per-asset adaptive calibration (item 15).

    Tracks each asset's recent win/loss record independently and returns
    a z-score adjustment to apply on top of the base escalated threshold.
    The idea: if an asset is performing well (high win rate), loosen the
    bar slightly so it trades more often. If it's struggling (low win rate),
    tighten it so the bot is more selective on that specific asset.

    Requires at least MIN_ASSET_TRADES resolved trades on this asset before
    any adjustment is made — below that sample size the adjustment is 0.0
    (neutral) to avoid overreacting to a handful of unlucky trades.

    This runs off state["asset_stats"], which background_order_watchdog
    updates after every resolved trade.
    """
    MIN_ASSET_TRADES = 20       # minimum sample before any adjustment kicks in
    TARGET_WIN_RATE  = 0.54     # above this → loosen slightly; below → tighten
    MAX_ADJUSTMENT   = 0.5      # never adjust more than ±0.5 z-points

    stats = state.get("asset_stats", {}).get(asset_str, {})
    wins  = stats.get("wins", 0)
    total = stats.get("wins", 0) + stats.get("losses", 0)

    if total < MIN_ASSET_TRADES:
        return 0.0   # not enough data yet, no adjustment

    win_rate = wins / total
    deviation = win_rate - TARGET_WIN_RATE

    # positive deviation (doing well)  → negative adjustment (lower bar, more trades)
    # negative deviation (struggling)  → positive adjustment (raise bar, fewer trades)
    raw_adj = -(deviation * 2.0)   # scale: 0.1 above/below target = ±0.2 z adjustment
    adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, raw_adj))

    if abs(adjustment) >= 0.05:
        logging.debug(f"📐 ASSET CALIBRATION [{asset_str}]: WR={win_rate:.1%} n={total} → z_adj={adjustment:+.2f}")

    return adjustment


def get_signals_improved(asset_str):
    """
    Regime-aware, streak-escalating signal engine.

    Trend-following in trending conditions, mean-reversion in ranging
    conditions. Both branches gate through a volatility-normalised z-score.

    STREAK ESCALATION (item 9): after each consecutive loss the effective
    z-bar, pullback requirement, and trend-consistency requirement all rise,
    making the bot demand progressively stronger evidence the deeper into a
    losing run it already is. On a win, current_step resets to 0 in
    background_order_watchdog and all bars drop back to their BASE values.

    CSV LOGGING (items 10+11): every fired signal now records the active
    asset name, the current step, and the effective z_threshold so the CSV
    can be used to calibrate these values with real data later.

    :param asset_str: The current active asset (e.g., 'AUDCHF_otc')
    :return: "call", "put", or None
    """
    global state
    asset_tracker = state.get("tick_tracker", {}).get(asset_str, {})
    buffer = asset_tracker.get("buffer")

    TREND_LOOKBACK = 60
    ENTRY_WINDOW   = 20

    # -------------------------------------------------------------------
    # STREAK-AWARE CONFIDENCE ESCALATION
    # The bar for entry rises with every consecutive loss (current_step),
    # and resets to BASE the moment a trade wins.
    # -------------------------------------------------------------------
    current_step = state.get("current_step", 0)

    BASE_Z_THRESHOLD         = 1.5
    BASE_PULLBACK_Z          = 0.6
    BASE_TREND_CONSISTENCY   = 0.55   # Loosened from 0.62 — 0.62 was too strict on 5s OTC feeds,
                                       # causing the trend branch to almost never fire. 0.55 means
                                       # 55% of ticks agreeing on direction counts as trending.
                                       # Testing on EURCHF specifically to see if looser trend
                                       # detection improves win rate on an asset where range
                                       # reversion consistently underperformed (37.5% historically).
    Z_ESCALATION_PER_STEP    = 0.5
    PULLBACK_ESC_PER_STEP    = 0.3
    CONSIST_ESC_PER_STEP     = 0.05

    Z_THRESHOLD        = min(2.5, BASE_Z_THRESHOLD       + (current_step * Z_ESCALATION_PER_STEP))
    PULLBACK_Z         = min(1.5, BASE_PULLBACK_Z        + (current_step * PULLBACK_ESC_PER_STEP))
    TREND_CONSISTENCY  = min(0.80, BASE_TREND_CONSISTENCY + (current_step * CONSIST_ESC_PER_STEP))

    # Apply per-asset calibration on top of the escalated threshold.
    asset_z_adj  = get_asset_z_adjustment(asset_str)
    Z_THRESHOLD  = max(1.0, Z_THRESHOLD + asset_z_adj)
    PULLBACK_Z   = max(0.3, PULLBACK_Z  + asset_z_adj * 0.5)

    # Minimum execution z: at step 0 the evaluation bar is 1.5 but the bot
    # only actually places a trade if z clears 1.8 — filtering out the
    # weakest marginal entries at base stake without killing frequency.
    # At step 1+ the escalated threshold already exceeds 1.8 so no change.
    MIN_EXECUTION_Z = 1.8 if current_step == 0 else Z_THRESHOLD

    MIN_SAMPLES = max(TREND_LOOKBACK, ENTRY_WINDOW) // 2

    signal = None
    if not buffer or len(buffer) < MIN_SAMPLES:
        return None

    prices = list(buffer)

    # -------------------------------------------------------------------
    # REGIME DETECTION
    # -------------------------------------------------------------------
    trend_window  = prices[-TREND_LOOKBACK:] if len(prices) >= TREND_LOOKBACK else prices
    net_move      = trend_window[-1] - trend_window[0]
    diffs         = [trend_window[i+1] - trend_window[i] for i in range(len(trend_window)-1)]
    agreeing      = sum(1 for d in diffs if d != 0 and (d > 0) == (net_move > 0))
    nonzero_diffs = sum(1 for d in diffs if d != 0)
    consistency   = (agreeing / nonzero_diffs) if nonzero_diffs else 0.0
    is_trending   = consistency >= TREND_CONSISTENCY
    trend_dir_up  = net_move > 0

    # -------------------------------------------------------------------
    # DIRECTIONAL FILTER
    # Confirmed from data: CALL win rate significantly lower than PUT.
    # Root cause: bot bets on upward reversion into a market that has a
    # downward macro drift, and vice versa. Before firing any signal,
    # check whether the macro direction opposes the intended bet.
    # If the 60-tick drift is downward, skip CALL entries.
    # If the 60-tick drift is upward, skip PUT entries.
    # Applied to both range reversion and trend pullback branches.
    # -------------------------------------------------------------------
    macro_drift_up = net_move > 0  # same window as regime detection

    # -------------------------------------------------------------------
    # ENTRY CALC
    # -------------------------------------------------------------------
    entry_window = prices[-ENTRY_WINDOW:] if len(prices) >= ENTRY_WINDOW else prices
    mean_price   = statistics.fmean(entry_window)
    stdev_price  = statistics.pstdev(entry_window)
    last_tick    = entry_window[-1]

    if stdev_price > 0:
        z = (last_tick - mean_price) / stdev_price

        def _meta(regime, direction):
            return {
                "asset":       asset_str,
                "regime":      regime,
                "consistency": round(consistency, 4),
                "z":           round(z, 4),
                "step":        current_step,
                "z_threshold": round(Z_THRESHOLD, 4),
                "direction":   direction,
            }

        # Single deceleration check (restored from previous engine)
        if len(entry_window) >= 3:
            decelerating = abs(entry_window[-1] - entry_window[-2]) < abs(entry_window[-2] - entry_window[-3])
        else:
            decelerating = False

        if is_trending:
            if trend_dir_up and -Z_THRESHOLD < z <= -PULLBACK_Z:
                if not macro_drift_up:
                    logging.debug(f"🚫 DIRECTIONAL FILTER: skipping CALL — macro drift is downward")
                elif abs(z) >= MIN_EXECUTION_Z:
                    logging.info(f"📈 TREND PULLBACK (up): z={z:.2f} consistency={consistency:.2f} step={current_step} z_bar={Z_THRESHOLD:.2f}")
                    signal = "call"
                    state["_pending_signal_meta"] = _meta("trend", signal)
            elif (not trend_dir_up) and PULLBACK_Z <= z < Z_THRESHOLD:
                # PUT unrestricted — performing well in data, no directional filter applied
                if abs(z) >= MIN_EXECUTION_Z:
                    logging.info(f"📉 TREND PULLBACK (dn): z={z:.2f} consistency={consistency:.2f} step={current_step} z_bar={Z_THRESHOLD:.2f}")
                    signal = "put"
                    state["_pending_signal_meta"] = _meta("trend", signal)
        else:
            if z <= -Z_THRESHOLD and decelerating:
                if not macro_drift_up:
                    logging.debug(f"🚫 DIRECTIONAL FILTER: skipping CALL — macro drift is downward")
                elif abs(z) >= MIN_EXECUTION_Z:
                    logging.info(f"⚡ RANGE REVERSION (low):  z={z:.2f} consistency={consistency:.2f} step={current_step} z_bar={Z_THRESHOLD:.2f}")
                    signal = "call"
                    state["_pending_signal_meta"] = _meta("range", signal)
            elif z >= Z_THRESHOLD and decelerating:
                # PUT unrestricted — performing well in data, no directional filter applied
                if abs(z) >= MIN_EXECUTION_Z:
                    logging.info(f"⚡ RANGE REVERSION (high): z={z:.2f} consistency={consistency:.2f} step={current_step} z_bar={Z_THRESHOLD:.2f}")
                    signal = "put"
                    state["_pending_signal_meta"] = _meta("range", signal)

    # -------------------------------------------------------------------
    # CALIBRATION AID: signal rate + regime split logged every 5 minutes
    # -------------------------------------------------------------------
    now  = time.time()
    rate = state.setdefault("_signal_rate", {"window_start": now, "count": 0,
                                              "trend_w": 0, "trend_l": 0,
                                              "range_w": 0, "range_l": 0})
    if signal:
        rate["count"] += 1

    # Update regime win/loss counters from asset_stats
    if now - rate["window_start"] >= 300:
        all_stats = state.get("asset_stats", {})
        tw = sum(s.get("wins",0)   for s in all_stats.values())
        tl = sum(s.get("losses",0) for s in all_stats.values())
        logging.info(f"📊 SIGNAL RATE: {rate['count']} signals in last 5 min ({rate['count']/5:.2f}/min)")
        logging.info(f"📊 OVERALL STATS: W={tw} L={tl} WR={tw/(tw+tl)*100:.1f}%" if tw+tl else "📊 OVERALL STATS: No trades yet")
        rate["window_start"] = now
        rate["count"] = 0

    return signal



SIGNAL_LOG_PATH = "signal_log.csv"
_SIGNAL_LOG_FIELDS = [
    "timestamp", "asset", "regime", "consistency", "z", "step", "z_threshold",
    "direction", "stake", "trade_id", "outcome", "net_profit",
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
        
        # Process progression states cleanly
        meta = meta or {}
        asset_name = meta.get("asset", state.get("active_asset", ""))

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
    last_trade_time = 0

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
                
                # --- UPDATED: READ DIRECTLY FROM THE SINGLE SOURCE OF TRUTH ---
                checked_payout = state.get("payout", 0)
                # -----------------------------------------------------------

                min_payout = state.get("min_payout", 80) 

                if checked_payout < min_payout:
                    if int(asyncio.get_event_loop().time()) % 10 == 0:
                        logging.warning(f"⏸️ PAYOUT PAUSE: {asset_str} at {checked_payout}% (Requires {min_payout}%)")
                    await asyncio.sleep(1)
                    continue


                # ASSET SWITCH: close the old subscription and open a real one
                # for the new asset via the proper persistent stream API.
                if asset_str != last_requested_asset:
                    try:
                        if last_requested_asset:
                            state["client"].unsubscribe_symbol_stream(last_requested_asset, on_live_tick)
                        await state["client"].subscribe_symbol_stream(asset_str, state["chart_tf"], on_live_tick)
                        last_requested_asset = asset_str
                        logging.info(f"📡 SUBSCRIBED: {asset_str} ({state['chart_tf']}s)")
                    except Exception as e:
                        logging.error(f"⚠️ Subscription Failed: {e}")
                        last_requested_asset = None  # Retry next loop

                    state["last_bar_time"] = 0
                    await asyncio.sleep(1.5)

                try:
                    current_time = asyncio.get_event_loop().time()

                    # --- BRAIN CENTER: SHIFT-BY-1 MARTINGALE ARITHMETIC ---
                    virtual_balance = state.get("funds_to_risk", 0) + state.get("daily_profit", 0)
                    
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
                        else:
                            pass

                    state["current_stake"] = stake

                    # NOTE: The pre-trade "stake > virtual_balance" hard-kill
                    # that used to live here has been removed. It was shutting
                    # the bot down based on a projected next-step amount before
                    # the current trade had even resolved — meaning a win (which
                    # would reset current_step to 0 and make the projection
                    # irrelevant) could never save it. The real post-resolution
                    # balance check now lives exclusively in
                    # background_order_watchdog, which only fires after the
                    # actual outcome is confirmed.

                    # -----------------------------------------------------------
                    # 3-LOSS PAUSE: after 3 consecutive losses, pause 60 seconds
                    # then resume at the EXACT same step — no reset, no ladder
                    # change. consecutive_losses is incremented in
                    # background_order_watchdog after each confirmed loss and
                    # reset to 0 after each confirmed win.
                    # -----------------------------------------------------------
                    if state.get("consecutive_losses", 0) >= 3:
                        logging.warning(f"⏸️ 3 CONSECUTIVE LOSSES: Pausing 60s. Resuming at Step {state['current_step']} (no reset)...")
                        state["consecutive_losses"] = 0
                        await asyncio.sleep(60)
                        logging.info(f"▶️ RESUMING: Back at Step {state['current_step']} | Stake: ${stake}")
                        continue

                    # -----------------------------------------------------------
                    # LIVE VOLATILITY GATE: computed entirely from the tick buffer
                    # in real time — no trade history needed. Compares the stdev
                    # of the most recent 20 tick-to-tick changes against the stdev
                    # of the preceding 60 tick-to-tick changes (the baseline).
                    # If recent volatility is more than 1.5x the baseline, the
                    # asset is behaving erratically right now and signal evaluation
                    # is skipped entirely until it calms below 1.2x.
                    # -----------------------------------------------------------
                    asset_tracker  = state.get("tick_tracker", {}).get(asset_str, {})
                    vol_buffer     = asset_tracker.get("buffer")
                    _vol_gate_open = True

                    if vol_buffer and len(vol_buffer) >= 40:
                        prices  = list(vol_buffer)
                        returns = [abs(prices[i+1] - prices[i]) for i in range(len(prices)-1)]
                        recent_vol   = statistics.pstdev(returns[-20:])  if len(returns) >= 20 else None
                        baseline_vol = statistics.pstdev(returns[-80:-20]) if len(returns) >= 80 else (
                                       statistics.pstdev(returns[:-20])   if len(returns) >= 40 else None)

                        if recent_vol and baseline_vol and baseline_vol > 0:
                            vol_ratio = recent_vol / baseline_vol
                            _vol_blocked = state.get("_vol_blocked", False)

                            if vol_ratio >= 1.5:
                                if not _vol_blocked:
                                    logging.warning(f"🌪️ VOLATILITY GATE CLOSED [{asset_str}]: ratio={vol_ratio:.2f}x — asset too erratic, skipping signals.")
                                state["_vol_blocked"] = True
                                _vol_gate_open = False
                            elif vol_ratio <= 1.2:
                                if _vol_blocked:
                                    logging.info(f"✅ VOLATILITY GATE OPEN [{asset_str}]: ratio={vol_ratio:.2f}x — resuming signals.")
                                state["_vol_blocked"] = False
                            else:
                                # in hysteresis band (1.2–1.5): maintain previous state
                                if _vol_blocked:
                                    _vol_gate_open = False

                    if not _vol_gate_open:
                        await asyncio.sleep(0.5)
                        continue

                    # Signal generation: regime-aware (trend pullback / range
                    # reversion) engine. See get_signals_improved().
                    signal = get_signals_improved(asset_str)
                    signal_meta = dict(state.get("_pending_signal_meta") or {})

                    # Suppress signal log spam: only evaluate+log if enough time
                    # has passed since the last trade (cooldown) and no trade is
                    # currently active. The signal is still computed (for the rate
                    # counter) but not logged repeatedly during the cooldown window.
                    in_cooldown = (current_time - last_trade_time) <= 15

                    if signal and not in_cooldown:
                        if state.get("is_paused"):
                            continue
                        last_trade_time = current_time
                        state["is_trading"] = True

                        logging.info(f"🎯 SIGNAL: {signal.upper()} | Level: {state['current_step'] + 1} | Stake: ${stake}")

                        # Deduct stake immediately so the UI balance reflects the
                        # live trade during its duration. background_order_watchdog
                        # adds back the full payout on a win, or leaves the deduction
                        # as-is on a loss.
                        state["daily_profit"] -= stake

                        await place_new_order(asset_str, stake, signal, meta=signal_meta)

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
            
            state.update({
                "active_asset": target_asset,
                "base_amount": round(float(data.get('base_amount', 1.0)), 3),
                "multipliers": data.get('multipliers', [1.0] * 10),
                "duration": int(data.get('duration', 5)),
                "chart_tf": int(data.get('chart_tf', 5)),
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

            async def start_session():
                try:
                    if state.get("client"):
                        try: await state["client"].disconnect()
                        except Exception: pass
                    
                    state["client"] = AsyncPocketOptionClient(state["ssid"], is_demo=True)
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

            # Hybrid payout: use scraped page value if available, else keep WebSocket value
            scraped_live = safe_int(data.get('scraped_payout'), 0)
            if scraped_live > 0:
                state["payout"] = scraped_live  # Page scrape is more accurate than WebSocket
            # If scraped_live == 0, payout_monitor() WebSocket value remains unchanged

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
            return web.json_response({"status": "ok"})
        
        if action == 'RESUME':
            # Manual RESUME — always works regardless of manual_pause flag
            state["is_paused"] = False
            state["manual_pause"] = False

        if action == 'AUTO_RESUME':
            # Auto RESUME from payout recovery — only works if not manually paused
            if not state.get("manual_pause", False):
                state["is_paused"] = False
            return web.json_response({"status": "ok"})

        if action == 'TOGGLE_PAUSE': 
            state["is_paused"] = not state["is_paused"]
            state["manual_pause"] = state["is_paused"]  # Sync manual_pause with toggled state
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
