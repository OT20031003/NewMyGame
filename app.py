# app.py
from flask import Flask, render_template, request, redirect, url_for
from Country import Country
from World import World
from Money import Money
import random
app = Flask(__name__)

# グローバルなWorldオブジェクト
turn_year = 3
world = None
# Currency Index の基準ターン設定
CURRENCY_INDEX_BASE_TURN = 80
# 初期化関数
def initialize_world(Load):
    global world
    world = World(turn_year, index_base_turn=CURRENCY_INDEX_BASE_TURN)
    # initial_price を追加して個別に物価レベルを設定
    default_countries = [
        # 日本: 円安反映 (1ドル=150円想定)。物価15000, 給与係数150 -> 購買力維持
        Country(name="Japan", money_name="Yen", turn_year=turn_year, population_p=5.99, salary_p=0.1*140.0, initial_price=0.1*5000, selfoperation=True, industry_p=1200, military_p=200),
        
        # アメリカ: 基軸 (基準値)。物価100, 給与係数1.0
        Country(name="USA", money_name="Dollar", turn_year=turn_year, population_p=6.3, salary_p=0.1*2.4, initial_price=0.1*100, selfoperation=True, industry_p=2100, military_p=2000),
        
        # フランス: ユーロ (1ドル=0.92ユーロ想定)。物価95, 給与0.95
        Country(name="France", money_name="Euro", turn_year=turn_year, population_p=5.75, salary_p=0.1*2.1, initial_price=0.1*80, selfoperation=True, industry_p=3000, military_p=300),
        
        Country(name="Itary", money_name="Euro", turn_year=turn_year, population_p=5.70, salary_p=0.1*1.5, initial_price=0.1*60, selfoperation=True, industry_p=3000, military_p=300),
        
        # ドイツ: 産業強め
        Country(name="Germany", money_name="Euro", turn_year=turn_year, population_p=5.9, salary_p=0.1*2.6, initial_price=0.1*95, selfoperation=True, industry_p=5000, military_p=250),
        
        # スイス
        Country(name="Switzerland", money_name="Swissfranc", turn_year=turn_year, population_p=4.9, salary_p=0.1*3.4, initial_price=0.1*140, selfoperation=True, industry_p=7500, military_p=250),
        
        # 中国: 人口多, 物価安(1ドル=7.2元), 給与低めだが産業力最強クラス
        Country(name="China", money_name="Yuan", turn_year=turn_year, population_p=7.0, salary_p=0.1*1.0, initial_price=0.1*100, selfoperation=True, industry_p=2000, military_p=1500),
        
        # イギリス: ポンド (1ドル=0.76ポンド想定)
        Country(name="England", money_name="Pond", turn_year=turn_year, population_p=5.66, salary_p=0.1*2.0, initial_price=0.1*70, selfoperation=True, industry_p=3500, military_p=300),
        
        Country(name="Russia", money_name="Ruble", turn_year=turn_year, population_p=6.10, salary_p=0.1*75.0, initial_price=0.1*4200, selfoperation=True, industry_p=500, military_p=1500),
        Country(name="Spain", money_name="Euro", turn_year=turn_year, population_p=5.66, salary_p=0.1*1.5, initial_price=0.1*60, selfoperation=True, industry_p=2900, military_p=400),
        
        # タイ: 新興国モデル (1ドル=33バーツ), 産業成長中
        Country(name="Thailand", money_name="Baht", turn_year=turn_year, population_p=5.7, salary_p=0.1*15.0, initial_price=0.1*500, selfoperation=True, industry_p=300, military_p=100)
    ]
    
    # === 通貨の初期設定 ===
    # value は「1 USD = 何単位の通貨か」を表すレートとして設定します。
    # base_currency=True の通貨(Dollar)が基準になります。
    # is_major=True で主要通貨バスケットに含めるかを指定
    
    default_money = [
        Money(name="Yen", interest=0.25, value=100.00, base_currency=False, is_major=True), # 主要通貨
        Money(name="Dollar", interest=4.5, value=1.0, base_currency=True, is_major=True),   # 基軸通貨(主要)
        Money(name="Euro", interest=3.5, value=0.92, base_currency=False, is_major=True),   # 主要通貨
        Money(name="Yuan", interest=3.0, value=7.20, base_currency=False, is_major=False),   # 主要通貨
        Money(name="Pond", interest=4.0, value=0.76, base_currency=False, is_major=True),   # 主要通貨
        Money(name="Baht", interest=2.5, value=33.0, base_currency=False, is_major=False),  # 非主要通貨
        Money(name="Swissfranc", interest=1.0, value=0.85, base_currency=False, is_major=False), # 主要通貨
        Money(name="CanadaDollar", interest=3.0, value=1.36, base_currency=False, is_major=False), # 主要通貨
        Money(name="AustraliaDollar", interest=3.0, value=1.50, base_currency=False, is_major=False), # 主要通貨
        Money(name="Ruble", interest=15.0, value=92.0, base_currency=False, is_major=False)  # 非主要通貨
    ]
    if Load == True:
        world.load()
        # Load時はWorldが再作成されない場合があるので、変数を強制的にセット
        world.index_base_turn = CURRENCY_INDEX_BASE_TURN
    else :
        for money in default_money:
            world.add_money(money)
        for country in default_countries:
            world.add_country(country)


