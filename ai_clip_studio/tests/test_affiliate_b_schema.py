"""Phase 1 tests — AFFILIATE_PROJECT_V1 schema, gates, product rules.

Covers the hard rules:
- UNKNOWN authorization / unconfirmed rights refuse export (AFF008/9).
- No invented links/prices/claims: product fields are user facts only.
- Protected OCR tracks (labels/logos/attribution/watermarks) cannot be
  targeted for removal without approval (AFF020).
- Mirror (hflip) needs explicit approval (AFF021).
- JSON Schema cross-check agrees with the dataclass validator.
"""
from __future__ import annotations

import copy
import unittest

from ai_clip_studio.affiliate.product import (
    effective_disclosure,
    neutral_description,
    price_display,
    product_claim_findings,
    scan_for_claims,
)
from ai_clip_studio.affiliate.schema import (
    AffiliateProject,
    EditOperation,
    OcrTrack,
    ProductInfo,
    SourceAuthorization,
    SourceVideo,
    export_allowed,
    parse_project,
    project_snapshot_hash,
    validate_against_json_schema,
    validate_project,
)


def _base_project(**overrides):
    data = {
        "schema_version": "AFFILIATE_PROJECT_V1",
        "project_id": "aff_test_001",
        "product": {"product_name": "Hộp đựng đồ nhà bếp"},
        "authorization": {"authorization_type": "USER_OWNED",
                          "commercial_rights_confirmed": True},
    }
    data.update(overrides)
    return data


class TestSourceUrl(unittest.TestCase):
    """source_url is provenance only: recorded, validated, never fetched."""

    def test_source_url_round_trips(self):
        project = parse_project(_base_project(source_video={
            "file_name": "demo.mp4", "file_size_bytes": 10,
            "sha256": "a" * 64,
            "source_url": "https://example.com/share/video/123"}))
        self.assertEqual(project.source_video.source_url,
                         "https://example.com/share/video/123")
        again = parse_project(project.to_dict())
        self.assertEqual(again.source_video.source_url,
                         "https://example.com/share/video/123")

    def test_bad_source_url_rejected(self):
        codes = {i.code for i in validate_project(_base_project(
            source_video={"file_name": "demo.mp4", "file_size_bytes": 10,
                          "source_url": "not-a-url"}))}
        self.assertIn("AFF004", codes)

    def test_json_schema_accepts_source_url(self):
        project = parse_project(_base_project(source_video={
            "file_name": "demo.mp4", "file_size_bytes": 10,
            "source_url": "https://example.com/share/video/123"}))
        self.assertEqual(validate_against_json_schema(project.to_dict()), [])

    def test_link_only_source_cannot_export(self):
        # A recorded link with no uploaded file has no checksum, so
        # the export gate refuses even with confirmed authorization.
        project = parse_project(_base_project(source_video={
            "file_name": "(link only — no file uploaded)",
            "file_size_bytes": 0,
            "source_url": "https://example.com/share/video/123"}))
        allowed, reasons = export_allowed(project)
        self.assertFalse(allowed)
        self.assertTrue(any("checksum" in r for r in reasons))

    def test_gate_codes_do_not_block_parsing(self):
        # UNKNOWN/unconfirmed is a storable intermediate state: the
        # project must reload (only export refuses). Structural
        # errors still raise.
        from ai_clip_studio.affiliate.schema import AffiliateError
        project = parse_project(_base_project(authorization={
            "authorization_type": "UNKNOWN",
            "commercial_rights_confirmed": False}))
        self.assertEqual(project.authorization.authorization_type, "UNKNOWN")
        with self.assertRaises(AffiliateError):
            parse_project(_base_project(product={"product_name": ""}))

    def test_seller_authorized_confirmed_passes_auth_gate(self):
        # The confirmed value for the real-video test job (Mai, 09:34):
        # SELLER_AUTHORIZED + commercial-rights confirmation set.
        project = parse_project(_base_project(
            authorization={"authorization_type": "SELLER_AUTHORIZED",
                           "commercial_rights_confirmed": True,
                           "rights_note": "Người bán đã cho phép mình dùng"},
            source_video={"file_name": "demo.mp4", "file_size_bytes": 10,
                          "sha256": "a" * 64}))
        allowed, reasons = export_allowed(project)
        self.assertTrue(allowed, reasons)


