# **Informe Técnico de Refactorización: Migración de SQL-Agent MVP a Arquitectura Agéntica de Grado Empresarial (v2)**

## **1\. Introducción y Análisis Estratégico de la Arquitectura**

La evolución de los sistemas basados en Modelos de Lenguaje Grande (LLM) ha transitado rápidamente de cadenas de ejecución lineales simples a arquitecturas cognitivas complejas capaces de razonamiento, planificación y autocorrección. El presente informe técnico detalla el plan de refactorización para migrar un Producto Mínimo Viable (MVP) de un agente SQL —que actualmente opera bajo un paradigma de "disparar y olvidar" (fire-and-forget)— hacia una arquitectura robusta, escalable y observable (v2). Esta nueva arquitectura se fundamenta en la orquestación de grafos de estados mediante **LangGraph**, la gestión estricta de datos con **Pydantic v2**, interfaces asíncronas de alto rendimiento con **FastAPI**, y una capa de persistencia y contexto vectorial unificada sobre **Supabase (PostgreSQL)**.

### **1.1 Limitaciones Críticas del MVP Actual**

El análisis de la arquitectura heredada revela deficiencias estructurales que impiden su despliegue en entornos de producción críticos. Los sistemas tradicionales de Text-to-SQL suelen implementarse como cadenas secuenciales (Sequential Chains) donde el éxito depende enteramente de una única inferencia correcta del LLM.1

Las limitaciones identificadas incluyen:

1. **Fragilidad ante Errores (Lack of Self-Correction):** En el modelo lineal, si el SQL generado contiene errores sintácticos o alucinaciones de esquema (referencias a columnas inexistentes), la ejecución falla terminalmente. No existe un mecanismo de retroalimentación que permita al agente interpretar el error de la base de datos y reformular la consulta.2  
2. **Ausencia de Estado Persistente (Statelessness):** La falta de una memoria a corto y largo plazo impide mantener conversaciones multi-turno. El agente no puede recordar aclaraciones previas del usuario ni preferencias de visualización, lo que resulta en una experiencia de usuario fragmentada y repetitiva.3  
3. **Contexto de Esquema Ineficiente:** La práctica común de inyectar la definición completa del esquema DDL (Data Definition Language) en el contexto del LLM provoca latencia elevada, costos excesivos de tokens y degradación del rendimiento del modelo debido al ruido informativo.  
4. **Riesgos de Seguridad:** La ejecución directa de SQL sin validación semántica ni aislamiento a nivel de roles expone la base de datos a inyecciones y accesos no autorizados.4

### **1.2 La Visión Arquitectónica v2: Grafos Cíclicos y Persistencia**

La arquitectura v2 propone un cambio de paradigma hacia un **Sistema Agéntico Cíclico**. Al utilizar LangGraph, modelamos el comportamiento del agente no como una línea recta, sino como un grafo dirigido (StateGraph) donde los nodos representan unidades de trabajo cognitivo (Planificación, Generación, Validación, Ejecución) y las aristas definen el flujo de control.6

Esta estructura permite implementar bucles de reintento y validación, donde el agente actúa como un sistema de control que converge hacia una solución correcta mediante iteraciones sucesivas. La integración con Supabase proporciona una doble función crítica: actúa como el almacén de datos transaccional y, simultáneamente, como la capa de persistencia del estado del grafo (Checkpointer), permitiendo pausar, reanudar y auditar la ejecución del agente en cualquier punto.3

## ---

**2\. Orquestación Avanzada con LangGraph y Patrones de Supervisión**

El núcleo de la refactorización reside en la adopción de LangGraph para gestionar el flujo de ejecución. A diferencia de las cadenas estáticas, LangGraph introduce el concepto de "grafos con estado" (Stateful Graphs), lo que es fundamental para construir agentes que puedan manejar la incertidumbre y la complejidad de las consultas analíticas empresariales.

### **2.1 Definición del Estado del Grafo con Pydantic v2**

En LangGraph, el estado (State) es una estructura de datos compartida que fluye a través de los nodos del grafo. Para la v2, es imperativo abandonar el uso de diccionarios no tipados (TypedDict laxos) en favor de modelos **Pydantic v2**. Pydantic v2, reescrito en Rust, ofrece un rendimiento de validación superior y garantiza que el estado del agente cumpla estrictamente con el contrato de datos definido en cada "super-paso" (super-step) de la ejecución.6

