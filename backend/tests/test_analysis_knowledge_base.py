import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from flask import Flask
    from extensions import db
    from app.logfile.models.model import AnalysisKnowledgeCase, QueryRecord
except ModuleNotFoundError as exc:
    Flask = None
    db = None
    AnalysisKnowledgeCase = None
    QueryRecord = None
    MISSING_DEPENDENCY = exc
else:
    MISSING_DEPENDENCY = None


@unittest.skipIf(MISSING_DEPENDENCY is not None, f"backend dependencies missing: {MISSING_DEPENDENCY}")
class AnalysisKnowledgeBaseTests(unittest.TestCase):
    def test_query_record_module_id_references_modules_table(self):
        foreign_keys = list(QueryRecord.__table__.c.module_id.foreign_keys)

        self.assertEqual(len(foreign_keys), 1)
        self.assertEqual(foreign_keys[0].target_fullname, "modules.id")

    def test_knowledge_case_has_reuse_and_conclusion_fields(self):
        columns = AnalysisKnowledgeCase.__table__.c

        self.assertIn("error_fingerprint", columns)
        self.assertIn("issue_category", columns)
        self.assertIn("conclusion_summary", columns)
        self.assertIn("root_cause", columns)
        self.assertIn("solution", columns)
        self.assertIn("confidence", columns)
        self.assertIn("hit_count", columns)

    def test_models_can_create_query_record_and_knowledge_case(self):
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
        with app.app_context():
            from app.modules.models.model import Module
            from app.product.models.model import Product

            db.create_all()
            product = Product(name="pal")
            module = Module(name="pal-quality-inspection")
            db.session.add_all([product, module])
            db.session.commit()

            case = AnalysisKnowledgeCase(
                product_id=product.id,
                module_id=module.id,
                error_fingerprint="fp-1",
                error_type="ConnectionResetError",
                error_message="Connection reset by peer",
                issue_category="network_issue",
                conclusion_summary="Redis connection was reset.",
                root_cause="Broker connection reset.",
                solution="Check Redis/network keepalive.",
                confidence=0.86,
            )
            db.session.add(case)
            db.session.commit()

            record = QueryRecord(
                product_id=product.id,
                module_id=module.id,
                log_file_path="/data/upload/demo.log",
                branch_url="https://code/repo.git",
                branch_version="master",
                answer=0,
                status="success",
                error_fingerprint="fp-1",
                hit_cache=True,
                knowledge_case_id=case.id,
            )
            db.session.add(record)
            db.session.commit()

            self.assertEqual(QueryRecord.query.count(), 1)
            self.assertEqual(AnalysisKnowledgeCase.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
