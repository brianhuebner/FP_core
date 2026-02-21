# domain/types_recipe.py — Recipe / Pipeline Domain Types
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from domain.types import SourceType


# ============================================================================
# RECIPE ENUMS
# ============================================================================

class ColumnDataType(Enum):
    STRING = "string"
    DECIMAL = "decimal"
    INTEGER = "integer"
    TIMESTAMP = "timestamp"
    DATE = "date"


class SemanticRole(Enum):
    IDENTIFIER = "identifier"
    DATE = "date"
    AMOUNT = "amount"
    CATEGORY = "category"
    DESCRIPTION = "description"


class AggregationOp(Enum):
    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVERAGE = "average"


class ConditionOp(Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    ALWAYS = "always"


class TransformOp(Enum):
    DIVIDE_BY_100 = "divide_by_100"
    DIVIDE_BY_1000 = "divide_by_1000"
    ABSOLUTE_VALUE = "absolute_value"
    NEGATE = "negate"


# ============================================================================
# RECIPE NODE DATACLASSES — All frozen/immutable
# ============================================================================

@dataclass(frozen=True)
class SourceSchema:
    recipe_id: str
    name: str
    source_system: SourceType
    file_pattern: Optional[str] = None
    row_grain: Optional[str] = None


@dataclass(frozen=True)
class Column:
    recipe_id: str
    name: str
    position: int
    data_type: ColumnDataType
    role: SemanticRole
    required: bool = True
    description: Optional[str] = None


@dataclass(frozen=True)
class Measure:
    recipe_id: str
    name: str
    operation: AggregationOp
    group_by: Tuple[str, ...] = ()
    split_by: Optional[str] = None
    split_column: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class Condition:
    recipe_id: str
    condition_id: str
    column: str
    operator: ConditionOp
    value: Optional[str] = None


@dataclass(frozen=True)
class AccountSlot:
    recipe_id: str
    slot_id: str
    role: str
    entry_type: str
    description: Optional[str] = None


@dataclass(frozen=True)
class MappingRule:
    recipe_id: str
    rule_name: str
    source_measure: str
    condition_operator: ConditionOp = ConditionOp.ALWAYS
    condition_value: Optional[str] = None
    memo_template: Optional[str] = None
    priority: int = 0
    split_by: Optional[str] = None
    sign_treatment: Optional[str] = None


@dataclass(frozen=True)
class AccountingRecipe:
    recipe_id: str
    name: str
    source_schema: str
    batch_key: Optional[str] = None
    journal_no_format: Optional[str] = None
    entries_per_file: Optional[int] = None
    visibility: str = "private"


@dataclass(frozen=True)
class OutputFormat:
    format_id: str
    name: str
    target_system: str
    file_format: str
    version: Optional[str] = None


@dataclass(frozen=True)
class OutputColumn:
    format_id: str
    name: str
    position: int
    data_type: ColumnDataType
    required: bool = True
    description: Optional[str] = None
    source_mapping: Optional[str] = None
    sign_convention: Optional[str] = None
    format_pattern: Optional[str] = None
    exclude_from_output: bool = False


@dataclass(frozen=True)
class ValidationRule:
    format_id: str
    name: str
    expression: str
    scope: str
    description: Optional[str] = None


@dataclass(frozen=True)
class EntryStructure:
    format_id: str
    entry_separator: str
    grouping_column: str
    date_column: str
    validation: Optional[str] = None
    description: Optional[str] = None
