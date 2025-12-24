# Informe de Implementación SQL-Agent v2

**Fecha:** 2025-12-24
**Documentos analizados:**
- `Agentes IA para ERP.docx` - Auditoría técnica con instrucciones paso a paso
- `SQL-Agent v2_ Refactorización y Robustez.md` - Arquitectura empresarial completa

---

## 1. RESUMEN EJECUTIVO

Se analizaron los documentos de arquitectura y se implementaron las mejoras más críticas para robustez del sistema. Sin embargo, **hay items que requieren acción manual del usuario** debido a limitaciones de acceso o decisiones de arquitectura.

### Estado General
- ✅ **Implementado:** 70% de mejoras críticas
- ⚠️ **Pendiente:** 20% requiere configuración manual en Supabase
- ❌ **Bloqueado:** 10% requiere decisiones de arquitectura

---

## 2. IMPLEMENTACIONES REALIZADAS

### 2.1 Parser JSON Robusto ✅
**Archivo:** `backend/app/utils/robust_parser.py`

Se creó un sistema de parsing con múltiples estrategias:
1. Parse directo JSON
2. Limpieza de markdown (```` ```json `````)
3. Extracción con regex
4. Fix de comillas simples
5. **OutputFixingParser** con LLM para auto-corrección

```python
from app.utils.robust_parser import parse_json_robust, OutputFixingParser

# Uso simple
data = parse_json_robust(llm_response)

# Con schema Pydantic
parser = OutputFixingParser(schema=QueryPlan, llm=my_llm)
plan = parser.parse(content)
```

### 2.2 Script de Refresh de Esquema ✅
**Archivo:** `backend/scripts/refresh_schema.py`

Script para extraer el esquema real de Supabase y generar `schema_snapshot.json`:

```bash
cd backend
python scripts/refresh_schema.py --output data/schema_snapshot.json
```

**Características:**
- Extrae tablas, columnas, tipos, PKs, FKs
- Whitelist configurable de tablas
- Descripciones de negocio personalizables
- Fallback si `information_schema` no está accesible

### 2.3 Memory Store para Long-Term Memory ✅
**Archivo:** `backend/app/memory/supabase_store.py`

Implementación de memoria persistente con:
- CRUD básico de memorias
- Namespaces (preferences, corrections, insights)
- TTL automático con limpieza
- Métodos de conveniencia

```python
from app.memory.supabase_store import get_memory_store

store = get_memory_store()
store.remember_preference(user_id, "dashboard_style", "minimal")
store.remember_correction(user_id, original, correction, reason)
```

### 2.4 Router con Fallback LLM Semántico ✅
**Archivo:** `backend/app/agents/intent_router.py`

El router ahora usa LLM cuando las heurísticas no son claras:
- Clasificación semántica de intención
- Detección de dominio (sales, inventory, conversations)
- Fallback robusto si LLM falla

### 2.5 Checkpointer con Thread ID ✅
**Archivo:** `backend/app/api/v1_chat.py`

- Ahora pasa `conversation_id` como `thread_id`
- Habilita persistencia real de conversaciones
- Compatible con MemorySaver (Windows) y PostgresSaver (Linux)

---

## 3. PENDIENTES QUE REQUIEREN ACCIÓN DEL USUARIO

### 3.1 ⚠️ Crear Tabla `agent_memory` en Supabase

**Acción requerida:** Ejecutar este SQL en Supabase SQL Editor:

```sql
-- Tabla para memoria a largo plazo del agente
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    key TEXT NOT NULL,
    content JSONB NOT NULL,
    embedding VECTOR(1536),  -- Requiere pgvector
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(user_id, namespace, key)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_agent_memory_user ON agent_memory(user_id, namespace);
CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(key);
```

### 3.2 ⚠️ Crear Rol `agent_read_only` en Supabase

**Por qué:** El agente NO debe conectarse con credenciales de servicio. Principio de mínimo privilegio.

**Acción requerida:**

```sql
-- 1. Crear rol con permisos limitados
CREATE ROLE agent_read_only WITH LOGIN PASSWORD 'tu_password_seguro';

-- 2. Dar permisos SELECT solo a tablas de negocio
GRANT SELECT ON orders TO agent_read_only;
GRANT SELECT ON order_items TO agent_read_only;
GRANT SELECT ON products TO agent_read_only;
GRANT SELECT ON buyers TO agent_read_only;
GRANT SELECT ON agent_interactions TO agent_read_only;
GRANT SELECT ON escalations TO agent_read_only;
GRANT SELECT ON conversations TO agent_read_only;

-- 3. Denegar acceso a tablas sensibles
REVOKE ALL ON auth.users FROM agent_read_only;
REVOKE ALL ON storage.objects FROM agent_read_only;
```

### 3.3 ⚠️ Habilitar Row Level Security (RLS)

**Por qué:** Filtrar datos automáticamente por usuario/tenant.

```sql
-- Ejemplo para tabla orders
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only see their orders"
ON orders FOR SELECT
USING (
    auth.uid()::text = seller_id::text
    OR current_setting('app.current_user_id', true) = seller_id::text
);
```

### 3.4 ⚠️ Configurar RPC para Refresh Schema

El script `refresh_schema.py` intenta usar RPC. Si falla, usa fallback.

**Opcional pero recomendado:**

