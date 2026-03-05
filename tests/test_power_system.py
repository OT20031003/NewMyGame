import random
import unittest

from Country import Country
from Money import Money
from World import World


class PowerSystemTests(unittest.TestCase):
    def _build_single_country_world(self):
        world = World(turn_year=3)
        money = Money(name="Dollar", interest=2.0, value=1.0, base_currency=True, is_major=True)
        world.add_money(money)
        country = Country(
            name="Alpha",
            money_name="Dollar",
            turn_year=3,
            population_p=5.0,
            salary_p=0.09,
            initial_price=95.0,
            selfoperation=False,
            industry_p=600.0,
            military_p=120.0,
        )
        country.usd = 1_000_000.0
        country.domestic_money = 500_000.0
        world.add_country(country)
        world.generate_territory_map(width=14, height=10, seed=17)
        return world, country, money

    def test_generated_map_contains_tile_power(self):
        world, _, _ = self._build_single_country_world()
        tile_power = world.territory_map.get("tile_power")
        self.assertIsInstance(tile_power, list)
        self.assertEqual(len(tile_power), world.territory_map["height"])
        self.assertEqual(len(tile_power[0]), world.territory_map["width"])
        self.assertTrue(all(isinstance(v, int) for row in tile_power for v in row))
        tiles = world.territory_map["tiles"]
        for y, row in enumerate(tiles):
            for x, cell in enumerate(row):
                if cell == world.EMPTY_TILE:
                    self.assertEqual(tile_power[y][x], 0)

    def test_reinforce_territory_requires_10pct_gdp_fx_reserve(self):
        world, country, _ = self._build_single_country_world()
        country.gdp_usd = 2000.0  # 強化コストは200.0 USD
        required = world.get_country_reinforce_cost_usd(country.name)
        self.assertAlmostEqual(required, 200.0, places=6)

        target = None
        for y, row in enumerate(world.territory_map["tiles"]):
            for x, owner in enumerate(row):
                if owner == country.name:
                    target = (x, y)
                    break
            if target:
                break
        self.assertIsNotNone(target)
        x, y = target

        country.usd = required - 1.0
        ok, message = world.reinforce_territory(country.name, x, y)
        self.assertFalse(ok)
        self.assertIn("GDPの10%", message)

        country.usd = required + 10.0
        before_power = world.territory_map["tile_power"][y][x]
        before_usd = country.usd
        ok, _ = world.reinforce_territory(country.name, x, y)
        self.assertTrue(ok)
        self.assertEqual(world.territory_map["tile_power"][y][x], min(world.MAX_TILE_POWER, before_power + 1))
        self.assertAlmostEqual(country.usd, before_usd - required, places=6)

    def test_birth_rate_uses_both_power_and_satisfaction(self):
        random.seed(11)
        country = Country(
            name="Alpha",
            money_name="Dollar",
            turn_year=3,
            population_p=5.0,
            salary_p=0.09,
            initial_price=95.0,
            selfoperation=False,
            industry_p=600.0,
            military_p=120.0,
        )
        low_power = country.estimate_birth_rate(
            avg_satisfaction=55.0,
            purchasing_power=1.2,
            territory_power=30,
            territory_tiles=10,
        )
        high_power = country.estimate_birth_rate(
            avg_satisfaction=55.0,
            purchasing_power=1.2,
            territory_power=400,
            territory_tiles=10,
        )
        low_satisfaction = country.estimate_birth_rate(
            avg_satisfaction=35.0,
            purchasing_power=1.2,
            territory_power=400,
            territory_tiles=10,
        )

        self.assertGreater(high_power, low_power)
        self.assertLess(low_satisfaction, high_power)

    def test_territory_event_logs_record_claim_and_reinforce(self):
        world, country, _ = self._build_single_country_world()
        world.turn = 12
        country.gdp_usd = 2000.0
        country.usd = 1_000_000.0

        target = None
        tiles = world.territory_map["tiles"]
        width = world.territory_map["width"]
        height = world.territory_map["height"]
        for y in range(height):
            for x in range(width):
                if tiles[y][x] != country.name:
                    continue
                for nx, ny in world._neighbors4(x, y, width, height):
                    if tiles[ny][nx] == world.EMPTY_TILE:
                        target = (nx, ny)
                        break
                if target:
                    break
            if target:
                break

        if target is None:
            self.skipTest("No adjacent empty tile found")

        x, y = target
        ok, _ = world.claim_territory(country.name, x, y)
        self.assertTrue(ok)
        ok, _ = world.reinforce_territory(country.name, x, y)
        self.assertTrue(ok)

        logs = world.get_territory_event_logs(limit=20)
        claim_log = next((row for row in logs if row["action"] == "claim" and row["x"] == x and row["y"] == y), None)
        reinforce_log = next((row for row in logs if row["action"] == "reinforce" and row["x"] == x and row["y"] == y), None)

        self.assertIsNotNone(claim_log)
        self.assertIsNotNone(reinforce_log)
        self.assertEqual(claim_log["turn"], 12)
        self.assertEqual(reinforce_log["turn"], 12)
        self.assertEqual(claim_log["country"], country.name)
        self.assertEqual(reinforce_log["country"], country.name)

    def test_industry_growth_stays_bounded_in_midrun(self):
        random.seed(7)
        world, country, money = self._build_single_country_world()
        start_industry = country.industry.caluc_power()
        start_population = country.get_population()

        for t in range(24):
            if world.turn % country.turn_year == 0:
                territory_power = world.get_country_territory_power(country.name)
                territory_tiles = world.get_territory_counts()[country.name]
                country.next_turn_year(
                    tax=country.tax,
                    bud=[40.0, 0.0, 20.0],
                    rate=money.get_rate(),
                    turn=world.turn,
                    domestic_interest=money.get_interest(),
                    usd_interest=money.get_interest(),
                    territory_power=territory_power,
                    territory_tiles=territory_tiles,
                )
            world.Next_turn()

        end_industry = country.industry.caluc_power()
        end_population = country.get_population()

        self.assertGreater(end_industry, start_industry)
        self.assertLess(end_industry / max(1.0, start_industry), 3.0)
        self.assertLess(end_population / max(1.0, start_population), 1.7)


if __name__ == "__main__":
    unittest.main()
