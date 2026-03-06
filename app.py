# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
from Country import Country
from World import World
from Money import Money
from number_format import format_ja_units
import random
import os
import threading
import time
from uuid import uuid4
app = Flask(__name__)

DEBUG_LOGS = os.getenv("MYGAME_DEBUG_LOGS", "0") == "1"

# グローバルなWorldオブジェクト
turn_year = 3
world = None
mp = {"exe":True} #ここはいじくらない
# Currency Index の基準ターン設定
CURRENCY_INDEX_BASE_TURN = 80
advance_jobs = {}
advance_jobs_lock = threading.Lock()
advance_turn_lock = threading.Lock()


@app.template_filter("ja_units")
def ja_units_filter(value):
    return format_ja_units(value)

def default_countries():
    return [
        # 日本: 円安反映 (1ドル=150円想定)。物価15000, 給与係数150 -> 購買力維持
        Country(name="Japan", money_name="Yen", turn_year=turn_year, population_p=5.90, salary_p=0.1*140.0, initial_price=0.1*7000, selfoperation=True, industry_p=1200, military_p=200),
        
        # アメリカ: 基軸 (基準値)。物価100, 給与係数1.0
        Country(name="USA", money_name="Dollar", turn_year=turn_year, population_p=6.3, salary_p=0.1*2.4, initial_price=0.1*100, selfoperation=True, industry_p=2100, military_p=2000),
        
        # フランス: ユーロ (1ドル=0.92ユーロ想定)。物価95, 給与0.95
        Country(name="France", money_name="Euro", turn_year=turn_year, population_p=5.75, salary_p=0.1*2.1, initial_price=0.1*80, selfoperation=True, industry_p=5500, military_p=300),
        
        Country(name="Itary", money_name="Euro", turn_year=turn_year, population_p=5.70, salary_p=0.1*1.5, initial_price=0.1*60, selfoperation=True, industry_p=5500, military_p=300),
        
        # ドイツ: 産業強め
        Country(name="Germany", money_name="Euro", turn_year=turn_year, population_p=5.9, salary_p=0.1*2.6, initial_price=0.1*95, selfoperation=True, industry_p=6000, military_p=250),
        
        # スイス Swissfranc
        Country(name="Switzerland", money_name="Swissfranc", turn_year=turn_year, population_p=4.9, salary_p=0.1*3.4, initial_price=0.1*140, selfoperation=True, industry_p=7500, military_p=250),
        
        # 中国: 人口多, 物価安(1ドル=7.2元), 給与低めだが産業力最強クラス
        Country(name="China", money_name="Yuan", turn_year=turn_year, population_p=6.5, salary_p=0.1*1.0, initial_price=0.1*400, selfoperation=True, industry_p=1000, military_p=10),
        
        # イギリス: ポンド (1ドル=0.76ポンド想定)
        Country(name="England", money_name="Pond", turn_year=turn_year, population_p=5.66, salary_p=0.1*2.0, initial_price=0.1*70, selfoperation=True, industry_p=3500, military_p=300),
        
        Country(name="Russia", money_name="Ruble", turn_year=turn_year, population_p=6.10, salary_p=0.1*75.0, initial_price=0.1*4200, selfoperation=True, industry_p=500, military_p=150),
        Country(name="Spain", money_name="Euro", turn_year=turn_year, population_p=5.66, salary_p=0.1*1.5, initial_price=0.1*60, selfoperation=True, industry_p=2900, military_p=400),
        
        # タイ: 新興国モデル (1ドル=33バーツ), 産業成長中
        Country(name="Thailand", money_name="Baht", turn_year=turn_year, population_p=5.7, salary_p=0.1*5.0, initial_price=0.1*500, selfoperation=True, industry_p=500, military_p=10)
    ]


