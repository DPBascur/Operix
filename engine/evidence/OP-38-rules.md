# OP-38 — Motor de reglas configurables

## Objetivo, criterio y dependencias

OP-38 evalúa variables descriptivas ya calculadas por OP-37 contra reglas de OP-30. Su criterio de cierre es: “La regla genera un evento cuando todas sus condiciones se cumplen y no lo genera cuando alguna condición requerida falla.” La evidencia esperada son pruebas positivas y negativas. Dependencias formales: OP-11, OP-30 y OP-37. OP-11 aporta el marco de reglas operacionales; OP-30 define y carga `RuleConfig`; OP-37 produce `FrameSpatialState` con pertenencia y permanencia. Aquí “evento” es solo un `EventCandidate` transitorio, no persistido.

> La IA percibe el entorno; las reglas interpretan el contexto.

`operix_engine.rules.RuleEngine` no abre videos, detecta, sigue objetos ni recalcula geometría, permanencia o proximidad. Tampoco consulta base de datos ni persiste resultados. Consume únicamente el estado de OP-37 y la configuración de OP-30.

## Primera regla y configuración

El ejemplo [`op30-zone-rule.json`](../config/examples/op30-zone-rule.json) conserva `rule_id`, `version`, `enabled` y `parameters`, y añade `kind=zone_dwell`, `class_name=person`, `zone_id=zona_critica_01`, `min_duration_s=2.0`. `RuleEngine` valida que los cuatro parámetros estén presentes, sean de los tipos correctos, que la zona exista en la configuración y que el umbral sea finito y no negativo. Rechaza tipos de regla no soportados y claves adicionales. `RuleConfig` sigue validando la estructura JSON general y conserva los parámetros inmutables.

La condición se satisface únicamente si la regla está habilitada, la clase del objeto coincide, existe la observación de la zona configurada, `inside == true` y `dwell_time_s >= min_duration_s`. La comparación es inclusiva en el umbral. Una clase diferente, zona ausente, objeto fuera de la zona, permanencia insuficiente o regla deshabilitada no emiten candidatos. El motor devuelve una `RuleEvaluation` por regla y objeto observado, con `evaluated`, `satisfied`, motivo simple, variables observadas y parámetros usados.

**El umbral temporal utilizado es un parámetro experimental configurable y no representa un umbral universal de seguridad.** No se incorpora proximidad en esta primera regla.

## Emisión y estado temporal

La clave de activación es `(rule_id, rule_version, track_id, zone_id)`. `false → true` emite un candidato; `true → true` no duplica; `true → false` rearma. Un track ausente deja de estar activo y una futura satisfacción puede emitir otro candidato. Un salto en el índice de frame limpia el estado activo; OP-37 ya corta la permanencia y OP-38 no reconstruye continuidad. `reset()` inicia otra sesión con la misma configuración. Para cambiar regla, versión o parámetros se construye un `RuleEngine` nuevo; su estado no se hereda de la instancia anterior.

`EventCandidate` es inmutable y conserva identificador/versión de regla, frame y tiempo de video, track, clase, zona, copia inmutable de parámetros, pertenencia observada y permanencia observada. No contiene ID persistente, reloj civil, usuario ni clasificación de riesgo.

**Un EventCandidate representa el cumplimiento de una regla configurada; no constituye por sí mismo la clasificación de un accidente, Near Miss, infracción o responsabilidad.** OP-39 podrá encargarse después de la persistencia y gestión de eventos, sin convertir automáticamente este candidato en una conclusión preventiva validada.

## Pruebas controladas

[`test_rules.py`](../tests/test_rules.py) usa tracks sintéticos y `SpatiotemporalAnalyzer` de OP-37 a 2 FPS, sin YOLO ni ByteTrack. Comprueba condición positiva y negativas (fuera, permanencia corta, clase, zona, regla deshabilitada); igualdad y valor superior al umbral; cambio de umbral por configuración; identidad, versión e inmutabilidad de parámetros; transiciones y rearmado; tracks independientes; ausencia y gap; configuración inválida, tipo no soportado, `reset()` y orden temporal. Una permanencia sintética de frames `0...4` a 2 FPS llega exactamente a `2.0 s` y emite un candidato; el frame siguiente continúa verdadero sin duplicación. La prueba negativa de la ventana OP-37 `139...147` conserva máximo `0.2 s` y no puede satisfacer `2.0 s`.

## Comprobación reproducible sobre tracks del dataset

Se reutilizó el JSONL local de OP-60/OP-35 para la muestra sintética NVIDIA `ceiling_04`, sin volver a ejecutar inferencia. SHA-256 del JSONL de entrada: `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`. Resolución `1920×1080`, `30 FPS`. El JSONL y el video permanecen fuera del repositorio.

Desde la raíz del repositorio, reemplazando el marcador con la ruta local del JSONL:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\evaluate_rules.py '<ruta-al-jsonl-de-tracks>' --expected-jsonl-sha256 ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5 --config .\engine\config\examples\op30-zone-rule.json --view-id ceiling_04 --width 1920 --height 1080 --fps 30 --end-frame 259
```

La comprobación procesó `260` frames consecutivos (`0...259`) y produjo **un** candidato: regla `restricted_zone_presence` v1, track `31`, frame `201`, tiempo de video `6.7 s`, zona `zona_critica_01`, permanencia observada `2.0 s`. El track entra a la zona en el frame `141`; antes del umbral la condición es falsa y después sigue verdadera sin candidatos duplicados en este intervalo. Esta muestra es sintética del dataset, no una medición de verdad-terreno operacional.

Se delimitó explícitamente la reproducción en `259`: siete cajas del track 36 en frames `260...266` sobrepasan el ancho `1920` del frame y OP-37 las rechaza. No se recortaron cajas ni se alteró OP-37 para ocultarlo. Por ello esta comprobación de OP-38 **no afirma haber evaluado los 277 frames**. El tramo continuo usado sí contiene la transición positiva y la persistencia posterior necesarias para esta regla. La detección de cajas fuera de límites es una limitación de datos de entrada para una futura integración del pipeline espacial.

## Resultados y limitaciones

La validación local aprobó **21/21 pruebas específicas** y **128/128 pruebas de la suite completa**, con las dos integraciones reales existentes habilitadas. `pip check`, `check_environment.py --require-cuda` (RTX 3070 y operación tensorial CUDA/CPU), `compileall` y `git diff --check` aprobaron. La suite no reejecuta el replay de 260 frames: este se comprobó aparte con el comando anterior.

La salida de candidatos depende de detecciones/tracks y variables previas; un ID fragmentado, perdido o espurio puede alterar la permanencia y la emisión. Los IDs son temporales y no identifican personas. La zona es ilustrativa, el material es sintético, no hay ground truth de riesgo y el umbral no fue validado con expertos. COCO no contiene una clase explícita `forklift`; esta regla inicial solo usa `person` y no demuestra evaluación fiable de interacción con maquinaria. No se declara Near Miss ni funcionamiento preventivo completo.
