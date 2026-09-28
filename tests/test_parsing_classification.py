import unittest

from app.parsing import has_financial_statement_sections


class FinancialSectionDetectionTest(unittest.TestCase):
    def test_skips_classifier_for_parsed_financial_statement(self):
        sections = {"item_8": "Financial statement content " * 30}

        self.assertTrue(has_financial_statement_sections(sections))

    def test_keeps_classifier_fallback_for_unstructured_document(self):
        sections = {"full_document": "Unstructured filing text " * 30}

        self.assertFalse(has_financial_statement_sections(sections))


if __name__ == "__main__":
    unittest.main()