def default_money():
    # === 通貨の初期設定 ===
    # value は「1 USD = 何単位の通貨か」を表すレートとして設定します。
    # base_currency=True の通貨(Dollar)が基準になります。
    # is_major=True で主要通貨バスケットに含めるかを指定
    return [
        Money(name="Yen", interest=0.25, value=120.00, base_currency=False, is_major=True), # 主要通貨
        Money(name="Dollar", interest=4.5, value=1.0, base_currency=True, is_major=True),   # 基軸通貨(主要)
        Money(name="Euro", interest=3.5, value=0.92, base_currency=False, is_major=True),   # 主要通貨
        Money(name="Yuan", interest=3.0, value=7.20, base_currency=False, is_major=False),   # 主要通貨
        Money(name="Pond", interest=4.0, value=0.76, base_currency=False, is_major=True),   # 主要通貨
        Money(name="Baht", interest=2.5, value=33.0, base_currency=False, is_major=False),  # 非主要通貨
        Money(name="Swissfranc", interest=1.0, value=0.85, base_currency=False, is_major=False), # 主要通貨
        Money(name="CanadaDollar", interest=3.0, value=1.36, base_currency=False, is_major=False), # 主要通貨
        Money(name="AustraliaDollar", interest=3.0, value=1.50, base_currency=False, is_major=False), # 主要通貨
        Money(name="Ruble", interest=15.0, value=92.0, base_currency=False, is_major=False),  # 非主要通貨
        Money(name="Gold", interest=5.0, value=1.0, base_currency=False, is_major=False)  # 非主要通貨
    ]


def setup_new_world():
    global world
    if world is None:
        world = World(turn_year, index_base_turn=CURRENCY_INDEX_BASE_TURN)
    for money in default_money():
        world.add_money(money)
    for country in default_countries():
        world.add_country(country)
    world.generate_territory_map()


# 初期化関数
def initialize_world(load_existing):
    global world, mp
    world = World(turn_year, index_base_turn=CURRENCY_INDEX_BASE_TURN)
    loaded = world.load() if load_existing else False
    if not loaded:
        setup_new_world()
    else:
        world.ensure_territory_map()
    # Load時はWorldが再作成されない場合があるので、変数を強制的にセット
    world.index_base_turn = CURRENCY_INDEX_BASE_TURN
    mp = {"exe":True}


@app.route('/')
def start():
    return render_template('start.html')


@app.route('/start/new', methods=['POST'])
def start_new():
    initialize_world(False)
    return redirect(url_for('index'))


@app.route('/start/load', methods=['POST'])
def start_load():
    initialize_world(True)
    return redirect(url_for('index'))


@app.before_request
def ensure_world_initialized():
    allowed_endpoints = {"start", "start_new", "start_load", "static"}
    if request.endpoint in allowed_endpoints:
        return None
    if world is None:
        return redirect(url_for('start'))
    return None


@app.route('/index')
def index():
    saved = request.args.get('saved') == '1'
    money_dict = {money.name: money for money in world.Money_list}
    world.ensure_territory_map()
    processed_countries = []
    for country in world.Country_list:
        money = money_dict[country.money_name]
        
        if country.get_gdp_usd() < 0:
            country.gdp_usd=country.caluc_gdp() / money.get_rate()
            country.past_gdp_usd[-1] = country.gdp_usd
        
        country.industry_power_usd = country.industry.caluc_power() / money.get_rate()
        country.committed_military = world.territory_map["military_committed"].get(country.name, 0.0)
        country.available_military = world.get_country_available_military(country.name)
        country.military_power_usd = country.available_military / money.get_rate()
        country.exchange_rate = money.get_rate()
        country.interest_rate = money.get_interest()
        country.price_usd = country.price.get_price() / money.get_rate()
        country.price_salary = country.get_average_salary() / country.price.get_price() if country.price.get_price() > 0 else -100.0 # 物価に対する収入の比率
        power_stats = world.get_country_territory_power_stats(country.name)
        country.territory_power_total = power_stats["total_power"]
        country.territory_power_avg = power_stats["average_power"]
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
        rate_dict = dict,
        saved=saved
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
        if DEBUG_LOGS:
            print(f"{target_country.name} operation mode switched to: {'AI' if target_country.selfoperation else 'Player'}")
    
    # indexに戻る
    return redirect(url_for('index'))

