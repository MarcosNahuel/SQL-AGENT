"""
Contract Tests

These tests verify that Pydantic schemas work correctly for:
1. Request/Response validation
2. Dashboard spec structure
3. Data payload integrity
4. Ref validation between spec and payload
"""

import pytest
from datetime import date, datetime
from typing import Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.dashboard import (
    DashboardSpec,
    SlotConfig,
    KpiCardConfig,
    ChartConfig,
    TableConfig,
    NarrativeConfig,
)
from app.schemas.payload import (
    DataPayload,
    KPIData,
    TimeSeriesData,
    TimeSeriesPoint,
    TopItemsData,
    TopItem,
    DatasetMeta,
)
from app.schemas.intent import QueryRequest, QueryPlan


class TestDashboardSpec:
    """Test DashboardSpec schema validation."""

    def test_valid_dashboard_spec(self):
        """Valid spec should be created successfully."""
        spec = DashboardSpec(
            title="Test Dashboard",
            subtitle="Test subtitle",
            slots=SlotConfig(
                filters=[],
                series=[
                    KpiCardConfig(
                        label="Total Sales",
                        value_ref="kpi.total_sales",
                        format="currency",
                    )
                ],
                charts=[
                    ChartConfig(
                        type="line_chart",
                        title="Sales Over Time",
                        dataset_ref="ts.sales_by_day",
                    )
                ],
                narrative=[
                    NarrativeConfig(type="summary", text="Sales are up 10%.")
                ],
            ),
        )
        assert spec.title == "Test Dashboard"
        assert len(spec.slots.series) == 1
        assert len(spec.slots.charts) == 1

    def test_kpi_card_formats(self):
        """KPI cards should accept valid formats."""
        for fmt in ["currency", "number", "percent"]:
            card = KpiCardConfig(
                label="Test",
                value_ref="kpi.test",
                format=fmt,
            )
            assert card.format == fmt

    def test_chart_types(self):
        """Charts should accept valid types."""
        for chart_type in ["line_chart", "bar_chart", "area_chart"]:
            chart = ChartConfig(
                type=chart_type,
                title="Test Chart",
                dataset_ref="ts.test",
            )
            assert chart.type == chart_type

    def test_table_config(self):
        """Table config should have columns."""
        table = TableConfig(
            title="Recent Orders",
            dataset_ref="table.recent_orders",
            columns=["id", "buyer", "amount"],
            max_rows=10,
        )
        assert len(table.columns) == 3
        assert table.max_rows == 10


class TestDataPayload:
    """Test DataPayload schema validation."""

    def test_empty_payload(self):
        """Empty payload should be valid."""
        payload = DataPayload(
            datasets_meta=[],
            available_refs=[],
        )
        assert payload.kpis is None
        assert payload.time_series is None

    def test_payload_with_kpis(self):
        """Payload with KPIs should work."""
        payload = DataPayload(
            kpis=KPIData(
                total_sales=100000.0,
                total_orders=50,
                avg_order_value=2000.0,
            ),
            datasets_meta=[
                DatasetMeta(
                    query_id="kpi_sales_summary",
                    row_count=1,
                    execution_time_ms=50.0,
                )
            ],
            available_refs=["kpi.total_sales", "kpi.total_orders"],
        )
        assert payload.kpis.total_sales == 100000.0
        assert len(payload.available_refs) == 2

    def test_payload_with_time_series(self):
        """Payload with time series should work."""
        payload = DataPayload(
            time_series=[
                TimeSeriesData(
                    series_name="sales_by_day",
                    points=[
                        TimeSeriesPoint(date="2024-12-01", value=10000.0),
                        TimeSeriesPoint(date="2024-12-02", value=15000.0),
                    ],
                )
            ],
            datasets_meta=[],
            available_refs=["ts.sales_by_day"],
        )
        assert len(payload.time_series) == 1
        assert len(payload.time_series[0].points) == 2

    def test_payload_with_top_items(self):
        """Payload with rankings should work."""
        payload = DataPayload(
            top_items=[
                TopItemsData(
                    ranking_name="products_by_revenue",
                    items=[
                        TopItem(rank=1, id="P001", title="Product A", value=50000.0),
                        TopItem(rank=2, id="P002", title="Product B", value=30000.0),
                    ],
                    metric="revenue",
                )
            ],
            datasets_meta=[],
            available_refs=["top.products_by_revenue"],
        )
        assert len(payload.top_items) == 1
        assert payload.top_items[0].items[0].rank == 1


