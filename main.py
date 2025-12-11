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
        """API 연결 및 초기 데이터 로드"""
        print("🔌 Binance API 연결 중...")
        self.client = await AsyncClient.create(API_KEY, API_SECRET)
        
        # 1. 거래소 정보 로드
        info = await self.client.futures_exchange_info()
        count = 0
        
        # [제외할 코인 목록] 변동성 없는 스테이블 코인들
        exclude_coins = ['USDCUSDT', 'USDPUSDT', 'FDUSDUSDT', 'BUSDUSDT'] 
        
        for s in info['symbols']:
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING' and s['contractType'] == 'PERPETUAL':
                # [추가] 스테이블 코인 페어 제외
                if s['symbol'] in exclude_coins: continue
                
                self.symbols.append(s['symbol'])
                
                # 필터 정보 파싱 (정밀도)
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
                
                self.symbol_info[s['symbol']] = {
                    'qty_prec': prec_qty,
                    'price_prec': prec_price,
                    'min_qty': min_qty
                }
                count += 1
        
        print(f"✅ 거래 가능 심볼 로드: {count}개 (스테이블 제외됨)")

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

    # (주의) 앞에 공백 4칸이 반드시 있어야 합니다.
    async def get_market_metrics(self, symbol):
        """
        [최적화됨] 하이브리드 캐싱 전략 적용
        - ATR(15m), RSI(3m): 변동이 적으므로 60초간 캐시(Cache) 사용
        - RSI(1m), Price, BB: 실시간성이 중요하므로 매번 API 호출
        => API 요청량 대폭 감소 (IP Ban 방지) + 반응 속도 유지
        """
        try:
            now = time.time()
            
            # 1. 캐시 데이터 확인
            cached_data = self.metrics_cache.get(symbol)
            is_cache_valid = False
            
            if cached_data:
                # 60초 이내에 갱신된 데이터라면 유효함
                if now - cached_data['updated_at'] < 60:
                    is_cache_valid = True
            
            # ====================================================
            # CASE A: 캐시가 유효함 (가벼운 1m 캔들만 호출 -> API 1회)
            # ====================================================
            if is_cache_valid:
                # 1m 캔들만 실시간 조회
                k_1m = await self.client.futures_klines(symbol=symbol, interval='1m', limit=30)
                if not k_1m: return None
                
                # 데이터프레임 변환
                df_1m = pd.DataFrame(k_1m).iloc[:, :6]
                df_1m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_1m['close'] = df_1m['close'].astype(float)
                
                # 1m 지표 계산 (실시간)
                rsi_1m = df_1m.ta.rsi(length=14).iloc[-1]
                bb = df_1m.ta.bbands(length=20, std=2.0)
                bb_cols = bb.columns.tolist()
                
                # 결과 조합 (캐시된 값 + 실시간 값)
                return {
                    'atr': cached_data['atr'],      # 캐시 사용
                    'rsi_3m': cached_data['rsi_3m'], # 캐시 사용
                    'rsi_1m': rsi_1m,               # 실시간
                    'bb_low': bb[bb_cols[0]].iloc[-1], # 실시간
                    'bb_high': bb[bb_cols[2]].iloc[-1],# 실시간
                    'price': float(df_1m['close'].iloc[-1]) # 실시간
                }

            # ====================================================
            # CASE B: 캐시 없음/만료 (전체 호출 -> API 3회 병렬)
            # ====================================================
            else:
                # 3개 API 동시 요청 (asyncio.gather로 속도 최적화)
                task_15m = self.client.futures_klines(symbol=symbol, interval='15m', limit=30)
                task_3m = self.client.futures_klines(symbol=symbol, interval='3m', limit=30)
                task_1m = self.client.futures_klines(symbol=symbol, interval='1m', limit=30)
                
                results = await asyncio.gather(task_15m, task_3m, task_1m, return_exceptions=True)
                
                k_15m, k_3m, k_1m = results
                
                # 하나라도 실패하면 중단
                if isinstance(k_15m, Exception) or not k_15m: return None
                if isinstance(k_3m, Exception) or not k_3m: return None
                if isinstance(k_1m, Exception) or not k_1m: return None

                # 1. 15m (ATR 계산)
                df_15m = pd.DataFrame(k_15m).iloc[:, :6]
                df_15m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_15m[['high', 'low', 'close']] = df_15m[['high', 'low', 'close']].astype(float)
                atr = df_15m.ta.atr(length=ATR_PERIOD).iloc[-1]
                
                # 2. 3m (RSI 계산)
                df_3m = pd.DataFrame(k_3m).iloc[:, :6]
                df_3m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_3m['close'] = df_3m['close'].astype(float)
                rsi_3m = df_3m.ta.rsi(length=14).iloc[-1]
                
                # 3. 1m (RSI & BB 계산)
                df_1m = pd.DataFrame(k_1m).iloc[:, :6]
                df_1m.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
                df_1m['close'] = df_1m['close'].astype(float)
                rsi_1m = df_1m.ta.rsi(length=14).iloc[-1]
                
                bb = df_1m.ta.bbands(length=20, std=2.0)
                bb_cols = bb.columns.tolist()
                
                # 캐시 업데이트 (중요)
                self.metrics_cache[symbol] = {
                    'atr': atr,
                    'rsi_3m': rsi_3m,
                    'updated_at': now
                }
                
                return {
                    'atr': atr,
                    'rsi_3m': rsi_3m,
                    'rsi_1m': rsi_1m,
                    'bb_low': bb[bb_cols[0]].iloc[-1],
                    'bb_high': bb[bb_cols[2]].iloc[-1],
                    'price': float(df_1m['close'].iloc[-1])
                }

        except Exception as e:
            # print(f"⚠️ 지표 계산 실패 ({symbol}): {e}") # 로그가 너무 많으면 주석 처리
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
        """메인 실행 루프"""
        await self.initialize()
        print(f"🚀 ATR Sniper Bot 가동 시작! (Target: {INITIAL_ENTRY_PCT*100}% Entry / Max {SYMBOL_LIMIT} Symbols)")
        
        # [추가] 생존 신고 타이머 초기화 (루프 밖)
        last_heartbeat_time = time.time()
        HEARTBEAT_INTERVAL = 300  # 300초 = 5분
        
        while True:
            # [필수 수정] 루프 시작 시 변수 초기화 (에러 방지)
            total_bal = 0.0
            avail_bal = 0.0
            exposure_pct = 0.0
            
            try:
                # 1. 계좌 및 포지션 업데이트
                # 만약 여기서 에러나면 except로 빠지지만, 혹시 모를 상황 대비
                res = await self.update_account_data()
                if res:
                    total_bal, avail_bal, exposure_pct = res
                    
                # 만약 계좌 조회가 실패해서 잔고가 0이면, 이번 루프는 스킵해야 안전함
                if total_bal <= 0:
                    print("⚠️ 계좌 잔고 조회 실패 또는 잔고 부족. 잠시 대기...")
                    await asyncio.sleep(5)
                    continue

                current_pos_count = len(self.positions)
                
                # ========================================
                # [업그레이드] 생존 신고 (Heartbeat) 로직
                # ========================================
                current_time = time.time()
                if current_time - last_heartbeat_time > HEARTBEAT_INTERVAL:
                    # ... (생략: 기존 코드와 동일)
                    cand_info = "대기중..."
                    if self.best_candidate['symbol']:
                        c = self.best_candidate
                        bb_mark = "O" if c['bb_break'] else "X"
                        cand_info = (
                            f"{c['symbol']}({c['type'][0]}) "
                            f"R1:{c['rsi_1m']:.1f} "
                            f"R3:{c['rsi_3m']:.1f} "
                            f"BB:{bb_mark}"
                        )
                        self.best_candidate = {'symbol': None, 'rsi_1m': 50, 'gap': 999}

                    print(
                        f"💓 [생존] 자산:${total_bal:.1f} | "
                        f"포지션:{current_pos_count} | "
                        f"1배:{exposure_pct:.1f}% | "
                        f"🔥후보: {cand_info}"
                    )    
                    last_heartbeat_time = current_time
                
                # ========================================
                # A. 보유 포지션 관리 (물타기 & TP)
                # ========================================
                for sym, pos in self.positions.items():
                    # 데이터 조회
                    metrics = await self.get_market_metrics(sym)
                    if not metrics: continue
                    
                    # 1. TP 갱신
                    await self.update_tp_order(sym, pos, metrics['atr'])
                    
                    # 2. 물타기(DCA) 체크
                    dca_count = pos['dca_count']
                    if dca_count >= MAX_DCA_COUNT: continue
                        
                    required_gap = DCA_ATR_GAPS[dca_count] * metrics['atr']
                    
                    # 조건 1: 가격 도달
                    price_condition = False
                    if pos['side'] == 'LONG':
                        dist = pos['entry_price'] - metrics['price']
                        if dist >= required_gap: price_condition = True
                    else:
                        dist = metrics['price'] - pos['entry_price']
                        if dist >= required_gap: price_condition = True
                        
                    # 조건 2: 신호 재발생
                    signal_condition = False
                    is_bad_price = (metrics['price'] < pos['entry_price']) if pos['side'] == 'LONG' else (metrics['price'] > pos['entry_price'])
                    
                    if is_bad_price:
                        if pos['side'] == 'LONG':
                            if (metrics['rsi_3m'] < RSI_3M_LONG_TH and 
                                metrics['rsi_1m'] < RSI_1M_LONG_TH and 
                                metrics['price'] < metrics['bb_low']):
                                signal_condition = True
                        else:
                            if (metrics['rsi_3m'] > RSI_3M_SHORT_TH and 
                                metrics['rsi_1m'] > RSI_1M_SHORT_TH and 
                                metrics['price'] > metrics['bb_high']):
                                signal_condition = True
                    
                    if price_condition or signal_condition:
                        dca_qty = pos['amount'] * DCA_MULTIPLIER
                        order_side = 'BUY' if pos['side'] == 'LONG' else 'SELL'
                        print(f"🌊 [DCA TRIGGER] {sym} #{dca_count+1} (Price: {price_condition}, Signal: {signal_condition})")
                        
                        success = await self.execute_order(sym, order_side, dca_qty)
                        if success:
                            self.state.update_position(sym, pos['side'], dca_count + 1)
                            await asyncio.sleep(1.0)

                # ========================================
                # B. 신규 진입 스캔 (포지션 여유 있을 때만)
                # ========================================
                if current_pos_count < SYMBOL_LIMIT:
                    import random
                    scan_candidates = [s for s in self.symbols if s not in self.positions]
                    # [안전 설정] 한 번에 10개만 스캔
                    scan_batch = random.sample(scan_candidates, min(len(scan_candidates), 10))
                    
                    for sym in scan_batch:
                        if len(self.positions) >= SYMBOL_LIMIT: break
                        
                        metrics = await self.get_market_metrics(sym)
                        # [안전 설정] API 과부하 방지 딜레이
                        await asyncio.sleep(0.2)
                        
                        if not metrics: continue
                        
                        # 롱/숏 진입 체크
                        entry_signal = None
                        if (metrics['rsi_3m'] < RSI_3M_LONG_TH and 
                            metrics['rsi_1m'] < RSI_1M_LONG_TH and 
                            metrics['price'] < metrics['bb_low']):
                            entry_signal = 'LONG'
                        elif (metrics['rsi_3m'] > RSI_3M_SHORT_TH and 
                              metrics['rsi_1m'] > RSI_1M_SHORT_TH and 
                              metrics['price'] > metrics['bb_high']):
                            entry_signal = 'SHORT'
                            
                        if entry_signal:
                            # 여기서 total_bal 사용 (이제 안전함)
                            entry_val = total_bal * INITIAL_ENTRY_PCT
                            required_margin = entry_val / LEVERAGE
                            
                            if avail_bal < required_margin:
                                print(f"⚠️ [SKIP] {sym} 증거금 부족 (Need: {required_margin:.2f})")
                                continue
                                
                            qty = self.calc_qty_from_usdt(sym, entry_val, metrics['price'])
                            
                            if qty > 0:
                                side = 'BUY' if entry_signal == 'LONG' else 'SELL'
                                print(f"🎯 [SNIPER ENTRY] {sym} {entry_signal} (RSI: {metrics['rsi_1m']:.1f})")
                                
                                success = await self.execute_order(sym, side, qty)
                                if success:
                                    self.state.update_position(sym, entry_signal, 0)
                                    await asyncio.sleep(1.0)
                                    self.positions[sym] = {'dummy': True} 

                        # 후보 모니터링 로직
                        dist_long = metrics['rsi_1m'] - RSI_1M_LONG_TH
                        dist_short = RSI_1M_SHORT_TH - metrics['rsi_1m']
                        
                        is_long_closer = dist_long < dist_short
                        target_type = "LONG" if is_long_closer else "SHORT"
                        current_gap = dist_long if is_long_closer else dist_short

                        if current_gap < self.best_candidate['gap']:
                            bb_cond = False
                            if target_type == "LONG":
                                bb_cond = metrics['price'] < metrics['bb_low']
                            else:
                                bb_cond = metrics['price'] > metrics['bb_high']

                            self.best_candidate = {
                                'symbol': sym,
                                'gap': current_gap,
                                'type': target_type,
                                'rsi_1m': metrics['rsi_1m'],
                                'rsi_3m': metrics['rsi_3m'],
                                'bb_break': bb_cond,
                                'price': metrics['price']
                            }
                            
            except Exception as e:
                print(f"❌ Main Loop Error: {e}")
                await asyncio.sleep(5)
            
            # 루프 딜레이
            await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    bot = BinanceSniperBot()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run_loop())
    except KeyboardInterrupt:
        print("🛑 봇 종료 요청")
