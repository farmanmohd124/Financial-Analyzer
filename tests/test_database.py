import tempfile
import unittest
from pathlib import Path

from app.database import DocumentDatabase


class DocumentDatabaseTest(unittest.TestCase):
    def test_documents_survive_database_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "filingscope.db"
            first_process_database = DocumentDatabase(str(database_path))
            first_process_database.initialize()
            first_process_database.save_document(
                "document-1",
                "annual-report.pdf",
                "processing",
            )
            first_process_database.save_document(
                "document-1",
                "annual-report.pdf",
                "complete",
                result={"revenue": [{"period": "2024", "value": "123"}]},
            )

            restarted_database = DocumentDatabase(str(database_path))
            document = restarted_database.get_document("document-1")

            self.assertEqual(document["status"], "complete")
            self.assertEqual(document["result"]["revenue"][0]["value"], "123")
            self.assertEqual(len(restarted_database.list_documents()), 1)


if __name__ == "__main__":
    unittest.main()