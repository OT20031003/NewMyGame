import random
import unittest

from Country import Country
from Money import Money
from World import World


class WorldMapTests(unittest.TestCase):
    def _build_world(self):
        world = World(turn_year=3)
        world.add_money(Money(name="Dollar", interest=3.0, value=1.0, base_currency=True, is_major=True))
        world.add_money(Money(name="Yen", interest=0.5, value=120.0, base_currency=False, is_major=True))

        a = Country(
            name="Alpha",
            money_name="Dollar",
            turn_year=3,
            population_p=5.2,
            salary_p=0.12,
            initial_price=100.0,
            selfoperation=True,
            industry_p=400,
            military_p=35,
        )
        b = Country(
            name="Beta",
            money_name="Yen",
            turn_year=3,
            population_p=5.0,
            salary_p=0.10,
            initial_price=90.0,
            selfoperation=True,
            industry_p=320,
            military_p=30,
        )
        g = Country(
            name="Gamma",
            money_name="Yen",
            turn_year=3,
            population_p=5.0,
            salary_p=0.10,
            initial_price=90.0,
            selfoperation=True,
            industry_p=280,
            military_p=25,
        )

        a.usd = 1_000_000.0
        a.domestic_money = 500.0
        b.usd = 1_000_000.0
        b.domestic_money = 500.0
        g.usd = 1_000_000.0
        g.domestic_money = 500.0

        world.add_country(a)
        world.add_country(b)
        world.add_country(g)
        return world

    def _find_cell(self, world, predicate):
        tiles = world.territory_map["tiles"]
        for y, row in enumerate(tiles):
            for x, cell in enumerate(row):
                if predicate(x, y, cell):
                    return x, y
        return None

    def _find_adjacent_empty(self, world, country_name):
        width = world.territory_map["width"]
        height = world.territory_map["height"]
        tiles = world.territory_map["tiles"]
        for y in range(height):
            for x in range(width):
                if tiles[y][x] != country_name:
                    continue
                for nx, ny in world._neighbors4(x, y, width, height):
                    if tiles[ny][nx] == world.EMPTY_TILE:
                        return nx, ny
        return None

    def test_generate_world_map_contains_required_tiles(self):
        world = self._build_world()
        world.generate_territory_map(width=16, height=10, seed=11)

        self.assertEqual(world.territory_map["width"], 16)
        self.assertEqual(world.territory_map["height"], 10)

        flat_tiles = [cell for row in world.territory_map["tiles"] for cell in row]
        self.assertIn(world.SEA_TILE, flat_tiles)
        self.assertIn(world.EMPTY_TILE, flat_tiles)
        self.assertIn("Alpha", flat_tiles)
        self.assertIn("Beta", flat_tiles)

    def test_claim_territory_success(self):
        world = self._build_world()
        world.generate_territory_map(width=18, height=12, seed=22)
        target = self._find_adjacent_empty(world, "Alpha")
        if target is None:
            self.skipTest("No adjacent empty tile found")

        x, y = target
        alpha = world._country_by_name("Alpha")
        alpha.usd = 1_000_000_000_000.0
        before_usd = alpha.usd
        before_domestic = alpha.domestic_money
        before_committed = world.territory_map["military_committed"]["Alpha"]

        ok, _ = world.claim_territory("Alpha", x, y)

        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tiles"][y][x], "Alpha")
        self.assertGreater(world.territory_map["military_committed"]["Alpha"], before_committed)
        self.assertLess(alpha.usd, before_usd)
        self.assertEqual(alpha.domestic_money, before_domestic)

    def test_claim_territory_rejects_sea(self):
        world = self._build_world()
        world.generate_territory_map(width=16, height=10, seed=33)
        sea = self._find_cell(world, lambda _x, _y, cell: cell == world.SEA_TILE)
        if sea is None:
            self.skipTest("Sea tile not found")

        ok, message = world.claim_territory("Alpha", sea[0], sea[1])

        self.assertFalse(ok)
        self.assertIn("海", message)

    def test_auto_intervention_base_currency_zeros_domestic_on_interval(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")  # 基軸通貨(Dollar)
        beta = world._country_by_name("Beta")    # 非基軸通貨(Yen)

        world.base_auto_intervention_interval = 5
        world.turn = 5
        alpha.domestic_money = 2500.0
        alpha.usd = 1000.0
        beta.domestic_money = 2500.0
        beta.usd = 1000.0
        before_alpha_usd = alpha.usd

        world._auto_intervene_base_currency_domestic()

        self.assertEqual(alpha.domestic_money, 0.0)
        self.assertGreater(alpha.usd, before_alpha_usd)
        self.assertEqual(alpha.turn_intervention_usd, 0.0)
        self.assertGreater(alpha.fx_neutral_intervention_usd, 0.0)
        self.assertEqual(beta.domestic_money, 2500.0)

    def test_auto_intervention_base_currency_skips_non_interval_turn(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        world.base_auto_intervention_interval = 5
        world.turn = 4
        alpha.domestic_money = 1234.0
        alpha.usd = 999.0

        world._auto_intervene_base_currency_domestic()

        self.assertEqual(alpha.domestic_money, 1234.0)
        self.assertEqual(alpha.usd, 999.0)

    def test_ai_negative_fx_reserve_triggers_buy_intervention(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")  # base currency & AI
        beta = world._country_by_name("Beta")    # non-base

        alpha.gdp_usd = 1000.0
        alpha.usd = -1500.0
        alpha.domestic_money = 0.0
        beta.gdp_usd = 1000.0
        beta.usd = 100.0  # 正値の国は対象外
        beta_before_usd = beta.usd
        beta_before_domestic = beta.domestic_money
        world.turn = 10

        world._auto_cover_ai_negative_fx_reserves()

        # |usd|/5 = 300 を購入して -1200 に改善
        self.assertAlmostEqual(alpha.usd, -1200.0, places=6)
        self.assertAlmostEqual(alpha.domestic_money, -300.0, places=6)
        self.assertAlmostEqual(alpha.turn_intervention_usd, 300.0, places=6)
        self.assertEqual(beta.usd, beta_before_usd)
        self.assertEqual(beta.domestic_money, beta_before_domestic)

    def test_ai_negative_fx_reserve_does_not_run_when_usd_positive(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        alpha.gdp_usd = 1000.0
        alpha.usd = 100.0
        alpha.domestic_money = 77.0
        world.turn = 10

        world._auto_cover_ai_negative_fx_reserves()

        self.assertEqual(alpha.usd, 100.0)
        self.assertEqual(alpha.domestic_money, 77.0)
        self.assertEqual(alpha.turn_intervention_usd, 0.0)

    def test_claim_territory_requires_adjacency(self):
        world = self._build_world()
        world.generate_territory_map(width=18, height=12, seed=44)

        def is_non_adjacent_empty(x, y, cell):
            return (
                cell == world.EMPTY_TILE
                and not world._is_adjacent_to_country(x, y, "Alpha")
                and not world._is_adjacent_via_sea(x, y, "Alpha")
            )

        target = self._find_cell(world, is_non_adjacent_empty)
        if target is None:
            self.skipTest("No non-adjacent empty tile found")

        ok, message = world.claim_territory("Alpha", target[0], target[1])

        self.assertFalse(ok)
        self.assertIn("隣接", message)

    def test_claim_territory_allows_narrow_sea_crossing(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 120.0
        beta.gdp_usd = 300.0
        gamma.gdp_usd = 180.0
        world.territory_map = {
            "width": 5,
            "height": 1,
            "tiles": [["Alpha", "__SEA__", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, _ = world.claim_territory("Alpha", 2, 0)
        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tiles"][0][2], "Alpha")

    def test_claim_territory_allows_long_sea_crossing(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 120.0
        beta.gdp_usd = 300.0
        gamma.gdp_usd = 180.0
        world.territory_map = {
            "width": 8,
            "height": 1,
            "tiles": [["Alpha", "__SEA__", "__SEA__", "__SEA__", "__SEA__", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, _ = world.claim_territory("Alpha", 5, 0)
        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tiles"][0][5], "Alpha")

    def test_claim_territory_allows_diagonal_sea_crossing(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 120.0
        beta.gdp_usd = 300.0
        gamma.gdp_usd = 180.0
        world.territory_map = {
            "width": 3,
            "height": 3,
            "tiles": [
                ["Alpha", "__SEA__", "Beta"],
                ["__SEA__", "__SEA__", "__SEA__"],
                ["Gamma", "__SEA__", ""],
            ],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, _ = world.claim_territory("Alpha", 2, 2)
        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tiles"][2][2], "Alpha")

    def test_claim_territory_rejects_bent_sea_path(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        alpha.gdp_usd = 120.0
        world.territory_map = {
            "width": 3,
            "height": 3,
            "tiles": [
                ["", "__SEA__", ""],
                ["Alpha", "__SEA__", ""],
                ["", "", "Beta"],
            ],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, message = world.claim_territory("Alpha", 2, 0)
        self.assertFalse(ok)
        self.assertIn("隣接", message)

    def test_territory_cost_uses_weighted_neighbor_gdp(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 150.0
        beta.gdp_usd = 300.0
        gamma.gdp_usd = 100.0
        world.territory_map = {
            "width": 7,
            "height": 1,
            "tiles": [["Alpha", "", "", "Beta", "", "", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        cost_usd, cost_military = world.territory_cell_cost("Alpha", 2, 0)
        expected_weighted = (300.0 * (1.0 / 2.0) + 100.0 * (1.0 / 5.0)) / ((1.0 / 2.0) + (1.0 / 5.0))
        self.assertAlmostEqual(cost_usd, expected_weighted * 0.20, places=6)
        expected_weighted_military = (30.0 * (1.0 / 2.0) + 25.0 * (1.0 / 5.0)) / ((1.0 / 2.0) + (1.0 / 5.0))
        self.assertAlmostEqual(cost_military, expected_weighted_military * 0.50, places=6)

    def test_claim_territory_fails_when_usd_short(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 50.0
        beta.gdp_usd = 1000.0
        gamma.gdp_usd = 800.0
        alpha.usd = 10.0
        alpha.domestic_money = 10_000_000.0
        before_domestic = alpha.domestic_money
        world.territory_map = {
            "width": 4,
            "height": 1,
            "tiles": [["Alpha", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, message = world.claim_territory("Alpha", 1, 0)
        self.assertFalse(ok)
        self.assertIn("USD", message)
        self.assertEqual(alpha.domestic_money, before_domestic)
        self.assertEqual(world.territory_map["tiles"][0][1], world.EMPTY_TILE)

    def test_claim_options_contains_reason_for_unclaimable_tile(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.gdp_usd = 50.0
        beta.gdp_usd = 1000.0
        gamma.gdp_usd = 800.0
        alpha.usd = 1.0
        world.territory_map = {
            "width": 4,
            "height": 1,
            "tiles": [["Alpha", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        options = world.get_claim_options("Alpha", require_resources=True)
        self.assertIn("1,0", options)
        self.assertFalse(options["1,0"]["claimable"])
        self.assertIn("USD", options["1,0"]["reason"])

    def test_claim_territory_fails_when_military_short(self):
        world = self._build_world()
        world.generate_territory_map(width=18, height=12, seed=55)
        target = self._find_adjacent_empty(world, "Alpha")
        if target is None:
            self.skipTest("No adjacent empty tile found")

        alpha = world._country_by_name("Alpha")
        world.territory_map["military_committed"]["Alpha"] = alpha.military.caluc_power()

        ok, message = world.claim_territory("Alpha", target[0], target[1])

        self.assertFalse(ok)
        self.assertIn("軍事力", message)

    def test_ai_auto_expand_claims_tile_for_selfoperation_country(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        beta.selfoperation = False
        gamma.selfoperation = False
        alpha.usd = 1_000_000_000_000.0
        before_usd = alpha.usd
        world.territory_map = {
            "width": 4,
            "height": 1,
            "tiles": [["Alpha", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        results = world.auto_expand_territory_for_ai(max_claims_per_country=1)

        self.assertEqual(world.territory_map["tiles"][0][1], "Alpha")
        self.assertTrue(any(r["country_name"] == "Alpha" for r in results))
        self.assertLess(alpha.usd, before_usd)
        self.assertGreater(world.territory_map["military_committed"]["Alpha"], 0.0)

    def test_ai_candidate_tiles_match_claimable_tiles_without_resources(self):
        world = self._build_world()
        world.territory_map = {
            "width": 5,
            "height": 1,
            "tiles": [["", "Alpha", "__SEA__", "", "Beta"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        expected = {tuple(xy) for xy in world.get_claimable_tiles("Alpha", require_resources=False)}
        actual = set(world._candidate_claim_tiles("Alpha"))

        self.assertEqual(actual, expected)

    def test_ai_auto_expand_skips_player_country(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        alpha.selfoperation = False
        beta.selfoperation = False
        gamma.selfoperation = False
        world.territory_map = {
            "width": 4,
            "height": 1,
            "tiles": [["Alpha", "", "Beta", "Gamma"]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        results = world.auto_expand_territory_for_ai(max_claims_per_country=1)

        self.assertEqual(world.territory_map["tiles"][0][1], world.EMPTY_TILE)
        self.assertEqual(world.territory_map["military_committed"]["Alpha"], 0.0)
        self.assertEqual(results, [])

    def test_set_capital_updates_country_capital(self):
        world = self._build_world()
        world.territory_map = {
            "width": 3,
            "height": 1,
            "tiles": [["Alpha", "Alpha", "Beta"]],
            "tile_power": [[5, 7, 8]],
            "capitals": {"Alpha": [0, 0], "Beta": [2, 0]},
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, _ = world.set_capital("Alpha", 1, 0)

        self.assertTrue(ok)
        self.assertEqual(world.get_country_capital("Alpha"), (1, 0))

    def test_set_capital_rejects_non_owned_tile(self):
        world = self._build_world()
        world.territory_map = {
            "width": 3,
            "height": 1,
            "tiles": [["Alpha", "Beta", ""]],
            "tile_power": [[5, 7, 0]],
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        ok, message = world.set_capital("Alpha", 1, 0)

        self.assertFalse(ok)
        self.assertIn("自国領", message)

    def test_ai_reinforce_target_prefers_capital_tile(self):
        world = self._build_world()
        alpha = world._country_by_name("Alpha")
        beta = world._country_by_name("Beta")
        gamma = world._country_by_name("Gamma")
        beta.selfoperation = False
        gamma.selfoperation = False
        alpha.usd = 1_000_000_000.0
        alpha.gdp_usd = 1000.0

        world.territory_map = {
            "width": 2,
            "height": 1,
            "tiles": [["Alpha", "Alpha"]],
            "tile_power": [[10, 10]],
            "capitals": {"Alpha": [0, 0]},
            "country_colors": {"Alpha": "#111", "Beta": "#222", "Gamma": "#333"},
            "military_committed": {"Alpha": 0.0, "Beta": 0.0, "Gamma": 0.0},
            "seed": None,
        }

        random.seed(12345)
        total = 3000
        capital_hits = 0
        for _ in range(total):
            target = world._select_ai_reinforce_target("Alpha")
            self.assertIsNotNone(target)
            if target == (0, 0):
                capital_hits += 1

        self.assertGreater(capital_hits / total, 0.55)

    def test_next_turn_calls_ai_auto_expand(self):
        world = self._build_world()
        calls = []
        world.auto_expand_territory_for_ai = lambda max_claims_per_country=1: calls.append(max_claims_per_country) or []

        world.Next_turn()

        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
