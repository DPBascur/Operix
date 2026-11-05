# Etapa 4 · Verificación de inconsistencias funcionales P1

La auditoría inicial se conserva como registro de los defectos. Las cuatro regresiones siguientes se ejecutaron primero sobre `4af4b3a5`, con el control de publicación de E4-01 vigente.

| Hallazgo | Reproducción y causa | Corrección y resultado |
| --- | --- | --- |
| E4-03 | Crear Demo A y enviar `PUT zone/` con `profile=B`. Devolvía 200 y cambiaba perfil y zona sin cambiar el clip. | Devuelve 409 y conserva fuente, huella, perfil y zona. Demo B se crea en otra sesión. Un video manual empieza sin zona y puede cambiar de perfil conservando su propio polígono. |
| E4-04 | Con resultado completo, pedir `result/?run=999` con `Range`. Devolvía 206 con el video vigente porque la vista ignoraba el parámetro. | Una ejecución inexistente, previa o ajena devuelve 404. Un parámetro vacío o duplicado devuelve 400. El run vigente acepta Range y abre el archivo bajo el mismo bloqueo que valida el run. |
| E4-02 | Aplicar un polígono cruzado, con vértices consecutivos repetidos, colineal o con lados solapados. La API solo comprobaba cardinalidad y coordenadas y devolvía 200. | La API llama a la validación geométrica del Motor con un tiempo máximo de cinco segundos. Devuelve 400 sin alterar el perfil ni la zona. Acepta un polígono cóncavo válido y responde 503 si el validador no está disponible. |
| E4-05 | Comparar `/rules` con la configuración de Demo C. La página mostraba ejemplos estáticos y el estado de sesión carecía del snapshot preparado. | El catálogo muestra los perfiles que carga el servidor. Análisis separa reglas preparadas, en ejecución y del resultado. La prueba compara la huella SHA-256 del JSON del Motor con el snapshot preparado, el resultado y la fuente del evento persistido, incluso si el archivo base cambia después de preparar la sesión. |

## Alcance y compatibilidad

- El validador usa el Python del Motor ya configurado. Así el Backend nativo conserva su entorno separado y ambas capas aplican la misma geometría.
- El enlace de resultado que omite `run` conserva el acceso al resultado vigente. Los resultados temporales previos siguen fuera de retención. En Windows, una reproducción que mantenga el archivo abierto puede requerir cerrar el reproductor y reintentar.
- Las reglas siguen configurándose en JSON del servidor. La UI muestra los parámetros declarados del snapshot, incluida la zona remapeada de una fuente manual. Los valores internos que el Motor derive por defecto siguen consultándose en el evento emitido. Una sesión abierta conserva su perfil cargado y una sesión nueva toma la versión vigente del JSON.
- La API añade campos opcionales para la UI. Eventos históricos y persistencia mantienen sus contratos. Las vistas muestran una indicación de indisponibilidad cuando falta un snapshot.

## Reproducción automatizada

- Backend desde `backend/` con el entorno PostgreSQL habitual y Python del Motor configurado. `python -B manage.py test --noinput` ejecuta `AnalysisSessionApiTests`, el recorrido `WebPersistenceTests` y los controles de publicación.
- Motor desde la raíz con su entorno. `python -B -m unittest discover -s engine/tests`.
- Frontend desde `frontend/`. `pnpm test`, `pnpm lint`, `pnpm typecheck` y `pnpm build`. La prueba `tests/browser/analysis-flow.test.mjs` usa `tests/fixtures/analysis-api.mjs` para verificar reglas, transiciones de fuente y resultado sin requerir inferencia.

## Resultados

- Backend con PostgreSQL. 134 aprobadas. Motor. 427 aprobadas y dos omitidas. Frontend. 41 aprobadas, lint y comprobación de tipos correctos. Compilación web correcta en un entorno de prueba con dependencias enlazadas, con advertencia de trazado del empaquetado standalone en esa copia.
- Chromium con API fixture. Una prueba integral aprobada. Verificó el catálogo y los snapshots antes y después del análisis, cambios de fuente, edición de zona, reproducción, histórico y evidencia. La comparación de temas espera a que cargue el detalle del evento.
- Demo C con pesos reales, CUDA y PostgreSQL aislado. 418/418 frames, dos eventos persistidos, PNG de proximidad recuperado con 200 y resultado vigente con Range 206. El run 999 devolvió 404. El evento de proximidad conservó regla `TEST_DATA_PAIR` v1, distancia normalizada 0.12882, máximo 0.25, duración de 1 s y la misma huella de configuración que el resultado.
- E4-01. La publicación autorizada del Motor persistió eventos y evidencia. Los POST anónimos de evento y PNG, repetidos por el proxy del frontend, devolvieron 403 y no causaron escrituras.
