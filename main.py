import asyncio
import time
import math
import json
import os
import sys
import warnings  # [추가]

# [추가] 지저분한 경고 메시지 숨기기
warnings.filterwarnings("ignore", category=UserWarning, module='pandas_ta_remake')
warnings.filterwarnings("ignore", category=DeprecationWarning)

from decimal import Decimal, ROUND_DOWN
from datetime import datetime

# 3rd party libraries
import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_remake as ta

# python-binance imports
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

# ==========================================
# ⚙️ 1. 사용자 설정 (CONFIG)
# ==========================================
# 새 코드 (환경 변수 강제)
API_KEY = os.environ.get("BINANCE_API_KEY")
API_SECRET = os.environ.get("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    print("❌ 환경 변수 오류: BINANCE_API_KEY 또는 SECRET이 설정되지 않았습니다.")
    # 디버깅용: 현재 설정된 모든 환경 변수 이름만 출력 (값은 보안상 출력 금지)
    print("설정된 변수 목록:", list(os.environ.keys()))
    sys.exit(1)
# ----------------- 전략 파라미터 -----------------
# 1. 심볼 및 리스크
SYMBOL_LIMIT = 3            # 총 보유 심볼 수 (Long + Short 합계)
LEVERAGE = 10               # 레버리지 10배
INITIAL_ENTRY_PCT = 0.05    # 1차 진입: 총 시드의 5% (안전 모드)
MIN_NOTIONAL = 6.0          # 최소 주문 금액 (여유있게 6불)

# 2. 진입 필터 (Sniper Entry) - 3중 필터
RSI_3M_LONG_TH = 25
RSI_3M_SHORT_TH = 75
RSI_1M_LONG_TH = 10
RSI_1M_SHORT_TH = 90
# 3차 필터: BB 이탈 (로직 내 구현)

# 3. 물타기 & 익절 (ATR 기반)
ATR_PERIOD = 14
ATR_TIMEFRAME = '15m'

# DCA 설정 (총 4회 진입: 1차 + 추가 3회)
# 보유 수량의 2배씩 추가 (1 -> 2 -> 6 -> 18)
DCA_MULTIPLIER = 2.0        # 수량 배수
MAX_DCA_COUNT = 3           # 추가 매수 최대 3회 (총 4회 진입)

# 차수별 ATR 간격 (2차, 3차, 4차 진입 시점)
DCA_ATR_GAPS = [3.0, 5.0, 7.0] 

# 익절 설정
TP_ATR_MULT = 2.5           # 목표: 평단 + 2.5 ATR
MIN_TP_PCT = 0.010          # 최소 수익률 1.0% 보장

# ----------------- 시스템 설정 -----------------
STATE_FILE = "bot_state.json"
SCAN_INTERVAL = 2.0         # 스캔 루프 딜레이 (초)
TP_UPDATE_INTERVAL = 900    # TP 갱신 주기 (15분 = 900초)

# ==========================================
# 💾 2. 상태 관리 (State Manager)
# ==========================================
class StateManager:
    def __init__(self):
        self.file = STATE_FILE
        self.data = {} # {symbol: {'dca_count': 0, 'side': 'LONG'}}
        self.load()
        
    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r') as f:
                    self.data = json.load(f)
                print(f"💾 상태 파일 로드 완료: {len(self.data)}개 포지션 데이터")
            except Exception as e:
                print(f"⚠️ 상태 파일 로드 실패 (초기화): {e}")
                self.data = {}
        else:
            self.data = {}

    def save(self):
        try:
            with open(self.file, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"⚠️ 상태 저장 실패: {e}")

    def update_position(self, symbol, side, dca_count):
        self.data[symbol] = {
            'side': side,
            'dca_count': dca_count,
            'updated_at': str(datetime.now())
        }
        self.save()

    def remove_position(self, symbol):
        if symbol in self.data:
            del self.data[symbol]
            self.save()

    def get_dca_count(self, symbol):
        return self.data.get(symbol, {}).get('dca_count', 0)

# ==========================================
# 🤖 3. 봇 핵심 로직 (Binance ATR Sniper Bot)
# ==========================================
class BinanceSniperBot:
    def __init__(self):
        self.client = None
        self.bm = None
        self.state = StateManager() # 여기서 딱 한 번만 생성됨 (정상)
        
        # 런타임 데이터
        self.symbols = []
        self.positions = {}
        self.symbol_info = {}
        self.last_tp_update = {}
        
        # [필수] 캐시 저장소는 여기에 있어야 합니다!
        self.metrics_cache = {} 
        
        self.best_candidate = {'symbol': None, 'rsi_1m': 50, 'gap': 999} 

    async def initialize(self):
        print("🔌 Binance API 연결 중...")
        # [수정] 프록시 설정 (Railway 환경변수 있으면 적용)
        proxy = os.environ.get("BINANCE_PROXY")
        self.client = await AsyncClient.create(API_KEY, API_SECRET, requests_params={'proxy': proxy} if proxy else None)
        
        # [추가] 관심종목 관리용 변수 초기화
        self.watch_list = set()
        self.last_slow_scan = 0
        
        info = await self.client.futures_exchange_info()
        count = 0
        
        # 제외 목록 (스테이블 등)
        exclude_coins = ['USDCUSDT', 'USDPUSDT', 'FDUSDUSDT', 'BUSDUSDT', 'TUSDUSDT'] 
        
        # [설정] 신규 상장 필터: 14일
        NEW_LISTING_THRESHOLD_MS = 14 * 24 * 60 * 60 * 1000
        current_time_ms = time.time() * 1000

        for s in info['symbols']:
            if s['quoteAsset'] != 'USDT' or s['status'] != 'TRADING' or s['contractType'] != 'PERPETUAL':
                continue

            sym = s['symbol']
            if sym in exclude_coins: continue

            # 신규 상장 제외
            onboard_date = s.get('onboardDate')
            if onboard_date:
                if (current_time_ms - onboard_date) < NEW_LISTING_THRESHOLD_MS: continue

            self.symbols.append(sym)
            
            # 필터 정보 파싱 (기존 동일)
            prec_qty = 0
            prec_price = 0
            min_qty = 0.0
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    prec_qty = int(round(-math.log(step_size, 10)))
                    min_qty = float(f['minQty'])
                elif f['filterType'] == 'PRICE_FILTER':
                    tick_size = float(f['tickSize'])
                    prec_price = int(round(-math.log(tick_size, 10)))
            
            self.symbol_info[sym] = {'qty_prec': prec_qty, 'price_prec': prec_price, 'min_qty': min_qty}
            count += 1
        
        print(f"✅ 거래 가능 심볼 로드: {count}개 (Smart Scan Ready)")

    async def update_account_data(self):
        """계좌 잔고 및 포지션 동기화 (핵심)"""
        try:
            acc = await self.client.futures_account()
            
            # 1. 총 자산 (Wallet Balance) - 진입 비중 계산용
            total_wallet_balance = 0.0
            available_balance = 0.0
            total_position_notional = 0.0
            
            for a in acc['assets']:
                if a['asset'] == 'USDT':
                    total_wallet_balance = float(a['walletBalance'])
                    available_balance = float(a['availableBalance'])
                    break
            
            # 2. 포지션 동기화
            api_positions = {}
            for p in acc['positions']:
                amt = float(p['positionAmt'])
                if amt != 0:
                    sym = p['symbol']
                    side = 'LONG' if amt > 0 else 'SHORT'

                    # 현재 포지션 명목가 (1배 기준 노출 금액)
                    notional = float(p.get('notional', 0.0))
                    total_position_notional += abs(notional)

                    saved_dca = self.state.get_dca_count(sym)

                    api_positions[sym] = {
                        'symbol': sym,
                        'side': side,
                        'amount': abs(amt),
                        'entry_price': float(p['entryPrice']),
                        'unrealizedProfit': float(p['unrealizedProfit']),
                        'dca_count': saved_dca
                    }

            self.positions = api_positions
            
            # 3. 상태 파일 청소 (청산된 포지션 제거)
            # 상태 파일에는 있는데 API 포지션에는 없으면 -> 청산된 것임
            # list()로 키 복사본을 만들어 순회 중 삭제 에러 방지
            for sym in list(self.state.data.keys()):
                if sym not in self.positions:
                    self.state.remove_position(sym)
                    # print(f"🧹 청산 확인 및 상태 제거: {sym}")

            # 4. 1배 노출 비율 계산
            exposure_pct = 0.0
            if total_wallet_balance > 0:
                exposure_pct = (total_position_notional / total_wallet_balance) * 100.0

            return total_wallet_balance, available_balance, exposure_pct

        except Exception as e:
            print(f"❌ 계좌 업데이트 오류: {e}")
            return 0, 0, 0.0

    # [신규 추가] 3분봉 RSI 스캔 함수 (가볍게 호출)
    async def scan_3m_rsi(self, symbol):
        try:
            # 30개만 가져와서 최소한의 데이터로 계산
            k = await self.client.futures_klines(symbol=symbol, interval='3m', limit=30)
            if not k: return False
            
            df = pd.DataFrame(k).iloc[:,:6]
            df.columns = ['t','o','h','l','c','v']
            df['c'] = df['c'].astype(float)
            
            # 여기서 WATCH_RSI_LOW/HIGH 상수는 전역변수로 설정되어 있어야 합니다 (예: 35, 65)
            # 만약 없으면 직접 숫자를 넣으세요 (35, 65)
            rsi = df.ta.rsi(length=14).iloc[-1]
            
            # 관심종목 기준 (35이하 or 65이상)
            if rsi <= 35 or rsi >= 65:
                return True
            return False
        except: return False

    async def get_market_metrics(self, symbol):
        """
        [최적화됨] 하이브리드 캐싱 + ATR 기반 변동성 계산
        - ATR(15m), RSI(3m): 60초 캐싱
        - RSI(1m), ATR(1m), Price: 실시간 계산
        """
        try:
            now = time.time()
            
            # 1. 캐시 데이터 확인
            cached_data = self.metrics_cache.get(symbol)
            is_cache_valid = False
            
            if cached_data:
                if now - cached_data['updated_at'] < 60:
                    is_cache_valid = True
            
            # ---------------------------------------------------
            # 공통: 실시간 데이터 (1m) 계산
            # ---------------------------------------------------
            # 캐시가 있든 없든 1m 데이터는 항상 새로 가져와야 함 (스나이핑 핵심)
            # 단, 캐시가 없을 때는 15m, 3m도 같이 가져와야 하므로 분기 처리
            
            task_1m = self.client.futures_klines(symbol=symbol, interval='1m', limit=30)
            
            if is_cache_valid:
                # 캐시 있으면 1m만 호출
                k_1m = await task_1m
                atr_15m = cached_data['atr']
                rsi_3m = cached_data['rsi_3m']
            else:
                # 캐시 없으면 3개 다 호출 (병렬)
                task_15m = self.client.futures_klines(symbol=symbol, interval='15m', limit=30)
                task_3m = self.client.futures_klines(symbol=symbol, interval='3m', limit=30)
                
                results = await asyncio.gather(task_15m, task_3m, task_1m, return_exceptions=True)
                k_15m, k_3m, k_1m = results
                
                if not k_15m or not k_3m or not k_1m: return None
                
                # 15m ATR 계산
                df_15m = pd.DataFrame(k_15m).iloc[:, :6]
                df_15m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_15m[['high', 'low', 'close']] = df_15m[['high', 'low', 'close']].astype(float)
                atr_15m = df_15m.ta.atr(length=ATR_PERIOD).iloc[-1]
                
                # 3m RSI 계산
                df_3m = pd.DataFrame(k_3m).iloc[:, :6]
                df_3m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_3m['close'] = df_3m['close'].astype(float)
                rsi_3m = df_3m.ta.rsi(length=14).iloc[-1]
                
                # 캐시 업데이트
                self.metrics_cache[symbol] = {
                    'atr': atr_15m,
                    'rsi_3m': rsi_3m,
                    'updated_at': now
                }

            # ---------------------------------------------------
            # 1m 데이터 처리 (핵심: 실시간 변동성 분석)
            # ---------------------------------------------------
            if not k_1m: return None
            
            df_1m = pd.DataFrame(k_1m).iloc[:, :6]
            df_1m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
            df_1m[['open', 'high', 'low', 'close']] = df_1m[['open', 'high', 'low', 'close']].astype(float)
            
            # 1. 1m RSI
            rsi_1m = df_1m.ta.rsi(length=14).iloc[-1]
            
            # 2. 볼린저 밴드
            bb = df_1m.ta.bbands(length=20, std=2.0)
            bb_cols = bb.columns.tolist() # [lower, mid, upper, bandwidth, percent]
            bb_low = bb[bb_cols[0]].iloc[-1]
            bb_high = bb[bb_cols[2]].iloc[-1]
            
            # 3. [신규] 1m ATR (평소 1분간 변동폭)
            atr_1m_series = df_1m.ta.atr(length=14)
            if atr_1m_series is None: return None
            atr_1m = atr_1m_series.iloc[-1]
            
            # 4. [신규] 현재 봉의 실제 변동폭 (시가 - 종가)
            # 양수 = 하락(음봉)의 길이, 음수 = 상승(양봉)의 길이
            current_open = float(df_1m['open'].iloc[-1])
            current_close = float(df_1m['close'].iloc[-1])
            current_move = current_open - current_close 
            
            return {
                'atr': atr_15m,         # 익절/물타기용 (15분 기준)
                'atr_1m': atr_1m,       # [신규] 진입 판단용 (1분 기준 변동성)
                'current_move': current_move, # [신규] 현재 봉의 움직임
                'rsi_3m': rsi_3m,
                'rsi_1m': rsi_1m,
                'bb_low': bb_low,
                'bb_high': bb_high,
                'price': current_close
            }

        except Exception as e:
            # print(f"⚠️ 지표 계산 실패 ({symbol}): {e}")
            return None

    def calc_qty_from_usdt(self, symbol, usdt_val, price):
        """USDT 금액 -> 코인 수량 변환 (최소 주문금액 체크 포함)"""
        if usdt_val < MIN_NOTIONAL: 
            return 0.0
            
        raw_qty = usdt_val / price
        info = self.symbol_info[symbol]
        step = 10 ** -info['qty_prec']
        
        # 내림 처리 (ROUND_DOWN)로 증거금 부족 방지
        qty = float(Decimal(str(raw_qty)).quantize(Decimal(str(step)), rounding=ROUND_DOWN))
        
        if qty < info['min_qty']:
            return 0.0
            
        return qty

    async def execute_order(self, symbol, side, qty, reduce_only=False):
        """주문 실행 Wrapper"""
        try:
            # 레버리지 10배 확인 (혹시 안되어있을까봐 진입 전 세팅)
            if not reduce_only:
                try:
                    await self.client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
                except: pass # 이미 되어있으면 에러날 수 있음 무시

            order = await self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=qty,
                reduceOnly=reduce_only
            )
            print(f"⚡ [EXECUTE] {symbol} {side} {qty} (Reduce:{reduce_only})")
            return True
        except BinanceAPIException as e:
            print(f"❌ 주문 실패 {symbol}: {e}")
            return False

    async def update_tp_order(self, symbol, pos, atr):
        """ATR 기반 TP 주문 갱신 (15분 주기)"""
        now = time.time()
        last = self.last_tp_update.get(symbol, 0)
        
        # 15분 미만이면 스킵
        if now - last < TP_UPDATE_INTERVAL:
            return

        entry = pos['entry_price']
        qty = pos['amount']
        
        # 목표가 계산: 평단 + 2.5 ATR
        # 최소 수익률(1.0%) 보장 로직
        min_profit_dist = entry * MIN_TP_PCT
        atr_profit_dist = atr * TP_ATR_MULT
        target_dist = max(atr_profit_dist, min_profit_dist)
        
        if pos['side'] == 'LONG':
            tp_price = entry + target_dist
            tp_side = 'SELL'
        else:
            tp_price = entry - target_dist
            tp_side = 'BUY'
            
        # 가격 정밀도 맞춤
        prec = self.symbol_info[symbol]['price_prec']
        tp_price = round(tp_price, prec)
        
        # 주문 갱신
        try:
            # 기존 TP 주문 취소
            await self.client.futures_cancel_all_open_orders(symbol=symbol)
            
            # 신규 TP 주문
            await self.client.futures_create_order(
                symbol=symbol,
                side=tp_side,
                type='LIMIT',
                timeInForce='GTC',
                quantity=qty,
                price=tp_price,
                reduceOnly=True
            )
            
            self.last_tp_update[symbol] = now
            print(f"♻️ [TP UPDATE] {symbol}: ${tp_price} (ATR:{atr:.4f})")
            
        except Exception as e:
            print(f"⚠️ TP 갱신 오류 {symbol}: {e}")

    async def run_loop(self):
        """메인 실행 루프 (Smart Scan 적용: 3분 주기 선별 + 3초 주기 집중 감시)"""
        await self.initialize()
        print(f"🚀 ATR Sniper Bot 가동 시작! (Target: {INITIAL_ENTRY_PCT*100}% Entry / Max {SYMBOL_LIMIT} Symbols)")
        
        # [설정] 진입 파라미터 (기존 로직 유지)
        IMPULSE_MULTIPLIER = 3.0
        RSI_ENTRY_TH = 16
        RSI_3M_LONG = 30
        RSI_3M_SHORT = 70
        
        # [Smart Scan 설정]
        FAST_SCAN_INTERVAL = 3.0    # 3초마다 정밀 검사 (집중 감시)
        SLOW_SCAN_INTERVAL = 180.0  # 3분마다 전체 스캔 (관심종목 갱신)
        
        last_heartbeat_time = time.time()
        HEARTBEAT_INTERVAL = 300  # 5분
        
        while True:
            total_bal = 0.0
            avail_bal = 0.0
            exposure_pct = 0.0
            
            try:
                # 1. 계좌 및 포지션 업데이트 (기존 동일)
                res = await self.update_account_data()
                if res:
                    total_bal, avail_bal, exposure_pct = res
                    
                if total_bal <= 0:
                    print("⚠️ 계좌 잔고 조회 실패. 대기...")
                    await asyncio.sleep(5)
                    continue

                # ========================================================
                # [Smart Scan Core] 3분마다 전체 종목 스캔 -> 관심종목(Watch List) 갱신
                # ========================================================
                if time.time() - self.last_slow_scan > SLOW_SCAN_INTERVAL:
                    print("🔍 [Slow Scan] 전체 시장 스캔 중... (관심종목 선별)")
                    new_watch = set()
                    
                    # 5개씩 끊어서 요청 (API 부하 분산)
                    chunk_size = 5
                    for i in range(0, len(self.symbols), chunk_size):
                        chunk = self.symbols[i:i+chunk_size]
                        # 병렬 처리로 3분봉 RSI 확인
                        tasks = [self.scan_3m_rsi(s) for s in chunk]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        for sym, hit in zip(chunk, results):
                            if hit is True: new_watch.add(sym)
                        
                        await asyncio.sleep(0.5) # API 밴 방지용 딜레이

                    self.watch_list = new_watch
                    print(f"📋 관심종목 업데이트 완료: {len(self.watch_list)}개")
                    self.last_slow_scan = time.time()

                current_pos_count = len(self.positions)
                
                # 생존 신고 (Heartbeat) - 기존 디버그 출력 유지
                current_time = time.time()
                if current_time - last_heartbeat_time > HEARTBEAT_INTERVAL:
                    cand_info = "대기중..."
                    if self.best_candidate['symbol']:
                        c = self.best_candidate
                        ratio = c.get('move_ratio', 0.0)
                        bb_mark = "O" if c.get('bb_break') else "X"
                        cand_info = (
                            f"{c['symbol']}({c['type'][0]}) "
                            f"R1:{c['rsi_1m']:.1f} "
                            f"R3:{c['rsi_3m']:.1f} "
                            f"BB:{bb_mark} "
                            f"Move:{ratio:.1f}x"
                        )
                        self.best_candidate = {'symbol': None, 'rsi_1m': 50, 'gap': 999}

                    print(
                        f"💓 [생존] 자산:${total_bal:.1f} | "
                        f"포지션:{current_pos_count} | "
                        f"관심종목:{len(self.watch_list)} | "
                        f"🔥후보: {cand_info}"
                    )    
                    last_heartbeat_time = current_time

                # 3. [Fast Scan] 감시 대상 설정
                # 감시 대상 = [관심종목] + [현재 보유 종목]
                target_pool = list(self.watch_list.union(set(self.positions.keys())))
                
                # 감시할 종목이 없으면 그냥 대기
                if not target_pool:
                    await asyncio.sleep(FAST_SCAN_INTERVAL)
                    continue

                # API 밴 방지: 최대 10개만 랜덤 추출하여 집중 감시
                scan_batch = target_pool
                if len(target_pool) > 10:
                    import random
                    # 보유 종목은 반드시 포함
                    holding = list(self.positions.keys())
                    others = list(self.watch_list - set(holding))
                    
                    # 10개 채우기 (보유종목 우선)
                    scan_batch = holding[:]
                    if len(scan_batch) < 10:
                        needed = 10 - len(scan_batch)
                        if others:
                            scan_batch.extend(random.sample(others, min(len(others), needed)))
                
                # ========================================
                # A. 보유 포지션 관리 (기존 로직 100% 동일)
                # ========================================
                for sym in scan_batch:
                    if sym not in self.positions: continue
                    
                    pos = self.positions[sym]
                    metrics = await self.get_market_metrics(sym)
                    if not metrics: continue
                    
                    # 1. TP 갱신
                    await self.update_tp_order(sym, pos, metrics['atr'])
                    
                    # 2. 물타기(DCA) 체크
                    dca_count = pos['dca_count']
                    if dca_count >= MAX_DCA_COUNT: continue
                    
                    safe_idx = min(dca_count, len(DCA_ATR_GAPS) - 1)
                    required_gap = DCA_ATR_GAPS[safe_idx] * metrics['atr']
                    
                    # 가격 조건
                    price_condition = False
                    if pos['side'] == 'LONG':
                        if (pos['entry_price'] - metrics['price']) >= required_gap: price_condition = True
                    else:
                        if (metrics['price'] - pos['entry_price']) >= required_gap: price_condition = True
                        
                    # 신호 재발생 조건
                    signal_condition = False
                    is_bad_price = (metrics['price'] < pos['entry_price']) if pos['side'] == 'LONG' else (metrics['price'] > pos['entry_price'])
                    
                    if is_bad_price:
                        if pos['side'] == 'LONG':
                            if metrics['rsi_1m'] < 35 and metrics['price'] < metrics['bb_low']:
                                signal_condition = True
                        else:
                            if metrics['rsi_1m'] > 65 and metrics['price'] > metrics['bb_high']:
                                signal_condition = True
                    
                    if price_condition or signal_condition:
                        dca_qty = pos['amount'] * DCA_MULTIPLIER
                        order_side = 'BUY' if pos['side'] == 'LONG' else 'SELL'
                        print(f"🌊 [DCA] {sym} #{dca_count+1} (Price:{price_condition}, Signal:{signal_condition})")
                        
                        success = await self.execute_order(sym, order_side, dca_qty)
                        if success:
                            self.state.update_position(sym, pos['side'], dca_count + 1)
                            await asyncio.sleep(1.0)

                # ========================================
                # B. 신규 진입 스캔 (기존 로직 100% 동일)
                # ========================================
                if current_pos_count < SYMBOL_LIMIT:
                    for sym in scan_batch:
                        if len(self.positions) >= SYMBOL_LIMIT: break
                        if sym in self.positions: continue # 이미 처리함
                        
                        metrics = await self.get_market_metrics(sym)
                        await asyncio.sleep(0.2)
                        
                        if not metrics: continue
                        
                        atr_1m = metrics['atr_1m']
                        current_move = metrics['current_move']
                        
                        move_ratio = abs(current_move) / atr_1m if atr_1m > 1e-9 else 0
                        
                        entry_signal = None
                        
                        # [LONG 진입 조건]
                        if (metrics['rsi_3m'] < RSI_3M_LONG and
                            metrics['price'] < metrics['bb_low'] and
                            metrics['rsi_1m'] < RSI_ENTRY_TH and 
                            current_move > (atr_1m * IMPULSE_MULTIPLIER)):
                            
                            print(
                                f"📉 [PANIC LONG] {sym} | "
                                f"R3:{metrics['rsi_3m']:.1f} "
                                f"R1:{metrics['rsi_1m']:.1f} "
                                f"BB:LOW(O) "
                                f"Move:{move_ratio:.1f}x"
                            )
                            entry_signal = 'LONG'
                            
                        # [SHORT 진입 조건]
                        elif (metrics['rsi_3m'] > RSI_3M_SHORT and
                              metrics['price'] > metrics['bb_high'] and
                              metrics['rsi_1m'] > (100 - RSI_ENTRY_TH) and 
                              (-current_move) > (atr_1m * IMPULSE_MULTIPLIER)):
                              
                            print(
                                f"📈 [SHOOT SHORT] {sym} | "
                                f"R3:{metrics['rsi_3m']:.1f} "
                                f"R1:{metrics['rsi_1m']:.1f} "
                                f"BB:HIGH(O) "
                                f"Move:{move_ratio:.1f}x"
                            )
                            entry_signal = 'SHORT'
                            
                        if entry_signal:
                            entry_val = total_bal * INITIAL_ENTRY_PCT
                            required_margin = entry_val / LEVERAGE
                            
                            if entry_val < MIN_NOTIONAL:
                                entry_val = MIN_NOTIONAL * 1.1

                            if avail_bal >= required_margin:
                                qty = self.calc_qty_from_usdt(sym, entry_val, metrics['price'])
                                if qty > 0:
                                    side = 'BUY' if entry_signal == 'LONG' else 'SELL'
                                    
                                    # 상세 진입 로그
                                    bb_status = "LOW" if entry_signal == 'LONG' else "HIGH"
                                    print(
                                        f"🎯 [ENTRY] {sym} {entry_signal} (Qty:{qty}) | "
                                        f"R1:{metrics['rsi_1m']:.1f} "
                                        f"R3:{metrics['rsi_3m']:.1f} "
                                        f"BB:{bb_status}(O) "
                                        f"Move:{move_ratio:.1f}x"
                                    )
                                    
                                    success = await self.execute_order(sym, side, qty)
                                    if success:
                                        self.state.update_position(sym, entry_signal, 0)
                                        await asyncio.sleep(1.0)
                                        self.positions[sym] = {'dummy': True}
                            else:
                                print(f"⚠️ [SKIP] {sym} 증거금 부족 (Need: ${required_margin:.2f})")

                        # [모니터링] 가장 강력한 후보 기록 (기존 로직 유지)
                        if move_ratio > self.best_candidate.get('move_ratio', 0):
                            target_type = "LONG" if current_move > 0 else "SHORT"
                            bb_check = False
                            if target_type == "LONG":
                                if metrics['price'] < metrics['bb_low']: bb_check = True
                            else:
                                if metrics['price'] > metrics['bb_high']: bb_check = True

                            self.best_candidate = {
                                'symbol': sym,
                                'type': target_type,
                                'rsi_1m': metrics['rsi_1m'],
                                'rsi_3m': metrics['rsi_3m'],
                                'move_ratio': move_ratio,
                                'bb_break': bb_check,
                                'gap': 0
                            }
                            
            except Exception as e:
                print(f"❌ Main Loop Error: {e}")
                await asyncio.sleep(5)
            
            # Smart Scan 딜레이 (3초)
            await asyncio.sleep(FAST_SCAN_INTERVAL)

if __name__ == "__main__":
    bot = BinanceSniperBot()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run_loop())
    except KeyboardInterrupt:
        print("🛑 봇 종료 요청")
