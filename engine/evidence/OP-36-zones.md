# OP-36 — Definición y pertenencia a zonas

## Objetivo y alcance

Criterio del Backlog V0.9: «Se define, guarda y recupera al menos una zona; el
sistema determina si un objeto está dentro o fuera». Evidencia esperada: «Archivo
de zonas y prueba dentro/fuera». Dependencias: OP-22 y OP-30.

Se reutiliza [el JSON de OP-30](../config/examples/op30-zone-rule.json), que
guarda la zona `zona_critica_01` para la vista `ceiling_04` con vértices
normalizados `(0.20, 0.20)`, `(0.55, 0.20)`, `(0.55, 0.70)` y `(0.20, 0.70)`.
`load_operational_config()` recupera ese archivo como `OperationalConfig` y
`Zone`; no se duplicó ningún modelo ni se añadió un formato nuevo. Los valores
de la zona son demostrativos, no límites de seguridad validados.

## Geometría implementada

`operix_engine.zone_geometry` expone `NormalizedPoint`,
`normalized_bottom_center(box, width, height)`, `point_in_zone(point, zone)` y
`bbox_in_zone(box, zone, width, height)`. El módulo recibe `BoundingBox` en
píxeles del frame original y `Zone` en coordenadas normalizadas; no depende de
YOLO, ByteTrack ni OpenCV.

El punto representativo de la caja es el **centro inferior**:

```text
x = (x_min + x_max) / (2 × width)
y = y_max / height
```

Es una aproximación al apoyo del objeto **en el plano de imagen**. No representa
una posición física ni una distancia en metros. Su fidelidad depende de
perspectiva, encuadre, oclusiones y calidad de la caja; en una vista casi cenital
el borde inferior no necesariamente coincide con los pies. No se implementan
homografía ni calibración de cámara.

La pertenencia usa cruce de rayos (regla par/impar) con comprobación previa de
punto sobre segmento. Un punto estrictamente interior, sobre un borde o sobre un
vértice se considera **dentro**; un punto exterior se considera **fuera**. La
tolerancia numérica de borde es `1e-12` en coordenadas normalizadas. Una caja
cuenta como dentro solo cuando lo está su centro inferior, incluso si otra parte
de la caja se superpone con el polígono. No se calcula porcentaje de solapamiento.

Se exigen dimensiones enteras positivas y cajas completamente dentro de los
límites del frame, sin recorte silencioso. `BoundingBox` ya rechaza coordenadas
no finitas, negativas y cajas de ancho/alto no positivo; `NormalizedPoint`
rechaza puntos no finitos o fuera de `[0,1]`. `Zone` de OP-30 comprueba la
estructura y el rango de los vértices. Antes de evaluar pertenencia, OP-36
rechaza lados nulos, área nula, lados adyacentes superpuestos e intersecciones
entre lados no adyacentes. Esta comprobación es geométrica: OP-30 sigue siendo
solo el cargador estructural y no garantiza por sí mismo validez topológica.
El polígono se expresa sin repetir el primer vértice al final.

## Pruebas unitarias

```powershell
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -p test_zone_geometry.py -v
```

Las pruebas cubren carga y recuperación de la zona de OP-30, interior/exterior,
cuatro bordes y cuatro vértices, normalización del centro inferior, caja
parcialmente superpuesta cuyo punto queda fuera, invariancia entre resoluciones,
dimensiones inválidas, caja fuera del frame, coordenadas no finitas, vértices
insuficientes, área nula, autointersección, vértice repetido, solapamiento de
lados y polígono cóncavo en ambos órdenes de vértices.

Resultado de la validación local: **16/16 pruebas OP-36 aprobadas**.
La suite completa, incluidas las integraciones reales existentes de YOLO y
ByteTrack, aprobó **91/91**. `pip check` informó que no hay dependencias rotas;
`check_environment.py --require-cuda` confirmó pruebas tensoriales CPU/CUDA,
OpenCV y NVIDIA GeForce RTX 3070; `compileall` terminó sin errores.

## Comprobación tabular sobre `ceiling_04`

Se utilizó el video sintético público ya identificado por OP-35/OP-60/OP-61:
`00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4`, SHA-256
`3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`.
OpenCV confirmó 1920×1080, 30 FPS y 277 frames; los frames 0 y 141 se
decodificaron correctamente. Las cajas reales se recuperaron del JSONL de
tracking previamente generado en la ejecución integrada de OP-61 (SHA-256
`ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`).
No se repitió la inferencia ni se guardaron nuevos medios en el repositorio.

| Frame | `track_id` | Clase | Caja `xyxy` en píxeles | Centro inferior normalizado | `zona_critica_01` |
| --- | ---: | --- | --- | --- | --- |
| 0 | 1 | `person` | `(1177.5587, 675.5476, 1222.7274, 797.2106)` | `(0.625075, 0.738158)` | Fuera |
| 141 | 31 | `person` | `(629.6606, 584.6583, 655.8845, 651.5026)` | `(0.334777, 0.603243)` | Dentro |

El resultado es exclusivamente geométrico: no interpreta presencia en zona como
riesgo ni demuestra identidad humana permanente. El JSONL empleado permaneció
fuera de Git; posteriormente se incorporó una copia verificada del video de
entrada en [`assets/demo`](../../assets/demo/README.md). La normalización no
vuelve intercambiables vistas, recortes o perspectivas distintos; la zona está
asociada a `view_id=ceiling_04`.

## Límite y continuidad

**OP-36 determina pertenencia espacial en el plano de imagen. No calcula
distancia física, permanencia, proximidad, riesgo ni eventos.**

OP-37 podrá asociar el resultado booleano de cada frame con `track_id`,
`frame_index`, referencia temporal y `zone_id`, y entonces estudiar continuidad
temporal. OP-36 no acumula estados ni modifica detector, tracker o reglas.
