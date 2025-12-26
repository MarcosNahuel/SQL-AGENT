#!/usr/bin/env python3
"""
SQL-Agent v2.5 - Verification Script
Validates that all critical imports and configurations are correct.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("SQL-Agent v2.5 - Final Verification")
    print("=" * 60)

    errors = []

    # Check 1: InsightStateV2 import
    print("\n[1/4] Checking InsightStateV2 import...")
    try:
        from app.schemas.agent_state import InsightStateV2, create_initial_state
        print("  [OK] InsightStateV2 imported successfully")

        # Verify it has messages field with add_messages
        state = create_initial_state(question="test", trace_id="test123")
        assert "messages" in state, "State missing 'messages' field"
        print("  [OK] InsightStateV2 has 'messages' field (memory enabled)")
    except Exception as e:
        errors.append(f"InsightStateV2: {e}")
        print(f"  [FAIL] {e}")

    # Check 2: Graph compilation
    print("\n[2/4] Checking graph compilation...")
    try:
        from app.graphs.insight_graph import build_insight_graph_v2, InsightState

        # Verify InsightState is InsightStateV2
        assert InsightState is InsightStateV2, "InsightState should be alias to InsightStateV2"
        print("  [OK] InsightState is correctly aliased to InsightStateV2")

        # Build graph without checkpointer
        graph = build_insight_graph_v2(checkpointer=None)
        print("  [OK] Graph compiled successfully")
    except Exception as e:
        errors.append(f"Graph: {e}")
        print(f"  [FAIL] {e}")

    # Check 3: IntentRouter with structured output
    print("\n[3/4] Checking IntentRouter...")
    try:
        from app.agents.intent_router import IntentRouter

        # Check that _route_with_llm uses structured output (code inspection)
        import inspect
        source = inspect.getsource(IntentRouter._route_with_llm)
        assert "with_structured_output" in source, "Missing with_structured_output"
        assert "json.loads" not in source or "# legacy" in source.lower(), "Contains legacy json.loads"
        print("  [OK] IntentRouter uses with_structured_output (no legacy parsing)")
    except Exception as e:
        errors.append(f"IntentRouter: {e}")
        print(f"  [FAIL] {e}")

    # Check 4: Database config
    print("\n[4/4] Checking database configuration...")
    try:
        # Read main.py and verify prepare_threshold
        main_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            main_content = f.read()

        assert "prepare_threshold" in main_content, "Missing prepare_threshold config"
        assert 'prepare_threshold": None' in main_content or "prepare_threshold=None" in main_content, \
            "prepare_threshold should be None"
        print("  [OK] Database pool has prepare_threshold=None (PgBouncer compatible)")
    except Exception as e:
        errors.append(f"Database: {e}")
        print(f"  [FAIL] {e}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"VERIFICATION FAILED - {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("VERIFICATION PASSED - All checks successful!")
        print("SQL-Agent v2.5 is ready for production.")
        sys.exit(0)

if __name__ == "__main__":
    main()