def _advance_turn_internal(form_data, progress_callback=None):
    # --- 1. ユーザー入力の取得処理 ---
    try:
        turn_count = int(form_data.get('turn_count', 1))
    except (TypeError, ValueError):
        turn_count = 1
    turn_count = max(1, turn_count)
    interest_inputs = {}
    if DEBUG_LOGS:
        print(f"app.py World turn: {world.turn + 1} へ移行")

    # 各国の為替介入入力の取得と実行部分
    for country in world.Country_list:
        intervention_input = form_data.get(f"intervention_{country.name}")
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
        input_value = form_data.get(key)
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
        # 自動介入（Domestic調整用）は為替計算から中立化する
        fx_neutral_by_country = {
            c.name: float(getattr(c, "fx_neutral_intervention_usd", 0.0) or 0.0)
            for c in world.Country_list
        }

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
                    current_intervention = getattr(c, 'turn_intervention_usd', 0.0)
                    neutral_intervention = fx_neutral_by_country.get(c.name, 0.0)
                    trade_balance = actual_usd_change - current_intervention - neutral_intervention
                    
                    total_trade_balance += trade_balance
                    total_gdp_usd += c.get_gdp_usd() # USD換算GDP
                
                if total_gdp_usd > 0:
                    base_trade_balance_ratio = (total_trade_balance / total_gdp_usd) * 100
                    
                # 基軸通貨エリアの一人当たりGDP (USD)
                b_total_gdp_usd = sum(c.get_gdp_usd() for c in b_countries)
                b_total_pop = sum(c.get_population() for c in b_countries)
                if b_total_pop > 0:
                    base_gdp_per_capita_usd = b_total_gdp_usd / b_total_pop
        
        if DEBUG_LOGS:
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
                    neutral_intervention = fx_neutral_by_country.get(c.name, 0.0)
                    trade_balance = actual_usd_change - current_intervention - neutral_intervention
                    
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

        # 中立化分は一度反映したら消費する
        for c in world.Country_list:
            if getattr(c, "fx_neutral_intervention_usd", 0.0) != 0.0:
                c.fx_neutral_intervention_usd = 0.0

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
                tax, budget_parts = country.budget_decide(
                    current_rate,
                    domestic_interest,
                    world.Country_list,
                )
                
                # 決定した予算を適用
                country.next_turn_year(
                    tax,
                    budget_parts,
                    current_rate,
                    world.turn,
                    domestic_interest,
                    base_interest,
                )
                
            # --- 手動操作 (User Operation) の場合 ---
            else:
                # ユーザー入力がある場合 (フォーム送信時)
                if not is_budget_executed and country.name in mp:
                    tax, budget_parts = mp[country.name]
                    if len(budget_parts) >= 3:
                        budget_parts = [float(budget_parts[0]), 0.0, float(budget_parts[2])]
                    else:
                        pension_part = float(budget_parts[0]) if len(budget_parts) > 0 else country.budget.budget[1]
                        military_part = float(budget_parts[1]) if len(budget_parts) > 1 else country.budget.budget[3]
                        budget_parts = [pension_part, 0.0, military_part]
                    country.next_turn_year(
                        tax,
                        budget_parts,
                        current_rate,
                        world.turn,
                        domestic_interest,
                        base_interest,
                    )
                
                # ユーザー入力がない場合 (自動進行時) -> 現状維持
                else:
                    current_budget_ratios = [
                        country.budget.budget[1], # pension
                        0.0, # legacy power (unused)
                        country.budget.budget[3]  # military
                    ]
                    country.next_turn_year(
                        country.bef_tax,
                        current_budget_ratios,
                        current_rate,
                        world.turn,
                        domestic_interest,
                        base_interest,
                    )

        # 入力処理済みフラグを立てる
        if not is_budget_executed:
            mp["exe"] = True
            
    # --- 2. メイン処理 ---

    # ループに入る前に一度経済状況を更新
    update_economy_interests()
    if progress_callback is not None:
        progress_callback(0, turn_count, world.turn)

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
        if progress_callback is not None:
            progress_callback(i + 1, turn_count, world.turn)


def _cleanup_finished_advance_jobs(max_jobs=30):
    with advance_jobs_lock:
        if len(advance_jobs) <= max_jobs:
            return
        # 完了済みジョブを古い順に削除する
        finished = sorted(
            (
                (jid, row.get("updated_at", 0.0))
                for jid, row in advance_jobs.items()
                if row.get("status") in ("done", "error")
            ),
            key=lambda item: item[1],
        )
        for jid, _ in finished:
            if len(advance_jobs) <= max_jobs:
                break
            advance_jobs.pop(jid, None)