class TestSchemaValidation(unittest.TestCase):
    def test_minimal_project_valid(self):
        self.assertEqual(validate_project(_base_project()), [])

    def test_unknown_authorization_blocks(self):
        data = _base_project(authorization={
            "authorization_type": "UNKNOWN",
            "commercial_rights_confirmed": False})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF008", codes)
        self.assertIn("AFF009", codes)

    def test_unconfirmed_rights_blocks(self):
        data = _base_project(authorization={
            "authorization_type": "LICENSED",
            "commercial_rights_confirmed": False})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF009", codes)
        self.assertNotIn("AFF008", codes)

    def test_bad_url_rejected(self):
        data = _base_project(product={
            "product_name": "X",
            "affiliate_url": "not-a-url"})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF004", codes)

    def test_bad_color_rejected(self):
        data = _base_project(product={
            "product_name": "X", "brand_color": "red"})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF005", codes)

    def test_affiliate_link_requires_disclosure(self):
        data = _base_project(product={
            "product_name": "X",
            "affiliate_url": "https://shopee.vn/aff/123"})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF019", codes)

    def test_negative_price_rejected(self):
        data = _base_project(product={
            "product_name": "X", "product_price": -5})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF006", codes)

    def test_duplicate_scene_ids_rejected(self):
        data = _base_project(video_analysis={"scenes": [
            {"scene_id": "S1", "start_time": 0, "end_time": 2},
            {"scene_id": "S1", "start_time": 2, "end_time": 4}]})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF010", codes)

    def test_bad_time_range_rejected(self):
        data = _base_project(video_analysis={"scenes": [
            {"scene_id": "S1", "start_time": 5, "end_time": 2}]})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF007", codes)

    def test_unknown_container_rejected(self):
        data = _base_project(source_video={
            "file_name": "x.avi", "file_size_bytes": 10,
            "container": "avi"})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF022", codes)

    def test_bad_checksum_rejected(self):
        data = _base_project(source_video={
            "file_name": "x.mp4", "file_size_bytes": 10,
            "sha256": "zzzz"})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF018", codes)

    def test_protected_track_removal_needs_approval(self):
        data = _base_project(
            ocr_tracks=[{"text_id": "T1", "original_text": "@creator",
                         "start_time": 0, "end_time": 2,
                         "text_classification": "CREATOR_ATTRIBUTION"}],
            edit_operations=[{"operation": "text_blur",
                              "target_track_id": "T1"}])
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF020", codes)

    def test_protected_track_with_approval_passes_gate(self):
        data = _base_project(
            ocr_tracks=[{"text_id": "T1", "original_text": "@creator",
                         "start_time": 0, "end_time": 2,
                         "text_classification": "CREATOR_ATTRIBUTION"}],
            edit_operations=[{"operation": "text_blur",
                              "target_track_id": "T1", "approved": True,
                              "approval_note": "owner approved"}])
        codes = {i.code for i in validate_project(data)}
        self.assertNotIn("AFF020", codes)

    def test_mirror_needs_approval(self):
        data = _base_project(edit_operations=[{"operation": "hflip"}])
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF021", codes)

    def test_unknown_edit_operation_rejected(self):
        data = _base_project(edit_operations=[{"operation": "deepfake"}])
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF016", codes)

    def test_dangling_track_reference_rejected(self):
        data = _base_project(edit_operations=[
            {"operation": "text_blur", "target_track_id": "NOPE"}])
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF011", codes)

    def test_subtitle_style_ranges(self):
        data = _base_project(subtitle_style={"font_size": 500})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF013", codes)

    def test_music_without_authorization_rejected(self):
        data = _base_project(audio_mix={"music_path": "/tmp/song.mp3",
                                        "music_authorized": False})
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF015", codes)

    def test_schema_version_mismatch(self):
        data = _base_project(schema_version="SOMETHING_ELSE")
        codes = {i.code for i in validate_project(data)}
        self.assertIn("AFF023", codes)

    def test_parse_round_trip(self):
        project = parse_project(_base_project())
        self.assertEqual(project.project_id, "aff_test_001")
        self.assertEqual(project.product.product_name, "Hộp đựng đồ nhà bếp")
        again = parse_project(project.to_dict())
        self.assertEqual(again.to_dict(), project.to_dict())

    def test_snapshot_hash_stable_and_sensitive(self):
        project = parse_project(_base_project())
        first = project_snapshot_hash(project)
        self.assertEqual(first, project_snapshot_hash(project))
        project.product.product_name = "Tên khác"
        self.assertNotEqual(first, project_snapshot_hash(project))

    def test_json_schema_agrees(self):
        project = parse_project(_base_project())
        self.assertEqual(validate_against_json_schema(project.to_dict()), [])
        bad = copy.deepcopy(project.to_dict())
        bad["authorization"]["authorization_type"] = "BOGUS"
        self.assertTrue(validate_against_json_schema(bad))