# 初期化
initialize_world(False)
mp = {"exe":True} #ここはいじくらない


@app.route('/')
def index():
    money_dict = {money.name: money for money in world.Money_list}
    processed_countries = []
    for country in world.Country_list:
        money = money_dict[country.money_name]
        
        if country.get_gdp_usd() < 0:
            country.gdp_usd=country.caluc_gdp() / money.get_rate()
            country.past_gdp_usd[-1] = country.gdp_usd
        
        country.industry_power_usd = country.industry.caluc_power() / money.get_rate()
        country.military_power_usd = country.military.caluc_power() / money.get_rate()
        country.exchange_rate = money.get_rate()
        country.interest_rate = money.get_interest()
        country.price_usd = country.price.get_price() / money.get_rate()
        country.price_salary = country.get_average_salary() / country.price.get_price() if country.price.get_price() > 0 else -100.0 # 物価に対する収入の比率
        processed_countries.append(country)

    sorted_countries = sorted(
        processed_countries,
        key=lambda c: -c.gdp_usd
    )
    dict = {}
    for c in (sorted_countries):
        for m in (world.Money_list):
            if c.money_name == m.name:
                dict[c.name] = m.get_rate()
    return render_template(
        'index.html',
        countries=sorted_countries,
        moneys=world.Money_list,
        turn=world.turn,
        turn_year=turn_year, 
        rate_dict = dict
    )
def bernoulli(p: float) -> bool:
    """確率pでTrueを返す"""
    return random.random() < p


@app.route('/toggle_operation/<name>')
def toggle_operation(name):
    # 名前で国を検索
    target_country = next((c for c in world.Country_list if c.name == name), None)
    
    if target_country:
        # フラグを反転 (True -> False, False -> True)
        target_country.selfoperation = not target_country.selfoperation
        print(f"{target_country.name} operation mode switched to: {'AI' if target_country.selfoperation else 'Player'}")
    
    # indexに戻る
    return redirect(url_for('index'))