La definición del estado debe capturar no solo el historial de mensajes, sino también artefactos intermedios críticos para el proceso de razonamiento y la visualización final.

| Componente del Estado | Tipo de Dato (Pydantic) | Descripción y Propósito |
| :---- | :---- | :---- |
| messages | list | Historial conversacional completo. Utiliza un reducer (operator.add) para acumular mensajes en lugar de sobrescribirlos.9 |
| user\_intent | str | Clasificación semántica de la intención del usuario (ej. "consulta\_agregada", "drill\_down"). |
| schema\_context | JSON / str | Subconjunto del esquema de la base de datos relevante para la consulta actual, obtenido dinámicamente. |
| generated\_sql | str | La consulta SQL candidata generada por el LLM. |
| sql\_valid | bool | Indicador de validez tras el paso por el nodo de validación sintáctica y de seguridad. |
| execution\_results | list\[dict\] | Resultados crudos retornados por Supabase tras la ejecución exitosa. |
| visualization\_config | TremorSchema | Configuración estructurada para renderizar gráficos en el frontend (ver Sección 8). |
| retry\_count | int | Contador para limitar los bucles de autocorrección y evitar ciclos infinitos. |

El uso de Pydantic permite inyectar validadores personalizados (@field\_validator) que pueden, por ejemplo, asegurar que el SQL generado no contenga comandos destructivos antes incluso de que el estado llegue al nodo de validación.10

### **2.2 Patrón de Supervisor Jerárquico**

Para sistemas complejos, un solo agente monolítico se vuelve inmanejable. La arquitectura v2 implementa el **Patrón Supervisor**.12 En este diseño, un nodo central "Supervisor" (impulsado por un LLM) actúa como orquestador, delegando tareas a agentes o nodos especializados (Workers) y sintetizando sus respuestas.

En el contexto del SQL-Agent, el Supervisor dirige el flujo entre:

1. **Agente de Planificación:** Descompone preguntas complejas ("¿Cuál es la tendencia de ventas comparada con el año anterior?") en pasos lógicos.  
2. **Agente SQL (Worker):** Especialista en la generación técnica de consultas y manejo de errores de base de datos.  
3. **Agente de Visualización:** Transforma los datos tabulares en configuraciones gráficas.

La comunicación entre el Supervisor y los Workers se gestiona mediante el objeto Command de LangGraph, que permite actualizaciones de estado y enrutamiento dinámico en una sola operación atómica.13 Esto es crucial para manejar "handoffs" (transferencias de control) donde el Supervisor delega explícitamente la autoridad de ejecución a un sub-grafo y espera un resultado estructurado de vuelta.

### **2.3 Diseño de Nodos y Flujo de Control Cíclico**

La topología del grafo para el Agente SQL específico (el "Worker" principal) sigue un patrón de ciclo de corrección:

1. **Nodo SchemaSelector:** Utiliza búsqueda vectorial para identificar tablas relevantes.  
2. **Nodo SQLGenerator:** Genera la consulta inicial basada en el esquema seleccionado.  
3. **Nodo Validator:** Analiza estáticamente la consulta (sin ejecutarla) buscando errores de sintaxis o violaciones de políticas de seguridad.  
4. **Nodo Executor:** Ejecuta la consulta contra Supabase. Si ocurre un error de tiempo de ejecución (ej. "División por cero"), captura la excepción.  
5. **Aristas Condicionales (Conditional Edges):**  
   * Si Validator o Executor reportan error → El flujo retorna al nodo SQLGenerator con el mensaje de error inyectado en el estado para un "reintento reflexivo".  
   * Si el resultado es exitoso → El flujo avanza al nodo Visualizer o retorna al Supervisor.

Este diseño convierte el proceso de generación de SQL en un bucle de retroalimentación cerrado, aumentando drásticamente la tasa de éxito en consultas complejas.1

## ---

**3\. Persistencia y Memoria: Integración Profunda con Supabase**

La capacidad de detener, reanudar y auditar la ejecución de un agente es lo que diferencia un juguete de una herramienta empresarial. LangGraph abstrae esto mediante el concepto de "Checkpointers". Para la v2, utilizaremos **Supabase (PostgreSQL)** como backend de persistencia, aprovechando su robustez y capacidad transaccional.

