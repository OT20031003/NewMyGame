import random
from Budget import Budget
from CountryPower import CountryPower
from Satisfaction import Satisfaction
import math
from Salary import Salary
from Price import Price
from Money import Money
import csv

class Country:
    def __init__(self, name, money_name, turn_year, population_p, salary_p, initial_price=100.0, selfoperation=False, industry_p=0.0, military_p=0.0):
        self.name = name
        self.turn_year = turn_year  # ターン年数
        
        self.money_name = money_name # 使用する通貨
        self.tax = 0.4 # 税率
        self.bef_tax = self.tax # 1つ前の税率
        self.salary_p = salary_p
        self.foreign_currency = {}
        self.budget = Budget() # 1年=turn_yearで使えるお金=gdp*tax
        
        # 国力 (Industry) と 軍事力 (Military) の初期化
        # これらは industry_p, military_p にのみ依存して決定される
        self.industry = CountryPower("Industry", industry_p) 
        self.military = CountryPower("Military", military_p) 
        
        self.population_p = population_p
        
        # 物価 (Price) の初期化
        # これは initial_price にのみ依存して決定される
        self.price = Price(turn_year, initial_price)
        
        self.population = [[0,20, 0] for _ in range(100)] # 人口の分布 (人口, 満足度, 収入)
        
        self.past_population = [ ]
        
        # 初期状態のスナップショットを取得（参照用）
        current_init_price = self.price.get_price()
        current_init_industry = self.industry.caluc_power()

        for i in range(100):
            # Salaryの初期化
            s = Salary(old=i, price=current_init_price, industry=current_init_industry, init=-1, coef=salary_p)
            
            # 人口と満足度の設定
            self.population[i] = [
                random.randint(int(pow(10, population_p)), int(2*pow(10, population_p))), 
                Satisfaction(initsatis=50.0, price=current_init_price, salary=s.get_salary(), tax=self.tax, turn_year=self.turn_year),  
                s
            ] 
            # 人口減少カーブの適用
            self.population[i][0] -= int((0.99 / (99*99))*(i**2) * self.population[i][0]) 
        
        self.gdp_usd = -10.0
        self.past_gdp_usd = [self.gdp_usd]
        self.past_gdp = [self.caluc_gdp()] # 過去のGDPを記録するリスト
        self.price_usd = 0.0
        
        self.usd = 0.0 # 共通通貨(ドル)の保持数 (FX Reserve)
        self.past_usd = [self.usd]
        
        # === 自国通貨残高の初期化 ===
        self.domestic_money = 0.0 # 自国通貨残高
        self.past_domestic_money = [self.domestic_money]
        
        # 貿易収支履歴 (初期値0)
        self.past_trade_balance = [0.0]
        
        self.price_salary = self.get_average_salary() / self.price.get_price() if self.price.get_price() > 0 else -100.0 # 物価に対する収入の比率
        self.selfoperation = selfoperation # 自律的操作を行うかどうか TODO
        self.past_population.append(self.get_population())
        self.turn_intervention_usd = 0.0

        # === イベントログの初期化 ===
        self.event_logs = []

        # === ★追加: 関税システム ===
        # キー: 相手国名(str), 値: 関税率(float, 0.10=10%)
        self.tariffs = {}
        # このターンに支払った輸入関税コスト（次ターンの物価計算に使用）
        self.turn_tariff_cost_usd = 0.0

    # === ログ記録用メソッド ===
    def add_log(self, turn, category, message):
        self.event_logs.append({
            "turn": turn,
            "type": category,
            "message": message
        })

    # === ★追加: 関税関連メソッド ===
    def set_tariff(self, target_country_name, rate):
        """指定した国への関税率を設定する"""
        if rate < 0.0: rate = 0.0
        if rate > 10.0: rate = 10.0 # 上限などのガード
        self.tariffs[target_country_name] = rate

    def get_tariff(self, target_country_name):
        """指定した国への関税率を取得する"""
        return self.tariffs.get(target_country_name, 0.0)

    def interest_decide(self, current_interest, inflation, gdp_growth, base_interest):
        if self.selfoperation == False:
            raise NotImplementedError("This method should be implemented in a subclass or set selfoperation to True.")
        
        target_real_rate = 2.0 
        new_interest = inflation + target_real_rate
        
        if new_interest < -10.0: new_interest = -10.0
        if new_interest > 50.0: new_interest = 50.0
            
        return new_interest
        
    def intervene(self, amount_usd, current_rate, turn):
        required_domestic = amount_usd * current_rate
        if amount_usd > 0:
            self.usd += amount_usd
            self.domestic_money -= required_domestic
            self.add_log(turn, "Intervention", f"Buy USD: {amount_usd:+.0f} $")
        elif amount_usd < 0:
            if self.usd + amount_usd >= 0:
                self.usd += amount_usd
                self.domestic_money -= required_domestic
                self.add_log(turn, "Intervention", f"Sell USD: {amount_usd:+.0f} $")
            else:
                print(f"{self.name}: USD不足のため介入できませんでした。")
                return 
        self.turn_intervention_usd += amount_usd

    def budget_decide(self, current_rate, domestic_interest):
        """
        予算と税率を決定するメソッド。
        Net Debt / GDP Ratio を ±300% 以内に収めることを最優先とし、
        その範囲内で経済指標や満足度に基づいた調整を行う。
        """
        if self.selfoperation == False:
            raise NotImplementedError("This method should be implemented in a subclass or set selfoperation to True.")

        # ==================================================================================
        # 0. パラメータ設定 (ここを調整することでAIの性格や安全マージンを変更できます)
        # ==================================================================================
        P = {
            # --- 制御の閾値 (単位: %) ---
            'LIMIT_SAFE': 150.0,       # 安全圏の境界 (ここまでは通常の経済運営)
            'LIMIT_WARNING': 200.0,    # 警戒圏の境界 (ここを超えると是正モードへ移行)
            'LIMIT_HARD': 300.0,       # 絶対防衛ライン (ゲームオーバー条件)

            # --- 借金過多 (Debt Ratio > 0) 時の動作 ---
            # 緊急時 (Ratio > 280%)
            'EMERGENCY_DEBT_TAX': 0.60,        # 緊急増税目標値
            'EMERGENCY_DEBT_BUDGET': 10.0,     # 緊急緊縮予算 (税収の'EMERGENCY_DEBT_BUDGET'%に抑え、40%を借金返済へ)
            'EMERGENCY_DEBT_WEIGHTS': [20.0, 60.0, 20.0], # 生存維持優先 [年金, 産業, 軍事]
            
            # 警戒時 (200% < Ratio <= 280%)
            'WARNING_DEBT_BUDGET': 60.0,       # 緩やかな緊縮 (税収の95%を使う)

            # --- 資産過多 (Debt Ratio < 0) 時の動作 ---
            # 緊急時 (Ratio < -280%)
            'EMERGENCY_ASSET_TAX': 0.30,       # 緊急減税目標値
            'EMERGENCY_ASSET_BUDGET': 400.0,   # 緊急放出予算 (税収の'EMERGENCY_ASSET_BUDGET/100倍を使う＝資産取り崩し)
            'EMERGENCY_ASSET_WEIGHTS': [20.0, 70.0, 10.0], # 産業投資特化 (GDP分母を拡大して比率是正)

            # 警戒時 (-280% <= Ratio < -200%)
            'WARNING_ASSET_BUDGET': 105.0,     # 緩やかな放出 (税収の105%を使う)

            # --- 通常時の調整パラメータ ---
            'NORMAL_TAX_MIN': 0.1,
            'NORMAL_TAX_MAX': 0.7,
            'NORMAL_TAX_STEP': 0.02,           # 通常時の税率変更幅
        }

        # ==================================================================================
        # 1. 現状分析 (Net Debt Ratio 計算 - HTMLとロジックを統一)
        # ==================================================================================
        gdp = self.caluc_gdp()
        
        # 純資産 = 国内通貨残高 + (外貨準備 * 現在の為替レート)
        # これにより、円安時に外貨を持っていると資産評価額が上がり、Ratioが改善する効果も反映される
        net_asset = self.domestic_money + (self.usd * current_rate)
        
        # 純債務 (Net Debt) = -純資産
        # プラスなら借金状態、マイナスなら資産超過状態
        net_debt = -net_asset
        
        debt_ratio = 0.0
        if gdp > 0:
            debt_ratio = (net_debt / gdp) * 100.0
        
        # その他の経済指標の取得
        gdp_growth = self.get_gdp_change()
        inflation = self.price.get_price_change_rate()
        usd_change = self.get_usd_change()
        
        avg_satisfaction = 0
        if len(self.population) > 0:
            total_satis = sum(p[1].get_satisfaction() for p in self.population)
            avg_satisfaction = total_satis / len(self.population)
        
        is_in_debt = self.domestic_money < 0 # 現金ベースでの赤字判定用

        # ==================================================================================
        # 2. 基本方針の決定 (ゾーン制御)
        # ==================================================================================
        new_tax = self.tax
        target_total_budget = 100.0 # 100.0 = 均衡財政 (入った税収分だけ使う)
        
        # 予算配分の初期値 (ベースライン)
        w_pension = 40.0
        w_industry = 40.0
        w_military = 20.0
        
        # --- ゾーンA: 緊急事態（借金地獄） Ratio > 280% ---
        if debt_ratio > P['LIMIT_WARNING']:
            # 目標値に向かって税率を強制変更
            if new_tax < P['EMERGENCY_DEBT_TAX']:
                new_tax += 0.05
            else:
                new_tax = P['EMERGENCY_DEBT_TAX']
            
            # 危険度(0.0~1.0)を計算: 300%に近づくほど強力に絞る
            severity = (debt_ratio - P['LIMIT_WARNING']) / (P['LIMIT_HARD'] - P['LIMIT_WARNING'])
            severity = min(1.0, max(0.0, severity))
            
            # 予算規模を圧縮 (例: 95% -> 60% へ段階的に移行)
            target_total_budget = P['WARNING_DEBT_BUDGET'] * (1.0 - severity) + P['EMERGENCY_DEBT_BUDGET'] * severity
            
            # 配分を生存維持モードへ強制変更
            w_pension, w_industry, w_military = P['EMERGENCY_DEBT_WEIGHTS']

        # --- ゾーンB: 警戒レベル（借金多め） 200% < Ratio <= 280% ---
        elif debt_ratio > P['LIMIT_SAFE']:
            # 緩やかな増税トレンド
            new_tax += P['NORMAL_TAX_STEP']
            # 緩やかな緊縮財政
            target_total_budget = P['WARNING_DEBT_BUDGET']
            # 産業投資を少し抑える
            w_industry *= 0.8
            
        # --- ゾーンC: 緊急事態（金余りすぎ） Ratio < -280% ---
        elif debt_ratio < -P['LIMIT_WARNING']:
            # 強制減税
            if new_tax > P['EMERGENCY_ASSET_TAX']:
                new_tax -= 0.05
            else:
                new_tax = P['EMERGENCY_ASSET_TAX']
            
            # 予算大放出
            target_total_budget = P['EMERGENCY_ASSET_BUDGET']
            
            # 産業投資に特化してGDP(分母)の拡大を狙う
            w_pension, w_industry, w_military = P['EMERGENCY_ASSET_WEIGHTS']

        # --- ゾーンD: 警戒レベル（金余り） -280% <= Ratio < -200% ---
        elif debt_ratio < -P['LIMIT_SAFE']:
            # 緩やかな減税
            new_tax -= P['NORMAL_TAX_STEP']
            # 緩やかな放出
            target_total_budget = P['WARNING_ASSET_BUDGET']
            # 産業重視
            w_industry *= 1.2

        # --- ゾーンE: 安全圏 (通常運転) -200% <= Ratio <= 200% ---
        else:
            # 既存のロジックベースで微調整を行う
            
            # 1. 為替・インフレ対策による税率調整
            if usd_change < -5.0: new_tax += 0.03 # 通貨防衛
            
            if inflation > 5.0: new_tax += 0.02 # インフレ抑制
            elif inflation < 0.0: new_tax -= 0.02 # デフレ対策
            
            if gdp_growth < 0.5 and not is_in_debt: new_tax -= 0.02 # 景気刺激
            elif is_in_debt: new_tax += 0.01 # 現金不足なら少し増税
            
            if avg_satisfaction < 40: new_tax -= 0.02 # 不満が高いなら減税
            
            # 2. 経済状況による予算規模調整
            if is_in_debt:
                target_total_budget = 95.0 # 現金赤字なら少し絞る
            elif gdp_growth < 1.0 and usd_change > 0:
                target_total_budget = 105.0 # 景気悪い＆外貨余裕ありなら吹かす
            elif gdp_growth > 4.0:
                target_total_budget = 95.0 # 加熱気味なら抑える

            # 3. 予算配分の調整
            if usd_change < -1.0: w_military *= (1.2 + min(3.0, abs(usd_change)) * 0.3)
            elif usd_change > 1.0: w_military *= 1.3
            
            if gdp_growth > 4.0: w_military *= 1.2
            if gdp_growth < 2.0: w_industry *= 1.4
            elif gdp_growth > 8.0: w_industry *= 0.8
            
            if avg_satisfaction < 50: w_pension *= 1.5

        # ==================================================================================
        # 3. 最終調整とセーフティネット (クリッピング)
        # ==================================================================================
        
        # 税率が常識的な範囲に収まるように制限
        new_tax = max(P['NORMAL_TAX_MIN'], min(P['NORMAL_TAX_MAX'], new_tax))

        # 【最終防衛ライン】
        # 計算結果がどうであれ、ハードリミット(300%)直前なら強制的にブレーキを踏む
        if debt_ratio > P['LIMIT_HARD'] - 10.0: # 例: 290%を超えていたら
            # どんなに景気が悪くても、予算を税収の半分以下にして借金返済に回す
            target_total_budget = min(target_total_budget, 50.0) 

        # 予算配分比率の正規化
        total_weight = w_pension + w_industry + w_military
        if total_weight == 0: total_weight = 1.0
        
        factor = target_total_budget / total_weight
        
        pension_alloc = w_pension * factor
        industry_alloc = w_industry * factor
        military_alloc = w_military * factor
        
        return new_tax, [pension_alloc, industry_alloc, military_alloc]
    
    def load(self, name):
        self.name = name
        with open(f"{name}.csv", 'r', newline='', encoding= 'utf-8') as file2:
            reader2 = csv.reader(file2)
            cnt = 0
            tcnt =-1
            pcnt = -1
            for row in reader2:
                if cnt == 0:
                    self.price = Price(int(row[1]))
                    self.turn_year = int(row[1])
                    self.money_name = row[2]
                    self.tax = float(row[3])
                    self.bef_tax = float(row[4])
                elif cnt == 1:
                    self.price.past_price = [float(x) for x in row]
                elif cnt == 2:
                    pass
                elif cnt == 3:
                    self.budget.budget = [float(row[0]), float(row[1]), float(row[2]), float(row[3])]
                elif cnt == 4:
                    tcnt = int(row[0])
                    self.budget.past_budget = []
                elif cnt <= 4 + tcnt:
                    self.budget.past_budget.append([float(row[0]), float(row[1]), float(row[2]), float(row[3])])
                elif cnt == 5 + tcnt:
                    self.industry = CountryPower(row[0])
                elif cnt == 6 + tcnt:
                    self.industry.turn = int(row[0])
                elif cnt == 7 + tcnt:
                    self.industry.past = [float(x) for x in row]
                elif cnt == 8 + tcnt:
                    self.industry.bef = float(row[0])
                elif cnt == 9 + tcnt:
                    self.industry.past_power = [float(x) for x in row]
                elif cnt == 9 + tcnt + 1:
                    self.military = CountryPower(row[0])
                elif cnt == 10 + tcnt + 1:
                    self.military.turn = int(row[0])
                elif cnt == 11 + tcnt + 1:
                    self.military.past = [float(x) for x in row]
                elif cnt == 12 + tcnt + 1:
                    self.military.bef = float(row[0])
                elif cnt == 12 + tcnt + 2:
                    self.military.past_power = [float(x) for x in row]
                elif cnt == 13 + tcnt + 2:
                    self.population = [[0,0, 0] for _ in range(int(row[0]))]
                    pcnt = int(row[0])
                elif cnt <= 13 + tcnt + pcnt + 2:
                    self.population[cnt - (14 + tcnt + 2)][0] = int(row[0])
                    self.population[cnt - (14 + tcnt + 2)][1] = Satisfaction(float(row[1]), float(row[2]), float(row[3]), float(row[4]), int(row[5]))
                    # 給料のロード時も、befsalaryなどが正しく設定されていれば問題ない
                    self.population[cnt - (14 + tcnt + 2)][2] = Salary(cnt - (14 + tcnt + 2), float(row[6]), float(row[7]), float(row[8]), coef=1)
                    self.population[cnt - (14 + tcnt + 2)][2].befsalary = float(row[9])
                    
                elif cnt == 14 + tcnt + pcnt + 2:
                    self.gdp_usd = float(row[0])
                    self.price_usd = float(row[1])
                    self.usd = float(row[2])
                    self.population_p = float(row[3])
                    self.salary_p = float(row[4])
                    self.selfoperation = True if row[5] == "True" else False
                    
                    if len(row) > 6:
                        self.domestic_money = float(row[6])
                    else:
                        self.domestic_money = 0.0

                elif cnt == 15 + tcnt + pcnt + 2:
                    self.past_gdp_usd = [float(x) for x in row]
                elif cnt == 16 + tcnt + pcnt + 2:
                    self.past_gdp = [float(x) for x in row]
                elif cnt == 17 + tcnt + pcnt + 2:
                    self.past_usd = [float(x) for x in row]
                elif cnt == 18 + tcnt + pcnt + 2:
                    self.past_population = [int(x) for x in row]
                elif cnt == 19 + tcnt + pcnt + 2:
                    self.past_domestic_money = [float(x) for x in row]
                
                elif cnt == 20 + tcnt + pcnt + 2:
                    self.past_trade_balance = [float(x) for x in row]
                
                # ★追加: 関税データの読み込み
                elif cnt == 21 + tcnt + pcnt + 2:
                    # 形式: target_country, rate, target_country, rate...
                    self.tariffs = {}
                    for i in range(0, len(row), 2):
                        if i+1 < len(row):
                            self.tariffs[row[i]] = float(row[i+1])

                cnt += 1
            
            # 古いセーブデータ対策
            if not hasattr(self, 'past_trade_balance'):
                self.past_trade_balance = [0.0] * len(self.past_gdp)
            if not hasattr(self, 'tariffs'):
                self.tariffs = {}
            if not hasattr(self, 'turn_tariff_cost_usd'):
                self.turn_tariff_cost_usd = 0.0

    def save_country(self):
        data = [[self.name,self.turn_year,self.money_name,
                 self.tax, self.bef_tax]]
        
        data.append(self.price.past_price)
        fc = []
        for k, v in self.foreign_currency:
            fc.append([k,v])
        data.append(fc)
        data.append(self.budget.budget)
        data.append([len(self.budget.past_budget)])
        for i in range(len(self.budget.past_budget)):
            data.append(self.budget.past_budget[i])
        for i in self.industry.save_list():
            data.append(i)
        for i in self.military.save_list():
            data.append(i)
        
        data.append([len(self.population)])
        for i in range(len(self.population)):
            tmp = [self.population[i][0]]
            for j in range(len(self.population[i][1].save_list())):
                tmp.append(self.population[i][1].save_list()[j])
            for j in range(len(self.population[i][2].save_list())):
                tmp.append(self.population[i][2].save_list()[j])
            data.append(tmp)   
        
        a = [self.gdp_usd, self.price_usd, self.usd, self.population_p, self.salary_p, self.selfoperation, self.domestic_money]
        data.append(a)
        
        data.append(self.past_gdp_usd)
        data.append(self.past_gdp)
        data.append(self.past_usd)
        data.append(self.past_population)
        data.append(self.past_domestic_money)
        
        data.append(self.past_trade_balance)
        
        # ★追加: 関税データの保存
        # 1行に平坦化して保存
        tf_row = []
        for target, rate in self.tariffs.items():
            tf_row.append(target)
            tf_row.append(rate)
        data.append(tf_row)
        
        with open(f'{self.name}.csv', 'w', newline='', encoding='utf-8') as file: 
            writer = csv.writer(file)
            writer.writerows(data)
    
    
    def get_usd_change(self):
        pt = len(self.past_usd) - 1 - 1
        if len(self.past_usd) < self.turn_year :
            return 0.0
        return (self.past_usd[-1] - self.past_usd[pt]) / (abs(self.past_usd[pt]) + 0.00001) * 100.0    
    
    def next_turn_year(self, tax, bud, rate, turn, domestic_interest, usd_interest):
        assert(len(self.population) == 100), "Population list should have 100 elements."
        
        if tax < 0 or tax > 1:
            return False
        
        if abs(tax - self.tax) > 0.001:
            change_type = "Tax Hike" if tax > self.tax else "Tax Cut"
            self.add_log(turn, "Fiscal Policy", f"{change_type}: {self.tax*100:.1f}% -> {tax*100:.1f}%")

        self.domestic_money *= (1 + domestic_interest / 100.0)
        self.usd *= (1 + usd_interest / 100.0)
        
        budget_surplus_ratio = 100 - (bud[0] + bud[1] + bud[2])
        current_gdp = self.caluc_gdp()
        self.domestic_money += (current_gdp * tax) * (budget_surplus_ratio / 100.0)

        # ---------------------------------------------------------
        # 2. 人口動態
        # ---------------------------------------------------------
        reproductive_group = self.population[20:40]
        total_repro_pop = sum(p[0] for p in reproductive_group)
        avg_satis_repro = sum(p[1].get_satisfaction() for p in reproductive_group) / len(reproductive_group) if reproductive_group else 50
        
        avg_salary_repro = sum(p[2].get_salary() for p in reproductive_group) / len(reproductive_group) if reproductive_group else 0
        current_price = self.price.get_price()
        purchasing_power = avg_salary_repro / (current_price + 1.0) 
        
        base_birth_rate = 0.035 
        satis_factor = (avg_satis_repro - 50.0) * 0.0004 
        econ_factor = min(purchasing_power * 0.005, 0.015) 
        
        final_birth_rate = max(0.005, base_birth_rate + satis_factor + econ_factor)
        
        new_babies = int(total_repro_pop * final_birth_rate)
        new_babies = int(new_babies * random.uniform(0.95, 1.05))
        
        welfare_quality = bud[0] 
        self.population.pop() 
        
        for i in range(len(self.population)):
            age = i
            current_pop = self.population[i][0]
            if current_pop <= 0: continue

            age_shift = 80 + (welfare_quality * 0.15)
            mortality_rate = 1.0 / (1.0 + math.e ** (-0.2 * (age - age_shift)))
            base_death_rate = 0.001 
            if age < 5: base_death_rate = 0.005 
            
            total_death_prob = base_death_rate + mortality_rate
            survivors = int(current_pop * (1.0 - total_death_prob))
            self.population[i][0] = max(0, survivors)

        new_generation = [
            new_babies, 
            Satisfaction(initsatis=50.0, price=current_price, salary=0, tax=self.tax, turn_year=self.turn_year), 
            Salary(old=0, price=0, industry=0, init=-1, coef=self.salary_p)
        ]
        self.population.insert(0, new_generation)
        assert(len(self.population) == 100)

        # ---------------------------------------------------------
        # 3. 予算執行と経済・満足度更新
        # ---------------------------------------------------------
        self.bef_tax = self.tax
        self.tax = tax
        
        total_tax_revenue = self.caluc_gdp() * self.tax
        self.budget.change_budget(total_tax_revenue, bud[0], bud[1], bud[2])
        
        # 20歳の就職
        self.population[20][2] = Salary(
            old=20, 
            price=current_price, 
            industry=self.industry.caluc_power(), 
            init=self.population[21][2].get_salary() * 0.98 if self.population[21][2].get_salary() > 0 else 100, 
            coef=self.salary_p
        )
        # 66歳の定年
        self.population[66][2] = Salary(0, 0, 0, 0, coef=self.salary_p)

        elderly_total_pop = sum(self.population[i][0] for i in range(66, 100))
        pension_budget_amount = total_tax_revenue * (bud[0] / 100.0)
        
        pension_per_capita = 0
        if elderly_total_pop > 0:
            pension_per_capita = pension_budget_amount / elderly_total_pop
        
        for i in range(100):
            person_satis = self.population[i][1]
            person_salary = self.population[i][2]
            
            if i >= 66:
                person_salary.set_salary(pension_per_capita)
                person_satis.change_satisfaction(price=current_price, salary=pension_per_capita, old=i, tax=tax)
                if pension_per_capita < current_price * 0.5:
                    person_satis.satisfaction *= 0.9 
            elif 20 <= i <= 65:
                person_salary.change_salary(industry=self.industry.caluc_power(), price=current_price, old=i)
                current_salary = person_salary.get_salary()
                person_satis.change_satisfaction(price=current_price, salary=current_salary, old=i, tax=tax)
            else:
                pass

        for i in range(1, 100):
            curr_satis = self.population[i][1].satisfaction
            prev_satis = self.population[i-1][1].satisfaction
            new_satis = curr_satis * 0.7 + prev_satis * 0.3
            self.population[i][1].set_satisfaction(new_satis)

        if current_price > 0:
            self.price_salary = self.get_average_salary() / current_price
        else:
            self.price_salary = -100.0

    def get_gdp_usd(self):
        return self.gdp_usd
    def set_gdp_usd(self, gdp_usd):
        self.gdp_usd = gdp_usd
        self.past_gdp_usd.append(gdp_usd)
    
    def get_domestic_money_change(self):
        pt = len(self.past_domestic_money) - 1 - 1
        if len(self.past_domestic_money) < 2:
            return 0.0
        return (self.past_domestic_money[-1] - self.past_domestic_money[pt]) / (abs(self.past_domestic_money[pt]) + 0.00001) * 100.0
           
    def next_turn(self, money, rate, turn):
        if not self.past_gdp_usd or self.past_gdp_usd[-1] < 0:
            current_gdp_usd = self.caluc_gdp() / (rate + 0.00001)
            if len(self.past_gdp_usd) > 0:
                self.past_gdp_usd[-1] = current_gdp_usd
            else:
                self.past_gdp_usd = [current_gdp_usd]
            self.gdp_usd = current_gdp_usd
            
        if len(self.past_gdp) < 2:
            gdp_growth = 0.0
        else:
            gdp_growth = self.get_gdp_change()
        gdp_growth = max(-10.0, min(10.0, gdp_growth))
        
        current_rate_val = money.get_rate()
        past_rates = money.get_past_rate()
        if len(past_rates) >= 2:
            prev_rate_val = past_rates[-2]
        else:
            prev_rate_val = current_rate_val
        exchange_change = 0.0
        if prev_rate_val > 0.0001:
            exchange_change = (current_rate_val - prev_rate_val) / prev_rate_val * 100.0
        exchange_change = max(-15.0, min(15.0, exchange_change))

        # === ★追加: 関税コストによるインフレ圧力 ===
        # 輸入関税コスト / GDP (USDベース) を計算し、それを物価上昇圧力として加算
        # exchange_change（正の値で自国通貨安＝輸入物価上昇）に上乗せして擬似的に表現する
        tariff_inflation_pressure = 0.0
        if self.gdp_usd > 0:
            tariff_ratio = self.turn_tariff_cost_usd / self.gdp_usd
            # 係数 100.0 で % 表記へ変換。さらに係数を掛けてインパクト調整してもよい。
            # ここではシンプルに、コスト比率10%なら物価が10%上がる圧力となると仮定。
            tariff_inflation_pressure = tariff_ratio * 1000.0
        
        # 圧力を適用
        exchange_change += tariff_inflation_pressure

        # ログ出力（デバッグ用）
        if tariff_inflation_pressure > 0.1:
            print(f"[{self.name}] Tariff Cost: {self.turn_tariff_cost_usd:.1f} USD, Inflation Pressure: +{tariff_inflation_pressure:.2f}%")

        # 計算が終わったら累積コストをリセット（次の貿易フェーズで再計算されるため）
        self.turn_tariff_cost_usd = 0.0
        # ===============================================

        try:
            interest_val = money.get_true_interest()
        except:
            interest_val = 0.0
            
        self.price.change_price(
            interest=interest_val,
            gdp_growth=gdp_growth,
            exchange_rate_change=exchange_change
        )

        elderly_population = sum(self.population[i][0] for i in range(66, 100))
        total_budget = self.budget.budget[0] if len(self.budget.budget) > 0 else 100.0
        pension_rate = self.budget.budget[1] if len(self.budget.budget) > 1 else 40.0
        pension_amount = total_budget * (pension_rate / 100.0)
        pension = pension_amount / elderly_population if elderly_population > 0 else 0 
        
        current_price = self.price.get_price()
        
        for i in range(len(self.population)):
            if i > 65:
                self.population[i][2].set_salary(pension)
                self.population[i][1].change_satisfaction(
                    price=current_price, salary=pension, old=i, tax=self.tax
                )
            else:
                self.population[i][1].change_satisfaction(
                    price=current_price, salary=self.population[i][2].get_salary(), old=i, tax=self.tax
                )
        
        for i in range(1, 100):
            prev_satis = self.population[i-1][1].satisfaction
            curr_satis = self.population[i][1].satisfaction
            self.population[i][1].set_satisfaction((curr_satis + prev_satis) / 2)
            
        ind_budget_rate = self.budget.budget[2] if len(self.budget.budget) > 2 else 40.0
        mil_budget_rate = self.budget.budget[3] if len(self.budget.budget) > 3 else 20.0
        
        investment_efficiency = 1.0
        if interest_val > 3.0:
            penalty = (interest_val - 3.0) * 0.03
            investment_efficiency = max(0.1, 1.0 - penalty)
            
        military_spillover = (mil_budget_rate * 0.01 * total_budget) * 0.20
        
        base_ind_investment = ind_budget_rate * 0.01 * total_budget
        self.industry.add_power((base_ind_investment + military_spillover) * investment_efficiency, rate, turn)
        self.military.add_power(mil_budget_rate * 0.01 * total_budget, rate, turn)
        
        industry_power = self.industry.caluc_power()
        for i in range(len(self.population)):
            self.population[i][2].change_salary(industry=industry_power, price=current_price, old=i)
        
        current_gdp = self.caluc_gdp()
        self.past_gdp.append(current_gdp)
        self.set_gdp_usd(current_gdp / (rate + 0.00001)) 
        self.past_population.append(self.get_population())
        self.past_domestic_money.append(self.domestic_money)

    def get_population(self):
        all_population = 0
        for i in range(len(self.population)):
            all_population += self.population[i][0]
        return all_population
    
    def caluc_gdp(self):
        gdp = 0.0
        for i in range(len(self.population)):
            if i < 20 or i > 65:
                continue
            gdp += self.population[i][0] * self.population[i][2].get_salary()
        return gdp
    def get_gdp(self):
        return self.past_gdp[-1]
    
    def add_money(self, old, money):
        salary = self.population[old][2].get_salary()
        per = (money - salary)/salary
        self.population[old][1].satisfaction *= (1 + per)
    
    def get_average_salary(self):
        ave = 0.0 
        p = 0
        for i in range(len(self.population)):
            if self.population[i][2].get_salary() == 0:
                continue
            ave += self.population[i][2].get_salary() * self.population[i][0]
            p += self.population[i][0]
        ave /= p if p > 0 else 1
        return ave
        
    def get_gdp_usd_change(self):
        if len(self.past_gdp_usd) < 2:
            return 0.0
        if len(self.past_gdp_usd) < self.turn_year:
            return (self.past_gdp_usd[-1] - self.past_gdp_usd[0]) / (self.past_gdp_usd[0] + 0.00001) * 100.0   
        return (self.past_gdp_usd[len(self.past_gdp_usd)-1] - self.past_gdp_usd[len(self.past_gdp_usd) - 1 - self.turn_year]) / (self.past_gdp_usd[len(self.past_gdp_usd) - 1 - self.turn_year] + 0.00001) * 100.0        
    
    def get_gdp_change(self):
        if len(self.past_gdp) < self.turn_year:
            return (self.past_gdp[-1] - self.past_gdp[0]) / (self.past_gdp[0] + 0.00001) * 100.0   
        return (self.past_gdp[len(self.past_gdp)-1] - self.past_gdp[len(self.past_gdp) - 1 - self.turn_year]) / (self.past_gdp[len(self.past_gdp) - 1 - self.turn_year] + 0.00001) * 100.0
    
    def __str__(self):
        return f"{self.name} (Money: {self.money_name}, Population: {self.population})"

    def __repr__(self):
        return f"Country(name={self.name}, Money={self.money_name}, population={self.population})"