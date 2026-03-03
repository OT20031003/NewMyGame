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
        before_usd = alpha.usd
        before_domestic = alpha.domestic_money
        before_committed = world.territory_map["military_committed"]["Alpha"]

        ok, _ = world.claim_territory("Alpha", x, y)

        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tiles"][y][x], "Alpha")
        self.assertGreater(world.territory_map["military_committed"]["Alpha"], before_committed)
        self.assertTrue(alpha.usd < before_usd or alpha.domestic_money < before_domestic)

    def test_claim_territory_rejects_sea(self):
        world = self._build_world()
        world.generate_territory_map(width=16, height=10, seed=33)
        sea = self._find_cell(world, lambda _x, _y, cell: cell == world.SEA_TILE)
        if sea is None:
            self.skipTest("Sea tile not found")

        ok, message = world.claim_territory("Alpha", sea[0], sea[1])

        self.assertFalse(ok)
        self.assertIn("海", message)

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

        cost_usd, _ = world.territory_cell_cost("Alpha", 2, 0)
        expected_weighted = (300.0 * (1.0 / 2.0) + 100.0 * (1.0 / 5.0)) / ((1.0 / 2.0) + (1.0 / 5.0))
        self.assertAlmostEqual(cost_usd, expected_weighted * 0.20, places=6)

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


if __name__ == "__main__":
    unittest.main()
