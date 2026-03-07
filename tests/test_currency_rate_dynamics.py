import unittest
from unittest.mock import patch

from CurrencyRate import CurrencyRate


class CurrencyRateDynamicsTests(unittest.TestCase):
    def _build_stable_rate(self):
        rate = CurrencyRate("Test", 100.0)
        # Warmup後の挙動を見るため、初期レートで履歴を伸ばしておく
        for _ in range(CurrencyRate.ANCHOR_BLEND_WARMUP_TURNS + 5):
            rate.past_rates.append(100.0)
        rate.rate = 100.0
        return rate

    @patch("CurrencyRate.random.randint", return_value=0)
    def test_small_intervention_moves_rate_noticeably(self, _mock_randint):
        rate = self._build_stable_rate()
        prev = rate.get_rate()

        rate.change_rate(
            new_interest=3.0,
            inflation=2.0,
            trade_balance_ratio=0.0,
            gdp_growth=2.0,
            base_interest=3.0,
            base_inflation=2.0,
            base_trade_balance_ratio=0.0,
            base_gdp_growth=2.0,
            intervention_ratio=0.001,  # 0.001%相当の小さな介入
            avg_gdp_per_capita_usd=10000.0,
            base_gdp_per_capita_usd=10000.0,
        )

        change = (rate.get_rate() - prev) / prev
        self.assertGreater(change, 0.002)

    @patch("CurrencyRate.random.randint", return_value=0)
    def test_intervention_direction_is_reflected(self, _mock_randint):
        rate_plus = self._build_stable_rate()
        rate_minus = self._build_stable_rate()
        prev = rate_plus.get_rate()

        common_kwargs = dict(
            new_interest=3.0,
            inflation=2.0,
            trade_balance_ratio=0.0,
            gdp_growth=2.0,
            base_interest=3.0,
            base_inflation=2.0,
            base_trade_balance_ratio=0.0,
            base_gdp_growth=2.0,
            avg_gdp_per_capita_usd=10000.0,
            base_gdp_per_capita_usd=10000.0,
        )
        rate_plus.change_rate(intervention_ratio=0.001, **common_kwargs)
        rate_minus.change_rate(intervention_ratio=-0.001, **common_kwargs)

        plus_change = (rate_plus.get_rate() - prev) / prev
        minus_change = (rate_minus.get_rate() - prev) / prev
        self.assertGreater(plus_change, 0.0)
        self.assertLess(minus_change, 0.0)

    @patch("CurrencyRate.random.randint", return_value=1)
    def test_turn_change_stays_bounded_with_extreme_inputs(self, _mock_randint):
        rate = self._build_stable_rate()
        prev = rate.get_rate()

        rate.change_rate(
            new_interest=100.0,
            inflation=-25.0,
            trade_balance_ratio=1000.0,
            gdp_growth=80.0,
            base_interest=-10.0,
            base_inflation=40.0,
            base_trade_balance_ratio=-1000.0,
            base_gdp_growth=-20.0,
            intervention_ratio=50.0,
            avg_gdp_per_capita_usd=50000.0,
            base_gdp_per_capita_usd=1000.0,
        )

        change = abs((rate.get_rate() - prev) / prev)
        self.assertLessEqual(change, 0.04)


if __name__ == "__main__":
    unittest.main()
