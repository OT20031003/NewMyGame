import math

class CountryPower:
    def __init__(self, name, init_val=0.0):
        # 共通通貨に基づく国力
        self.name = name
        
        # 初期値の設定
        # Industry と Military は蓄積型（ストック）として扱う
        # past_power (ストック) に初期値を入れ、past (フロー/投資) は0とします
        if name == "Industry" or name == "Military":
            self.past = [0.0]
            self.past_power = [init_val]
        else:
            # その他の要素（もしあれば）は加重平均型の初期化
            self.past = [init_val]
            self.past_power = [init_val]

        self.bef = init_val
        self.turn = 0 # save用のダミー、使わない

    def save_list(self):
        data = [[self.name], [self.turn], self.past, [self.bef], self.past_power]
        return data
    
    def add_power(self, power, rate, turn):
        #print(f"{self.name}, rate = {rate}, bef power = {power}")
        power = (math.sqrt(power/ rate)) / 10**5
        #print(f"{self.name}, rate = {rate}, aft power = {power}")
        
        self.bef = self.caluc_power()
        self.past.append(power)
        
        self.past_power.append(self.caluc_power())
        

    def caluc_power(self, alpha=0.7):
        """
        指数加重を用いて国力を計算する。
        IndustryとMilitaryは蓄積型（ストック）として計算し、成長を促す。
        """
        # --- Industry（産業）と Military（軍事）の特別処理: 蓄積型モデル ---
        if self.name == "Industry" or self.name == "Military":
            # 前回の国力（ストック）を取得
            if len(self.past_power) > 0:
                prev_power = self.past_power[-1]
            else:
                prev_power = 0.0
            
            # 今回の投資（フロー）
            current_input = self.past[-1]
            
            # 【修正変更点】
            # 蓄積型ロジックを適用
            
            # 1. 減価償却なしで単純加算
            accumulated_power = prev_power + current_input
            
            # 2. 自然成長率の適用
            # インフレで実質投資額(current_input)が増えなくても成長するようにする
            growth_rate = 1.006
            
            val = accumulated_power * growth_rate
            
            # 単調増加保証（もし計算結果が前回を下回っても、前回値を維持）
            if val < prev_power:
                val = prev_power
            
            return val

        # --- その他の要素は従来の加重平均モデル ---
        power_sum = 0.0
        wsum = 0.0
        
        # self.past の各要素に対してループ
        for i in range(len(self.past)):
            w = (1 - alpha) ** (len(self.past) - 1 - i)
            power_sum += self.past[i] * w
            wsum += w
        
        if wsum == 0:
            return 0.0
            
        return power_sum / wsum
    
    def change_power(self):
        if len(self.past_power) < 2:
            return 0.0
        now = self.past_power[-1]
        bef2 = self.past_power[len(self.past_power) - 2]
        return (now - bef2) / (abs(bef2) + 0.00001) * 100.0