@app.route('/advance_turn', methods=['POST'])
def advance_turn():
    # --- 1. ユーザー入力の取得処理 ---
    turn_count = int(request.form.get('turn_count', 1))
    interest_inputs = {}
    print(f"app.py World turn: {world.turn + 1} へ移行")

    # 各国の為替介入入力の取得と実行部分
    for country in world.Country_list:
        intervention_input = request.form.get(f"intervention_{country.name}")
        country.turn_intervention_usd = 0.0
        
        if intervention_input:
            try:
                amount_usd = float(intervention_input)
                if amount_usd != 0:
                    money = next((m for m in world.Money_list if m.name == country.money_name), None)
                    if money:
                        current_rate = money.get_rate()
                        # 第3引数に world.turn を渡す
                        country.intervene(amount_usd, current_rate, world.turn)
            except ValueError:
                pass

    # 各国の金利入力フォームの値を取得
    for country in world.Country_list:
        key = f"interest_{country.money_name}_{country.name}"
        input_value = request.form.get(key)
        if input_value:
            try:
                rate = float(input_value)
                # 同じ通貨に対して複数の入力がある場合に対応するためリスト化
                interest_inputs.setdefault(country.money_name, []).append(rate)
            except ValueError:
                raise FileNotFoundError

    def update_economy_interests():
        """
        各通貨の経済指標（インフレ率、貿易収支、成長率）を集計し、為替と金利を更新する。
        """
        # --- 1. 基軸通貨(Dollar)の指標を計算 ---
        base_interest = 0.0
        base_inflation = 0.0
        base_trade_balance_ratio = 0.0
        base_gdp_growth = 0.0
        base_gdp_per_capita_usd = 0.0 
        
        # 基軸通貨を探す
        base_money = next((m for m in world.Money_list if m.base_currency), None)
        
        if base_money:
            base_interest = base_money.get_true_interest()
            
            # 基軸通貨を使用している国々のデータを集計
            b_countries = [c for c in world.Country_list if c.money_name == base_money.name]
            if b_countries:
                # インフレ率平均
                base_inflation = sum(c.price.get_price_change_rate() for c in b_countries) / len(b_countries)
                # GDP成長率平均
                base_gdp_growth = sum(c.get_gdp_change() for c in b_countries) / len(b_countries)
                
                # 貿易収支対GDP比 (エリア全体)
                # Trade Balance = 現在のUSD保有量 - 1ターン前のUSD保有量
                total_trade_balance = 0.0
                total_gdp_usd = 0.0
                for c in b_countries:
                    prev_usd = c.past_usd[-2] if len(c.past_usd) >= 2 else c.usd
                    
                    # 実際の増減
                    actual_usd_change = c.usd - prev_usd
                    # 純粋な貿易収支 = 実際の増減 - 介入による増減
                    # 基軸通貨国も介入する場合に備えて同じロジックを適用
                    trade_balance = actual_usd_change - getattr(c, 'turn_intervention_usd', 0.0)
                    
                    total_trade_balance += trade_balance
                    total_gdp_usd += c.get_gdp_usd() # USD換算GDP
                
                if total_gdp_usd > 0:
                    base_trade_balance_ratio = (total_trade_balance / total_gdp_usd) * 100
                    
                # 基軸通貨エリアの一人当たりGDP (USD)
                b_total_gdp_usd = sum(c.get_gdp_usd() for c in b_countries)
                b_total_pop = sum(c.get_population() for c in b_countries)
                if b_total_pop > 0:
                    base_gdp_per_capita_usd = b_total_gdp_usd / b_total_pop
        
        print(f"#### Base(USD) - Inf: {base_inflation:.2f}%, Growth: {base_gdp_growth:.2f}%, Trade/GDP: {base_trade_balance_ratio:.2f}%, GDP/Cap: {base_gdp_per_capita_usd:.0f}")

        # --- 2. 各通貨の更新 ---
        for money in world.Money_list:
            money_name = money.name
            
            # その通貨を使用している国々のデータを集計
            countries = [c for c in world.Country_list if c.money_name == money_name]
            
            avg_inflation = 0.0
            avg_gdp_growth = 0.0
            area_trade_balance_ratio = 0.0
            intervention_ratio = 0.0 
            avg_gdp_per_capita_usd = 0.0 
            
            if countries:
                avg_inflation = sum(c.price.get_price_change_rate() for c in countries) / len(countries)
                avg_gdp_growth = sum(c.get_gdp_change() for c in countries) / len(countries)
                
                total_trade_balance = 0.0
                total_intervention_usd = 0.0 
                total_gdp_usd = 0.0
                
                for c in countries:
                    # Trade Balance (Flow) = Current Stock - Previous Stock
                    prev_usd = c.past_usd[-2] if len(c.past_usd) >= 2 else c.usd
                    actual_usd_change = c.usd - prev_usd
                    
                    # 純粋な貿易収支 = 実際の増減 - 介入による増減
                    # c.turn_intervention_usd はこのターンの介入額
                    current_intervention = getattr(c, 'turn_intervention_usd', 0.0)
                    trade_balance = actual_usd_change - current_intervention
                    
                    total_trade_balance += trade_balance
                    total_intervention_usd += current_intervention
                    total_gdp_usd += c.get_gdp_usd()
                
                if total_gdp_usd > 0:
                    area_trade_balance_ratio = (total_trade_balance / total_gdp_usd) * 100
                    # 介入比率の計算 (介入額 / GDP)
                    intervention_ratio = (total_intervention_usd / total_gdp_usd) * 100
                
                # 対象通貨エリアの一人当たりGDP (USD)
                c_total_gdp_usd = sum(c.get_gdp_usd() for c in countries)
                c_total_pop = sum(c.get_population() for c in countries)
                if c_total_pop > 0:
                    avg_gdp_per_capita_usd = c_total_gdp_usd / c_total_pop

            # 金利入力の確認と適用
            if money_name in interest_inputs:
                # ユーザー入力がある場合
                values = interest_inputs[money_name]
                avg_input_interest = sum(values) / len(values)
                money.change_interest(avg_input_interest, 
                                      avg_inflation, area_trade_balance_ratio, avg_gdp_growth,
                                      base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                                      intervention_ratio=intervention_ratio,
                                      avg_gdp_per_capita_usd=avg_gdp_per_capita_usd, 
                                      base_gdp_per_capita_usd=base_gdp_per_capita_usd 
                                      )
            else:
                # 自動または維持
                # 自律操作判定（代表国を使用）
                target_country = countries[0] if countries else None
                
                if target_country and target_country.selfoperation:
                    # 現在の通貨の金利を取得
                    current_money_interest = money.get_interest()
                    
                    # アルゴリズム呼び出し（Country.interest_decideを使用）
                    decided_interest = target_country.interest_decide(
                        current_money_interest, 
                        avg_inflation, 
                        avg_gdp_growth, 
                        base_interest
                    )
                    
                    # 金利を更新
                    money.stay_interest(avg_inflation, area_trade_balance_ratio, avg_gdp_growth,
                                        base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                                        new_interest=decided_interest,
                                        intervention_ratio=intervention_ratio,
                                        avg_gdp_per_capita_usd=avg_gdp_per_capita_usd, 
                                        base_gdp_per_capita_usd=base_gdp_per_capita_usd 
                                        )
                else:
                    # 自律操作でない（かつユーザー入力もない）場合は現状維持
                    money.stay_interest(avg_inflation, area_trade_balance_ratio, avg_gdp_growth,
                                        base_interest, base_inflation, base_trade_balance_ratio, base_gdp_growth,
                                        intervention_ratio=intervention_ratio,
                                        avg_gdp_per_capita_usd=avg_gdp_per_capita_usd, 
                                        base_gdp_per_capita_usd=base_gdp_per_capita_usd 
                                        )

    # --- 内部関数定義: 予算の適用ロジック ---
    def apply_yearly_budget():
        """
        数年に一度(turn_year毎)の予算・税率の適用処理
        """
        is_budget_executed = mp["exe"]
        
        # 基軸通貨(Dollar)の金利を取得
        base_interest = 0.0
        for money in world.Money_list:
            if money.base_currency:
                base_interest = money.get_interest()
                break
        
        # 全ての国について処理
        for country in world.Country_list:
            # その国の通貨情報を取得
            current_rate = 0.0
            domestic_interest = 0.0
            for money in world.Money_list:
                if money.name == country.money_name:
                    current_rate = money.get_rate()
                    domestic_interest = money.get_interest()

            # --- 自動操作 (Self Operation) の場合 ---
            if country.selfoperation:
                # アルゴリズムに基づいて予算を決定
                # 引数: 為替レート, 金利
                tax, budget_parts = country.budget_decide(current_rate, domestic_interest)
                
                # 決定した予算を適用
                country.next_turn_year(tax, budget_parts, current_rate, world.turn, domestic_interest, base_interest)
                
            # --- 手動操作 (User Operation) の場合 ---
            else:
                # ユーザー入力がある場合 (フォーム送信時)
                if not is_budget_executed and country.name in mp:
                    tax, budget_parts = mp[country.name]
                    country.next_turn_year(tax, budget_parts, current_rate, world.turn, domestic_interest, base_interest)
                
                # ユーザー入力がない場合 (自動進行時) -> 現状維持
                else:
                    current_budget_ratios = [
                        country.budget.budget[1], # pension
                        country.budget.budget[2], # industry
                        country.budget.budget[3]  # military
                    ]
                    country.next_turn_year(country.bef_tax, current_budget_ratios, current_rate, world.turn, domestic_interest, base_interest)

        # 入力処理済みフラグを立てる
        if not is_budget_executed:
            mp["exe"] = True
            
    # --- 2. メイン処理 ---

    # ループに入る前に一度経済状況を更新
    update_economy_interests()

    # 指定ターン数だけ時間を進める
    for i in range(turn_count):
        is_turn_year_cycle = (world.turn % turn_year == 0)

        # 予算更新タイミングなら適用
        if is_turn_year_cycle:
            apply_yearly_budget()

        # 特定のログ保存処理
        if i == 0 and is_turn_year_cycle:
            if world.Country_list:
                last_country = world.Country_list[-1]
                last_country.past_population.append(last_country.get_population())

        # 2回目以降のループでは、ターンごとに金利計算を行う
        if i != 0:
            update_economy_interests()

        # ワールドのターンを進める
        world.Next_turn()

    return redirect(url_for('index'))


