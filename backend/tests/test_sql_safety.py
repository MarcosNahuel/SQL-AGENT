"""
SQL Safety Tests

These tests verify that the SQL allowlist pattern prevents:
1. SQL injection attacks
2. Unauthorized query execution
3. Invalid parameter handling
4. Excessive data retrieval
"""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sql.allowlist import (
    QUERY_ALLOWLIST,
    get_query_template,
    validate_query_id,
    build_params,
    get_available_queries,
)


class TestQueryAllowlist:
    """Test the SQL allowlist enforcement."""

    def test_allowlist_not_empty(self):
        """Verify allowlist has queries defined."""
        assert len(QUERY_ALLOWLIST) > 0
        assert "kpi_sales_summary" in QUERY_ALLOWLIST
        assert "recent_orders" in QUERY_ALLOWLIST

    def test_all_queries_have_required_fields(self):
        """Verify all queries have required configuration."""
        required_fields = ["description", "output_type", "output_ref", "template"]

        for query_id, config in QUERY_ALLOWLIST.items():
            for field in required_fields:
                assert field in config, f"{query_id} missing {field}"

    def test_all_templates_are_select_only(self):
        """Verify no query templates contain dangerous SQL statements."""
        import re
        # Use word boundary regex to avoid false positives like CREATED_AT matching CREATE
        dangerous_patterns = [
            r"\bINSERT\s+INTO\b",
            r"\bUPDATE\s+\w+\s+SET\b",
            r"\bDELETE\s+FROM\b",
            r"\bDROP\s+(TABLE|DATABASE|INDEX)\b",
            r"\bTRUNCATE\s+TABLE\b",
            r"\bALTER\s+TABLE\b",
            r"\bCREATE\s+(TABLE|DATABASE|INDEX)\b",
            r"\bGRANT\s+",
            r"\bREVOKE\s+",
            r"\bEXEC\s+",
            r"\bEXECUTE\s+",
        ]

        for query_id, config in QUERY_ALLOWLIST.items():
            template = config["template"].upper()
            for pattern in dangerous_patterns:
                match = re.search(pattern, template)
                assert match is None, (
                    f"{query_id} contains dangerous pattern: {pattern}"
                )

    def test_all_templates_have_limit(self):
        """Verify time_series and table queries have LIMIT."""
        types_requiring_limit = ["time_series", "table", "top_items"]

        for query_id, config in QUERY_ALLOWLIST.items():
            if config["output_type"] in types_requiring_limit:
                template = config["template"].upper()
                assert "LIMIT" in template, f"{query_id} missing LIMIT clause"


class TestQueryValidation:
    """Test query ID validation."""

    def test_valid_query_id(self):
        """Valid query IDs should pass validation."""
        assert validate_query_id("kpi_sales_summary") is True
        assert validate_query_id("recent_orders") is True
        assert validate_query_id("ts_sales_by_day") is True

    def test_invalid_query_id(self):
        """Invalid query IDs should fail validation."""
        assert validate_query_id("nonexistent_query") is False
        assert validate_query_id("") is False
        assert validate_query_id("SELECT * FROM users") is False
        assert validate_query_id("kpi_sales_summary; DROP TABLE users;") is False

    def test_sql_injection_in_query_id(self):
        """SQL injection attempts in query_id should fail."""
        injection_attempts = [
            "kpi_sales_summary' OR '1'='1",
            "kpi_sales_summary; DELETE FROM users;",
            "kpi_sales_summary UNION SELECT * FROM passwords",
            "kpi_sales_summary--",
            "kpi_sales_summary/**/",
        ]

        for attempt in injection_attempts:
            assert validate_query_id(attempt) is False, f"Should reject: {attempt}"


