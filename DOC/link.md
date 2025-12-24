# **Referencias Oficiales para Modernización (Contexto para Refactorización)**

Aquí tienes la documentación oficial que valida el uso de las tecnologías solicitadas en el "Master Prompt". Utiliza estas fuentes para configurar las versiones más recientes disponibles.

### **1\. Next.js 16 / Turbopack**

* **Next.js 16 (React 19 RC Support):** Vercel ha estado integrando soporte para React 19 y el compilador.  
  * *Fuente:* [Next.js Blog \- React 19 Support](https://nextjs.org/blog/next-15-rc) (Nota: Aunque dice 15 RC, la arquitectura interna apunta a la estabilidad de estas features).  
* **Turbopack (Stable):** Ya es estable para desarrollo.  
  * *Fuente:* [Turbopack Documentation](https://nextjs.org/docs/architecture/turbopack)

### **2\. Tailwind CSS v4.0 (Oxide Engine)**

* **Anuncio Oficial v4.0 Alpha/Beta:** El nuevo motor Oxide en Rust y la configuración "CSS-first".  
  * *Fuente:* [Tailwind CSS v4.0 Announcement](https://tailwindcss.com/blog/tailwindcss-v4-alpha)  
  * *Repositorio:* [Tailwind CSS GitHub (v4 branch)](https://github.com/tailwindlabs/tailwindcss/tree/next)  
* **Migración a v4:** Guía sobre cómo eliminar tailwind.config.js y usar @theme.  
  * *Fuente:* [Tailwind v4 Upgrade Guide](https://tailwindcss.com/docs/upgrade-guide)

### **3\. React 19 / React Compiler**

* **React Compiler (antes React Forget):** Ya disponible para probar en Next.js.  
  * *Fuente:* [React Blog \- React Compiler](https://react.dev/blog/2024/02/15/react-labs-what-we-have-been-working-on-february-2024)  
* **React 19 Beta:** Documentación de las nuevas APIs como use y Server Actions mejorados.  
  * *Fuente:* [React 19 Beta Announcement](https://www.google.com/search?q=https://react.dev/blog/2024/04/25/react-19-beta)

### **4\. Shadcn/ui & Charts**

* **Shadcn Charts:** La nueva librería de gráficos basada en Recharts pero con arquitectura de componentes.  
  * *Fuente:* [Shadcn/ui Charts Documentation](https://ui.shadcn.com/docs/components/chart)  
* **Recharts \+ Tailwind:** Patrones modernos de integración.  
  * *Fuente:* [Recharts Documentation](https://www.google.com/search?q=https://recharts.org/en-US/)

### **5\. Vercel AI SDK 4.0 (Core)**

* **AI SDK RSC (React Server Components):** Streaming de UI y Generative UI.  
  * *Fuente:* [Vercel AI SDK Docs](https://sdk.vercel.ai/docs)  
  * *Streaming React Components:* [AI SDK \- Stream UI](https://sdk.vercel.ai/docs/concepts/ai-rsc)

Instrucción para el Agente:  
Si una versión específica (ej. "16.2") no aparece en npm como latest, utiliza el tag canary (para Next.js) o rc (para React) para acercarte lo más posible a la especificación, o la última versión stable que soporte las características mencionadas (PPR, Turbopack, React Compiler).