import random
import math

class Price:
    def __init__(self, turn_year, initial_price=100.0):
        self.past_price = [initial_price]
        self.turn_year = turn_year
        # 初期インフレ率の仮定 (0.0 ~ 0.02 程度)
        self.current_inflation = 0.01 

    def change_price(self, interest, gdp_growth=0.0, exchange_rate_change=0.0):
        # 1. インフレ慣性 (過去の影響)
        if len(self.past_price) >= 2:
            prev_inflation = (self.past_price[-1] - self.past_price[-2]) / self.past_price[-2]
        else:
            prev_inflation = self.current_inflation

        # 2. 実質金利効果
        # 金利がインフレ率より「どれだけ高いか」を見る
        real_interest = interest * 0.01 - prev_inflation
        natural_rate = 0.01
        
        # 感応度を調整（-0.5程度で十分）
        monetary_pressure = -0.5 * (real_interest - natural_rate)

        # 3. その他の圧力（影響力を大幅に下げる）
        potential_growth = 2.0
        # 係数を 0.15 -> 0.05 に下げる
        demand_pressure = 0.05 * ((gdp_growth - potential_growth) * 0.01)
        
        # 係数を 0.1 -> 0.02 に下げる
        import_pressure = 0.02 * (exchange_rate_change * 0.01)

        # ランダムショックも小さくする
        shock = random.normalvariate(0, 0.001)

        # === 【重要】新しいインフレ率の決定 ===
        # 移動平均（スムージング）を導入してグラフを滑らかにする
        
        target_inflation = 0.02 # 目標 2%

        # A. まず、現在の経済状況に基づいた「あるべきインフレ率（理論値）」を計算
        # targetに、金利や需要などの圧力を加えます
        calculated_raw_inflation = target_inflation + \
                                   monetary_pressure + demand_pressure + import_pressure + shock

        # B. 移動平均処理
        # 前回のインフレ率(prev_inflation)を多く残し、新しい理論値の変化を少しだけ反映させる
        smoothing_factor = 0.2  # 0.1〜0.3推奨。小さいほどグラフの線が滑らかになります
        
        new_inflation = (prev_inflation * (1 - smoothing_factor)) + \
                        (calculated_raw_inflation * smoothing_factor)

        # 安全装置
        # === 変更点: デフレの下限を緩和 (-5% -> -30%) ===
        # これにより、高金利時に物価が為替上昇以上に下落し、GDP(USD)の自動増加を防ぐ
        new_inflation = max(-0.30, min(0.50, new_inflation))
        
        # 更新処理
        current_price = self.past_price[-1]
        new_price_val = current_price * (1 + new_inflation)
        if new_price_val < 0.01: new_price_val = 0.01

        self.past_price.append(new_price_val)
        self.current_inflation = new_inflation
        
        return new_price_val

    def get_price(self):
        return self.past_price[-1]

    def get_price_change_rate(self):
        if len(self.past_price) < 2:
            return 0.0
        back = self.turn_year
        if back >= len(self.past_price):
            back = len(self.past_price) - 1
        if back <= 0:
            return 0.0

        old_price = self.past_price[-1 - back]
        current_price = self.past_price[-1]
        
        if old_price <= 0: return 0.0
            
        return (current_price - old_price) * 100.0 / old_price