### **3.1 Implementación de PostgresCheckpointer Asíncrono**

La persistencia en LangGraph funciona guardando una instantánea (snapshot) del estado del grafo después de cada paso. Utilizaremos la librería langgraph-checkpoint-postgres en su modalidad asíncrona (AsyncPostgresSaver) para no bloquear el bucle de eventos de FastAPI.3

La configuración técnica requiere instanciar un pool de conexiones a la base de datos de Supabase. Es crítico configurar correctamente el pool (usando psycopg v3 o asyncpg) con parámetros como autocommit=True y row\_factory=dict\_row para asegurar la compatibilidad con el serializador de LangGraph.8

Python

\# Ejemplo conceptual de configuración del Checkpointer  
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  
from psycopg\_pool import AsyncConnectionPool

DB\_URI \= "postgresql://user:pass@aws-0-us-west-1.pooler.supabase.com:6543/postgres"

\# El pool debe ser gestionado a nivel de aplicación (lifespan de FastAPI)  
async def get\_checkpointer():  
    async with AsyncConnectionPool(conninfo=DB\_URI, max\_size=20, kwargs={"autocommit": True}) as pool:  
        checkpointer \= AsyncPostgresSaver(pool)  
        await checkpointer.setup() \# Crea las tablas de checkpoints si no existen  
        return checkpointer

Este checkpointer crea automáticamente tablas en Supabase (checkpoints, checkpoint\_writes) que almacenan versiones serializadas del estado.8 Esto permite:

* **Time Travel:** Depurar fallos inspeccionando estados pasados de una conversación específica.  
* **Human-in-the-Loop:** El grafo puede configurarse para interrumpirse antes de acciones sensibles (como ejecutar un SQL costoso) y esperar la aprobación humana (vía API), reanudando la ejecución exactamente donde se quedó gracias al checkpoint almacenado.18

### **3.2 Estrategias de Memoria: Corto vs. Largo Plazo**

La arquitectura distingue dos tipos de memoria gestionadas sobre Supabase:

1. **Memoria a Corto Plazo (Thread-Scoped):** Gestionada automáticamente por el PostgresCheckpointer. Mantiene el contexto de la sesión actual (mensajes, resultados intermedios). Es efímera en cuanto a relevancia (dura lo que dura la sesión de análisis) pero persistente técnicamente.19  
2. **Memoria a Largo Plazo (Semantic Store):** Para que el agente "aprenda" de interacciones pasadas, implementamos un almacén de memoria semántica utilizando pgvector en Supabase.  
   * **Mecanismo:** Cuando el usuario corrige al agente ("No uses la tabla users, usa active\_users"), el agente almacena esta preferencia o regla en una tabla agent\_memory con un vector de embedding.  
   * **Recuperación:** En futuras ejecuciones, el nodo SchemaSelector consulta esta memoria para recuperar reglas de negocio aprendidas, mejorando la precisión con el tiempo.20

## ---

**4\. Introspección Dinámica de Esquemas y Vinculación (Schema Linking)**

Uno de los desafíos más grandes en agentes SQL es el manejo de esquemas extensos. Enviar un DDL de 200 tablas a un LLM es inviable. La arquitectura v2 implementa un sistema de **Retrieval-Augmented Generation (RAG) Estructural**.

### **4.1 Extracción de Metadatos con SQLAlchemy**

Utilizaremos SQLAlchemy y su módulo Inspector para extraer metadatos de la base de datos en tiempo real. A diferencia de enfoques estáticos, esto permite que el agente siempre trabaje con la estructura más reciente de la base de datos.22

El proceso de introspección debe ser granular. No basta con nombres de tablas; el agente necesita:

* Nombres y tipos de columnas.  
* Claves foráneas (para entender relaciones y joins).  
* Comentarios de columnas (donde reside a menudo la semántica del negocio).

Para optimizar el contexto, implementamos un script de utilidad que convierte estos metadatos reflejados en una representación JSON ligera o un formato DDL simplificado, eliminando ruido innecesario.24

### **4.2 Selección Inteligente de Tablas (Schema Linking)**

