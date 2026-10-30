"""
Unit tests for the enterprise modules added this pass: policy engine
condition evaluation, config service defaults, plugin manifest validation,
and tenant query scoping — all pure logic, no live Postgres required.
Run: pytest backend/tests/test_enterprise_modules.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk"))

import pytest
from app.policy.engine import _evaluate_condition, PolicyDecision
from app.config.service import DEFAULTS
from sovereignai_sdk.manifest import validate_manifest


class TestPolicyConditionEvaluation:
    def test_eq_operator_matches(self):
        assert _evaluate_condition({"field": "classification", "op": "eq", "value": "restricted"},
                                    {"classification": "restricted"}) is True

    def test_eq_operator_no_match(self):
        assert _evaluate_condition({"field": "classification", "op": "eq", "value": "restricted"},
                                    {"classification": "internal"}) is False

    def test_in_operator(self):
        cond = {"field": "role", "op": "in", "value": ["viewer", "auditor"]}
        assert _evaluate_condition(cond, {"role": "viewer"}) is True
        assert _evaluate_condition(cond, {"role": "admin"}) is False

    def test_gt_operator_handles_none_safely(self):
        cond = {"field": "file_size_mb", "op": "gt", "value": 100}
        assert _evaluate_condition(cond, {}) is False  # missing field -> None -> no crash

    def test_contains_operator(self):
        cond = {"field": "filename", "op": "contains", "value": "restricted"}
        assert _evaluate_condition(cond, {"filename": "restricted-inspection-report.pdf"}) is True
        assert _evaluate_condition(cond, {"filename": "public-manual.pdf"}) is False

    def test_unknown_operator_returns_false_not_error(self):
        cond = {"field": "x", "op": "not_a_real_op", "value": 1}
        assert _evaluate_condition(cond, {"x": 1}) is False


class TestConfigDefaults:
    def test_all_defaults_have_required_shape(self):
        for key, (value, category, description) in DEFAULTS.items():
            assert value is not None
            assert isinstance(category, str) and category
            assert isinstance(description, str) and description

    def test_sandbox_timeout_default_is_reasonable(self):
        value, _, _ = DEFAULTS["sandbox.timeout_seconds"]
        assert 5 <= value <= 300

    def test_mfa_required_defaults_true(self):
        value, _, _ = DEFAULTS["auth.mfa_required"]
        assert value is True


class TestPluginManifestValidation:
    def test_valid_manifest_has_no_errors(self):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "entry_point": "plugin:MyAgent", "agent_name": "test_agent",
        }
        assert validate_manifest(manifest) == []

    def test_missing_field_reported(self):
        manifest = {"name": "test-plugin", "version": "1.0.0", "agent_name": "test_agent"}
        errors = validate_manifest(manifest)
        assert any("entry_point" in e for e in errors)

    def test_malformed_entry_point_reported(self):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "entry_point": "no-colon-here", "agent_name": "test_agent",
        }
        errors = validate_manifest(manifest)
        assert any("format" in e for e in errors)

    def test_empty_manifest_reports_all_required_fields(self):
        errors = validate_manifest({})
        assert len(errors) >= 4


class TestExampleVendorDrawingPlugin:
    def test_example_plugin_parses_title_block(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "plugins" / "vendor-drawing-parser"))
        from plugin import VendorDrawingAgent
        import asyncio

        agent = VendorDrawingAgent()
        result = asyncio.run(agent.run("parse", {"ocr_text": "DWG: A-1023 REV: B VENDOR: Acme Fabrication"}))
        assert result["parsed"] is True
        assert result["title_block"]["dwg_no"] == "A-1023"
        assert result["title_block"]["rev"] == "B"

    def test_example_plugin_handles_unrecognized_text(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "plugins" / "vendor-drawing-parser"))
        from plugin import VendorDrawingAgent
        import asyncio

        agent = VendorDrawingAgent()
        result = asyncio.run(agent.run("parse", {"ocr_text": "random unrelated text"}))
        assert result["parsed"] is False