def _advance_turn_worker(job_id, form_data):
    try:
        with advance_turn_lock:
            def on_progress(step, total, current_turn):
                percent = 100.0 if total <= 0 else (float(step) / float(total)) * 100.0
                with advance_jobs_lock:
                    job = advance_jobs.get(job_id)
                    if not job:
                        return
                    job["current_step"] = int(step)
                    job["total_steps"] = int(total)
                    job["current_turn"] = int(current_turn)
                    job["progress_percent"] = max(0.0, min(100.0, percent))
                    job["updated_at"] = time.time()

            _advance_turn_internal(form_data, progress_callback=on_progress)

        with advance_jobs_lock:
            job = advance_jobs.get(job_id)
            if job:
                job["status"] = "done"
                job["current_step"] = int(job.get("total_steps", 0))
                job["current_turn"] = int(job.get("target_turn", job.get("current_turn", 0)))
                job["progress_percent"] = 100.0
                job["message"] = "ターン進行が完了しました。"
                job["updated_at"] = time.time()
    except Exception as exc:
        with advance_jobs_lock:
            job = advance_jobs.get(job_id)
            if job:
                job["status"] = "error"
                job["message"] = f"ターン進行でエラー: {exc}"
                job["updated_at"] = time.time()


@app.route('/advance_turn', methods=['POST'])
def advance_turn():
    form_data = request.form.to_dict(flat=True)
    with advance_turn_lock:
        _advance_turn_internal(form_data)
    return redirect(url_for('index'))


@app.route('/advance_turn/start', methods=['POST'])
def advance_turn_start():
    form_data = request.form.to_dict(flat=True)
    try:
        turn_count = int(form_data.get("turn_count", 1))
    except (TypeError, ValueError):
        turn_count = 1
    turn_count = max(1, turn_count)

    with advance_jobs_lock:
        running = next(
            ((jid, row) for jid, row in advance_jobs.items() if row.get("status") == "running"),
            None,
        )
        if running is not None:
            running_id, running_row = running
            payload = {"job_id": running_id}
            payload.update(running_row)
            return jsonify(payload), 409

        start_turn = int(world.turn)
        job_id = uuid4().hex
        advance_jobs[job_id] = {
            "status": "running",
            "message": "ターン進行を開始しました。",
            "current_step": 0,
            "total_steps": turn_count,
            "current_turn": start_turn,
            "start_turn": start_turn,
            "target_turn": start_turn + turn_count,
            "progress_percent": 0.0,
            "updated_at": time.time(),
        }

    worker = threading.Thread(target=_advance_turn_worker, args=(job_id, form_data), daemon=True)
    worker.start()
    _cleanup_finished_advance_jobs()
    return jsonify({"job_id": job_id}), 202


@app.route('/advance_turn/progress/<job_id>', methods=['GET'])
def advance_turn_progress(job_id):
    with advance_jobs_lock:
        job = advance_jobs.get(job_id)
        if job is None:
            return jsonify({"error": "job_not_found"}), 404
        payload = {"job_id": job_id}
        payload.update(job)
    return jsonify(payload)


@app.route('/submit_budget', methods=['POST'])
def submit_budget():
    for country in world.Country_list:
        try:
            tax = float(request.form.get(f"tax_{country.name}", country.tax))
            pension = float(request.form.get(f"pension_{country.name}", country.budget.budget[1]))
            military = float(request.form.get(f"military_{country.name}", country.budget.budget[3]))
            budget_parts = [pension, 0.0, military]
            mp[country.name] = [tax, budget_parts]
        except Exception as e:
            print(f"[エラー] {country.name} の予算更新中にエラー: {e}")
    mp["exe"] = False
    return redirect(url_for('index'))

@app.route('/quit')
def quit():
    world.save()
    return redirect(url_for('index', saved='1'))
    
    
    
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

@app.route('/world_map')
def world_map():
    message = request.args.get("message", "")
    world_map_data = world.ensure_territory_map()
    territory_event_logs = world.get_territory_event_logs(limit=200)
    base_money = world.get_base_currency()
    territory_counts = world.get_territory_counts()
    countries = []
    for country in world.Country_list:
        available_military = world.get_country_available_military(country.name)
        power_stats = world.get_country_territory_power_stats(country.name)
        reinforce_cost_usd = world.get_country_reinforce_cost_usd(country.name)
        capital = world.get_country_capital(country.name)
        countries.append({
            "name": country.name,
            "money_name": country.money_name,
            "territory_count": territory_counts.get(country.name, 0),
            "available_military": available_military,
            "usd": country.usd,
            "territory_power_total": power_stats["total_power"],
            "territory_power_avg": power_stats["average_power"],
            "reinforce_cost_usd": reinforce_cost_usd,
            "capital_x": capital[0] if capital else None,
            "capital_y": capital[1] if capital else None,
        })

    countries = sorted(countries, key=lambda c: c["name"])
    claim_options_by_country = {
        c["name"]: world.get_claim_options(c["name"], require_resources=True)
        for c in countries
    }
    selected_country = request.args.get("selected_country", "")
    valid_names = {c["name"] for c in countries}
    if selected_country not in valid_names and countries:
        selected_country = countries[0]["name"]

    return render_template(
        'world_map.html',
        map_data=world_map_data,
        countries=countries,
        base_currency_name=base_money.name if base_money else "USD",
        message=message,
        selected_country=selected_country,
        claim_options_by_country=claim_options_by_country,
        territory_event_logs=territory_event_logs,
    )

