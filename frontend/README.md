# Operix Frontend

Base técnica y maqueta visual en desarrollo del frontend de Operix.

## Requisitos

- Node.js 24.2.0 (declarado en `.node-version`)
- pnpm 11.28.2 administrado mediante Corepack

## Instalación y ejecución

```bash
corepack enable pnpm
pnpm install
pnpm dev
```

La aplicación queda disponible en `http://localhost:3000`.

## Scripts

- `pnpm dev`: servidor de desarrollo.
- `pnpm build`: build de producción.
- `pnpm start`: ejecuta el build de producción.
- `pnpm lint`: validación con ESLint.
- `pnpm typecheck`: validación de TypeScript.
- `pnpm test`: pruebas deterministas del editor sin navegador ni dependencias nuevas. Node 24.2.0 puede informar advertencias de Type Stripping experimental; no requiere cambiar el tipo de módulo del proyecto.
- `pnpm format`: aplica Prettier.
- `pnpm format:check`: comprueba el formato.

## Estructura

- `src/app`: App Router y rutas base.
- `src/components`: componentes técnicos mínimos.
- `src/features`: módulos funcionales aislados por dominio.
- `src/types`: contratos de dominio provisionales.
- `src/mocks`: datos exclusivos para desarrollo del frontend.
- `src/services`: servicios desacoplados y adaptador de datos activo.
- `src/config`: configuración pública del frontend.

Por defecto, el frontend usa `MockAdapter`; esos datos no provienen del Motor Python ni representan persistencia real. Para consultar los eventos y ejecutar análisis visual local, configurar `frontend/.env.local` con `NEXT_PUBLIC_DATA_SOURCE=api` y `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`, y reiniciar Next.js. `/events` consulta la API; `/analysis` usa sesiones temporales del Backend y requiere los pesos indicados en `backend/README.md`. Durante el análisis muestra MJPEG; al terminar cambia a un MP4 H.264 con reproducción, pausa y búsqueda. La fuente queda temporalmente disponible para editar la zona y volver a analizar sin subirla de nuevo. «Detener» conserva la fuente; «Limpiar sesión» borra fuente y resultado. El FPS del Motor indica procesamiento, no velocidad de reproducción. Las demás vistas mantienen sus datos de desarrollo. Los fallos de API se muestran sin reemplazar silenciosamente datos reales por mock. El frontend nunca conecta directamente con el Motor.

En modo API, `/events` consulta PostgreSQL a través de los filtros del Backend `occurred_after`, `occurred_before` y `event_type`. Las fechas y horas se introducen en la hora local del navegador y se envían con zona horaria explícita; el único tipo admitido actualmente es `zone_dwell` (permanencia en zona). Se pueden aplicar y limpiar filtros sin recargar la aplicación. En modo mock se conserva la búsqueda y el filtro de zona locales de la maqueta.

Las rutas `/` y `/rules` muestran datos de desarrollo. `/analysis` procesa video real si el Backend está configurado; `/events` consulta datos persistidos en modo API. Las rutas `/zones` e `/indicators` están preparadas sin simular funcionalidad todavía; `/dashboard` redirige al dashboard principal en `/`.

## Design tokens

- Midnight Navy — `#0B1320` — texto oscuro y fondos profundos.
- Deep Blue — `#0F2747` — color principal.
- Vibrant Blue — `#3B82F6` — acento principal.
- Teal Cyan — `#2FD1C8` — acento secundario, procesamiento y estados positivos.
- Cool Gray — `#E5E7EB` — bordes y superficies neutras.
- White — `#FFFFFF` — fondo base.

Los tokens están disponibles como variables CSS globales y utilidades Tailwind con el prefijo `brand-`, por ejemplo `bg-brand-primary`, `text-brand-accent` y `border-brand-neutral`.
