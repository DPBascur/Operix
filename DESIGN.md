---
name: Operix
description: Espacio de revisión preventiva, industrial y analítico
colors:
  primary: "#3767e8"
  primary-dark-theme: "#3b82f6"
  surface: "#ffffff"
  background: "#f7f8fa"
  foreground: "#17191d"
  sidebar: "#171b21"
  background-dark-theme: "#050607"
  background-secondary-dark-theme: "#0a0c0e"
  sidebar-dark-theme: "#0d0f12"
  surface-dark-theme: "#111418"
  surface-muted-dark-theme: "#171b20"
  foreground-dark-theme: "#f3f5f7"
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
  control: "10px dark / pill light"
  panel: "8px dark / 1rem light"
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

El azul identifica acciones, selección y datos destacados; el turquesa permanece vinculado al análisis visual. El modo oscuro usa una escala neutra: fondo `#050607`, shell `#0a0c0e`, sidebar `#0d0f12`, superficie `#111418` y elevación `#171b20`. Divisores `#232830`, texto principal `#f3f5f7` y acento `#3b82f6`. El login comparte esta familia en ambos lados. El botón primario usa texto oscuro sobre azul para conservar contraste de lectura; los campos tienen un borde funcional más visible que los divisores pasivos. El estado de conexión muestra texto y símbolo, no solo color.

## Typography

Tipografía de trabajo heredada, sin nuevas fuentes descargadas. Títulos de peso medio/alto, tracking contenido y cifras tabulares en resúmenes. La información de procedencia debe seguir siendo legible; los tamaños auxiliares pequeños de pantallas heredadas no se convierten en un objetivo para nuevas vistas.

## Layout

Sidebar de 15.5rem en escritorio; menú desplegable debajo de 1200px. Contenido analítico limitado a 1600px. A tablet los resúmenes pasan a dos columnas; las gráficas se apilan en móvil. Usuarios conserva tabla en escritorio/tablet y presenta cada cuenta como fila compacta apilada debajo de 600px, con acción de edición visible. El formulario contextual pasa debajo del listado sin exigir modal.

## Elevation & Depth

Paneles analíticos abiertos con separadores finos. En dark la navegación mantiene su posición, pero usa una superficie neutra sólida y bordes sutiles; no se apoya en glow, gradientes ni sombras decorativas. El modo claro conserva su tratamiento anterior.

## Shapes

En dark los botones tienen 10px de radio, los inputs 8px y los paneles 8px; el shell conserva un radio moderado. Los controles de estado/toggle pueden seguir siendo píldoras. El modo claro conserva sus radios existentes.

## Components

Botones primary, secondary, ghost, outline y destructive; tamaños default, icon y small. Hover, foco, active y disabled distinguibles. Inputs con etiqueta persistente, ayuda y error en el contexto del formulario. Indicador API con estado real de salud, no una declaración de disponibilidad GPU. Gráficas con valores textuales alternativos.

Motion (`motion/react`) se reserva para entrada/salida de menú móvil, entrada del editor contextual y aparición inicial de paneles; color y hover sencillos siguen en CSS. Las duraciones compartidas son 150/220/340 ms, con desplazamientos máximos de 8 px y sin rebotes decorativos. La animación ilustrativa del login se limita a un ciclo de 2,8 s y se desactiva con movimiento reducido. Los KPI no reaparecen al cambiar de período, las listas de datos permanecen estáticas y el estado de API cambia de inmediato. No se anima el video ni el pipeline.

## Do's and Don'ts

- Do conservar procedencia y límites junto a los datos.
- Do mantener cancelación, foco y alternativa de teclado.
- Do separar estados demo de registros reales y errores.
- Don't presentar una cuenta demo como autorización del servidor.
- Don't convertir eventos de reglas en incidentes confirmados.
- Don't cambiar geometría, percepción o reglas para favorecer una composición visual.
