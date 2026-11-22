"""Offline tests for the deterministic logic. No AI model is needed:  python3 -m unittest discover -s tests"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.clients = app.load_clients()
        self.products = {p["id"]: p for p in app.load_products()}

    def test_minimum_content(self):
        self.assertGreaterEqual(len(self.clients), 2)
        self.assertGreaterEqual(len(self.products), 3)

    def test_products_have_features_and_limitations(self):
        for p in self.products.values():
            self.assertTrue(p["features"] and p["limitations"], p["id"])

    def test_clients_reference_real_products_and_have_hidden_info(self):
        for c in self.clients.values():
            self.assertTrue(c["hidden_information"], c["id"])
            for pid in c["suitable_product_ids"] + c["unsuitable_product_ids"]:
                self.assertIn(pid, self.products, f"{c['id']} -> {pid}")
            self.assertFalse(set(c["suitable_product_ids"]) & set(c["unsuitable_product_ids"]))

    def test_public_profile_never_contains_hidden_details(self):
        for c in self.clients.values():
            public = json.dumps(c["public_profile"])
            for h in c["hidden_information"]:
                self.assertNotIn(h["detail"], public)

    def test_prompt_templates_fill(self):
        pr = app.load_prompts()
        pr["client_system"].format(profile="p", personality="x", hidden="h")
        self.assertIn("What went well", pr["coach_system"])


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.fatima = app.load_clients()["fatima"]
        self.products = app.load_products()

    def test_technique_counts_open_and_closed(self):
        h = [{"role": "student", "content": "Hello, thanks for coming. Can you tell me about your business?"},
             {"role": "client", "content": "Sure."},
             {"role": "student", "content": "Do you have any loans?"},
             {"role": "student", "content": "Who are your customers and how fast do they pay?"}]
        t = app.question_technique(h)
        self.assertEqual((t["open"], t["closed"], t["total"]), (2, 1, 3))

    def test_product_verdicts(self):
        recs = "1) Business Murabaha Finance 2) Invoice Finance 3) Platinum Travel Credit Card"
        v = {x["id"]: x["verdict"] for x in app.product_verdicts(self.fatima, recs, self.products)}
        self.assertEqual(v["sme-murabaha-finance"], "suitable")
        self.assertEqual(v["invoice-finance"], "unsuitable")
        self.assertEqual(v["premium-credit-card"], "unsuitable")

    def test_unsuitable_warnings_name_the_product(self):
        w = app.unsuitable_warnings(self.fatima, "I recommend the Business Working Capital Line", self.products)
        self.assertEqual(len(w), 1)
        self.assertIn("Working Capital", w[0])

    def test_no_warning_for_suitable_product(self):
        self.assertEqual(app.unsuitable_warnings(self.fatima, "Business Murabaha Finance", self.products), [])


class GatingTests(unittest.TestCase):
    """The unlock step is the leak barrier: with the model stubbed, only unlocked facts reach the client prompt."""

    def setUp(self):
        app._unlock_cache.clear()
        self.fatima = app.load_clients()["fatima"]

    def _system_prompt(self, unlocked):
        captured = {}

        def fake(messages, temperature=0.7):
            captured["system"] = messages[0]["content"]
            return "ok"

        with mock.patch.object(app, "chat_completion", side_effect=fake):
            app.client_reply(self.fatima, [{"role": "student", "content": "Hi"}], unlocked=unlocked)
        return captured["system"]

    def test_locked_facts_are_not_in_client_prompt(self):
        prompt = self._system_prompt([])
        for h in self.fatima["hidden_information"]:
            self.assertNotIn(h["detail"], prompt)

    def test_unlocked_fact_is_in_client_prompt_and_others_are_not(self):
        items = self.fatima["hidden_information"]
        prompt = self._system_prompt([items[1]])
        self.assertIn(items[1]["detail"], prompt)
        self.assertNotIn(items[0]["detail"], prompt)

    def test_unlock_parsing_ignores_out_of_range_numbers(self):
        with mock.patch.object(app, "chat_completion", return_value="2, 99, 0"):
            self.assertEqual(app._topics_for_question(self.fatima, "q1"), [2])

    def test_none_unlocks_nothing(self):
        with mock.patch.object(app, "chat_completion", return_value="NONE"):
            self.assertEqual(app.unlocked_items(self.fatima, [{"role": "student", "content": "Hello"}]), [])


if __name__ == "__main__":
    unittest.main()
