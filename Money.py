from Interest import Interest
from CurrencyRate import CurrencyRate
import csv

class Money:
    # ★修正: base_index_rate に名称変更 (旧 rate_at_turn_50)
    def __init__(self, name, interest, value, base_currency, is_major=False):
        self.name = name # 通貨名
        self.interest = Interest(interest) # 利率
        self.rate = CurrencyRate(name, value) # 通貨の価値（初期値は1.0）
        self.base_currency = base_currency # 基軸通貨かどうかのフラグ
        self.is_major = is_major # ★追加: 主要通貨フラグ（インデックス計算のバスケットに含めるか）
        
        # === ★追加: 通貨インデックス関連 ===
        self.currency_index = 100.0
        self.past_indices = [100.0]
        self.base_index_rate = None # 基準ターン時点のレートを保持
    def load(self, name):
        with open(f"{name}.csv", 'r', newline='', encoding= 'utf-8') as file2:
            reader = csv.reader(file2)
            cnt = 0
            for row in reader:
                if cnt == 0:
                    self.name = row[0]
                elif cnt == 1:
                    self.interest = Interest(0)
                    self.interest.interest = [float(x) for x in row]
                elif cnt == 2:
                    self.rate = CurrencyRate(name, 0.0)
                    self.rate.rate = float(row[1])
                    self.rate.past_usd = float(row[2])
                    self.rate.past_usd_interest = float(row[3])
                    self.rate.count = float(row[4])
                    self.rate.past_interest = float(row[5])
                    self.rate.past_based_usd = float(row[6])
                elif cnt == 3:
                    self.rate.past_rates = [float(x) for x in row]
                elif cnt == 4:
                    if row[0] == "True":
                        self.base_currency = True
                    else:
                        self.base_currency = False
                # === ★追加: インデックスデータのロード ===
                elif cnt == 5:
                    self.past_indices = [float(x) for x in row]
                    self.currency_index = self.past_indices[-1]
                elif cnt == 6:
                    # ★修正: 変数名変更に対応
                    if row[0] != "None":
                        self.base_index_rate = float(row[0])
                    else:
                        self.base_index_rate = None
                # ★追加: 主要通貨フラグのロード
                elif cnt == 7:
                    if row[0] == "True":
                        self.is_major = True
                    else:
                        self.is_major = False

                cnt += 1
    def save_money(self):
        data = [[self.name]]
        data.append(self.interest.interest)
        data.append([self.rate.currency, self.rate.rate, self.rate.past_usd, self.rate.past_usd_interest, self.rate.count, self.rate.past_interest, self.rate.past_based_usd])
        data.append(self.rate.past_rates)
        data.append([self.base_currency])
        # === ★追加: インデックスデータのセーブ ===
        data.append(self.past_indices)
        # ★修正: 変数名変更に対応
        data.append([self.base_index_rate])
        # ★追加: 主要通貨フラグのセーブ
        data.append([self.is_major])
        
        with open(f'{self.name}.csv', 'w', newline='', encoding='utf-8') as file: 
            writer = csv.writer(file)
            writer.writerows(data) # 複数の行をまとめて書き込む
        
    def change_interest(self, ninterest, 
                        inflation, trade_balance_ratio, gdp_growth,
                        base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                        intervention_ratio=0.0,
                        avg_gdp_per_capita_usd=0.0, # ★追加
                        base_gdp_per_capita_usd=0.0 # ★追加
                        ): 
        
        self.interest.change_interest(ninterest)
        
        if self.base_currency:
            return False
        else:
            # 基軸通貨以外の場合、為替レートを更新
            self.rate.change_rate(
                new_interest=self.interest.get_true_interest(), 
                inflation=inflation,
                trade_balance_ratio=trade_balance_ratio,
                gdp_growth=gdp_growth,
                base_interest=base_interest,
                base_inflation=base_inflation,
                base_trade_balance_ratio=base_trade_balance_ratio,
                base_gdp_growth=base_gdp_growth,
                intervention_ratio=intervention_ratio,
                avg_gdp_per_capita_usd=avg_gdp_per_capita_usd, # ★追加
                base_gdp_per_capita_usd=base_gdp_per_capita_usd # ★追加
            )
        return self.interest.get_interest()
    
    def stay_interest(self, inflation, trade_balance_ratio, gdp_growth,
                      base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                      new_interest=None,
                      intervention_ratio=0.0,
                      avg_gdp_per_capita_usd=0.0, # ★追加
                      base_gdp_per_capita_usd=0.0 # ★追加
                      ):
        if new_interest is None:
            ninterest = self.interest.get_interest()
        else:
            ninterest = new_interest
            
        self.change_interest(ninterest, inflation, trade_balance_ratio, gdp_growth,
                             base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                             intervention_ratio=intervention_ratio,
                             avg_gdp_per_capita_usd=avg_gdp_per_capita_usd, # ★追加
                             base_gdp_per_capita_usd=base_gdp_per_capita_usd # ★追加
                             )
        
        return self.interest.get_interest()
        
   
    def get_true_interest(self):
        return self.interest.get_true_interest()
    
    def get_interest(self):
        return self.interest.get_interest()
    
    
    def get_past_rate(self):
        return self.rate.get_past_rates()
    
    def get_rate(self):
        # 通貨の価値を基軸通貨の価値で割る
        if self.base_currency:
            return 1.0
        else :
            return self.rate.get_rate()
        
    
    def change_based_interest(self, based_interest):
        # 基軸通貨に基づく
        self.rate.change_based_currency(based_interest)