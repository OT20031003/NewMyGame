import math

class CountryPower:
    def __init__(self, name, init_val=0.0):
        # 共通通貨に基づく国力
        self.name = name
        
        # 初期値の設定
        # Industry と Military は蓄積型（ストック）として扱う
        if name == "Industry" or name == "Military":
            self.past = [0.0]
            self.past_power = [init_val]
        else:
            # その他の要素
            self.past = [init_val]
            self.past_power = [init_val]

        self.bef = init_val
        self.turn = 0 

    def save_list(self):
        data = [[self.name], [self.turn], self.past, [self.bef], self.past_power]
        return data
    
    def add_power(self, power, rate, turn):
        # 予算(power)をレート換算し、平方根をとる
        # 値のスケールを4〜5桁に収めるため 2000 で除算（前回の調整）
        scaled_power = (math.sqrt(power / rate)) / 2000.0
        
        # 今回の計算前の値を保存（UI表示等のため）
        self.bef = self.caluc_power()
        
        # 投資リストに追加
        self.past.append(scaled_power)
        
        # 新しい国力を計算して追加
        self.past_power.append(self.caluc_power())
        

    def caluc_power(self, alpha=0.7):
        """
        IndustryとMilitaryは蓄積型（ストック）。
        毎ターンの投資額を積み上げつつ、序盤の急成長を抑制するリミッターを設ける。
        """
        # --- Industry（産業）と Military（軍事）の特別処理 ---
        if self.name == "Industry" or self.name == "Military":
            # 前回の国力（ストック）
            if len(self.past_power) > 0:
                prev_power = self.past_power[-1]
            else:
                prev_power = 0.0
            
            # 今回の投資（フロー）
            # add_power内でappendされた最新の値を使用
            current_input = self.past[-1]
            
            # 1. 基本計算（単純加算モデル）
            val = prev_power + current_input
            
            # 2. 変動制限（リミッター）
            # 最初の50ターン（初期値含めてリスト長が50以下の場合）は
            # 成長率を前回比 +5% 以内に制限する
            if len(self.past_power) <= 50 and prev_power > 0:
                max_val = prev_power * 1.02
                if val > max_val:
                    val = max_val
            
            return val

        # --- その他の要素は従来の加重平均モデル ---
        power_sum = 0.0
        wsum = 0.0
        
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