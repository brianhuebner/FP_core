# tests/persistence/test_merge_keys.py — Verify MERGE key registry
import pytest

from domain.types import NodeLabel
from domain.ontology_recipe import merged_ontology
from persistence.merge_keys import MERGE_KEYS, validate_merge_keys


class TestMergeKeysCompleteness:
    def test_every_node_label_has_entry(self):
        for label in NodeLabel:
            assert label in MERGE_KEYS, (
                f"NodeLabel.{label.name} missing from MERGE_KEYS"
            )

    def test_count_matches_node_labels(self):
        assert len(MERGE_KEYS) == len(NodeLabel)


class TestMergeKeysAreRequiredProperties:
    def test_validate_merge_keys_passes(self):
        errors = validate_merge_keys()
        assert errors == [], f"Validation errors: {errors}"

    def test_keys_are_subsets_of_required(self):
        ontology = merged_ontology()
        for label, keys in MERGE_KEYS.items():
            if label == NodeLabel.REFERENCE:
                continue
            schema = ontology[label]
            required = schema.properties.required
            for key in keys:
                assert key in required, (
                    f"MERGE_KEYS[{label.name}] key '{key}' "
                    f"not in required: {sorted(required)}"
                )


class TestReferenceNodeKeys:
    def test_reference_has_empty_keys(self):
        assert MERGE_KEYS[NodeLabel.REFERENCE] == ()


class TestCoreAccountingKeys:
    def test_account_key(self):
        assert MERGE_KEYS[NodeLabel.ACCOUNT] == ("code",)

    def test_transaction_key(self):
        assert MERGE_KEYS[NodeLabel.TRANSACTION] == ("transaction_id",)

    def test_transaction_line_key(self):
        assert MERGE_KEYS[NodeLabel.TRANSACTION_LINE] == ("line_id",)

    def test_entity_key(self):
        assert MERGE_KEYS[NodeLabel.ENTITY] == ("entity_id",)

    def test_dimension_key(self):
        assert MERGE_KEYS[NodeLabel.ANALYTICAL_DIMENSION] == ("dimension_id",)

    def test_allocation_rule_key(self):
        assert MERGE_KEYS[NodeLabel.ALLOCATION_RULE] == ("rule_id",)

    def test_data_source_key(self):
        assert MERGE_KEYS[NodeLabel.DATA_SOURCE] == ("source_id",)


class TestRecipeScopedKeys:
    def test_source_schema_key(self):
        assert MERGE_KEYS[NodeLabel.SOURCE_SCHEMA] == ("recipe_id", "name")

    def test_column_key(self):
        assert MERGE_KEYS[NodeLabel.COLUMN] == ("recipe_id", "name")

    def test_measure_key(self):
        assert MERGE_KEYS[NodeLabel.MEASURE] == ("recipe_id", "name")

    def test_condition_key(self):
        assert MERGE_KEYS[NodeLabel.CONDITION] == ("recipe_id", "condition_id")

    def test_account_slot_key(self):
        assert MERGE_KEYS[NodeLabel.ACCOUNT_SLOT] == ("recipe_id", "slot_id")

    def test_mapping_rule_key(self):
        assert MERGE_KEYS[NodeLabel.MAPPING_RULE] == ("recipe_id", "rule_name")

    def test_accounting_recipe_key(self):
        assert MERGE_KEYS[NodeLabel.ACCOUNTING_RECIPE] == ("recipe_id",)

    def test_output_format_key(self):
        assert MERGE_KEYS[NodeLabel.OUTPUT_FORMAT] == ("recipe_id", "name")

    def test_output_column_key(self):
        assert MERGE_KEYS[NodeLabel.OUTPUT_COLUMN] == ("format_id", "name")

    def test_validation_rule_key(self):
        assert MERGE_KEYS[NodeLabel.VALIDATION_RULE] == ("format_id", "name")

    def test_batch_format_key(self):
        assert MERGE_KEYS[NodeLabel.BATCH_FORMAT] == ("recipe_id",)


class TestValidateMergeKeysDetectsErrors:
    def test_missing_label_detected(self):
        partial = {k: v for k, v in MERGE_KEYS.items() if k != NodeLabel.ACCOUNT}
        errors = validate_merge_keys(partial)
        assert any("ACCOUNT" in e for e in errors)

    def test_invalid_key_detected(self):
        bad_keys = dict(MERGE_KEYS)
        bad_keys[NodeLabel.ACCOUNT] = ("code", "nonexistent_field")
        errors = validate_merge_keys(bad_keys)
        assert any("nonexistent_field" in e for e in errors)
