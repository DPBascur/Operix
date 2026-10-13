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

Actualmente, los servicios usan `MockAdapter`; los datos no provienen del Motor Python ni representan persistencia real. La futura integración deberá reemplazar ese adaptador por uno que consuma el Backend Django REST API, sin conectar el frontend directamente con el Motor.

Las rutas `/`, `/analysis`, `/events` y `/rules` muestran datos de desarrollo. Las rutas `/zones` e `/indicators` están preparadas sin simular funcionalidad todavía; `/dashboard` redirige al dashboard principal en `/`.

## Design tokens

- Midnight Navy — `#0B1320` — texto oscuro y fondos profundos.
- Deep Blue — `#0F2747` — color principal.
- Vibrant Blue — `#3B82F6` — acento principal.
- Teal Cyan — `#2FD1C8` — acento secundario, procesamiento y estados positivos.
- Cool Gray — `#E5E7EB` — bordes y superficies neutras.
- White — `#FFFFFF` — fondo base.

Los tokens están disponibles como variables CSS globales y utilidades Tailwind con el prefijo `brand-`, por ejemplo `bg-brand-primary`, `text-brand-accent` y `border-brand-neutral`.
