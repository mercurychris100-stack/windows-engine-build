import asyncio
import sys
import os
import json
import re
from aiohttp import web
import aiohttp_cors

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def cleanup_logs():
    for log_file in ['bot_log.txt', 'bot_error.txt']:
        if os.path.exists(log_file):
            try:
                if os.path.getsize(log_file) > 1048576:
                    os.remove(log_file)
            except:
                continue

cleanup_logs()

if getattr(sys, 'frozen', False) or '__compiled__' in globals():
    sys.stdout = open('bot_log.txt', 'a', encoding='utf-8', buffering=1)
    sys.stderr = open('bot_error.txt', 'a', encoding='utf-8', buffering=1)

sys.path.append(os.path.join(os.getcwd(), 'pocketoptionapi-async'))
from pocketoptionapi_async import AsyncPocketOptionClient

def universal_asset_cleaner(raw_asset):
    raw_str = str(raw_asset).upper().strip()
    is_otc = 'OTC' in raw_str
    clean_key = re.sub('[^A-Z0-9]', '', raw_str.replace('OTC', ''))
    REGISTRY = {
        'KESUSD': 'KESUSD_otc', 
        'NGNUSD': 'NGNUSD_otc', 
        'ZARUSD': 'ZARUSD_otc', 
        'UAHUSD': 'UAHUSD_otc', 
        'USDVND': 'USDVND_otc', 
        'USDARS': 'USDARS_otc', 
        'GOLD': 'XAUUSD_otc' if is_otc else 'XAUUSD', 
        'BTCUSD': 'BTCUSD_otc' if is_otc else 'BTCUSD', 
        'BITCOIN': 'BTCUSD_otc', 
        'US100': 'US100_otc' if is_otc else 'US100', 
        'SP500': 'SP500_otc' if is_otc else 'SP500'
    }
    if clean_key in REGISTRY:
        return REGISTRY[clean_key]
    else:
        if is_otc:
            return f'{clean_key}_otc'
        else:
            return clean_key

state = {
    'client': None, 
    'is_running': False, 
    'multipliers': [0.0] * 10, 
    'base_amount': 1.0, 
    'current_stake': 1.0, 
    'current_step': 0, 
    'auto_mode': False, 
    'last_trade': {'asset': '', 'direction': '', 'expiry': 5}, 
    'processed_orders': set()
}

async def process_trade_result(order_id, expiry):
    if order_id in state['processed_orders']:
        return None
    else:
        try:
            await asyncio.sleep(expiry)
            result = None
            
            # 1. LIVE CHECK LOOP (Ceiling extended to 20 seconds / 100 loops)
            for _ in range(100):
                result = await state['client'].check_order_result(order_id)
                if result and hasattr(result, 'status') and (result.status.lower() != 'pending'):
                    break
                await asyncio.sleep(0.2)
            
            # 2. INTERNAL MEMORY FALLBACK (Highly reliable local dictionary scan)
            if not result or (hasattr(result, 'status') and result.status.lower() == 'pending'):
                print(f"⚠️ Live check timed out for order {order_id}. Querying library internal memory...")
                client_instance = state['client']
                
                for cache_dict_name in ['_order_results', '_orders', '_active_orders']:
                    if hasattr(client_instance, cache_dict_name):
                        cache_dict = getattr(client_instance, cache_dict_name)
                        if order_id in cache_dict:
                            cached_res = cache_dict[order_id]
                            if cached_res and hasattr(cached_res, 'status') and cached_res.status.lower() != 'pending':
                                result = cached_res
                                print(f"🔍 Success: Recovered order {order_id} from library cache: {cache_dict_name}")
                                break
                        else:
                            for k, v in cache_dict.items():
                                if getattr(v, 'order_id', None) == order_id or getattr(v, 'request_id', None) == order_id:
                                    if hasattr(v, 'status') and v.status.lower() != 'pending':
                                        result = v
                                        print(f"🔍 Success: Recovered order {order_id} via property scan in: {cache_dict_name}")
                                        break
                    if result:
                        break

            if result:
                state['processed_orders'].add(order_id)
                status_str = str(result.status).lower()
                profit = float(result.profit) if hasattr(result, 'profit') else 0
                is_actually_tie = any((x in status_str for x in ['draw', 'tie', 'equal'])) or profit == 0.0
                print(f'📊 DEBUG: Status={status_str} | Profit={profit}')
                if 'win' in status_str or profit > 0.01:
                    print('✅ WIN CONFIRMED: Resetting to Step 0.')
                    state['current_step'] = 0
                    state['current_stake'] = state['base_amount']
                    return
                else:
                    if is_actually_tie:
                        print(f"🟡 TIE DETECTED: Repeating Step {state['current_step']} (${state['current_stake']})")
                        if state['auto_mode'] and state['is_running']:
                            await place_new_order(state['last_trade']['asset'], state['current_stake'], state['last_trade']['direction'], expiry)
                        return None
                    else:
                        print(f"❌ LOSS CONFIRMED at Step {state['current_step']}")
                        if state['current_step'] < 9:
                            next_mult = state['multipliers'][state['current_step']]
                            if next_mult <= 0:
                                state['current_step'] = 0
                                state['current_stake'] = state['base_amount']
                                return
                            else:
                                state['current_stake'] = round(state['current_stake'] * next_mult, 2)
                                state['current_step'] += 1
                                if state['auto_mode']:
                                    if state['is_running']:
                                        await place_new_order(state['last_trade']['asset'], state['current_stake'], state['last_trade']['direction'], expiry)
                        else:
                            state['current_step'] = 0
                            state['current_stake'] = state['base_amount']
            else:
                # RISK-MANAGED FREEZE LOGIC: Locks state during network blackout
                print(f"🚨 CRITICAL DATA BLACKOUT: Order {order_id} could not be verified by live checks or memory.")
                print(f"🛑 SAFETY HALT: Freezing bot state at Step {state['current_step']} (${state['current_stake']}). Please check PO Platform manually.")
                state['is_running'] = False
                state['auto_mode'] = False
                
        except Exception as e:
            print(f'⚠️ Watcher Error: {e}')

