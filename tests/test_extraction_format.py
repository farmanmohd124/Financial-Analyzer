import unittest

from app.extraction import format_extracted_metrics


class FormatExtractedMetricsTest(unittest.TestCase):
    def test_formats_metric_labels_and_summary(self):
        payload = {
            "revenue": [{"period": "2024", "value": "391,035"}, {"period": "2023", "value": "383,285"}],
            "gross_profit": [{"period": "2024", "value": "180,683"}],
            "operating_income": [{"period": "2024", "value": "123,216"}],
            "profit": [{"period": "2024", "value": "93,736"}],
            "gross_margin": [],
            "operating_margin": [],
            "total_assets": [{"period": "2024", "value": "364,980"}],
            "total_liabilities": [{"period": "2024", "value": "308,030"}],
            "cash_and_equivalents": [{"period": "2024", "value": "29,943"}],
            "operating_cash_flow": [{"period": "2024", "value": "118,254"}],
            "free_cash_flow": [],
            "eps": [{"period": "2024", "value": "6.08"}],
            "sentiment": {"label": "neutral", "justification": "The filing is neutral."},
            "risk_factors": []
        }

        result = format_extracted_metrics(payload)

        self.assertEqual(result["revenue"][0]["label"], "Revenue")
        self.assertEqual(result["revenue"][0]["metric"], "revenue")
        self.assertIn("Revenue", result["summary"])
        self.assertIn("2024", result["summary"])
        self.assertEqual(result["eps"][0]["unit"], "reported currency per share")


if __name__ == "__main__":
    unittest.main()
