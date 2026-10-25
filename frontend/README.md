# Operix Frontend

Interfaz de Operix para análisis de video, revisión de eventos e histórico, con acceso y cuentas demostrativas locales explícitas.

## Requisitos

- Node.js 24.2.0 (declarado en `.node-version`)
- pnpm 11.28.2 administrado mediante Corepack

## Instalación y ejecución

```bash
corepack enable pnpm
pnpm install --frozen-lockfile
pnpm dev
```

La aplicación queda disponible en `http://localhost:3000`.

## Scripts

- `pnpm dev`: servidor de desarrollo.
- `pnpm build`: build de producción.
- `pnpm start`: ejecuta el build de producción.
- `pnpm lint`: validación con ESLint.
- `pnpm typecheck`: validación de TypeScript.
- `pnpm test`: pruebas deterministas del editor, agregaciones históricas y validación de cuentas demo, sin GPU ni dependencias nuevas. Node 24.2.0 puede informar advertencias de Type Stripping experimental; no requiere cambiar el tipo de módulo del proyecto.
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

Por defecto, el frontend usa `MockAdapter`; esos datos no provienen del Motor Python ni representan persistencia real. Para consultar los eventos y ejecutar análisis visual local, configurar `frontend/.env.local` con `NEXT_PUBLIC_DATA_SOURCE=api` y `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`, y reiniciar Next.js. `/events` consulta la API; `/analysis` usa sesiones temporales del Backend y requiere los pesos indicados en `backend/README.md`. Durante el análisis muestra MJPEG; al terminar cambia a un MP4 H.264 con reproducción, pausa y búsqueda. La fuente queda temporalmente disponible para editar la zona y volver a analizar sin subirla de nuevo. «Detener» conserva la fuente; «Limpiar sesión» borra fuente y resultado. El FPS del Motor indica procesamiento, no velocidad de reproducción. El histórico, indicadores y detalle consultan registros persistidos en modo API; login/usuarios y vistas preparatorias conservan sus límites de demostración. Los fallos de API se muestran sin reemplazar silenciosamente datos reales por mock. El frontend nunca conecta directamente con el Motor.

En modo API, `/events` consulta PostgreSQL a través de los filtros del Backend `occurred_after`, `occurred_before` y `event_type`. Las fechas y horas se introducen en la hora local del navegador y se envían con zona horaria explícita; se admiten `zone_dwell` (permanencia en zona) y `person_forklift_proximity` (proximidad persona–montacargas). Se pueden aplicar y limpiar filtros sin recargar la aplicación. En modo mock se conserva la búsqueda y el filtro de zona locales de la maqueta.

`/` e `/indicators` muestran el dashboard histórico, con selector explícito de ejemplo ilustrativo o registros API. En modo API, el mes UTC seleccionado consulta `/events/frequencies/` para frecuencia diaria y por tipo, y `/events/` para desglose horario, zona y actividad reciente; la comparación usa el mes UTC anterior. Se reconcilian los totales y se informa si los registros cambian entre consultas. Un mes vacío muestra un estado sin registros, sin estadísticas inventadas. Estos conteos pueden incluir ensayos y no equivalen a tasas verificadas de incidentes. `/dashboard` redirige a `/`. `/login` y `/users` son una demo local sin contraseñas ni autorización Backend y no bloquean el análisis. `/analysis` y `/events` conservan su integración real; `/rules` mantiene contexto de desarrollo y `/zones` su estado preparatorio. El estado global consulta salud de API/base de datos, no certifica modelos ni GPU. Véase [alcance y contratos del refresh](UI_REFRESH.md).

## Design tokens

- Azul Operix — `--primary`: `#3767E8` en claro, `#2F6FDC` en oscuro; texto primario blanco.
- Superficies — `--background`, `--surface` y `--surface-muted`, con pares claro/oscuro existentes.
- Sidebar — `--sidebar`: `#171B21` en claro, `#0D0F12` en oscuro.
- Turquesa — `#2FD1C8`, reservado al contexto visual del análisis.
- Estados — `--success`, `--warning`, `--danger`; siempre acompañados de texto.

Los tokens se exponen mediante variables CSS y `@theme inline`, por ejemplo `bg-primary`, `text-foreground` y `border-border`. El refresh amplía los controles sin alterar la semántica del pipeline.

## Estado de integración

El [snapshot de Etapa 3](../engine/evidence/ETAPA3-PROJECT-STATE.md) separa
funcionalidad y validación. El detalle prioriza PNG, mediciones y tiempo del video;
la trazabilidad completa es desplegable. La fecha UTC proxy no se presenta como
fecha de grabación. La [guía Docker](../deployment/docker/README.md) ofrece una
ruta local alternativa con build standalone, sin sustituir el modo nativo.