class TestRefValidation:
    """Test that spec refs match payload available_refs."""

    def test_all_refs_available(self):
        """All refs in spec should exist in payload."""
        spec = DashboardSpec(
            title="Test",
            slots=SlotConfig(
                series=[
                    KpiCardConfig(
                        label="Sales",
                        value_ref="kpi.total_sales",
                        format="currency",
                    )
                ],
                charts=[
                    ChartConfig(
                        type="line_chart",
                        title="Trend",
                        dataset_ref="ts.sales_by_day",
                    )
                ],
            ),
        )

        payload = DataPayload(
            kpis=KPIData(total_sales=100000.0),
            time_series=[
                TimeSeriesData(series_name="sales_by_day", points=[])
            ],
            datasets_meta=[],
            available_refs=["kpi.total_sales", "ts.sales_by_day"],
        )

        # Extract refs from spec
        spec_refs = []
        for kpi in spec.slots.series:
            spec_refs.append(kpi.value_ref)
            if kpi.delta_ref:
                spec_refs.append(kpi.delta_ref)
        for chart in spec.slots.charts:
            spec_refs.append(chart.dataset_ref)

        # Validate all refs exist
        for ref in spec_refs:
            assert ref in payload.available_refs, f"Ref {ref} not in payload"

    def test_missing_ref_detectable(self):
        """Missing refs should be detectable."""
        spec_refs = ["kpi.total_sales", "ts.nonexistent"]
        available_refs = ["kpi.total_sales", "ts.sales_by_day"]

        missing = [ref for ref in spec_refs if ref not in available_refs]
        assert "ts.nonexistent" in missing


class TestQueryRequest:
    """Test QueryRequest schema."""

    def test_minimal_request(self):
        """Minimal request with just question."""
        req = QueryRequest(question="How are sales?")
        assert req.question == "How are sales?"
        assert req.date_from is None

    def test_request_with_dates(self):
        """Request with date range."""
        req = QueryRequest(
            question="Sales this month",
            date_from=date(2024, 12, 1),
            date_to=date(2024, 12, 31),
        )
        assert req.date_from == date(2024, 12, 1)

    def test_request_with_filters(self):
        """Request with custom filters."""
        req = QueryRequest(
            question="Sales by channel",
            filters={"channel": "mercadolibre"},
        )
        assert req.filters["channel"] == "mercadolibre"


class TestQueryPlan:
    """Test QueryPlan schema."""

    def test_simple_plan(self):
        """Simple plan with query IDs."""
        plan = QueryPlan(
            query_ids=["kpi_sales_summary", "recent_orders"],
            params={},
        )
        assert len(plan.query_ids) == 2

    def test_plan_with_params(self):
        """Plan with parameters."""
        plan = QueryPlan(
            query_ids=["kpi_sales_summary"],
            params={"date_from": "2024-12-01", "date_to": "2024-12-31"},
        )
        assert plan.params["date_from"] == "2024-12-01"


class TestDatasetMeta:
    """Test DatasetMeta schema."""

    def test_meta_creation(self):
        """Meta should capture execution details."""
        meta = DatasetMeta(
            query_id="kpi_sales_summary",
            row_count=1,
            execution_time_ms=123.45,
        )
        assert meta.query_id == "kpi_sales_summary"
        assert meta.row_count == 1
        assert meta.execution_time_ms == 123.45
        assert meta.executed_at is not None


class TestKPIData:
    """Test KPIData schema with dynamic fields."""

    def test_standard_kpis(self):
        """Standard KPI fields should work."""
        kpi = KPIData(
            total_sales=100000.0,
            total_orders=50,
            avg_order_value=2000.0,
            total_units=100,
        )
        assert kpi.total_sales == 100000.0

    def test_ai_kpis(self):
        """AI interaction KPIs should work."""
        kpi = KPIData(
            total_interactions=1000,
            escalated_count=50,
            escalation_rate=5.0,
            auto_responded=950,
        )
        assert kpi.escalation_rate == 5.0

    def test_extra_fields_allowed(self):
        """Extra fields should be allowed (extra='allow')."""
        kpi = KPIData(
            total_sales=100000.0,
            custom_metric=42,  # Extra field
        )
        assert hasattr(kpi, "custom_metric")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