El nodo SchemaSelector precede a la generación de SQL. Su función es filtrar el universo de tablas disponibles a un subconjunto relevante.

1. **Indexación:** Se genera un índice vectorial en Supabase (pgvector) sobre las descripciones textuales de todas las tablas y sus columnas principales.  
2. **Búsqueda:** Ante una consulta de usuario ("Ventas del Q3 en Latam"), el nodo realiza una búsqueda de similitud semántica para recuperar las tablas más probables (ej. sales, regions, periods).  
3. **Inyección:** Solo los esquemas de estas tablas seleccionadas se inyectan en el schema\_context del estado del agente.1

Este enfoque reduce drásticamente las alucinaciones, ya que el LLM solo "ve" las tablas que necesita para la tarea específica.

## ---

**5\. Interfaz API Asíncrona con FastAPI**

La interfaz del agente debe ser capaz de manejar la naturaleza asíncrona y de larga duración de los procesos agénticos. FastAPI es la elección ideal debido a su soporte nativo para asyncio, compatibilidad con Pydantic y capacidad de Streaming.

### **5.1 Desacoplamiento de Ejecución y Respuesta**

Una operación agéntica puede tardar desde segundos hasta minutos. Bloquear una petición HTTP tradicional es inaceptable. La v2 utiliza un modelo basado en **Streaming de Eventos** (Server-Sent Events \- SSE).

El endpoint principal /chat no devuelve simplemente una respuesta JSON final. En su lugar, devuelve un StreamingResponse que emite eventos en tiempo real conforme el grafo de LangGraph avanza por sus nodos.25

Python

\# Esquema conceptual del endpoint de streaming  
@app.post("/chat/stream")  
async def stream\_chat(request: ChatRequest, background\_tasks: BackgroundTasks):  
    \# Compilar grafo con checkpointer  
    app \= get\_compiled\_graph()  
      
    async def event\_generator():  
        async for event in app.astream\_events(inputs, config={"configurable": {"thread\_id": request.thread\_id}}):  
            \# Emitir eventos: inicio de nodo, generación de tokens, cambio de estado  
            yield f"data: {json.dumps(event)}\\n\\n"  
              
    return StreamingResponse(event\_generator(), media\_type="text/event-stream")

Esto permite al frontend mostrar indicadores de progreso granulares ("Analizando esquema...", "Generando SQL...", "Corrigiendo error...") mejorando significativamente la experiencia de usuario.

### **5.2 Tareas en Segundo Plano (Background Tasks)**

Para operaciones que no requieren feedback inmediato al usuario (como la reindexación de vectores tras una actualización de esquema o el registro de métricas de uso detalladas), FastAPI utiliza BackgroundTasks. Esto asegura que la respuesta principal no se vea penalizada por tareas de mantenimiento.19

## ---

**6\. Visualización Estructurada: De Datos a Dashboards**

El objetivo final no es solo ejecutar SQL, sino presentar información ("Insights"). La arquitectura v2 incluye un nodo dedicado Visualizer que transforma los resultados tabulares (execution\_results) en especificaciones de visualización estandarizadas.

### **6.1 Esquemas JSON para Visualización (Tremor/Nivo)**

Para garantizar que el frontend pueda renderizar gráficos sin lógica compleja, el agente debe devolver una configuración JSON estricta. Definimos esquemas Pydantic que mapean a las propiedades esperadas por librerías de componentes como **Tremor** o **Nivo Charts**.28

El nodo Visualizer recibe los datos y la intención del usuario, y decide la mejor representación visual (ej. Gráfico de Líneas para series temporales, Gráfico de Barras para comparaciones categóricas).

**Ejemplo de Estructura de Salida (Schema):**

JSON

{  
  "viz\_type": "bar\_chart",  
  "config": {  
    "title": "Ventas por Región \- Q3",  
    "x\_axis\_key": "region\_name",  
    "y\_axis\_key": "total\_sales",  
    "colors": \["blue", "teal"\]  
  },  
  "data":  
}

El uso de la función with\_structured\_output de LangChain (o tool\_calls en modelos OpenAI) garantiza que el LLM respete rigurosamente este esquema JSON, eliminando errores de renderizado en el cliente.30

## ---

**7\. Seguridad y Gestión de Roles en Base de Datos**

