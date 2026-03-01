from Country import Country
from Money import Money
import csv
import math

class World:
    # ★修正: index_base_turn 引数を追加 (デフォルト50)
    def __init__(self, turn_year, index_base_turn=50):
        self.Country_list = []
        self.turn = 0
        self.turn_year = turn_year
        self.Money_list = []  # 通貨のリスト
        self.index_base_turn = index_base_turn # Currency Indexの基準ターン

    def add_country(self, country):
        if isinstance(country, Country):
            self.Country_list.append(country)
        else:
            raise TypeError("Only instances of Country can be added.")
        
    def add_money(self, money):
        if isinstance(money, Money):
            self.Money_list.append(money)
        else:
            raise TypeError("Only instances of Money can be added.")
        
    def save(self):
        data = [[self.turn, self.turn_year]]
        tmp = []
        for i in range(len(self.Country_list)):
            tmp.append(self.Country_list[i].name)
        data.append(tmp)
        tmp = []
        for i in range(len(self.Money_list)):
            tmp.append(self.Money_list[i].name)
        data.append(tmp)
        with open(f'World.csv', 'w', newline='', encoding='utf-8') as file: 
            writer = csv.writer(file)
            writer.writerows(data)
        for i in range(len(self.Country_list)):
            self.Country_list[i].save_country()
        for j in range(len(self.Money_list)):
            self.Money_list[j].save_money()
    
    def load(self):
        try:
            # CSVファイルを開く (読み込みモード 'r'、改行コードなし newline='')
            # encoding='utf-8' を指定することで、日本語などの文字化けを防ぐ
            self.Country_list.clear()
            self.Money_list.clear()
            with open("World.csv", 'r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                # データを1行ずつ読み込む
                cnt = 0
                for row in reader:
                    if cnt == 0:
                        self.turn = int(row[0])
                        self.turn_year = int(row[1])
                    elif cnt == 1:
                        
                        for i in range(len(row)):
                            c1 = Country(row[i], "d", -1, 1, 1)
                            c1.load(row[i])
                            self.add_country(c1)
                    elif cnt == 2:
                        
                        for i in range(len(row)):
                            # ★修正: デフォルトのコンストラクタに合わせて is_major=False (CSV読み込みで上書きされる)
                            m1 = Money(row[i], 0, 0, False, is_major=False)
                            m1.load(row[i])
                            self.add_money(m1)
                    cnt += 1

        except FileNotFoundError:
            print(f"エラー: ファイル  が見つかりません。")
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            
    def Next_turn(self):
        self.turn += 1
        
        # ★追加: AIによる関税率の自動更新 (前ターンのデータを使うため、リセット前に実行)
        for country in self.Country_list:
            country.decide_and_update_tariffs(self.Country_list)

        # 1. 各国のターン進行
        for country in self.Country_list:
            # ターン開始時に貿易内訳をリセット (AI判断が終わった後で行う)
            country.trade_balance_breakdown = {}

            my_money = next((m for m in self.Money_list if m.name == country.money_name), None)
            if my_money:
                country.next_turn(my_money, my_money.get_rate(), self.turn)

        # ====== ★追加: 同じ通貨圏のインフレ率を連動（GDP加重平均） ======
        sync_strength = 0.6  # 連動の強さ（0.0で連動なし、1.0で完全一致）
        currency_groups = {}
        
        # 通貨ごとに国をグループ化
        for country in self.Country_list:
            if country.money_name not in currency_groups:
                currency_groups[country.money_name] = []
            currency_groups[country.money_name].append(country)

        # グループごとにインフレ率を調整
        for money_name, group in currency_groups.items():
            if len(group) > 1: # 同じ通貨を使う国が複数いる場合のみ処理
                total_weight = 0.0
                weighted_inflation_sum = 0.0
                
                # 通貨圏全体のGDPと、加重インフレ率の合計を計算
                for c in group:
                    gdp = max(0.01, c.get_gdp_usd()) # ゼロ除算防止
                    
                    # ★変更: 単純なGDPではなく、GDPの2乗（あるいは1.5乗など）を重みにする
                    # これにより、GDPが突出している国(USAなど)の影響力が圧倒的になります。
                    # もしこれでも足りなければ `** 3.0` にすると完全なる覇権状態になります。
                    weight = gdp ** 2.0 
                    
                    total_weight += weight
                    weighted_inflation_sum += c.price.current_inflation * weight

                # 圧倒的影響力を持たせた加重平均インフレ率の算出
                avg_inflation = weighted_inflation_sum / total_weight

                # 各国のインフレ率を平均値に平滑化
                for c in group:
                    current_inf = c.price.current_inflation
                    synced_inf = (current_inf * (1.0 - sync_strength)) + (avg_inflation * sync_strength)
                    
                    # 1. インフレ率の変数を更新
                    c.price.current_inflation = synced_inf
                    
                    # 2. 既に計算・追加されてしまった「今ターンの物価」を再計算して上書き
                    if len(c.price.past_price) >= 2:
                        prev_price = c.price.past_price[-2] # 1ターン前の物価
                        # 連動後のインフレ率を使って今ターンの物価を出し直す
                        corrected_price = max(0.01, prev_price * (1.0 + synced_inf))
                        c.price.past_price[-1] = corrected_price # 履歴の最後（今ターン）を上書き
        # ================================================================

        # このターンの貿易収支を一時記録する辞書を作成
        current_turn_trade_balance = {c.name: 0.0 for c in self.Country_list}

        
        # 2. 国際貿易
        for i in range(len(self.Country_list)-1):
            country_a = self.Country_list[i]
            rate_a = 1.0
            money_a = next((m for m in self.Money_list if m.name == country_a.money_name), None)
            if money_a: rate_a = money_a.get_rate()
            
            industry_a = country_a.industry.caluc_power()
            # ゼロ除算防止
            price_a = max(0.01, country_a.price.get_price() / (rate_a + 0.00001))
            gdp_a = max(0.0, country_a.get_gdp_usd())

            for k in range(i+1, len(self.Country_list)):
                country_b = self.Country_list[k]
                rate_b = 1.0
                money_b = next((m for m in self.Money_list if m.name == country_b.money_name), None)
                if money_b: rate_b = money_b.get_rate()
                
                industry_b = country_b.industry.caluc_power()
                price_b = max(0.01, country_b.price.get_price() / (rate_b + 0.00001))
                gdp_b = max(0.0, country_b.get_gdp_usd())

                # === 【重要修正】関税を考慮した競争力の計算 ===
                price_sensitivity = 1.0
                bonus_a = 1.0
                bonus_b = 1.0
                
                if money_a and money_a.base_currency: bonus_a *= 1.2
                if money_b and money_b.base_currency: bonus_b *= 1.2

                # --- 関税の適用 (Effective Priceの計算) ---
                # B国市場で売るA国製品の価格 = A国価格 * (1 + B国がA国にかける関税)
                tariff_b_to_a = country_b.get_tariff(country_a.name)
                eff_price_a_in_b = price_a * (1.0 + tariff_b_to_a)

                # A国市場で売るB国製品の価格 = B国価格 * (1 + A国がB国にかける関税)
                tariff_a_to_b = country_a.get_tariff(country_b.name)
                eff_price_b_in_a = price_b * (1.0 + tariff_a_to_b)

                eff_industry_a = industry_a * bonus_a
                eff_industry_b = industry_b * bonus_b

                # 価格競争力の比較（実効価格を使用）
                if eff_price_a_in_b < eff_price_b_in_a:
                    # Aの方が安い
                    ratio = eff_price_b_in_a / eff_price_a_in_b
                    eff_industry_a *= pow(ratio, price_sensitivity)
                else:
                    # Bの方が安い
                    ratio = eff_price_a_in_b / eff_price_b_in_a
                    eff_industry_b *= pow(ratio, price_sensitivity)

                trade_scale = (gdp_a + gdp_b) / 2.0
                industry_diff = abs(eff_industry_a - eff_industry_b)
                max_industry = max(eff_industry_a, eff_industry_b, 1.0)
                competitiveness_factor = industry_diff / max_industry
                
                sensitivity = 0.05 
                trade_volume = int(trade_scale * competitiveness_factor * sensitivity)

                # --- 軍事力による交渉力 ---
                mil_power_a = country_a.military.caluc_power()
                mil_power_b = country_b.military.caluc_power()
                mil_ratio = (mil_power_a + 1000) / (mil_power_b + 1000)

                is_a_winner = (eff_industry_a > eff_industry_b)

                if is_a_winner:
                    if mil_ratio > 1.0:
                        trade_volume = int(trade_volume * min(1.5, mil_ratio))
                    else:
                        trade_volume = int(trade_volume * max(0.5, mil_ratio))
                else:
                    if mil_ratio < 1.0:
                        trade_volume = int(trade_volume * min(1.5, 1.0 / (mil_ratio + 0.0001)))
                    else:
                        trade_volume = int(trade_volume * max(0.5, 1.0 / (mil_ratio + 0.0001)))

                # --- 富の移動と関税コストの集計 ---
                if is_a_winner:
                    # Aが輸出 (Bが輸入)
                    country_a.usd += trade_volume
                    country_b.usd -= trade_volume
                    
                    # 貿易収支の記録
                    current_turn_trade_balance[country_a.name] += trade_volume
                    current_turn_trade_balance[country_b.name] -= trade_volume
                    
                    # ★追加: 国別内訳の記録 (Aはプラス, Bはマイナス)
                    country_a.trade_balance_breakdown[country_b.name] = country_a.trade_balance_breakdown.get(country_b.name, 0.0) + trade_volume
                    country_b.trade_balance_breakdown[country_a.name] = country_b.trade_balance_breakdown.get(country_a.name, 0.0) - trade_volume

                    # ★追加: B国は輸入したため、関税コストが発生
                    # 関税コスト = 輸入額(trade_volume) * 関税率(tariff_b_to_a)
                    tariff_cost = trade_volume * tariff_b_to_a
                    country_b.turn_tariff_cost_usd += tariff_cost

                else:
                    # Bが輸出 (Aが輸入)
                    country_a.usd -= trade_volume
                    country_b.usd += trade_volume
                    
                    # 貿易収支の記録
                    current_turn_trade_balance[country_a.name] -= trade_volume
                    current_turn_trade_balance[country_b.name] += trade_volume
                    
                    # ★追加: 国別内訳の記録 (Bはプラス, Aはマイナス)
                    country_a.trade_balance_breakdown[country_b.name] = country_a.trade_balance_breakdown.get(country_b.name, 0.0) - trade_volume
                    country_b.trade_balance_breakdown[country_a.name] = country_b.trade_balance_breakdown.get(country_a.name, 0.0) + trade_volume

                    # ★追加: A国は輸入したため、関税コストが発生
                    tariff_cost = trade_volume * tariff_a_to_b
                    country_a.turn_tariff_cost_usd += tariff_cost

        # 3. 履歴の更新
        for country in self.Country_list:
            country.past_usd.append(country.usd)
            
            # 計算した貿易収支を履歴に追加
            balance = current_turn_trade_balance.get(country.name, 0.0)
            country.past_trade_balance.append(balance)

        

        # === 4. Currency Indexの計算 (★修正: 主要通貨のみ参照) ===
        # 固定の50ではなく self.index_base_turn を使用
        # 基準ターンで基準レートをスナップショット
        if self.turn == self.index_base_turn:
            for m in self.Money_list:
                m.base_index_rate = m.get_rate()
                print(f"Captured Base Rate for {m.name}: {m.base_index_rate}")

        if self.turn >= self.index_base_turn:
            # 基軸通貨(USD)とそれ以外を分ける
            base_money = next((m for m in self.Money_list if m.base_currency), None)
            non_base_monies = [m for m in self.Money_list if not m.base_currency]

            if base_money and non_base_monies:
                # --- Dollar Index (Base Currency Index) の計算 ---
                # is_major=True の通貨のみをバスケットに入れる
                major_basket = [m for m in non_base_monies if m.is_major]
                
                ratios = []
                for m in major_basket:
                    if m.base_index_rate and m.base_index_rate > 0:
                        ratio = m.get_rate() / m.base_index_rate
                        ratios.append(ratio)
                
                # 平均を取ってインデックス化 (Base Turn = 100)
                # 主要通貨が定義されていない場合などは 1.0 (Index=100) とする
                usd_strength_factor = sum(ratios) / len(ratios) if ratios else 1.0
                base_money.currency_index = usd_strength_factor * 100.0

                # --- Other Indices (Yen Index etc) の計算 ---
                # 全ての通貨について、主要通貨バスケットで計算された usd_strength_factor を使用して算出
                for m in non_base_monies:
                    if m.get_rate() > 0 and m.base_index_rate:
                        strength_vs_usd = m.base_index_rate / m.get_rate()
                        m.currency_index = strength_vs_usd * base_money.currency_index
            
            else:
                # 万が一基軸通貨がない場合などは100維持
                for m in self.Money_list:
                    m.currency_index = 100.0
        else:
            # 基準ターン未満はすべて100
            for m in self.Money_list:
                m.currency_index = 100.0
        
        # 履歴への追加
        for m in self.Money_list:
            m.past_indices.append(m.currency_index)
    def __str__(self):
        return f"World with {len(self.Country_list)} countries."

    def __repr__(self):
        return f"World(countries={self.Country_list})"