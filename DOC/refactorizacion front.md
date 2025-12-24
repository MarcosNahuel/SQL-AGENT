# **Master Prompt: Transformación Estética y Tecnológica del SQL-AGENT (v16.2 Hyper-Edge)**

**Contexto:** Este repositorio es un Agente SQL de ultra-alto rendimiento. El objetivo es posicionar el frontend en el nivel "Tier 0" de la industria para 2026, utilizando las versiones más avanzadas de Next.js, React y Tailwind.

### **1\. Actualización del Core Tecnológico (Hyper-Bleeding Edge)**

Por favor, realiza las siguientes actualizaciones críticas utilizando las versiones más recientes (incluyendo canales Canary si es necesario para estabilidad futura):

* **Next.js 16.2+ (Active LTS/Canary):** Configura el proyecto para utilizar **Turbopack 2.0** (motor de compilación ultra-rápido). Implementa el **Partial Pre-Rendering (PPR)** en todas las rutas del dashboard para tiempos de carga de \<100ms.  
* **React 19.3 / 20 (Alpha Features):** Utiliza el **React Compiler** de forma nativa para eliminar useMemo. Implementa el nuevo hook use cache para persistencia de datos entre componentes de servidor.  
* **Tailwind CSS v4.1 (Oxide Engine):** Migra a la v4.1 que utiliza el motor de Rust optimizado. Configura el sistema de diseño mediante @theme en globals.css eliminando por completo cualquier rastro de configuración en archivos JS/TS.  
* **Vercel AI SDK 4.0:** Actualiza a la v4.0 para el manejo de streams de datos del Agente SQL, permitiendo actualizaciones parciales de la UI mientras la IA genera la respuesta.

### **2\. Visualización de Datos de Próxima Generación**

Refactoriza el ChartRenderer.tsx utilizando la arquitectura **Shadcn/ui Charts v3 (Advanced)**:

* **Motores Híbridos:** Combina **Recharts** con **Framer Motion 12** para animaciones basadas en estados físicos (no solo transiciones).  
* **Estética "Liquid Design":**  
  * **Gradientes Adaptativos:** Los gráficos deben cambiar de color dinámicamente según la tendencia de los datos (ej: verde esmeralda para subidas, rojo neón para caídas).  
  * **Glass-Hydration:** Tooltips con efecto de cristal de alta refracción, backdrop-blur-2xl y bordes con iluminación perimetral (border-glow).  
* **Interacción Háptica Visual:** Los gráficos deben reaccionar al cursor con un efecto de "atracción magnética" en los puntos de datos (Data Points).

### **3\. Experiencia de Usuario "Premium OLED"**

Aplica estos principios de diseño para un look de aplicación de $100B:

* **Tipografía Inter & Geist:** Usa **Geist Mono** para los fragmentos de SQL y **Geist Sans** para la interfaz, con interletrado ajustado para legibilidad máxima en pantallas 4K.  
* **OLED Black Architecture:** Fondo \#000000 absoluto. Las tarjetas (cards) no deben tener fondo sólido, sino un borde white/10 y un gradiente de fondo casi invisible para dar profundidad.  
* **View Transitions API:** Implementa transiciones fluidas de "Hero Animation" cuando un gráfico se expande o cuando el agente cambia de estado.  
* **Sonner v2 & Micro-feedback:** Notificaciones que sigan la curvatura de la pantalla y sonidos de sistema sutiles (opcionales) para confirmar ejecuciones de SQL.

### **4\. Flujo de Ejecución para la IA**

1. **Fase de Auditoría:** Revisa package.json y genera el plan de migración a **Next.js 16.2**.  
2. **Fase de Estilos:** Borra tailwind.config.ts y recrea la identidad visual en globals.css usando el estándar v4.1.  
3. **Fase de Componentes:** Instala los nuevos componentes de **Shadcn v3** y refactoriza el ChartRenderer para que soporte múltiples tipos de gráficos (Bar, Line, Area, Radial, Scatter) con un solo componente inteligente.  
4. **Fase de Dashboard:** Reorganiza el DashboardRenderer.tsx en un layout de "Bento Grid" dinámico que se ajuste según la importancia de los datos devueltos por la IA.

**Meta Final:** El SQL-AGENT debe sentirse como una extensión natural del pensamiento del usuario: instantáneo, visualmente impecable y tecnológicamente imbatible.