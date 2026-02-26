import math, random

class CurrencyRate:
    def __init__(self, currency: str, rate: float):
        self.currency = currency
        self.rate = rate
        self.past_rates = [rate]
        
        # 互換性のため既存の変数は残すが、計算には使わないものもある
        self.past_interest = 0.0
        self.past_usd = 0.0 # FX reserves (Used for logging/compatibility)
        self.past_usd_interest = 0.0 
        self.count = 0.0
        self.past_based_usd = 0.0
        
        # 新しい経済指標の履歴
        self.past_inflation = 0.0
        self.past_base_inflation = 0.0

    def change_rate(self, new_interest: float, inflation: float, 
                    trade_balance_ratio: float, gdp_growth: float,
                    base_interest: float, base_inflation: float, 
                    base_trade_balance_ratio: float, base_gdp_growth: float,
                    intervention_ratio: float = 0.0,
                    avg_gdp_per_capita_usd: float = 0.0,  # ★追加
                    base_gdp_per_capita_usd: float = 0.0  # ★追加
                    ):
        """
        為替レートを更新する。
        intervention_ratio: (介入額USD / GDP_USD) * 100。
        プラスならドル買い介入（円安要因）、マイナスならドル売り介入（円高要因）。
        """
        
        # --- 1. 購買力平価 (PPP) 的な圧力 ---
        # インフレ率の差分を計算 (自国インフレが高いとプラス -> レート上昇=通貨安)
        # 【修正】係数を掛け、1ターンですべて反映させず、30%程度ずつ織り込ませる
        inflation_diff = ((inflation - base_inflation) / 100.0) * 0.3

        # --- 2. 実質金利差 (Real Interest Rate Differential) ---
        # 実質金利 = 名目金利 - インフレ率
        real_interest = new_interest - inflation
        base_real_interest = base_interest - base_inflation
        real_interest_diff = real_interest - base_real_interest
        
        # 金利への感応度 (係数 0.10)
        interest_effect = math.tanh(real_interest_diff * 0.2) * 0.17

        # --- 3. 貿易収支 (Trade Balance) ---
        trade_diff = trade_balance_ratio - base_trade_balance_ratio
        trade_effect = math.tanh(trade_diff * 2.0) * 0.07

        # --- 4. 経済成長率 (Real GDP Growth) ---
        # 【重要】名目成長率(gdp_growth)からインフレ率を引いて「実質成長率」にする
        # これにより、インフレによる見せかけのGDP成長を通貨高要因から除外する
        real_gdp_growth = gdp_growth - inflation
        base_real_gdp_growth = base_gdp_growth - base_inflation
        
        real_growth_diff = real_gdp_growth - base_real_gdp_growth
        
        # 実質成長率が高いなら通貨高要因
        growth_effect = math.tanh(real_growth_diff * 0.1) * 0.01
        # growth_effect = math.tanh(real_growth_diff * 0.1) * 0.10
        # --- 5. 為替介入 (Intervention) ---
        # 介入比率に応じてレートを動かす
        # プラス（ドル買い・自国売り）なら、レート上昇（通貨安）要因
        intervention_effect = math.tanh(intervention_ratio * 5.0) * 0.15

        # --- 6. 一人当たりGDP (GDP Per Capita) ---
        # 一人当たりGDPが高い国にやや有利（通貨高）になるように
        # 基準（USD）との比率を見る
        # ベースが0の場合は1として回避
        safe_base_gdp = base_gdp_per_capita_usd if base_gdp_per_capita_usd > 0 else 1.0
        gdp_capita_ratio = (avg_gdp_per_capita_usd - base_gdp_per_capita_usd) / safe_base_gdp
        
        # 影響度は「やや」有利とのことなので、係数は小さめに設定
        # プラス（相手より豊か）なら通貨高（レート減）要因 -> マイナス
        # GDP差が2倍でも tanh(1.0) ~ 0.76 -> * 0.05 = 0.038 (約3.8%の変動圧力)
        gdp_capita_effect = math.tanh(gdp_capita_ratio) * 0.05

        # --- 総合的な変動率 ---
        # inflation_diff, intervention_effect はプラスなら通貨安(レート増)要因
        # interest/trade/growth/gdp_capita effectはプラスなら通貨高(レート減)要因なのでマイナスをつける
        total_change = inflation_diff - (interest_effect + trade_effect + growth_effect + gdp_capita_effect) + intervention_effect
        
        # ランダムな投機的変動
        random_noise = random.randint(-1, 1) * 0.005
        
        # --- 7. 安全装置（変動幅キャップ） ---
        # 1ターンでの変動を最大 ±25% に制限する (暴走防止)
        if total_change > 0.25: total_change = 0.25
        if total_change < -0.25: total_change = -0.25

        # レートの更新
        prev_rate = self.past_rates[-1]
        self.rate = prev_rate * (1 + total_change + random_noise)

        print(f"--- {self.currency} ---")
        print(f"  Inflation Diff: {inflation_diff*100:.2f}% -> Base Change: {inflation_diff:.4f}")
        print(f"  Real Int Diff: {real_interest_diff:.2f}% -> Effect: {-interest_effect:.4f}")
        print(f"  Real Growth Diff: {real_growth_diff:.2f}% -> Effect: {-growth_effect:.4f}")
        print(f"  GDP/Capita Diff Ratio: {gdp_capita_ratio:.2f} -> Effect: {-gdp_capita_effect:.4f}")
        print(f"  Intervention: {intervention_ratio:.2f}% -> Effect: {intervention_effect:.4f}")
        print(f"  Total Change: {total_change:.4f}")
        print(f"  New Rate: {self.rate:.2f}")

        # 安全策
        if self.rate <= 0.01:
            self.rate = 0.01 
            
        self.past_rates.append(self.rate)
        
        # 履歴更新
        self.past_inflation = inflation
        self.past_base_inflation = base_inflation
        self.past_interest = new_interest
    
    def value_cut(self, x, y):
        if x >= 0.0:
            if x >= y:
                x = y
        else:
            if x < -y:
                x = -y
        return x
    def get_rate(self):
        return self.past_rates[-1]
    
    def set_rate(self, new_rate: float):
        self.rate = new_rate
        self.past_rates.append(new_rate)
        
    
    
    
    def get_past_rates(self):
        return self.past_rates
    def __str__(self):
        return f"{self.currency}: {self.rate}"

    def __repr__(self):
        return f"CurrencyRate(currency={self.currency}, rate={self.rate})"