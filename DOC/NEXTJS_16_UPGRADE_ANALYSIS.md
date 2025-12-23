# Analisis de Upgrade a Next.js 16

## Estado Actual
- **Version actual**: Next.js 14.2.18
- **React**: 18.3.1
- **Node.js requerido**: 18+

## Next.js 16 - Resumen (Release: Oct 21, 2025)

### Nuevas Features Principales

#### 1. Cache Components (`"use cache"`)
```tsx
// Nueva directiva para caching explicito
"use cache";

export default async function ProductList() {
  const products = await getProducts();
  return <ul>...</ul>;
}
```
- Reemplaza PPR (Partial Pre-Rendering)
- Caching opt-in en lugar de opt-out
- Habilitar en `next.config.ts`:
```ts
const nextConfig = {
  cacheComponents: true,
};
```

#### 2. `proxy.ts` (reemplaza `middleware.ts`)
```ts
// Antes: middleware.ts
export function middleware(request: NextRequest) { }

// Ahora: proxy.ts
export default function proxy(request: NextRequest) {
  return NextResponse.redirect(new URL('/home', request.url));
}
```

#### 3. Turbopack (ahora default)
- 2-5x builds de produccion mas rapidos
- 10x Fast Refresh mas rapido
- Opt-out con `--webpack` flag si hay problemas

#### 4. React Compiler (estable)
```ts
const nextConfig = {
  reactCompiler: true,
};
```

#### 5. Next.js DevTools MCP
- Integracion con AI para debugging
- Logs unificados
- Awareness de paginas

#### 6. APIs de Cache Mejoradas
```ts
// revalidateTag ahora requiere profile
revalidateTag('blog-posts', 'max');

// Nuevo: updateTag (solo Server Actions)
updateTag(`user-${userId}`);

// Nuevo: refresh()
refresh(); // Refresca datos no cacheados
```

---

## Requisitos de Upgrade

| Requisito | Minimo | Actual en SQL-Agent |
|-----------|--------|---------------------|
| Node.js | 20.9.0 | Verificar |
| TypeScript | 5.1.0 | 5.7.2 OK |
| Browsers | Chrome/Edge/Firefox 111+, Safari 16.4+ | OK |

---

## Breaking Changes Criticos

### 1. Removidos Completamente
- **AMP support**: No usamos, OK
- **`next lint`**: Debemos usar ESLint directamente
- **`devIndicators`**: Configuracion removida
- **`serverRuntimeConfig` / `publicRuntimeConfig`**: Usar env vars

### 2. Cambios de Comportamiento

#### Async params/searchParams (Ya preparado en Next.js 15)
```tsx
// ANTES (sincrono - YA NO FUNCIONA)
export default function Page({ params }) {
  const { id } = params;
}

// AHORA (asincrono - REQUERIDO)
export default async function Page({ params }) {
  const { id } = await params;
}
```

#### Async cookies/headers/draftMode
```tsx
// ANTES
const cookieStore = cookies();

// AHORA
const cookieStore = await cookies();
```

#### Parallel Routes requieren `default.js`
- Todos los slots paralelos necesitan archivo `default.js` explicito

### 3. Cambios de Imagenes
- `minimumCacheTTL`: 60s -> 4 horas
- `imageSizes`: Removido `16` de defaults
- Local images con query strings requieren config

---

## Plan de Migracion para SQL-Agent

### Fase 1: Preparacion (Antes de upgrade)
1. [ ] Actualizar Node.js a 20.9.0+
2. [ ] Verificar que no usamos `middleware.ts` (si lo usamos, renombrar a `proxy.ts`)
3. [ ] Auditar uso de `cookies()`, `headers()` - agregar `await`
4. [ ] Verificar `params` y `searchParams` son `async`

### Fase 2: Upgrade Incremental
```bash
# Opcion 1: Codemod automatico
npx @next/codemod@canary upgrade latest

# Opcion 2: Manual
npm install next@latest react@latest react-dom@latest
```

### Fase 3: Post-Upgrade
1. [ ] Habilitar Turbopack (default, pero verificar)
2. [ ] Evaluar React Compiler
3. [ ] Evaluar Cache Components
4. [ ] Testear build de produccion

---

## Archivos a Revisar en SQL-Agent

### Frontend Files
```
frontend/
├── app/
│   └── page.tsx          # Verificar params/searchParams
├── middleware.ts         # Renombrar a proxy.ts si existe
├── components/
│   └── *.tsx            # Sin cambios necesarios
└── lib/
    └── *.ts             # Sin cambios necesarios
```

### Verificaciones Especificas

#### 1. Verificar si usamos middleware
```bash
# En frontend/
ls middleware.ts 2>/dev/null && echo "EXISTE - Renombrar a proxy.ts"
```

#### 2. Verificar uso de cookies/headers
```bash
grep -r "cookies()" frontend/
grep -r "headers()" frontend/
```

#### 3. Verificar params sincrono
```bash
grep -rn "{ params }" frontend/app/
grep -rn "{ searchParams }" frontend/app/
```

---

## Beneficios del Upgrade

1. **Performance**
   - Builds 2-5x mas rapidos con Turbopack
   - Fast Refresh 10x mas rapido
   - Mejor caching con Cache Components

2. **Developer Experience**
   - DevTools MCP para debugging con AI
   - Logs mejorados en dev y build
   - React Compiler reduce re-renders

3. **Futuro**
   - React 19.2 support (View Transitions, Activity)
   - Build Adapters para deploys custom

---

## Riesgos

1. **Breaking Changes**: `middleware.ts` -> `proxy.ts`
2. **Node.js 18 ya no soportado**: Actualizar runtime
3. **Turbopack default**: Puede haber edge cases

---

## Recomendacion

**ESPERAR** hasta:
1. Estabilizar la aplicacion actual
2. Tener tests automatizados
3. Next.js 16.1+ con fixes de bugs iniciales

**Timeline sugerido**: Q2 2026 (6 meses post-release)

---

## Comandos de Upgrade (cuando este listo)

```bash
# Backup
git checkout -b upgrade-nextjs-16

# Upgrade automatico
cd frontend
npx @next/codemod@canary upgrade latest

# Verificar
npm run build
npm run dev

# Si hay errores de Turbopack, usar webpack temporalmente
npm run build -- --webpack
```