@app.route('/submit_budget', methods=['POST'])
def submit_budget():
    for country in world.Country_list:
        try:
            tax = float(request.form.get(f"tax_{country.name}", country.tax))
            pension = float(request.form.get(f"pension_{country.name}", country.budget.budget[1]))
            industry = float(request.form.get(f"industry_{country.name}", country.budget.budget[2]))
            military = float(request.form.get(f"military_{country.name}", country.budget.budget[3]))
            budget_parts = [pension, industry, military]
            mp[country.name] = [tax, budget_parts]
        except Exception as e:
            print(f"[エラー] {country.name} の予算更新中にエラー: {e}")
    mp["exe"] = False
    return redirect(url_for('index'))

@app.route('/quit')
def quit():
    world.save()
    return redirect(url_for('index'))
    
    
    
@app.route('/budget_decision_index')
def budget_decision_index():
    money_dict = {money.name: money for money in world.Money_list}
    sorted_countries = sorted(
        world.Country_list,
        key=lambda c: -(c.caluc_gdp() / money_dict[c.money_name].get_rate())
    )
    return render_template(
        'budget_decision_index.html',
        countries=sorted_countries,
        turn=world.turn,
        turn_year=turn_year
    )

@app.route('/country/<name>')
def show_country(name):
    target_country = None
    for c in world.Country_list:
        if c.name == name:
            target_country = c
            break

    if not target_country:
        return "Country not found", 404

    target_money = None
    for m in world.Money_list:
        if m.name == target_country.money_name:
            target_money = m
            break

    if not target_money:
        return "Currency for country not found", 404

    # 全国のデータを集計して比較用データを作成
    all_countries_data = {}
    for c in world.Country_list:
        # GDP History (USD)
        gdp_usd_history = c.past_gdp_usd
        
        # GDP Per Capita History (USD)の計算
        gdp_per_capita_history = []
        pop_history = c.past_population
        
        # データ長を揃える（短い方に合わせる）
        min_len = min(len(gdp_usd_history), len(pop_history))
        
        for i in range(min_len):
            pop = pop_history[i]
            gdp = gdp_usd_history[i]
            if pop > 0:
                gdp_per_capita_history.append(gdp / pop)
            else:
                gdp_per_capita_history.append(0.0)
        
        all_countries_data[c.name] = {
            "gdp_usd_history": gdp_usd_history,
            "gdp_per_capita_history": gdp_per_capita_history,
            "industry_history": c.industry.past_power # 産業力履歴
        }

    # mp: 他通貨との為替レートを格納する辞書
    # key: 他通貨名, value: 1 他通貨 = X 自国通貨
    mp = {}
    target_currency_rate_vs_usd = target_money.get_rate()

    for other_money in world.Money_list:
        if other_money.name == target_money.name:
            continue
        
        other_currency_rate_vs_usd = other_money.get_rate()
        
  
        rate = target_currency_rate_vs_usd / (other_currency_rate_vs_usd + 0.00001)
        mp[other_money.name] = rate

    # --- 実質金利差データの計算 (Real Interest Rate Differential vs Base Country) ---
    base_money = next((m for m in world.Money_list if m.base_currency), None)
    base_country = None
    real_interest_diff_data = []

    if base_money:
        # 基軸通貨を使用している国（USA等）を探す
        base_country = next((c for c in world.Country_list if c.name == "USA"), None)
        if not base_country:
            # USAが見つからない場合は基軸通貨を使用している最初の国
            base_country = next((c for c in world.Country_list if c.money_name == base_money.name), None)

    if base_money and base_country:
        # データの取得
        t_interests = target_money.interest.interest
        t_prices = target_country.price.past_price
        
        b_interests = base_money.interest.interest
        b_prices = base_country.price.past_price
        
        # データ長を揃える
        min_len = min(len(t_interests), len(t_prices), len(b_interests), len(b_prices))
        
        for i in range(min_len):
            # ターゲット国の実質金利
            t_nom = t_interests[i]
            t_inf = 0.0
            if i > 0 and t_prices[i-1] > 0:
                t_inf = (t_prices[i] - t_prices[i-1]) / t_prices[i-1] * 100.0
            t_real = t_nom - t_inf
            
            # 基軸国の実質金利
            b_nom = b_interests[i]
            b_inf = 0.0
            if i > 0 and b_prices[i-1] > 0:
                b_inf = (b_prices[i] - b_prices[i-1]) / b_prices[i-1] * 100.0
            b_real = b_nom - b_inf
            
            # 差分
            real_interest_diff_data.append(t_real - b_real)

    return render_template(
        'country_detail.html', 
        country=target_country, 
        money=target_money, 
        mp=mp,
        real_interest_diff_data=real_interest_diff_data,
        base_country_name=base_country.name if base_country else "Base",
        index_base_turn=CURRENCY_INDEX_BASE_TURN,
        all_countries_data=all_countries_data
    )

# === ★追加: 関税設定を更新するルート ===
@app.route('/update_tariff', methods=['POST'])
def update_tariff():
    country_name = request.form.get('country_name')
    target_name = request.form.get('target_name')
    
    try:
        tariff_rate = float(request.form.get('tariff_rate', 0.0))
        # %入力(0-100)を内部値(0.0-1.0)へ変換
        tariff_rate_val = tariff_rate / 100.0
    except ValueError:
        tariff_rate_val = 0.0
        
    country = next((c for c in world.Country_list if c.name == country_name), None)
    if country:
        country.set_tariff(target_name, tariff_rate_val)
        print(f"Updated Tariff: {country.name} -> {target_name} : {tariff_rate}%")
        
    return redirect(url_for('show_country', name=country_name))

if __name__ == '__main__':
    app.run(host='0.0.0.0')