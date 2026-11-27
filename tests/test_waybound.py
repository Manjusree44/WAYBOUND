"""Automated tests for WAYBOUND data storage, discovery, recommendations, and verification."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import discovery
import storage
import verify_data


class WayboundDiscoveryTests(unittest.TestCase):
    def test_step1_to_3_counts(self) -> None:
        places = discovery.load_destinations()
        safe = discovery.safe_places(places)
        self.assertEqual(len(places), 45)
        self.assertEqual(len(safe), 13)
        self.assertEqual(len(discovery.filter_places(places, state="Telangana")), 21)
        self.assertEqual(len(discovery.filter_places(safe, state="Telangana")), 7)
        self.assertEqual(len(discovery.load_food()), 15)
        self.assertEqual(len(discovery.load_crafts()), 20)
        self.assertEqual(len(discovery.load_experiences()), 13)
        self.assertEqual(len(discovery.load_gi_products()), 40)
        self.assertEqual(len(discovery.load_media_assets()), 12)
        self.assertEqual(len(discovery.load_sources_reference()), 319)

    def test_filtering_and_search(self) -> None:
        hyderabad_foods = discovery.filter_food(discovery.load_food(), district="Hyderabad", gi_only=True)
        self.assertTrue(any(f["food_id"] == "FOD-TG-0001" for f in hyderabad_foods))

        results = discovery.search_all("Pembarthi", safe_only=True)
        self.assertEqual([d["destination_id"] for d in results["destinations"]], ["DST-TG-0001"])
        self.assertEqual([c["craft_id"] for c in results["crafts"]], ["CRF-TG-0001"])
        self.assertEqual([e["experience_id"] for e in results["experiences"]], ["CEX-TG-0001"])

    def test_relationships_and_nearby_recommendations(self) -> None:
        related = discovery.things_at("DST-TG-0001")
        self.assertEqual(len(related["crafts"]), 1)
        self.assertEqual(len(related["experiences"]), 1)
        self.assertGreaterEqual(len(related["gi_products"]), 1)
        self.assertGreaterEqual(len(related["sources"]), 1)
        self.assertGreaterEqual(len(related["statewide_food"]), 1)

        recs = discovery.recommend_nearby("DST-TG-0001", radius_km=120, limit=5, safe_only=True)
        self.assertTrue(len(recs) >= 1)
        self.assertTrue(all(r["destination_id"] != "DST-TG-0001" for r in recs))
        self.assertEqual(recs, sorted(recs, key=lambda r: r["distance_km"]))

        border_recs = discovery.recommend_nearby(
            "DST-AP-0004", radius_km=150, limit=5, safe_only=True, same_state_only=True
        )
        self.assertTrue(len(border_recs) >= 1)

        details = discovery.get_destination_details("DST-TG-0001")
        self.assertIsNotNone(details)
        self.assertEqual(details["destination"]["name"], "Pembarthi")

    def test_json_and_sqlite_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            json_files = storage.export_json(data_dir="data", out_dir=tmp_path / "json")
            self.assertIn("bundle", json_files)
            bundle = json.loads((tmp_path / "json" / "waybound_data.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle["counts"]["destinations"], 45)
            self.assertEqual(bundle["counts"]["food"], 15)

            db_path = storage.build_sqlite(data_dir="data", db_path=tmp_path / "waybound.db")
            conn = storage.get_connection(db_path)
            try:
                safe_count = conn.execute(
                    "SELECT COUNT(*) FROM destinations "
                    "WHERE record_kind = 'point_destination' "
                    "AND verification_status = 'verified_official_source'"
                ).fetchone()[0]
                self.assertEqual(safe_count, 13)
                joined = conn.execute(
                    "SELECT c.craft_name FROM crafts c "
                    "JOIN destinations d ON c.destination_id = d.destination_id "
                    "WHERE d.destination_id = 'DST-TG-0001'"
                ).fetchall()
                self.assertEqual(len(joined), 1)
            finally:
                conn.close()

    def test_verification_audit_passes(self) -> None:
        report = verify_data.verify_all(data_dir="data", write_report=False)
        self.assertTrue(report["all_checks_passed"], msg=str(report))
        self.assertEqual(report["counts"]["destinations_safe"], 13)


if __name__ == "__main__":
    unittest.main()
