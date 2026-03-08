from Country import Country
from Money import Money
import math
import random
import os
from number_format import format_ja_units
from persistence import get_connection, init_db, load_world_state, save_world_state

DEBUG_LOGS = os.getenv("MYGAME_DEBUG_LOGS", "0") == "1"

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
    MIN_TILE_POWER = 1
    MAX_TILE_POWER = 250
    REINFORCE_GDP_RATIO = 0.10
    AI_REINFORCE_ATTEMPT_CHANCE = 0.30
    AI_CAPITAL_REINFORCE_WEIGHT = 1.45
    BASE_AUTO_INTERVENTION_INTERVAL = 20
    BASE_AUTO_INTERVENTION_EPSILON = 0.5
    BASE_AUTO_INTERVENTION_IMBALANCE_RATIO = 0.35
    TERRITORY_EVENT_LOG_LIMIT = 600

    # ★修正: index_base_turn 引数を追加 (デフォルト50)
    def __init__(self, turn_year, index_base_turn=50):
        self.Country_list = []
        self.turn = 0
        self.turn_year = turn_year
        self.Money_list = []  # 通貨のリスト
        self.index_base_turn = index_base_turn # Currency Indexの基準ターン
        self.territory_map = None
        env_interval = os.getenv("MYGAME_BASE_AUTO_INTERVENTION_INTERVAL")
        try:
            interval = int(env_interval) if env_interval is not None else self.BASE_AUTO_INTERVENTION_INTERVAL
        except (TypeError, ValueError):
            interval = self.BASE_AUTO_INTERVENTION_INTERVAL
        self.base_auto_intervention_interval = max(1, interval)
        self.base_auto_intervention_epsilon = self.BASE_AUTO_INTERVENTION_EPSILON
        env_imbalance_ratio = os.getenv("MYGAME_BASE_AUTO_INTERVENTION_IMBALANCE_RATIO")
        try:
            imbalance_ratio = (
                float(env_imbalance_ratio)
                if env_imbalance_ratio is not None
                else self.BASE_AUTO_INTERVENTION_IMBALANCE_RATIO
            )
        except (TypeError, ValueError):
            imbalance_ratio = self.BASE_AUTO_INTERVENTION_IMBALANCE_RATIO
        self.base_auto_intervention_imbalance_ratio = max(0.0, min(1.0, imbalance_ratio))

    def _normalize_territory_event_logs(self, raw_logs):
        normalized = []
        if not isinstance(raw_logs, list):
            return normalized

        # 古いログを間引いてから正規化してコストを一定に保つ
        scan_source = raw_logs[-(self.TERRITORY_EVENT_LOG_LIMIT * 2):]
        for row in scan_source:
            if not isinstance(row, dict):
                continue

            country = row.get("country")
            action = row.get("action")
            try:
                turn = int(row.get("turn", 0))
                x = int(row.get("x", -1))
                y = int(row.get("y", -1))
            except (TypeError, ValueError):
                continue

            if not isinstance(country, str) or country == "":
                continue
            if action not in ("claim", "reinforce"):
                continue

            item = {
                "turn": max(0, turn),
                "country": country,
                "action": action,
                "x": x,
                "y": y,
            }
            if "power_before" in row:
                try:
                    item["power_before"] = int(row["power_before"])
                except (TypeError, ValueError):
                    pass
            if "power_after" in row:
                try:
                    item["power_after"] = int(row["power_after"])
                except (TypeError, ValueError):
                    pass
            normalized.append(item)

        if len(normalized) > self.TERRITORY_EVENT_LOG_LIMIT:
            normalized = normalized[-self.TERRITORY_EVENT_LOG_LIMIT:]
        return normalized

    def _append_territory_event_log(self, country_name, action, x, y, **extra):
        if not self.territory_map:
            return

        logs = self.territory_map.get("event_logs")
        if not isinstance(logs, list):
            logs = []
            self.territory_map["event_logs"] = logs

        event = {
            "turn": int(self.turn),
            "country": country_name,
            "action": action,
            "x": int(x),
            "y": int(y),
        }
        for key in ("power_before", "power_after"):
            if key in extra and extra[key] is not None:
                try:
                    event[key] = int(extra[key])
                except (TypeError, ValueError):
                    continue

        logs.append(event)
        overflow = len(logs) - self.TERRITORY_EVENT_LOG_LIMIT
        if overflow > 0:
            del logs[:overflow]

    def _auto_intervene_base_currency_domestic(self):
        """
        一定ターンごとに FX(USD) と Domestic(USD換算) の偏りを検出し、
        差分比率が閾値を超えた国のみ介入で 50:50 に近づける。
        自動調整分は為替計算へ中立化するため fx_neutral_intervention_usd 側に記録する。
        """
        if self.turn <= 0:
            return
        if self.turn % self.base_auto_intervention_interval != 0:
            return

        eps = self.base_auto_intervention_epsilon
        imbalance_threshold = self.base_auto_intervention_imbalance_ratio
        for country in self.Country_list:
            money = self._money_by_name(country.money_name)
            if money is None:
                continue

            current_rate = money.get_rate()
            if current_rate <= 0:
                continue

            domestic_usd = country.domestic_money / current_rate
            total_abs = abs(country.usd) + abs(domestic_usd)
            if total_abs <= eps:
                if abs(country.domestic_money) <= eps:
                    country.domestic_money = 0.0
                continue

            imbalance_ratio = abs(country.usd - domestic_usd) / (total_abs + 0.00001)
            if imbalance_ratio < imbalance_threshold:
                continue

            # 介入で usd と domestic_usd を同値(50:50)に寄せる
            target_usd = (country.usd + domestic_usd) / 2.0
            amount_usd = target_usd - country.usd
            if abs(amount_usd) <= eps / (current_rate + 0.00001):
                continue

            if amount_usd < 0:
                sell_capacity = max(0.0, country.usd)
                if sell_capacity <= 0.0:
                    continue
                amount_usd = max(amount_usd, -sell_capacity)
                if amount_usd == 0.0:
                    continue

            before_turn_intervention = country.turn_intervention_usd
            country.intervene(amount_usd, current_rate, self.turn)
            executed_amount = country.turn_intervention_usd - before_turn_intervention
            if executed_amount != 0.0:
                country.turn_intervention_usd -= executed_amount
                country.fx_neutral_intervention_usd += executed_amount
            if abs(country.domestic_money) <= eps:
                country.domestic_money = 0.0

    def _auto_cover_ai_negative_fx_reserves(self):
        """
        AIモードかつ基軸通貨国に限定し、FX(USD)が -GDP_USD を下回った場合に
        通常の介入ロジックで USD を買い戻す。
        """
        base_money = self.get_base_currency()
        if base_money is None:
            return

        for country in self.Country_list:
            if not getattr(country, "selfoperation", False):
                continue
            if country.money_name != base_money.name:
                continue
            if country.usd >= 0:
                continue

            gdp_usd = self._country_gdp_base_currency(country.name)
            if gdp_usd <= 0:
                continue
            if abs(country.usd) <= gdp_usd:
                continue

            money = self._money_by_name(country.money_name)
            if money is None:
                continue
            current_rate = money.get_rate()
            if current_rate <= 0:
                continue

            amount_usd = abs(country.usd) / 5.0
            country.intervene(amount_usd, current_rate, self.turn)
            
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

    def _first_country_tile_position(self, country_name, tiles=None):
        source_tiles = tiles
        if source_tiles is None:
            if not self.territory_map:
                return None
            source_tiles = self.territory_map.get("tiles", [])
        for y, row in enumerate(source_tiles):
            for x, owner in enumerate(row):
                if owner == country_name:
                    return x, y
        return None

    def _terrain_power_from_score(self, score):
        # 地形スコアをもとに 1〜4 の初期Powerを与える
        normalized = max(0.0, min(1.0, score / 3.2))
        return int(self.MIN_TILE_POWER + round(normalized * 3.0))

    def _clamp_tile_power(self, value, owner):
        if owner == self.SEA_TILE:
            return 0
        if owner == self.EMPTY_TILE:
            return 0
        return max(self.MIN_TILE_POWER, min(self.MAX_TILE_POWER, int(value)))

    def _get_tile_power_value(self, x, y):
        if not self.territory_map:
            return 0
        tile_power = self.territory_map.get("tile_power", [])
        if y < 0 or y >= len(tile_power):
            return 0
        row = tile_power[y]
        if x < 0 or x >= len(row):
            return 0
        try:
            return int(row[x])
        except (TypeError, ValueError):
            return 0

    def _normalize_capitals(self, raw_capitals, tiles, width, height):
        normalized = {}
        if isinstance(raw_capitals, dict):
            for country in self.Country_list:
                raw_pos = raw_capitals.get(country.name)
                if not isinstance(raw_pos, (list, tuple)) or len(raw_pos) != 2:
                    continue
                try:
                    x = int(raw_pos[0])
                    y = int(raw_pos[1])
                except (TypeError, ValueError):
                    continue
                if 0 <= x < width and 0 <= y < height and tiles[y][x] == country.name:
                    normalized[country.name] = [x, y]

        for country in self.Country_list:
            if country.name in normalized:
                continue
            pos = self._first_country_tile_position(country.name, tiles=tiles)
            if pos is not None:
                normalized[country.name] = [pos[0], pos[1]]
        return normalized

    def get_country_capital(self, country_name):
        self.ensure_territory_map()
        capitals = self.territory_map.get("capitals", {})
        if not isinstance(capitals, dict):
            return None
        raw_pos = capitals.get(country_name)
        if not isinstance(raw_pos, (list, tuple)) or len(raw_pos) != 2:
            return None
        try:
            x = int(raw_pos[0])
            y = int(raw_pos[1])
        except (TypeError, ValueError):
            return None
        width = self.territory_map.get("width", 0)
        height = self.territory_map.get("height", 0)
        if x < 0 or y < 0 or x >= width or y >= height:
            return None
        if self.territory_map["tiles"][y][x] != country_name:
            return None
        return x, y

    def set_capital(self, country_name, x, y):
        self.ensure_territory_map()
        width = self.territory_map["width"]
        height = self.territory_map["height"]
        if x < 0 or y < 0 or x >= width or y >= height:
            return False, "指定したマスは地図の範囲外です。"

        country = self._country_by_name(country_name)
        if country is None:
            return False, "対象の国が見つかりません。"

        owner = self.territory_map["tiles"][y][x]
        if owner != country_name:
            return False, "自国領のみ首都に設定できます。"

        capitals = self.territory_map.get("capitals")
        if not isinstance(capitals, dict):
            capitals = {}
            self.territory_map["capitals"] = capitals

        current = None
        raw_current = capitals.get(country_name)
        if isinstance(raw_current, (list, tuple)) and len(raw_current) == 2:
            try:
                current = (int(raw_current[0]), int(raw_current[1]))
            except (TypeError, ValueError):
                current = None
        if current == (x, y):
            return True, f"{country_name} の首都は既に ({x}, {y}) です。"

        capitals[country_name] = [x, y]
        return True, f"{country_name} の首都を ({x}, {y}) に設定しました。"

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
        raw_tile_power = self.territory_map.get("tile_power", [])
        raw_capitals = self.territory_map.get("capitals", {})
        has_raw_tile_power = isinstance(raw_tile_power, list) and len(raw_tile_power) == height
        normalized_tile_power = []
        for row in tiles:
            if not isinstance(row, list) or len(row) != width:
                self.territory_map = None
                return
            normalized_row = []
            power_row = []
            y = len(normalized_tiles)
            raw_power_row = raw_tile_power[y] if has_raw_tile_power and isinstance(raw_tile_power[y], list) else []
            for cell in row:
                x = len(normalized_row)
                if cell == self.SEA_TILE:
                    normalized_row.append(self.SEA_TILE)
                    power_row.append(0)
                elif isinstance(cell, str) and (cell == self.EMPTY_TILE or cell in valid_owners):
                    normalized_row.append(cell)
                    if x < len(raw_power_row):
                        raw_val = raw_power_row[x]
                    else:
                        raw_val = self.MIN_TILE_POWER if cell in valid_owners else 0
                    power_row.append(self._clamp_tile_power(raw_val, cell))
                else:
                    normalized_row.append(self.EMPTY_TILE)
                    power_row.append(0)
            normalized_tiles.append(normalized_row)
            normalized_tile_power.append(power_row)

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

        normalized_capitals = self._normalize_capitals(raw_capitals, normalized_tiles, width, height)
        self.territory_map = {
            "width": width,
            "height": height,
            "tiles": normalized_tiles,
            "tile_power": normalized_tile_power,
            "capitals": normalized_capitals,
            "country_colors": self._assign_country_colors(self.territory_map.get("country_colors")),
            "military_committed": normalized_committed,
            "seed": self.territory_map.get("seed"),
            "event_logs": self._normalize_territory_event_logs(self.territory_map.get("event_logs", [])),
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
        tile_power = [
            [
                0 if tiles[y][x] != self.SEA_TILE else 0
                for x in range(width)
            ]
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

        capitals = {}
        for country_name in country_names:
            seed_pos = seed_positions.get(country_name)
            if seed_pos is not None:
                capitals[country_name] = [seed_pos[0], seed_pos[1]]
                continue
            pos = self._first_country_tile_position(country_name, tiles=tiles)
            if pos is not None:
                capitals[country_name] = [pos[0], pos[1]]

        # 空き地Powerは0固定。保有領土のみ初期Powerを付与。
        for y in range(height):
            for x in range(width):
                owner = tiles[y][x]
                if owner in country_names:
                    tile_power[y][x] = self._terrain_power_from_score(scores[y][x])
                else:
                    tile_power[y][x] = 0

        self.territory_map = {
            "width": width,
            "height": height,
            "tiles": tiles,
            "tile_power": tile_power,
            "capitals": capitals,
            "country_colors": self._assign_country_colors(),
            "military_committed": {c.name: 0.0 for c in self.Country_list},
            "seed": seed,
            "event_logs": [],
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

    def get_country_territory_power(self, country_name):
        self.ensure_territory_map()
        total_power = 0
        tiles = self.territory_map["tiles"]
        tile_power = self.territory_map.get("tile_power", [])
        for y, row in enumerate(tiles):
            for x, owner in enumerate(row):
                if owner == country_name:
                    total_power += self._get_tile_power_value(x, y)
        return int(total_power)

    def get_country_territory_power_stats(self, country_name):
        self.ensure_territory_map()
        tiles = self.territory_map["tiles"]
        powers = []
        for y, row in enumerate(tiles):
            for x, owner in enumerate(row):
                if owner == country_name:
                    powers.append(self._get_tile_power_value(x, y))

        if not powers:
            return {"total_power": 0, "average_power": 0.0, "max_power": 0}

        total = sum(powers)
        return {
            "total_power": int(total),
            "average_power": float(total / len(powers)),
            "max_power": int(max(powers)),
        }

    def get_all_country_territory_power(self):
        self.ensure_territory_map()
        result = {c.name: 0 for c in self.Country_list}
        tiles = self.territory_map["tiles"]
        for y, row in enumerate(tiles):
            for x, owner in enumerate(row):
                if owner in result:
                    result[owner] += self._get_tile_power_value(x, y)
        return result

    def get_territory_event_logs(self, limit=200):
        self.ensure_territory_map()
        logs = self.territory_map.get("event_logs", [])
        if not isinstance(logs, list):
            return []
        max_items = max(0, int(limit))
        if max_items == 0:
            return []
        return list(reversed(logs[-max_items:]))

    def get_country_available_military(self, country_name):
        self.ensure_territory_map()
        country = self._country_by_name(country_name)
        if country is None:
            return 0.0
        committed = self.territory_map["military_committed"].get(country_name, 0.0)
        return max(0.0, country.military.caluc_power() - committed)

    def get_country_reinforce_cost_usd(self, country_name):
        gdp_usd = self._country_gdp_base_currency(country_name)
        return max(0.0, gdp_usd * self.REINFORCE_GDP_RATIO)

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
                    f"USDが不足しています。必要 {format_ja_units(cost_usd)} / 保有 {format_ja_units(country.usd)}",
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
                power_value = self._get_tile_power_value(x, y)
                if ok:
                    reason = (
                        f"占領可能です。Power {power_value} / 消費: {cost_military:.1f} Military / "
                        f"{format_ja_units(cost_usd)} USD"
                    )
                else:
                    reason = msg
                options[key] = {
                    "claimable": ok,
                    "reason": reason,
                    "cost_usd": round(cost_usd, 1),
                    "cost_military": round(cost_military, 1),
                    "tile_power": int(power_value),
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
        current_power = self._get_tile_power_value(x, y)
        if current_power <= 0:
            current_power = self.MIN_TILE_POWER
            self.territory_map["tile_power"][y][x] = current_power
        capitals = self.territory_map.get("capitals")
        if not isinstance(capitals, dict):
            capitals = {}
            self.territory_map["capitals"] = capitals
        if country_name not in capitals:
            capitals[country_name] = [x, y]
        self._append_territory_event_log(
            country_name=country_name,
            action="claim",
            x=x,
            y=y,
            power_after=current_power,
        )
        return True, (
            f"{country_name} が領土を拡大しました。Power {current_power} を確保 / "
            f"消費: {cost_military:.1f} Military / {format_ja_units(cost_usd)} USD"
        )

    def reinforce_territory(self, country_name, x, y):
        self.ensure_territory_map()
        width = self.territory_map["width"]
        height = self.territory_map["height"]
        if x < 0 or y < 0 or x >= width or y >= height:
            return False, "指定したマスは地図の範囲外です。"

        country = self._country_by_name(country_name)
        if country is None:
            return False, "対象の国が見つかりません。"

        owner = self.territory_map["tiles"][y][x]
        if owner != country_name:
            return False, "自国領のみ強化できます。"

        current_power = self._get_tile_power_value(x, y)
        if current_power >= self.MAX_TILE_POWER:
            return False, f"この領土は既に最大Power({self.MAX_TILE_POWER})です。"

        required_usd = self.get_country_reinforce_cost_usd(country_name)
        if country.usd < required_usd:
            return (
                False,
                f"FX Reserveが不足しています。必要 {format_ja_units(required_usd)} USD (GDPの10%) / 保有 {format_ja_units(country.usd)} USD",
            )

        country.usd -= required_usd
        self.territory_map["tile_power"][y][x] = min(self.MAX_TILE_POWER, max(self.MIN_TILE_POWER, current_power + 1))
        new_power = self.territory_map["tile_power"][y][x]
        self._append_territory_event_log(
            country_name=country_name,
            action="reinforce",
            x=x,
            y=y,
            power_before=current_power,
            power_after=new_power,
        )
        return True, (
            f"{country_name} が領土強化を実施。Power {current_power} → {new_power} / "
            f"消費 {format_ja_units(required_usd)} USD (GDPの10%)"
        )

    def _select_ai_claim_target(self, country_name):
        candidate_tiles = self._candidate_claim_tiles(country_name)
        if not candidate_tiles:
            return None

        best = None
        best_score = None
        for x, y in candidate_tiles:
            ok, _msg, _country, cost_usd, cost_military = self._validate_claim_territory(
                country_name,
                x,
                y,
                require_resources=True,
            )
            if not ok:
                continue
            enemy_adjacent = self._adjacent_enemy_count(x, y, country_name)
            score = (cost_military, cost_usd, -enemy_adjacent, y, x)
            if best_score is None or score < best_score:
                best_score = score
                best = (x, y, cost_usd, cost_military)
        return best

    def _candidate_claim_tiles(self, country_name):
        self.ensure_territory_map()
        width = self.territory_map["width"]
        height = self.territory_map["height"]
        tiles = self.territory_map["tiles"]

        if not self._country_has_any_territory(country_name):
            all_empty = []
            for y, row in enumerate(tiles):
                for x, cell in enumerate(row):
                    if cell == self.EMPTY_TILE:
                        all_empty.append((x, y))
            return all_empty

        positions = self._country_tile_positions().get(country_name, [])
        candidates = set()

        for tx, ty in positions:
            for nx, ny in self._neighbors4(tx, ty, width, height):
                if tiles[ny][nx] == self.EMPTY_TILE:
                    candidates.add((nx, ny))

            for dx, dy in self._directions8():
                cx = tx + dx
                cy = ty + dy
                sea_len = 0
                while 0 <= cx < width and 0 <= cy < height:
                    cell = tiles[cy][cx]
                    if cell == self.SEA_TILE:
                        sea_len += 1
                        cx += dx
                        cy += dy
                        continue
                    if sea_len >= 1 and cell == self.EMPTY_TILE:
                        candidates.add((cx, cy))
                    break

        return list(candidates)

    def _candidate_reinforce_tiles(self, country_name):
        self.ensure_territory_map()
        tiles = self.territory_map["tiles"]
        candidates = []
        for y, row in enumerate(tiles):
            for x, owner in enumerate(row):
                if owner != country_name:
                    continue
                if self._get_tile_power_value(x, y) >= self.MAX_TILE_POWER:
                    continue
                candidates.append((x, y))
        return candidates

    def _select_ai_reinforce_target(self, country_name):
        candidates = self._candidate_reinforce_tiles(country_name)
        if not candidates:
            return None

        capital = self.get_country_capital(country_name)
        weights = []
        for x, y in candidates:
            current_power = max(self.MIN_TILE_POWER, self._get_tile_power_value(x, y))
            deficit_ratio = max(0.0, float(self.MAX_TILE_POWER - current_power) / float(self.MAX_TILE_POWER))
            weight = 1.0 + (deficit_ratio * 0.25)
            if capital is not None and (x, y) == capital:
                weight *= self.AI_CAPITAL_REINFORCE_WEIGHT
            weights.append(max(0.01, weight))

        return random.choices(candidates, weights=weights, k=1)[0]

    def auto_reinforce_territory_for_ai(self, attempt_chance=None):
        self.ensure_territory_map()
        if attempt_chance is None:
            chance = float(self.AI_REINFORCE_ATTEMPT_CHANCE)
        else:
            try:
                chance = float(attempt_chance)
            except (TypeError, ValueError):
                chance = float(self.AI_REINFORCE_ATTEMPT_CHANCE)
        chance = max(0.0, min(1.0, chance))

        results = []
        for country in self.Country_list:
            if not getattr(country, "selfoperation", False):
                continue
            if random.random() > chance:
                continue

            target = self._select_ai_reinforce_target(country.name)
            if target is None:
                continue
            x, y = target
            ok, msg = self.reinforce_territory(country.name, x, y)
            if not ok:
                continue
            results.append({"country_name": country.name, "x": x, "y": y, "message": msg})

        return results

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
        self._auto_intervene_base_currency_domestic()
        self._auto_cover_ai_negative_fx_reserves()
        
        # ★追加: AIによる関税率の自動更新 (前ターンのデータを使うため、リセット前に実行)
        for country in self.Country_list:
            country.decide_and_update_tariffs(self.Country_list)

        territory_power_map = self.get_all_country_territory_power()
        territory_counts = self.get_territory_counts()

        # 1. 各国のターン進行
        for country in self.Country_list:
            # ターン開始時に貿易内訳をリセット (AI判断が終わった後で行う)
            country.trade_balance_breakdown = {}

            my_money = next((m for m in self.Money_list if m.name == country.money_name), None)
            if my_money:
                country.next_turn(
                    my_money,
                    my_money.get_rate(),
                    self.turn,
                    territory_power=territory_power_map.get(country.name, 0),
                    territory_tiles=territory_counts.get(country.name, 0),
                )

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
        # AIモードの国は確率で領土強化を行う。首都は通常より少し優先する。
        self.auto_reinforce_territory_for_ai()

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
                if DEBUG_LOGS:
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