@app.route('/world_map/claim', methods=['POST'])
def claim_world_map():
    country_name = request.form.get("country_name", "")
    action_mode = request.form.get("action_mode", "claim")
    try:
        x = int(request.form.get("x", "-1"))
        y = int(request.form.get("y", "-1"))
    except ValueError:
        return redirect(url_for('world_map', message="座標が不正です。", selected_country=country_name))

    if action_mode == "reinforce":
        success, msg = world.reinforce_territory(country_name, x, y)
    elif action_mode == "set_capital":
        success, msg = world.set_capital(country_name, x, y)
    else:
        success, msg = world.claim_territory(country_name, x, y)
    if success:
        world.save()
    return redirect(url_for('world_map', message=msg, selected_country=country_name))

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

        # Price Inflation Rate 履歴（各国の turn_year を使用）
        inflation_history = []
        turn_year = c.turn_year
        prices = c.price.past_price
        for i in range(turn_year, len(prices)):
            base_price = prices[i - turn_year]
            if base_price != 0:
                inflation_history.append(((prices[i] - base_price) / base_price) * 100.0)
            else:
                inflation_history.append(0.0)

        # Net Debt / GDP Ratio 履歴（%）
        debt_ratio_history = []
        domestic_hist = c.past_domestic_money
        usd_hist = c.past_usd
        gdp_hist = c.past_gdp

        c_money = next((m for m in world.Money_list if m.name == c.money_name), None)
        is_base_currency = c_money.base_currency if c_money else False
        rate_hist = c_money.get_past_rate() if c_money else []

        debt_len = min(len(domestic_hist), len(usd_hist), len(gdp_hist))
        for i in range(debt_len):
            rate = 1.0
            if not is_base_currency:
                if i < len(rate_hist):
                    rate = rate_hist[i]
                elif len(rate_hist) > 0:
                    rate = rate_hist[-1]

            gdp = gdp_hist[i]
            if gdp != 0:
                debt = -(domestic_hist[i] + usd_hist[i] * rate)
                debt_ratio_history.append((debt / gdp) * 100.0)
            else:
                debt_ratio_history.append(0.0)

        # Income by Age (対象国通貨ベース) を閲覧中の国通貨へ換算
        income_by_age_local = [c.population[i][2].get_salary() for i in range(100)]
        c_rate_vs_usd = c_money.get_rate() if c_money else 1.0
        target_rate_vs_usd = target_money.get_rate()
        rate_to_target = target_rate_vs_usd / (c_rate_vs_usd + 0.00001)
        income_by_age_converted = [v * rate_to_target for v in income_by_age_local]

        all_countries_data[c.name] = {
            "gdp_usd_history": gdp_usd_history,
            "gdp_per_capita_history": gdp_per_capita_history,
            "industry_history": c.industry.past_power,  # 産業力履歴
            "price_inflation_history": inflation_history,
            "debt_ratio_history": debt_ratio_history,
            "population_history": c.past_population,
            "income_by_age_converted": income_by_age_converted
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
        if DEBUG_LOGS:
            print(f"Updated Tariff: {country.name} -> {target_name} : {tariff_rate}%")
        
    return redirect(url_for('show_country', name=country_name))


@app.route('/update_tariff_bulk', methods=['POST'])
def update_tariff_bulk():
    country_name = request.form.get('country_name')
    try:
        tariff_rate = float(request.form.get('tariff_rate', 0.0))
        tariff_rate_val = tariff_rate / 100.0
    except ValueError:
        tariff_rate_val = 0.0

    country = next((c for c in world.Country_list if c.name == country_name), None)
    if country:
        for other in world.Country_list:
            if other.name == country.name:
                continue
            country.set_tariff(other.name, tariff_rate_val)
        if DEBUG_LOGS:
            print(f"Bulk Tariff Updated: {country.name} all targets -> {tariff_rate}%")

    return redirect(url_for('show_country', name=country_name))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
