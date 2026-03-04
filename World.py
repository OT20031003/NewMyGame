from Country import Country
from Money import Money
import math
import random
from persistence import get_connection, init_db, load_world_state, save_world_state

class World:
    SEA_TILE = "__SEA__"
    EMPTY_TILE = ""
    TERRITORY_COLOR_PALETTE = [
        "#e63946",
        "#1d3557",
        "#2a9d8f",
        "#e9c46a",
        "#f4a261",
        "#8ab17d",
        "#264653",
        "#6d597a",
        "#577590",
        "#bc4749",
        "#4361ee",
        "#7f5539",
        "#118ab2",
        "#ef476f",
    ]

    # ★修正: index_base_turn 引数を追加 (デフォルト50)
    def __init__(self, turn_year, index_base_turn=50):
        self.Country_list = []
        self.turn = 0
        self.turn_year = turn_year
        self.Money_list = []  # 通貨のリスト
        self.index_base_turn = index_base_turn # Currency Indexの基準ターン
        self.territory_map = None

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

    def _neighbors4(self, x, y, width, height):
        if x > 0:
            yield x - 1, y
        if x + 1 < width:
            yield x + 1, y
        if y > 0:
            yield x, y - 1
        if y + 1 < height:
            yield x, y + 1

    def _directions8(self):
        return (
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),            (1, 0),
            (-1, 1),  (0, 1),   (1, 1),
        )

    def _country_by_name(self, country_name):
        return next((c for c in self.Country_list if c.name == country_name), None)

    def _money_by_name(self, money_name):
        return next((m for m in self.Money_list if m.name == money_name), None)

    def get_base_currency(self):
        return next((m for m in self.Money_list if m.base_currency), None)

    def _assign_country_colors(self, existing_colors=None):
        colors = {}
        if isinstance(existing_colors, dict):
            for k, v in existing_colors.items():
                if isinstance(k, str) and isinstance(v, str):
                    colors[k] = v

        for idx, country in enumerate(sorted(self.Country_list, key=lambda c: c.name)):
            if country.name not in colors:
                colors[country.name] = self.TERRITORY_COLOR_PALETTE[idx % len(self.TERRITORY_COLOR_PALETTE)]
        return colors

    def _country_has_any_territory(self, country_name):
        if not self.territory_map:
            return False
        tiles = self.territory_map.get("tiles", [])
        return any(country_name in row for row in tiles)

    def _is_adjacent_to_country(self, x, y, country_name):
        if not self.territory_map:
            return False
        width = self.territory_map.get("width", 0)
        height = self.territory_map.get("height", 0)
        tiles = self.territory_map.get("tiles", [])
        for nx, ny in self._neighbors4(x, y, width, height):
            if tiles[ny][nx] == country_name:
                return True
        return False

    def _adjacent_enemy_count(self, x, y, country_name):
        if not self.territory_map:
            return 0
        width = self.territory_map.get("width", 0)
        height = self.territory_map.get("height", 0)
        tiles = self.territory_map.get("tiles", [])
        count = 0
        for nx, ny in self._neighbors4(x, y, width, height):
            owner = tiles[ny][nx]
            if owner not in (self.EMPTY_TILE, self.SEA_TILE, country_name):
                count += 1
        return count

    def _country_tile_positions(self):
        positions = {c.name: [] for c in self.Country_list}
        if not self.territory_map:
            return positions
        tiles = self.territory_map.get("tiles", [])
        for y, row in enumerate(tiles):
            for x, owner in enumerate(row):
                if owner in positions:
                    positions[owner].append((x, y))
        return positions

    def _country_gdp_base_currency(self, country_name):
        country = self._country_by_name(country_name)
        if country is None:
            return 0.0
        gdp_usd = country.get_gdp_usd()
        if gdp_usd is not None and gdp_usd > 0:
            return gdp_usd

        money = self._money_by_name(country.money_name)
        rate = money.get_rate() if money else 1.0
        if rate <= 0:
            rate = 1.0
        estimated = country.caluc_gdp() / rate
        return max(0.0, estimated)

    def _country_military_power(self, country_name):
        country = self._country_by_name(country_name)
        if country is None:
            return 0.0
        return max(0.0, country.military.caluc_power())

    def _weighted_neighbor_gdp(self, x, y, exclude_country=None):
        positions = self._country_tile_positions()
        weighted_sum = 0.0
        weight_sum = 0.0

        for cname, coords in positions.items():
            if cname == exclude_country or not coords:
                continue
            min_dist = min(abs(x - cx) + abs(y - cy) for cx, cy in coords)
            weight = 1.0 / (min_dist + 1.0)
            gdp = self._country_gdp_base_currency(cname)
            if gdp <= 0.0:
                continue
            weighted_sum += gdp * weight
            weight_sum += weight

        if weight_sum > 0.0:
            return weighted_sum / weight_sum

        fallbacks = []
        for c in self.Country_list:
            if c.name == exclude_country:
                continue
            gdp = self._country_gdp_base_currency(c.name)
            if gdp > 0:
                fallbacks.append(gdp)
        if fallbacks:
            return sum(fallbacks) / len(fallbacks)
        return 0.0

    def _weighted_neighbor_military(self, x, y, exclude_country=None):
        positions = self._country_tile_positions()
        weighted_sum = 0.0
        weight_sum = 0.0

        for cname, coords in positions.items():
            if cname == exclude_country or not coords:
                continue
            min_dist = min(abs(x - cx) + abs(y - cy) for cx, cy in coords)
            weight = 1.0 / (min_dist + 1.0)
            military = self._country_military_power(cname)
            if military <= 0.0:
                continue
            weighted_sum += military * weight
            weight_sum += weight

        if weight_sum > 0.0:
            return weighted_sum / weight_sum

        fallbacks = []
        for c in self.Country_list:
            if c.name == exclude_country:
                continue
            military = self._country_military_power(c.name)
            if military > 0:
                fallbacks.append(military)
        if fallbacks:
            return sum(fallbacks) / len(fallbacks)
        return 0.0

    def _is_adjacent_via_sea(self, x, y, country_name):
        if not self.territory_map:
            return False
        width = self.territory_map.get("width", 0)
        height = self.territory_map.get("height", 0)
        tiles = self.territory_map.get("tiles", [])

        for dx, dy in self._directions8():
            cx = x + dx
            cy = y + dy
            sea_len = 0
            while 0 <= cx < width and 0 <= cy < height:
                cell = tiles[cy][cx]
                if cell == self.SEA_TILE:
                    sea_len += 1
                    cx += dx
                    cy += dy
                    continue

                # 海を1マス以上またいだ先で、最初に当たる陸地が自国なら海越し隣接。
                if sea_len >= 1 and cell == country_name:
                    return True
                break

        return False

    def territory_cell_cost(self, country_name, x, y):
        regional_weighted_avg_gdp = self._weighted_neighbor_gdp(x, y, exclude_country=country_name)
        base_currency_cost = max(0.0, regional_weighted_avg_gdp * 0.20)
        weighted_military_avg = self._weighted_neighbor_military(x, y, exclude_country=country_name)
        military_cost = max(0.0, weighted_military_avg * 0.50)
        return base_currency_cost, military_cost

    def normalize_territory_map(self):
        if not isinstance(self.territory_map, dict):
            self.territory_map = None
            return

        width = int(self.territory_map.get("width", 0))
        height = int(self.territory_map.get("height", 0))
        tiles = self.territory_map.get("tiles", [])
        if width <= 0 or height <= 0 or len(tiles) != height:
            self.territory_map = None
            return

        valid_owners = {c.name for c in self.Country_list}
        normalized_tiles = []
        for row in tiles:
            if not isinstance(row, list) or len(row) != width:
                self.territory_map = None
                return
            normalized_row = []
            for cell in row:
                if cell == self.SEA_TILE:
                    normalized_row.append(self.SEA_TILE)
                elif isinstance(cell, str) and (cell == self.EMPTY_TILE or cell in valid_owners):
                    normalized_row.append(cell)
                else:
                    normalized_row.append(self.EMPTY_TILE)
            normalized_tiles.append(normalized_row)

        committed = self.territory_map.get("military_committed", {})
        normalized_committed = {}
        if isinstance(committed, dict):
            for country in self.Country_list:
                try:
                    normalized_committed[country.name] = max(0.0, float(committed.get(country.name, 0.0)))
                except (TypeError, ValueError):
                    normalized_committed[country.name] = 0.0
        else:
            for country in self.Country_list:
                normalized_committed[country.name] = 0.0

        self.territory_map = {
            "width": width,
            "height": height,
            "tiles": normalized_tiles,
            "country_colors": self._assign_country_colors(self.territory_map.get("country_colors")),
            "military_committed": normalized_committed,
            "seed": self.territory_map.get("seed"),
        }

    def ensure_territory_map(self):
        if self.territory_map is None:
            self.generate_territory_map()
        else:
            self.normalize_territory_map()
            if self.territory_map is None:
                self.generate_territory_map()
        return self.territory_map

    def generate_territory_map(self, width=28, height=16, seed=None):
        if width < 12:
            width = 12
        if height < 8:
            height = 8

        rng = random.Random(seed)
        scores = [[0.0 for _ in range(width)] for _ in range(height)]
        blob_count = max(4, min(10, (width * height) // 60))
        base_radius = min(width, height) * 0.35

        for _ in range(blob_count):
            cx = rng.uniform(-0.15 * width, 1.15 * width)
            cy = rng.uniform(-0.2 * height, 1.2 * height)
            radius = rng.uniform(base_radius * 0.6, base_radius * 1.35)
            weight = rng.uniform(0.9, 1.6)
            for y in range(height):
                for x in range(width):
                    dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                    if dist < radius:
                        scores[y][x] += (1.0 - dist / radius) * weight

        threshold = 0.95
        land_mask = [[False for _ in range(width)] for _ in range(height)]
        target_min = 0.40
        target_max = 0.74
        min_span = max(1.0, min(width, height) * 0.5)

        for _ in range(7):
            land_count = 0
            for y in range(height):
                for x in range(width):
                    edge_distance = min(x, width - 1 - x, y, height - 1 - y)
                    edge_boost = edge_distance / min_span
                    noise = rng.uniform(-0.20, 0.20)
                    is_land = (scores[y][x] + edge_boost + noise) > threshold
                    land_mask[y][x] = is_land
                    if is_land:
                        land_count += 1
            ratio = land_count / float(width * height)
            if target_min <= ratio <= target_max:
                break
            if ratio < target_min:
                threshold -= 0.08
            else:
                threshold += 0.08

        tiles = [
            [self.EMPTY_TILE if land_mask[y][x] else self.SEA_TILE for x in range(width)]
            for y in range(height)
        ]

        land_cells = [(x, y) for y in range(height) for x in range(width) if tiles[y][x] == self.EMPTY_TILE]
        country_names = [c.name for c in self.Country_list]
        seed_positions = {}
        available = land_cells[:]

        if available and country_names:
            rng.shuffle(available)
            for idx, country_name in enumerate(country_names):
                if not available:
                    break
                if idx == 0 or not seed_positions:
                    pos = available.pop()
                else:
                    sample = available if len(available) <= 180 else rng.sample(available, 180)
                    pos = max(
                        sample,
                        key=lambda p: min(abs(p[0] - sx) + abs(p[1] - sy) for sx, sy in seed_positions.values()),
                    )
                    available.remove(pos)
                seed_positions[country_name] = pos
                tiles[pos[1]][pos[0]] = country_name

        for country_name, pos in seed_positions.items():
            target_cells = rng.randint(2, 4)
            owned = [pos]
            for _ in range(target_cells - 1):
                frontier = []
                for ox, oy in owned:
                    for nx, ny in self._neighbors4(ox, oy, width, height):
                        if tiles[ny][nx] == self.EMPTY_TILE and (nx, ny) not in frontier:
                            frontier.append((nx, ny))
                if not frontier:
                    break
                nx, ny = rng.choice(frontier)
                tiles[ny][nx] = country_name
                owned.append((nx, ny))

        missing = [name for name in country_names if not any(name in row for row in tiles)]
        for country_name in missing:
            candidates = [(x, y) for y in range(height) for x in range(width) if tiles[y][x] == self.EMPTY_TILE]
            if not candidates:
                break
            x, y = rng.choice(candidates)
            tiles[y][x] = country_name

        self.territory_map = {
            "width": width,
            "height": height,
            "tiles": tiles,
            "country_colors": self._assign_country_colors(),
            "military_committed": {c.name: 0.0 for c in self.Country_list},
            "seed": seed,
        }
        return self.territory_map

    def get_territory_counts(self):
        self.ensure_territory_map()
        counts = {c.name: 0 for c in self.Country_list}
        tiles = self.territory_map["tiles"]
        for row in tiles:
            for owner in row:
                if owner in counts:
                    counts[owner] += 1
        return counts

    def get_country_available_military(self, country_name):
        self.ensure_territory_map()
        country = self._country_by_name(country_name)
        if country is None:
            return 0.0
        committed = self.territory_map["military_committed"].get(country_name, 0.0)
        return max(0.0, country.military.caluc_power() - committed)

    def _validate_claim_territory(self, country_name, x, y, require_resources=True):
        self.ensure_territory_map()
        width = self.territory_map["width"]
        height = self.territory_map["height"]

        if x < 0 or y < 0 or x >= width or y >= height:
            return False, "指定したマスは地図の範囲外です。", None, 0.0, 0.0

        cell = self.territory_map["tiles"][y][x]
        if cell == self.SEA_TILE:
            return False, "海マスは獲得できません。", None, 0.0, 0.0
        if cell != self.EMPTY_TILE:
            return False, "そのマスはすでに他国領です。", None, 0.0, 0.0

        country = self._country_by_name(country_name)
        if country is None:
            return False, "対象の国が見つかりません。", None, 0.0, 0.0

        if self._country_has_any_territory(country_name):
            direct_adjacent = self._is_adjacent_to_country(x, y, country_name)
            sea_adjacent = self._is_adjacent_via_sea(x, y, country_name)
            if not direct_adjacent and not sea_adjacent:
                return False, "占領は自国領に隣接する空き地、または海越し隣接マスのみ可能です。", country, 0.0, 0.0

        cost_usd, cost_military = self.territory_cell_cost(country_name, x, y)

        if require_resources:
            available_military = self.get_country_available_military(country_name)
            if available_military < cost_military:
                return (
                    False,
                    f"軍事力が不足しています。必要 {cost_military:.1f} / 利用可能 {available_military:.1f}",
                    country,
                    cost_usd,
                    cost_military,
                )
            if country.usd < cost_usd:
                return (
                    False,
                    f"USDが不足しています。必要 {cost_usd:.1f} / 保有 {country.usd:.1f}",
                    country,
                    cost_usd,
                    cost_military,
                )

        return True, "", country, cost_usd, cost_military

    def get_claimable_tiles(self, country_name, require_resources=True):
        options = self.get_claim_options(country_name, require_resources=require_resources)
        return [
            [int(x), int(y)]
            for key, option in options.items()
            if option["claimable"]
            for x, y in [key.split(",", 1)]
        ]

    def get_claim_options(self, country_name, require_resources=True):
        self.ensure_territory_map()
        if self._country_by_name(country_name) is None:
            return {}

        options = {}
        tiles = self.territory_map["tiles"]
        for y, row in enumerate(tiles):
            for x, cell in enumerate(row):
                if cell != self.EMPTY_TILE:
                    continue
                ok, msg, _, cost_usd, cost_military = self._validate_claim_territory(
                    country_name,
                    x,
                    y,
                    require_resources=require_resources,
                )
                key = f"{x},{y}"
                if ok:
                    reason = f"占領可能です。消費: {cost_military:.1f} Military / {cost_usd:.1f} USD"
                else:
                    reason = msg
                options[key] = {
                    "claimable": ok,
                    "reason": reason,
                    "cost_usd": round(cost_usd, 1),
                    "cost_military": round(cost_military, 1),
                }
        return options

    def claim_territory(self, country_name, x, y):
        ok, msg, country, cost_usd, cost_military = self._validate_claim_territory(
            country_name,
            x,
            y,
            require_resources=True,
        )
        if not ok:
            return False, msg

        country.usd -= cost_usd

        self.territory_map["military_committed"][country_name] = (
            self.territory_map["military_committed"].get(country_name, 0.0) + cost_military
        )
        self.territory_map["tiles"][y][x] = country_name
        return True, f"{country_name} が領土を拡大しました。消費: {cost_military:.1f} Military / {cost_usd:.1f} USD"

    def _select_ai_claim_target(self, country_name):
        claimable_tiles = self.get_claimable_tiles(country_name, require_resources=True)
        if not claimable_tiles:
            return None

        best = None
        best_score = None
        for x, y in claimable_tiles:
            cost_usd, cost_military = self.territory_cell_cost(country_name, x, y)
            enemy_adjacent = self._adjacent_enemy_count(x, y, country_name)
            score = (cost_military, cost_usd, -enemy_adjacent, y, x)
            if best_score is None or score < best_score:
                best_score = score
                best = (x, y, cost_usd, cost_military)
        return best

    def auto_expand_territory_for_ai(self, max_claims_per_country=1):
        self.ensure_territory_map()
        if max_claims_per_country <= 0:
            return []

        results = []
        for country in self.Country_list:
            if not getattr(country, "selfoperation", False):
                continue

            claims_done = 0
            while claims_done < max_claims_per_country:
                target = self._select_ai_claim_target(country.name)
                if target is None:
                    break

                x, y, _cost_usd, _cost_military = target
                ok, msg = self.claim_territory(country.name, x, y)
                if not ok:
                    break

                results.append({"country_name": country.name, "x": x, "y": y, "message": msg})
                claims_done += 1

        return results
        
    def save(self):
        init_db()
        country_names = [c.name for c in self.Country_list]
        money_names = [m.name for m in self.Money_list]
        self.ensure_territory_map()

        with get_connection() as conn:
            conn.execute("BEGIN")
            save_world_state(
                turn=self.turn,
                turn_year=self.turn_year,
                index_base_turn=self.index_base_turn,
                country_names=country_names,
                money_names=money_names,
                territory_map=self.territory_map,
                conn=conn,
            )
            for country in self.Country_list:
                country.save_country(conn=conn)
            for money in self.Money_list:
                money.save_money(conn=conn)

            if country_names:
                placeholders = ",".join("?" for _ in country_names)
                conn.execute(
                    f"DELETE FROM country_state WHERE name NOT IN ({placeholders})",
                    country_names,
                )
            else:
                conn.execute("DELETE FROM country_state")

            if money_names:
                placeholders = ",".join("?" for _ in money_names)
                conn.execute(
                    f"DELETE FROM money_state WHERE name NOT IN ({placeholders})",
                    money_names,
                )
            else:
                conn.execute("DELETE FROM money_state")

            conn.commit()
    
    def load(self):
        init_db()
        state = load_world_state()
        if state is None:
            return False

        self.Country_list.clear()
        self.Money_list.clear()
        self.turn = state["turn"]
        self.turn_year = state["turn_year"]
        self.index_base_turn = state["index_base_turn"]
        self.territory_map = state.get("territory_map")

        for cname in state["country_names"]:
            c1 = Country(cname, "d", -1, 1, 1)
            if not c1.load(cname):
                return False
            self.add_country(c1)

        for mname in state["money_names"]:
            m1 = Money(mname, 0, 0, False, is_major=False)
            if not m1.load(mname):
                return False
            self.add_money(m1)

        self.normalize_territory_map()
        if self.territory_map is None:
            self.generate_territory_map()
        return True
            
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

        # AIモードの国は毎ターン自動で領土拡大を試みる（1ターン1マス）
        self.auto_expand_territory_for_ai(max_claims_per_country=1)

        # このターンの貿易収支を一時記録する辞書を作成
        current_turn_trade_balance = {c.name: 0.0 for c in self.Country_list}
        available_military_map = {c.name: self.get_country_available_military(c.name) for c in self.Country_list}

        
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
                mil_power_a = available_military_map.get(country_a.name, 0.0)
                mil_power_b = available_military_map.get(country_b.name, 0.0)
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