La seguridad es el componente más crítico en un agente SQL. La arquitectura v2 implementa una defensa en profundidad.

### **7.1 Principio de Mínimo Privilegio (Role Management)**

El agente **nunca** debe conectarse a Supabase con credenciales de superusuario (postgres o service\_role). Se debe crear un rol específico en PostgreSQL (agent\_read\_only) con permisos estrictamente limitados:

* Permiso SELECT solo en tablas de negocio permitidas (Allow-list).  
* Denegación explícita en tablas de sistema o sensibles (auth.users, tablas de configuración).  
* Uso de connection pooling en Supabase configurado para utilizar este rol específico para las sesiones del agente.32

### **7.2 Row Level Security (RLS)**

Dado que Supabase expone la base de datos, las políticas RLS son la última línea de defensa. El agente debe ejecutar las consultas dentro de un contexto que respete el RLS.

* **Implementación:** Antes de ejecutar el SQL generado, el nodo Executor debe establecer variables de configuración de sesión (ej. set\_config('app.current\_user\_id', 'user\_123', true)) dentro de la misma transacción. Esto asegura que el motor de base de datos filtre automáticamente las filas a las que el usuario actual no tiene acceso, incluso si el LLM intenta seleccionar "todos los datos".33

### **7.3 Análisis Estático de Consultas**

El nodo Validator incorpora lógica determinista (no LLM) utilizando librerías de análisis SQL (como sqlglot) para rechazar categóricamente cualquier sentencia que contenga palabras clave destructivas (DROP, DELETE, INSERT, GRANT, ALTER). Este es un "hard guardrail" que no depende de la probabilidad del modelo.2

## ---

**8\. Plan de Migración y Hoja de Ruta**

La transición del MVP a la v2 se estructura en fases para mitigar riesgos.

### **Fase 1: Fundamentos del Grafo y Estado (Semanas 1-2)**

* **Objetivo:** Reemplazar las cadenas lineales por StateGraph de LangGraph.  
* **Acciones:**  
  * Definir los modelos Pydantic v2 para AgentState.  
  * Implementar nodos básicos (Planner, Generator) aislados.  
  * Configurar la validación estricta de tipos.  
  * *Entregable:* Un agente que funciona en memoria local con flujo cíclico básico.

### **Fase 2: Persistencia y Capa de Datos (Semanas 3-4)**

* **Objetivo:** Integrar Supabase y PostgresCheckpointer.  
* **Acciones:**  
  * Configurar AsyncPostgresSaver con el pool de conexiones de Supabase.  
  * Implementar el script de introspección de esquemas con SQLAlchemy.  
  * Configurar pgvector e indexar los metadatos de las tablas.  
  * *Entregable:* Agente con memoria persistente y conocimiento dinámico del esquema.

### **Fase 3: Interfaz y Seguridad (Semanas 5-6)**

* **Objetivo:** Exponer vía FastAPI y asegurar la ejecución.  
* **Acciones:**  
  * Desarrollar endpoints de Streaming (SSE) en FastAPI.  
  * Implementar el rol de base de datos agent\_read\_only y probar políticas RLS.  
  * Integrar el nodo Visualizer con esquemas JSON estructurados.  
  * *Entregable:* API robusta lista para integración con frontend.

### **Fase 4: Observabilidad y Pruebas (Semana 7\)**

* **Objetivo:** Garantizar la fiabilidad en producción.  
* **Acciones:**  
  * Implementar trazabilidad con LangSmith para monitorizar pasos del grafo y costos.  
  * Crear tests de regresión: Un dataset de preguntas naturales vs. SQL esperado para validar que los cambios no degradan la precisión.  
  * *Entregable:* Sistema desplegado en entorno de staging con monitorización activa.

## **9\. Conclusión**

La refactorización propuesta transforma el SQL-Agent de una herramienta experimental a una plataforma de inteligencia de datos empresarial. Al adoptar **LangGraph**, ganamos control granular sobre el flujo cognitivo y capacidades de recuperación ante errores. **Supabase** centraliza la persistencia y el conocimiento vectorial, simplificando la infraestructura. **FastAPI** y **Pydantic** aseguran que el sistema sea performante, seguro y fácil de mantener. Esta arquitectura v2 no solo resuelve los problemas de estabilidad del MVP, sino que sienta las bases para futuras capacidades avanzadas como la colaboración multi-agente y el aprendizaje continuo.

