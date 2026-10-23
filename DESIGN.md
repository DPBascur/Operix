---
name: Operix
description: Espacio de revisión preventiva, industrial y analítico
colors:
  primary: "#3767e8"
  primary-dark-theme: "#6f8dff"
  surface: "#ffffff"
  background: "#f7f8fa"
  foreground: "#17191d"
  sidebar: "#101317"
  surface-dark-theme: "#12151a"
  foreground-dark-theme: "#f5f6f8"
  border: "#dde1e6"
  analysis-teal: "#2fd1c8"
typography:
  headline:
    fontFamily: "Segoe UI Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.65rem, 2.7vw, 2.25rem)"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Segoe UI Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  control: "0.75rem"
  panel: "1rem"
  pill: "999px"
spacing:
  compact: "0.5rem"
  control: "1rem"
  panel: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0.65rem 1rem"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
---

# Design System: Operix

## Overview

Industrial, analítico, moderno y profesional: el carácter acordado por el usuario. El sistema conserva el logo y los colores existentes, con una composición más clara para operar y revisar antecedentes. La expresividad se concentra en el preview ilustrativo del acceso; las pantallas de trabajo priorizan legibilidad y acciones.

## Colors

El azul identifica acciones y selección; el turquesa permanece vinculado al análisis visual. Los temas claro y oscuro usan los pares ya definidos en `globals.css`. El estado de conexión muestra texto y símbolo, no solo color. El verde del texto de conexión se oscurece en tema claro para asegurar contraste.

## Typography

Tipografía de trabajo heredada, sin nuevas fuentes descargadas. Títulos de peso medio/alto, tracking contenido y cifras tabulares en resúmenes. La información de procedencia debe seguir siendo legible; los tamaños auxiliares pequeños de pantallas heredadas no se convierten en un objetivo para nuevas vistas.

## Layout

Sidebar de 15.5rem en escritorio; menú desplegable debajo de 1024px. Contenido analítico limitado a 1600px. A tablet los resúmenes pasan a dos columnas; las gráficas se apilan en móvil. Usuarios conserva tabla en escritorio/tablet y presenta cada cuenta como fila compacta apilada debajo de 600px, con acción de edición visible. El formulario contextual pasa debajo del listado sin exigir modal.

## Elevation & Depth

Paneles planos con borde y separación tonal. No se añaden sombras ornamentales ni halos. Los controles heredados pueden mantener elevación existente; no se redefinen como norma global.

## Shapes

Controles curvos, paneles de esquina suave y pills únicamente para estados o selección compacta. Los botones de icono mantienen objetivo táctil y nombre accesible.

## Components

Botones primary, secondary, ghost, outline y destructive; tamaños default, icon y small. Hover, foco, active y disabled distinguibles. Inputs con etiqueta persistente, ayuda y error en el contexto del formulario. Indicador API con estado real de salud, no una declaración de disponibilidad GPU. Gráficas con valores textuales alternativos.

La animación del login es una composición ilustrativa de la plataforma, acotada a dos ciclos y desactivada con movimiento reducido. No se añaden animaciones al pipeline ni al reloj del preview.

## Do's and Don'ts

- Do conservar procedencia y límites junto a los datos.
- Do mantener cancelación, foco y alternativa de teclado.
- Do separar estados demo de registros reales y errores.
- Don't presentar una cuenta demo como autorización del servidor.
- Don't convertir eventos de reglas en incidentes confirmados.
- Don't cambiar geometría, percepción o reglas para favorecer una composición visual.
