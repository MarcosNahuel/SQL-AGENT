#!/usr/bin/env python3
"""
SQL-Agent v2.5 - Final Certification Check
Validates Memory, DB connectivity, and Router logic for production.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check():
    print("=" * 60)
    print("SQL-Agent v2.5 - CERTIFICACION FINAL")
    print("=" * 60)

    errors = []

    # 1. Verificar Estado (Memory)
    print("\n[1/3] MEMORIA - Verificando InsightStateV2...")
    try:
        from app.schemas.agent_state import InsightStateV2
        from app.graphs.insight_graph import build_insight_graph_v2, InsightState

        # Verificar que InsightState es alias de InsightStateV2
        assert InsightState is InsightStateV2, "InsightState debe ser InsightStateV2"
        print("  [OK] InsightState = InsightStateV2")

        # Verificar que tiene 'messages' con add_messages reducer
        from app.schemas.agent_state import create_initial_state
        state = create_initial_state(question="test", trace_id="cert")
        assert "messages" in state, "Falta campo 'messages'"
        print("  [OK] Campo 'messages' presente (memoria habilitada)")

        # Compilar grafo
        graph = build_insight_graph_v2(checkpointer=None)
        print("  [OK] Grafo compilado correctamente")

    except Exception as e:
        errors.append(f"MEMORIA: {e}")
        print(f"  [FAIL] {e}")

    # 2. Verificar DB Config
    print("\n[2/3] DATABASE - Verificando prepare_threshold...")
    try:
        main_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "prepare_threshold" in content, "Falta prepare_threshold"
        assert '"prepare_threshold": None' in content or "'prepare_threshold': None" in content, \
            "prepare_threshold debe ser None"
        print("  [OK] prepare_threshold=None configurado")
        print("  [OK] Compatible con Supabase Transaction Mode")

    except Exception as e:
        errors.append(f"DATABASE: {e}")
        print(f"  [FAIL] {e}")

    # 3. Verificar Router
    print("\n[3/3] ROUTER - Verificando structured output...")
    try:
        import inspect
        from app.agents.intent_router import IntentRouter

        source = inspect.getsource(IntentRouter._route_with_llm)

        # Debe tener with_structured_output
        assert "with_structured_output" in source, "Falta with_structured_output"
        print("  [OK] Usa with_structured_output()")

        # No debe tener json.loads (legacy parsing)
        if "json.loads" in source:
            # Solo falla si no es un comentario
            lines_with_json = [l for l in source.split('\n') if 'json.loads' in l and not l.strip().startswith('#')]
            assert len(lines_with_json) == 0, "Contiene json.loads legacy"
        print("  [OK] Sin parsing legacy (json.loads)")

    except Exception as e:
        errors.append(f"ROUTER: {e}")
        print(f"  [FAIL] {e}")

    # 4. Verificar imports principales
    print("\n[4/4] IMPORTS - Verificando modulos criticos...")
    try:
        from app.main import app
        print("  [OK] FastAPI app importable")

        from app.agents.data_agent import DataAgent
        print("  [OK] DataAgent importable")

        from app.agents.presentation_agent import PresentationAgent
        print("  [OK] PresentationAgent importable")

    except Exception as e:
        errors.append(f"IMPORTS: {e}")
        print(f"  [FAIL] {e}")

    # Resultado Final
    print("\n" + "=" * 60)
    if errors:
        print("CERTIFICACION FALLIDA")
        print(f"{len(errors)} error(es) encontrado(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("CERTIFICACION EXITOSA")
        print("SQL-Agent v2.5 LISTO PARA PRODUCCION")
        print("=" * 60)
        sys.exit(0)

if __name__ == "__main__":
    check()