#### **Obras citadas**

1. Architecting State-of-the-Art Text-to-SQL Agents for Enterprise Complexity \- Towards AI, fecha de acceso: diciembre 24, 2025, [https://pub.towardsai.net/architecting-state-of-the-art-text-to-sql-agents-for-enterprise-complexity-629c5c5197b8](https://pub.towardsai.net/architecting-state-of-the-art-text-to-sql-agents-for-enterprise-complexity-629c5c5197b8)  
2. Build a custom SQL agent \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langgraph/sql-agent](https://docs.langchain.com/oss/python/langgraph/sql-agent)  
3. Memory \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langgraph/add-memory](https://docs.langchain.com/oss/python/langgraph/add-memory)  
4. LangChain SQL Agent Tutorial 2025 \- Gist \- GitHub, fecha de acceso: diciembre 24, 2025, [https://gist.github.com/shibyan-ai-engineer/e1228f29492811894d93030930b692cd](https://gist.github.com/shibyan-ai-engineer/e1228f29492811894d93030930b692cd)  
5. Least Privilege for LLM Agents: Applying Security Principles to Model Selection \- Medium, fecha de acceso: diciembre 24, 2025, [https://medium.com/@michael.hannecke/least-privilege-for-llm-agents-applying-security-principles-to-model-selection-57760accb041](https://medium.com/@michael.hannecke/least-privilege-for-llm-agents-applying-security-principles-to-model-selection-57760accb041)  
6. Pydantic AI vs LangGraph: Features, Integrations, and Pricing Compared \- ZenML Blog, fecha de acceso: diciembre 24, 2025, [https://www.zenml.io/blog/pydantic-ai-vs-langgraph](https://www.zenml.io/blog/pydantic-ai-vs-langgraph)  
7. Workflows and agents \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langgraph/workflows-agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)  
8. langgraph-checkpoint-postgres \- PyPI, fecha de acceso: diciembre 24, 2025, [https://pypi.org/project/langgraph-checkpoint-postgres/](https://pypi.org/project/langgraph-checkpoint-postgres/)  
9. Part 1: How LangGraph Manages State for Multi-Agent Workflows (Best Practices) \- Medium, fecha de acceso: diciembre 24, 2025, [https://medium.com/@bharatraj1918/langgraph-state-management-part-1-how-langgraph-manages-state-for-multi-agent-workflows-da64d352c43b](https://medium.com/@bharatraj1918/langgraph-state-management-part-1-how-langgraph-manages-state-for-multi-agent-workflows-da64d352c43b)  
10. How to Build AI Agents Using Pydantic AI \- Ema, fecha de acceso: diciembre 24, 2025, [https://www.ema.co/additional-blogs/addition-blogs/build-ai-agents-pydantic-ai](https://www.ema.co/additional-blogs/addition-blogs/build-ai-agents-pydantic-ai)  
11. Models \- Pydantic Validation, fecha de acceso: diciembre 24, 2025, [https://docs.pydantic.dev/latest/concepts/models/](https://docs.pydantic.dev/latest/concepts/models/)  
12. langchain-ai/langgraph-supervisor-py \- GitHub, fecha de acceso: diciembre 24, 2025, [https://github.com/langchain-ai/langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py)  
13. How Agent Handoffs Work in Multi-Agent Systems | Towards Data Science, fecha de acceso: diciembre 24, 2025, [https://towardsdatascience.com/how-agent-handoffs-work-in-multi-agent-systems/](https://towardsdatascience.com/how-agent-handoffs-work-in-multi-agent-systems/)  
14. langgraph/docs/docs/concepts/multi\_agent.md at main · langchain ..., fecha de acceso: diciembre 24, 2025, [https://github.com/langchain-ai/langgraph/blob/main/docs/docs/concepts/multi\_agent.md](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/concepts/multi_agent.md)  
15. langgraph/docs/docs/tutorials/extraction/retries.ipynb at main \- GitHub, fecha de acceso: diciembre 24, 2025, [https://github.com/langchain-ai/langgraph/blob/main/docs/docs/tutorials/extraction/retries.ipynb](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/tutorials/extraction/retries.ipynb)  
16. Saving User message manually for AsyncPostgreSaver checkpointer \- LangGraph, fecha de acceso: diciembre 24, 2025, [https://forum.langchain.com/t/saving-user-message-manually-for-asyncpostgresaver-checkpointer/1741](https://forum.langchain.com/t/saving-user-message-manually-for-asyncpostgresaver-checkpointer/1741)  
17. langgraph-checkpoint-postgres issue with version update \#3557 \- GitHub, fecha de acceso: diciembre 24, 2025, [https://github.com/langchain-ai/langgraph/issues/3557](https://github.com/langchain-ai/langgraph/issues/3557)  
18. Node-based \- in the CopilotKit docs, fecha de acceso: diciembre 24, 2025, [https://docs.copilotkit.ai/langgraph/human-in-the-loop/node-flow](https://docs.copilotkit.ai/langgraph/human-in-the-loop/node-flow)  
19. Memory overview \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langgraph/memory](https://docs.langchain.com/oss/python/langgraph/memory)  
20. FareedKhan-dev/langgraph-long-memory: A detail Implementation of handling long-term memory in Agentic AI \- GitHub, fecha de acceso: diciembre 24, 2025, [https://github.com/FareedKhan-dev/langgraph-long-memory](https://github.com/FareedKhan-dev/langgraph-long-memory)  
21. Integrate AgentCore Memory with LangChain or LangGraph \- AWS Documentation, fecha de acceso: diciembre 24, 2025, [https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-integrate-lang.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-integrate-lang.html)  
22. Inspection and Reflection \- SQLAlchemy Dialect \- CrateDB, fecha de acceso: diciembre 24, 2025, [https://cratedb.com/docs/sqlalchemy-cratedb/inspection-reflection.html](https://cratedb.com/docs/sqlalchemy-cratedb/inspection-reflection.html)  
23. SQLAlchemy ORM check if column is a foreign\_key \- Stack Overflow, fecha de acceso: diciembre 24, 2025, [https://stackoverflow.com/questions/34894038/sqlalchemy-orm-check-if-column-is-a-foreign-key](https://stackoverflow.com/questions/34894038/sqlalchemy-orm-check-if-column-is-a-foreign-key)  
24. expobrain/sqlalchemy-to-json-schema \- GitHub, fecha de acceso: diciembre 24, 2025, [https://github.com/expobrain/sqlalchemy-to-json-schema](https://github.com/expobrain/sqlalchemy-to-json-schema)  
25. How to kick off background runs \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/langsmith/background-run](https://docs.langchain.com/langsmith/background-run)  
26. Use the graph API \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langgraph/use-graph-api](https://docs.langchain.com/oss/python/langgraph/use-graph-api)  
27. Subagents \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langchain/multi-agent/subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)  
28. tremor \- The react library to build dashboards fast \- CodeSandbox, fecha de acceso: diciembre 24, 2025, [http://codesandbox.io/p/github/gabros20/tremor](http://codesandbox.io/p/github/gabros20/tremor)  
29. Line chart \- nivo, fecha de acceso: diciembre 24, 2025, [https://nivo.rocks/line/](https://nivo.rocks/line/)  
30. How to Get Structured JSON Output From LLM Models Using Python | by Gopal Katariya, fecha de acceso: diciembre 24, 2025, [https://gopalkatariya.medium.com/how-to-get-structured-json-output-from-llm-models-using-python-3da6bf41342c](https://gopalkatariya.medium.com/how-to-get-structured-json-output-from-llm-models-using-python-3da6bf41342c)  
31. JSON Agent \- Lamatic.ai Docs, fecha de acceso: diciembre 24, 2025, [https://lamatic.ai/docs/agents/json-agent](https://lamatic.ai/docs/agents/json-agent)  
32. Build a SQL agent \- Docs by LangChain, fecha de acceso: diciembre 24, 2025, [https://docs.langchain.com/oss/python/langchain/sql-agent](https://docs.langchain.com/oss/python/langchain/sql-agent)  
33. AI Prompt: Database: Declarative Database Schema | Supabase Docs, fecha de acceso: diciembre 24, 2025, [https://supabase.com/docs/guides/getting-started/ai-prompts/declarative-database-schema](https://supabase.com/docs/guides/getting-started/ai-prompts/declarative-database-schema)