class TestExportGate(unittest.TestCase):
    def _project(self, **overrides):
        return parse_project(_base_project(**overrides))

    def test_gate_refuses_without_source(self):
        allowed, reasons = export_allowed(self._project())
        self.assertFalse(allowed)
        self.assertIn("no source video recorded", reasons)

    def test_gate_refuses_unknown_authorization(self):
        # UNKNOWN authorization cannot be parsed (AFF008); build a valid
        # project and downgrade it, as a user clearing confirmation would.
        project = self._project()
        project.authorization.authorization_type = "UNKNOWN"
        project.source_video = SourceVideo(
            file_name="x.mp4", file_size_bytes=10, sha256="a" * 64)
        allowed, reasons = export_allowed(project)
        self.assertFalse(allowed)
        self.assertTrue(any("UNKNOWN" in r for r in reasons))

    def test_gate_refuses_unapproved_script(self):
        from ai_clip_studio.affiliate.schema import AffiliateScript
        project = self._project()
        project.source_video = SourceVideo(
            file_name="x.mp4", file_size_bytes=10, sha256="a" * 64)
        project.script = AffiliateScript(variant="demonstration",
                                         target_seconds=30.0)
        allowed, reasons = export_allowed(project)
        self.assertFalse(allowed)
        self.assertTrue(any("not approved" in r for r in reasons))

    def test_gate_passes_when_everything_confirmed(self):
        from ai_clip_studio.affiliate.schema import AffiliateScript
        project = self._project()
        project.source_video = SourceVideo(
            file_name="x.mp4", file_size_bytes=10, sha256="a" * 64)
        project.script = AffiliateScript(variant="demonstration",
                                         target_seconds=30.0,
                                         approved=True,
                                         approved_by="Mai")
        allowed, reasons = export_allowed(project)
        self.assertTrue(allowed, reasons)


class TestProductRules(unittest.TestCase):
    def test_price_display_empty_when_missing(self):
        self.assertEqual(price_display(ProductInfo(product_name="X")), "")

    def test_price_display_formats_vnd(self):
        product = ProductInfo(product_name="X", product_price=129000)
        self.assertEqual(price_display(product), "129.000 VND")

    def test_neutral_description_uses_facts_only(self):
        product = ProductInfo(product_name="Hộp X", product_category="Nhà bếp")
        text = neutral_description(product, "mở hộp, xếp đồ vào")
        self.assertIn("Hộp X", text)
        self.assertIn("mở hộp, xếp đồ vào", text)
        self.assertNotIn("giảm giá", text)

    def test_default_disclosure_when_link_present(self):
        product = ProductInfo(product_name="X",
                              affiliate_url="https://shopee.vn/aff/1")
        disclosure = effective_disclosure(product)
        self.assertIn("tiếp thị liên kết", disclosure)

    def test_no_disclosure_when_no_link_and_blank(self):
        self.assertEqual(effective_disclosure(ProductInfo(product_name="X")), "")

    def test_claim_scanner_flags_medical_and_discount(self):
        findings = scan_for_claims("Sản phẩm chữa khỏi bệnh, giảm giá 50% hôm nay")
        kinds = [f["kind"] for f in findings]
        self.assertTrue(any("medical" in k for k in kinds))
        self.assertTrue(any("discount" in k for k in kinds))

    def test_claim_scanner_flags_testimonial(self):
        findings = scan_for_claims("Mình đã dùng sản phẩm này rất tốt")
        self.assertTrue(any("testimonial" in f["kind"] for f in findings))

    def test_product_claim_findings_cover_fields(self):
        product = ProductInfo(product_name="X",
                              product_benefits=["giảm cân nhanh chóng"])
        findings = product_claim_findings(product)
        self.assertTrue(any(f["field"] == "product_benefits" for f in findings))


if __name__ == "__main__":
    unittest.main()