async def place_new_order(asset, amount, direction, expiry):
    try:
        state['last_trade'] = {'asset': asset, 'direction': direction, 'expiry': expiry}
        order = await state['client'].place_order(asset, amount, direction, expiry)
        if order:
            if hasattr(order, 'order_id'):
                if len(state['processed_orders']) > 50:
                    state['processed_orders'].clear()
                asyncio.create_task(process_trade_result(order.order_id, expiry))
                print(f'🚀 TRADE: {asset} | {direction.upper()} | ${amount} | {expiry}s')
    except Exception as e:
        print(f'❌ Order Error: {e}')

async def handle_request(request):
    try:
        data = await request.json()
        action = data.get('action')
        if action == 'STATUS':
            bal, is_demo_val = (0.0, True)
            if state['client'] and state['client'].is_connected:
                try:
                    bal_data = await state['client'].get_balance()
                    bal, is_demo_val = (bal_data.balance, bal_data.is_demo)
                except:
                    bal, is_demo_val = (getattr(state['client'], 'balance', 0), getattr(state['client'], 'is_demo', True))
            return web.json_response({'status': 'ok', 'balance': bal, 'step': state['current_step'], 'current_stake': state['current_stake'], 'is_demo': is_demo_val, 'is_running': state['is_running']})
        else:
            if action == 'TRADE':
                asset = universal_asset_cleaner(data.get('asset', 'eurusd_otc'))
                expiry = int(data.get('expiry', 5))
                if state['current_step'] == 0:
                    state['current_stake'] = state['base_amount']
                await place_new_order(asset, state['current_stake'], data['direction'], expiry)
                return web.json_response({'status': 'ok'})
            else:
                if action == 'SYNC':
                    state['is_running'] = True
                    if 'multipliers' in data:
                        state['multipliers'] = data['multipliers']
                    if 'base_amount' in data:
                        state['base_amount'] = float(data['base_amount'])
                    if 'auto_mode' in data:
                        state['auto_mode'] = data['auto_mode']
                    input_ssid = data.get('ssid', '').strip()
                    if input_ssid:
                        if state['client']:
                            try:
                                await state['client'].disconnect()
                            except:
                                pass
                        state['client'] = AsyncPocketOptionClient(input_ssid, is_demo=data.get('is_demo', True))
                        await state['client'].connect()
                    return web.json_response({'status': 'ok'})
                else:
                    if action == 'STOP':
                        state.update({'is_running': False, 'auto_mode': False, 'current_step': 0})
                        state['processed_orders'].clear()
                        if state['client']:
                            try:
                                await state['client'].disconnect()
                            except Exception as ce:
                                print(f"⚠️ Clean disconnect skipped or failed: {ce}")
                        state['current_stake'] = state['base_amount']
                        return web.json_response({'status': 'ok'})
                    else:
                        return web.json_response({'status': 'ok'})
    except Exception as e:
        return web.json_response({'status': 'error', 'message': str(e)})

app = web.Application()
cors = aiohttp_cors.setup(app, defaults={'*': aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers='*', allow_headers='*', allow_methods=['POST', 'OPTIONS'])})
resource = app.router.add_resource('/control')
cors.add(resource.add_route('POST', handle_request))

if __name__ == '__main__':
    print('✅ Full Engine with Master Cleaner Ready @ http://127.0.0.1:5000')
    web.run_app(app, host='127.0.0.1', port=5000)
