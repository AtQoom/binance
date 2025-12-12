import asyncio
import json
import os
import sys
import time
import math
import warnings
import random
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

# 3rd party libraries
import pandas as pd
import numpy as np
try:
    import pandas_ta as ta
except ImportError:
    pass 

from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

# ==========================================
# ⚙️ 0. 시스템 설정 및 초기화
# ==========================================
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)
warnings.filterwarnings("ignore")

API_KEY = os.environ.get("BINANCE_API_KEY")
API_SECRET = os.environ.get("BINANCE_API_SECRET")
PROXY = os.environ.get("BINANCE_PROXY")

if not API_KEY or not API_SECRET:
    print("❌ [FATAL] API Key/Secret 미설정")
    sys.exit(1)

# ==========================================
# 📊 1. 전략 파라미터 (RSI 업데이트됨)
# ==========================================
# 1. 심볼 및 리스크
SYMBOL_LIMIT = 3            
LEVERAGE = 10               
INITIAL_ENTRY_PCT = 0.05    
MIN_NOTIONAL = 6.0          

# 2. 진입 필터 (Sniper Entry) - [수정 완료]
RSI_3M_LONG = 30        # (수정됨: 25 -> 30)
RSI_3M_SHORT = 70       # (수정됨: 75 -> 70)
RSI_1M_LONG_TH = 16     # (수정됨: 10 -> 16)
RSI_1M_SHORT_TH = 84    # (수정됨: 90 -> 84)

# 3. 기울기 (Impulse) 조건
# (ATR 대비 3배 이상의 급격한 가격 변화 = 급격한 기울기)
IMPULSE_MULTIPLIER = 3.0    

# 4. 물타기(DCA) & 익절(TP)
ATR_PERIOD = 14
DCA_MULTIPLIER = 2.0        
MAX_DCA_COUNT = 3           
DCA_ATR_GAPS = [3.0, 5.0, 7.0] 
TP_ATR_MULT = 2.5           
MIN_TP_PCT = 0.01           

# 5. 시스템 설정
STATE_FILE = "bot_state.json"
HISTORY_LIMIT = 400         # 초기 로딩 캔들 수
MEMORY_MAX_LEN = 1000       # 메모리 유지 갯수
REFRESH_INTERVAL = 3600     # 심볼 정보 갱신 (1시간)
TP_UPDATE_INTERVAL = 900    # TP 갱신 (15분)

# ==========================================
# 💾 2. 상태 관리 (State Manager)
# ==========================================
class StateManager:
    def __init__(self):
        self.file = STATE_FILE
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r') as f:
                    self.data = json.load(f)
                print(f"💾 상태 로드 완료: {len(self.data)}개 포지션")
            except:
                self.data = {}

    def save(self):
        try:
            with open(self.file, 'w') as f:
                json.dump(self.data, f, indent=4)
        except: pass

    def update(self, symbol, side, dca_count):
        self.data[symbol] = {
            'side': side, 'dca_count': dca_count, 'updated_at': str(datetime.now())
        }
        self.save()

    def remove(self, symbol):
        if symbol in self.data:
            del self.data[symbol]
            self.save()

    def get_dca_count(self, symbol):
        return self.data.get(symbol, {}).get('dca_count', 0)