```sql
-- Crear función RPC para ejecutar SQL arbitrario (SOLO LECTURA)
CREATE OR REPLACE FUNCTION execute_sql(query text)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    -- Validar que solo sea SELECT
    IF NOT (query ~* '^\\s*SELECT') THEN
        RAISE EXCEPTION 'Only SELECT queries allowed';
    END IF;

    EXECUTE 'SELECT jsonb_agg(row_to_json(t)) FROM (' || query || ') t'
    INTO result;

    RETURN COALESCE(result, '[]'::jsonb);
END;
$$;
```

---

## 4. DIFICULTADES ENCONTRADAS

### 4.1 TypedDict vs Pydantic en LangGraph
**Problema:** LangGraph espera `TypedDict` para el estado del grafo, pero los documentos recomiendan Pydantic.

**Solución actual:** Mantener `TypedDict` para el estado interno, usar Pydantic solo para:
- Validación de salidas LLM
- Modelos de request/response de API
- Configuración

**Implicación:** No se puede usar validación automática en cada paso del grafo.

### 4.2 PostgresSaver en Windows
**Problema:** `langgraph-checkpoint-postgres` usa `psycopg3` async que no funciona bien en Windows.

**Solución actual:** Fallback a `MemorySaver` (en memoria).

**Recomendación:**
- Desarrollo: usar MemorySaver
- Producción (Linux/Docker): usar PostgresSaver

### 4.3 Acceso a `information_schema` vía API
**Problema:** La API de Supabase no expone directamente `information_schema`.

**Solución actual:** El script `refresh_schema.py` tiene fallback que infiere columnas desde datos reales.

**Alternativa:** Crear función RPC (ver sección 3.4).

### 4.4 pgvector para Búsqueda Semántica
**Problema:** La búsqueda semántica de tablas requiere `pgvector` que puede no estar habilitado.

**Estado:** No implementado en esta iteración.

**Para habilitar:**
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 5. DECISIONES DE ARQUITECTURA A TOMAR

### 5.1 ¿Migrar todo a Supabase Cloud?

**Pros:**
- Infraestructura gestionada
- pgvector incluido
- Edge Functions para cron jobs
- Auth integrada

**Contras:**
- Costo mensual (~$25/mes mínimo para producción)
- Dependencia de vendor
- Latencia adicional vs self-hosted

**Recomendación:**
- **Desarrollo:** Mantener self-hosted (Easypanel)
- **Producción:** Evaluar migración a Supabase Cloud si:
  - Necesitas pgvector para RAG
  - Quieres Auth gestionada
  - El volumen justifica el costo

### 5.2 ¿Implementar SQL Dinámico o Mantener Allowlist?

**Estado actual:** Allowlist estático de queries.

**Documentos sugieren:** SQL dinámico con validación.

**Recomendación:** Mantener allowlist por ahora. Es más seguro y suficiente para MVP.

### 5.3 ¿Implementar Supervisor Pattern Completo?

**Estado actual:** Supervisor simplificado (router → data → presentation).

**Documentos sugieren:** Supervisor con múltiples workers especializados.

**Recomendación:** Evaluar si la complejidad actual justifica más agentes.

---

## 6. PREGUNTAS PARA RESOLVER

### 6.1 Sobre Supabase
1. ¿Tu instancia actual (Easypanel) tiene pgvector habilitado?
2. ¿Quieres migrar a Supabase Cloud? ¿Cuál es el presupuesto?
3. ¿Necesitas multi-tenant (RLS por vendedor/tienda)?

### 6.2 Sobre Arquitectura
1. ¿El sistema necesita recordar correcciones entre sesiones?
2. ¿Cuántos usuarios concurrentes esperas?
3. ¿Es aceptable la latencia actual (~40s en queries complejas)?

### 6.3 Sobre Seguridad
1. ¿Quién debería tener acceso a qué datos?
2. ¿Necesitas auditoría de queries ejecutadas?
3. ¿Hay datos sensibles que NO deben exponerse nunca?

---

## 7. PRÓXIMOS PASOS RECOMENDADOS

### Inmediato (Hoy)
1. [ ] Ejecutar SQL para crear tabla `agent_memory`
2. [ ] Probar script `refresh_schema.py`
3. [ ] Verificar que todo sigue funcionando

### Corto Plazo (Esta semana)
1. [ ] Crear rol `agent_read_only` y configurar permisos
2. [ ] Decidir sobre migración a Supabase Cloud
3. [ ] Implementar tests para los nuevos componentes

### Mediano Plazo (Próximo mes)
1. [ ] Evaluar pgvector para RAG de esquema
2. [ ] Implementar pipeline de métricas diarias
3. [ ] Agregar observabilidad completa (LangSmith)

---

## 8. ARCHIVOS CREADOS/MODIFICADOS

### Nuevos
- `backend/scripts/refresh_schema.py` - Script de refresh de esquema
- `backend/scripts/__init__.py` - Módulo de scripts
- `backend/app/utils/robust_parser.py` - Parser JSON robusto
- `backend/app/memory/supabase_store.py` - Memory store persistente

### Modificados (sesión anterior)
- `backend/app/agents/data_agent.py` - Parser robusto
- `backend/app/agents/intent_router.py` - LLM fallback
- `backend/app/agents/presentation_agent.py` - Parser robusto
- `backend/app/api/v1_chat.py` - Thread ID para checkpointer

---

## 9. CONTACTO PARA DUDAS

Este informe fue generado automáticamente. Para resolver las preguntas de la sección 6, proporciona la información al chat y continuaremos con la implementación.

**Prioridad recomendada:**
1. Primero: Ejecutar SQL de `agent_memory`
2. Segundo: Decidir sobre Supabase Cloud
3. Tercero: Configurar seguridad (rol read_only)

---

*Generado por Claude Code - SQL-Agent v2 Implementation*