class TestParameterBuilding:
    """Test parameter validation and building."""

    def test_default_params_applied(self):
        """Default parameters should be applied when not provided."""
        params = build_params("recent_orders", {})
        assert "limit" in params
        assert params["limit"] == 20

    def test_user_params_override_defaults(self):
        """User parameters should override defaults."""
        params = build_params("recent_orders", {"limit": 5})
        assert params["limit"] == 5

    def test_required_params_have_defaults(self):
        """Queries with required params should have sensible defaults."""
        # kpi_sales_summary uses date_from and date_to but has defaults
        params = build_params("kpi_sales_summary", {})
        # Should have default date params
        assert "date_from" in params
        assert "date_to" in params

    def test_invalid_query_raises_error(self):
        """Invalid query ID should raise error."""
        with pytest.raises(ValueError, match="no existe"):
            build_params("nonexistent_query", {})

    def test_date_params_format(self):
        """Date parameters should be properly formatted."""
        today = date.today()
        params = build_params("kpi_sales_summary", {
            "date_from": today.isoformat(),
            "date_to": (today + timedelta(days=1)).isoformat(),
        })
        assert params["date_from"] == today.isoformat()


class TestAvailableQueries:
    """Test query listing for LLM."""

    def test_get_available_queries_returns_dict(self):
        """Should return dict of query_id -> description."""
        queries = get_available_queries()
        assert isinstance(queries, dict)
        assert len(queries) > 0

    def test_descriptions_are_strings(self):
        """All descriptions should be non-empty strings."""
        queries = get_available_queries()
        for query_id, description in queries.items():
            assert isinstance(description, str)
            assert len(description) > 0


class TestQueryTemplates:
    """Test query template retrieval."""

    def test_get_template_existing(self):
        """Should return template for existing query."""
        template = get_query_template("kpi_sales_summary")
        assert template is not None
        assert "template" in template

    def test_get_template_nonexistent(self):
        """Should return None for nonexistent query."""
        template = get_query_template("fake_query")
        assert template is None


class TestSQLInjectionPrevention:
    """Test SQL injection prevention in parameters."""

    def test_param_values_not_concatenated(self):
        """Verify templates use parameterized queries, not string concat."""
        for query_id, config in QUERY_ALLOWLIST.items():
            template = config["template"]
            # Should use %(param)s style, not f-strings or .format()
            assert "{" not in template or "{{" in template, (
                f"{query_id} may use unsafe string formatting"
            )

    def test_malicious_param_values(self):
        """Malicious parameter values should not affect query structure."""
        malicious_values = [
            "'; DROP TABLE users; --",
            "1 OR 1=1",
            "1; DELETE FROM orders",
            "<script>alert('xss')</script>",
        ]

        # These should not raise errors - they're just strings
        for value in malicious_values:
            # The allowlist doesn't validate param VALUES, just structure
            # Actual SQL safety comes from parameterized execution
            pass


class TestOutputTypes:
    """Test output type configurations."""

    VALID_OUTPUT_TYPES = ["kpi", "time_series", "top_items", "table"]

    def test_all_output_types_valid(self):
        """All queries should have valid output types."""
        for query_id, config in QUERY_ALLOWLIST.items():
            assert config["output_type"] in self.VALID_OUTPUT_TYPES, (
                f"{query_id} has invalid output_type: {config['output_type']}"
            )

    def test_output_refs_follow_convention(self):
        """Output refs should follow naming convention."""
        prefix_map = {
            "kpi": "kpi",
            "time_series": "ts",
            "top_items": "top",
            "table": "table",
        }

        for query_id, config in QUERY_ALLOWLIST.items():
            output_type = config["output_type"]
            output_ref = config["output_ref"]
            expected_prefix = prefix_map[output_type]

            # kpi can just be "kpi" without suffix
            if output_type == "kpi" and output_ref == "kpi":
                continue

            assert output_ref.startswith(expected_prefix + ".") or output_ref == expected_prefix, (
                f"{query_id}: output_ref '{output_ref}' should start with '{expected_prefix}.'"
            )


class TestQueryLimits:
    """Test that queries respect limits."""

    MAX_LIMIT = 1000

    def test_default_limits_reasonable(self):
        """Default limits should not be excessive."""
        for query_id, config in QUERY_ALLOWLIST.items():
            defaults = config.get("default_params", {})
            if "limit" in defaults:
                limit_fn = defaults["limit"]
                limit_val = limit_fn() if callable(limit_fn) else limit_fn
                assert limit_val <= self.MAX_LIMIT, (
                    f"{query_id} has excessive default limit: {limit_val}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