# ==========================================
# 🤖 3. 하이브리드 스나이퍼 봇 (Core)
# ==========================================
class HybridSniperBot:
    def __init__(self):
        self.client = None
        self.bm = None
        self.state = StateManager()
        
        # 데이터 저장소
        self.symbols = []
        self.symbol_info = {}
        self.positions = {}
        self.klines = {}           # {symbol: DataFrame(1m)}
        self.ready_symbols = set() # 웜업 완료된 심볼
        
        # 관리 변수
        self.cooldowns = {}        # 주문 에러 쿨다운
        self.last_tp_update = {}   # TP 갱신 시간
        self.candidates = 0        # 후보군 카운트
        self.last_heartbeat = 0    

    async def initialize(self):
        print("🔌 [Init] Binance API 연결...")
        self.client = await AsyncClient.create(API_KEY, API_SECRET, requests_params={'proxy': PROXY} if PROXY else None)
        await self.refresh_exchange_info(is_init=True)
        
    async def refresh_exchange_info(self, is_init=False, target_symbol=None):
        """심볼 정보 갱신 (1시간 주기 or 에러 시 긴급)"""
        try:
            info = await self.client.futures_exchange_info()
            
            exclude = ['USDCUSDT', 'USDPUSDT', 'FDUSDUSDT', 'BUSDUSDT', 'TUSDUSDT']
            now_ms = time.time() * 1000
            new_list_ms = 14 * 24 * 3600 * 1000

            temp_symbols = []
            for s in info['symbols']:
                sym = s['symbol']
                if target_symbol and sym != target_symbol: continue

                if s['quoteAsset'] != 'USDT' or s['status'] != 'TRADING': continue
                if sym in exclude: continue
                if s.get('onboardDate') and (now_ms - s['onboardDate'] < new_list_ms): continue

                if not target_symbol: temp_symbols.append(sym)

                prec_qty = 0
                prec_price = 0
                min_qty = 0.0
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        prec_qty = int(round(-math.log(float(f['stepSize']), 10)))
                        min_qty = float(f['minQty'])
                    elif f['filterType'] == 'PRICE_FILTER':
                        prec_price = int(round(-math.log(float(f['tickSize']), 10)))
                
                self.symbol_info[sym] = {'qty_prec': prec_qty, 'price_prec': prec_price, 'min_qty': min_qty}
                if sym not in self.klines: self.klines[sym] = pd.DataFrame()

            if not target_symbol:
                self.symbols = temp_symbols
                if is_init: print(f"✅ 심볼 로드: {len(self.symbols)}개 (필터 적용)")
            else:
                print(f"♻️ [Repair] {target_symbol} 정보 갱신 완료")

        except Exception as e:
            print(f"❌ 정보 갱신 실패: {e}")

    async def slow_warmup_worker(self):
        """🐢 웜업: 과거 데이터 로딩 (REST)"""
        print("🔥 [Warmup] 과거 데이터 로딩 시작 (Safe Mode)...")
        total = len(self.symbols)
        priority = list(self.state.data.keys())
        others = [s for s in self.symbols if s not in priority]
        
        for idx, sym in enumerate(priority + others):
            try:
                k = await self.client.futures_klines(symbol=sym, interval='1m', limit=HISTORY_LIMIT)
                if k:
                    df = pd.DataFrame(k).iloc[:, :6]
                    df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                    df = df.astype(float)
                    df['time'] = pd.to_datetime(df['time'], unit='ms')
                    df.set_index('time', inplace=True)
                    self.klines[sym] = df
                    self.ready_symbols.add(sym)
            except: pass
            
            await asyncio.sleep(0.5) 
            if idx > 0 and idx % 50 == 0:
                print(f"⏳ 로딩 중... {idx}/{total}")

        print("🎉 [Warmup] 전체 데이터 준비 완료!")

    def resample_data(self, df_1m, interval):
        """🧪 1m -> 3m/15m 변환"""
        if df_1m.empty: return pd.DataFrame()
        try:
            logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
            return df_1m.resample(interval).agg(logic).dropna()
        except: return pd.DataFrame()

    async def process_stream_data(self, msg):
        """⚡ 웹소켓 데이터 처리"""
        if 'data' not in msg: return
        data = msg['data']
        sym = data['s']
        k = data['k']
        
        row_time = pd.to_datetime(k['t'], unit='ms')
        new_row = pd.DataFrame([{
            'open': float(k['o']), 'high': float(k['h']), 'low': float(k['l']), 
            'close': float(k['c']), 'volume': float(k['v'])
        }], index=[row_time])

        if sym not in self.klines: self.klines[sym] = new_row
        else:
            if not self.klines[sym].empty and self.klines[sym].index[-1] == row_time:
                self.klines[sym].update(new_row)
            else:
                self.klines[sym] = pd.concat([self.klines[sym], new_row])
                if len(self.klines[sym]) > MEMORY_MAX_LEN:
                    self.klines[sym] = self.klines[sym].iloc[-MEMORY_MAX_LEN:]

        if sym in self.ready_symbols:
            await self.check_strategy(sym, float(k['c']))

    async def check_strategy(self, sym, current_price):
        """🧠 전략 코어 (기울기/RSI 체크)"""
        if sym in self.cooldowns:
            if time.time() < self.cooldowns[sym]: return
            del self.cooldowns[sym]

        df_1m = self.klines[sym]
        if len(df_1m) < 50: return

        try:
            # --- 지표 계산 ---
            rsi_1m = df_1m.ta.rsi(length=14).iloc[-1]
            bb = df_1m.ta.bbands(length=20, std=2.0)
            bb_low, bb_high = bb.iloc[-1, 0], bb.iloc[-1, 2]
            atr_1m = df_1m.ta.atr(length=14).iloc[-1]
            
            # Resampling
            df_3m = self.resample_data(df_1m, '3min')
            if len(df_3m) < 14: return
            rsi_3m = df_3m.ta.rsi(length=14).iloc[-1]

            df_15m = self.resample_data(df_1m, '15min')
            if len(df_15m) < 14: return
            atr_15m = df_15m.ta.atr(length=ATR_PERIOD).iloc[-1]

            # --- 로직 실행 ---
            pos = self.positions.get(sym)
            
            # [A] 보유 중
            if pos:
                await self.manage_position(sym, pos, current_price, atr_15m, rsi_1m, bb_low, bb_high)
            
            # [B] 미보유: 신규 진입 (기울기 포함)
            else:
                if len(self.positions) >= SYMBOL_LIMIT: return
                
                open_p = df_1m['open'].iloc[-1]
                move = open_p - current_price 
                
                is_candidate = False
                
                # LONG: RSI + BB + 급락(기울기)
                if (rsi_3m < RSI_3M_LONG and current_price < bb_low and 
                    rsi_1m < RSI_1M_LONG_TH and move > (atr_1m * IMPULSE_MULTIPLIER)):
                    
                    print(f"🚀 [SIGNAL] {sym} LONG (R3:{rsi_3m:.1f} R1:{rsi_1m:.1f} Move:{move:.2f})")
                    await self.execute_entry(sym, 'LONG', current_price, atr_15m)
                    is_candidate = True

                # SHORT: RSI + BB + 급등(기울기)
                elif (rsi_3m > RSI_3M_SHORT and current_price > bb_high and 
                      rsi_1m > RSI_1M_SHORT_TH and (-move) > (atr_1m * IMPULSE_MULTIPLIER)):
                    
                    print(f"🚀 [SIGNAL] {sym} SHORT (R3:{rsi_3m:.1f} R1:{rsi_1m:.1f} Move:{move:.2f})")
                    await self.execute_entry(sym, 'SHORT', current_price, atr_15m)
                    is_candidate = True
                
                if not is_candidate and (rsi_3m < RSI_3M_LONG or rsi_3m > RSI_3M_SHORT):
                    self.candidates += 1

        except: pass

    async def manage_position(self, sym, pos, price, atr, rsi_1m, bb_low, bb_high):
        """포지션 관리"""
        if time.time() - self.last_tp_update.get(sym, 0) > TP_UPDATE_INTERVAL:
            await self.update_tp_order(sym, pos, atr)

        dca_cnt = pos['dca']
        if dca_cnt >= MAX_DCA_COUNT: return
        
        gap = DCA_ATR_GAPS[min(dca_cnt, len(DCA_ATR_GAPS)-1)] * atr
        entry = pos['entry']
        side = pos['side']
        
        do_dca = False
        if side == 'LONG':
            if (entry - price) >= gap:
                if rsi_1m < 35 and price < bb_low: do_dca = True
        else:
            if (price - entry) >= gap:
                if rsi_1m > 65 and price > bb_high: do_dca = True
                
        if do_dca:
            qty = pos['amount'] * DCA_MULTIPLIER
            print(f"🌊 [DCA] {sym} #{dca_cnt+1} 진입")
            await self.execute_order(sym, 'BUY' if side=='LONG' else 'SELL', qty, is_dca=True)

    async def execute_entry(self, sym, side, price, atr):
        """신규 진입"""
        try:
            acc = await self.client.futures_account()
            bal = float(acc['totalWalletBalance'])
            
            val = bal * INITIAL_ENTRY_PCT
            if val < MIN_NOTIONAL: val = MIN_NOTIONAL * 1.1
            
            qty = self.calc_qty(sym, val, price)
            if qty == 0: return

            order_side = 'BUY' if side == 'LONG' else 'SELL'
            if await self.execute_order(sym, order_side, qty):
                self.state.update(sym, side, 0)
                # 중복 방지
                self.positions[sym] = {'symbol': sym, 'side': side, 'amount': qty, 'entry': price, 'dca': 0}
                await self.update_tp_order(sym, self.positions[sym], atr)
                
        except Exception as e:
            print(f"⚠️ 진입 실패 {sym}: {e}")

    async def execute_order(self, sym, side, qty, is_dca=False, reduce_only=False):
        """주문 실행"""
        try:
            if not is_dca and not reduce_only:
                try:
                    await self.client.futures_change_leverage(symbol=sym, leverage=LEVERAGE)
                except: pass

            await self.client.futures_create_order(
                symbol=sym, side=side, type='MARKET', quantity=qty, reduceOnly=reduce_only
            )
            
            if is_dca:
                pos = self.positions.get(sym)
                if pos: self.state.update(sym, pos['side'], pos['dca'] + 1)
            
            return True

        except BinanceAPIException as e:
            print(f"❌ 주문 오류 {sym}: {e}")
            if e.code in [-1013, -1111]:
                print(f"🔧 {sym} 정보 긴급 갱신")
                await self.refresh_exchange_info(target_symbol=sym)
            self.cooldowns[sym] = time.time() + 300 
            return False
        except: return False

    async def update_tp_order(self, symbol, pos, atr):
        """TP 주문 갱신"""
        try:
            entry = pos.get('entry_price', pos.get('entry', 0))
            qty = pos['amount']
            side = pos['side']
            
            min_profit = entry * MIN_TP_PCT
            target_profit = max(atr * TP_ATR_MULT, min_profit)
            
            tp_price = entry + target_profit if side == 'LONG' else entry - target_profit
            
            prec = self.symbol_info[symbol]['price_prec']
            tp_price = round(tp_price, prec)
            
            tp_side = 'SELL' if side == 'LONG' else 'BUY'
            
            await self.client.futures_cancel_all_open_orders(symbol=symbol)
            await self.client.futures_create_order(
                symbol=symbol, side=tp_side, type='LIMIT', 
                quantity=qty, price=tp_price, timeInForce='GTC', reduceOnly=True
            )
            self.last_tp_update[symbol] = time.time()
            print(f"♻️ [TP] {symbol} 목표가 재설정: ${tp_price}")
            
        except: pass

    def calc_qty(self, sym, usdt, price):
        """수량 계산"""
        if usdt < MIN_NOTIONAL: return 0.0
        info = self.symbol_info.get(sym)
        if not info: return 0.0
        
        raw = usdt / price
        step = 10 ** -info['qty_prec']
        qty = float(Decimal(str(raw)).quantize(Decimal(str(step)), rounding=ROUND_DOWN))
        
        return qty if qty >= info['min_qty'] else 0.0

    async def sync_account(self):
        """계좌 동기화"""
        while True:
            try:
                acc = await self.client.futures_account()
                real_pos = {}
                for p in acc['positions']:
                    amt = float(p['positionAmt'])
                    if amt != 0:
                        sym = p['symbol']
                        side = 'LONG' if amt > 0 else 'SHORT'
                        dca = self.state.get_dca_count(sym)
                        real_pos[sym] = {
                            'symbol': sym, 'side': side, 'amount': abs(amt), 
                            'entry': float(p['entryPrice']), 'dca': dca
                        }
                
                self.positions = real_pos
                for s in list(self.state.data.keys()):
                    if s not in real_pos: self.state.remove(s)
                    
            except: pass
            await asyncio.sleep(10)

    async def scheduled_tasks(self):
        """정기 작업"""
        while True:
            now = time.time()
            dt = datetime.now()
            
            if dt.minute % 3 == 0 and dt.second < 5:
                if now - self.last_heartbeat > 60:
                    print(
                        f"💓 [Status] {dt.strftime('%H:%M')} | "
                        f"Pos: {len(self.positions)}/{SYMBOL_LIMIT} | "
                        f"Ready: {len(self.ready_symbols)}/{len(self.symbols)} | "
                        f"Cand: {self.candidates}"
                    )
                    self.candidates = 0
                    self.last_heartbeat = now
            
            if int(now) % REFRESH_INTERVAL == 0:
                await self.refresh_exchange_info()
                
            await asyncio.sleep(1)

    async def run(self):
        await self.initialize()
        
        self.bm = BinanceSocketManager(self.client)
        streams = [f"{s.lower()}@kline_1m" for s in self.symbols]
        ts = self.bm.multiplex_socket(streams)
        
        asyncio.create_task(self.slow_warmup_worker())
        asyncio.create_task(self.sync_account())
        asyncio.create_task(self.scheduled_tasks())
        
        print(f"🚀 [Hybrid Bot] 가동 시작 (Streams: {len(streams)})")
        
        async with ts as tscm:
            while True:
                res = await tscm.recv()
                await self.process_stream_data(res)

if __name__ == "__main__":
    bot = HybridSniperBot()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        print("🛑 종료")
