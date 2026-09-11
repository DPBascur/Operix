# OP-16 — Investigación de datasets públicos

## Objetivo y alcance

Esta evidencia identifica datasets públicos con personas, maquinaria y escenarios
industriales aplicables al prototipo de Operix. La comparación se limita a fuentes
documentadas y evalúa su utilidad para RF-01, RF-02 y R-01. No se descargaron datos
adicionales para realizar esta investigación.

Consulta realizada el 10 de septiembre de 2026.

## Matriz comparativa

| Criterio | NVIDIA PhysicalAI SDG-Warehouse | Video Dataset for Safe and Unsafe Behaviours | TOMIE Dataset | VIRAT Video Dataset |
| --- | --- | --- | --- | --- |
| Rol en la evaluación | Candidato principal | Alternativa principal de contraste | Candidato complementario | Alternativa descartada para el PoC base |
| Dominio o escenario | Almacén sintético; eventos de seguridad industrial, incluida proximidad persona–montacargas | Fábrica real; conductas seguras e inseguras observadas por cámaras de vigilancia | Almacén experimental real; movimiento de entidades logísticas | Vigilancia real en espacios exteriores con personas y vehículos |
| Tipo de datos | Clips de video RGB sintético y artefactos multimodales | Clips de video RGB real | Secuencias sincronizadas de imágenes RGB y datos de captura de movimiento | Video RGB real desde cámaras terrestres y aéreas |
| Volumen | 122.967 clips, unas 412 horas; escenario `forklift_human_nearmiss`: 27.939 clips y 549 GiB RGB | 691 clips; aproximadamente 10 GB en el espejo público consultado | 112.860 frames, aproximadamente 16 minutos y 640.936 instancias de entidades | Release 2.0 terrestre: aproximadamente 8,5 horas de video HD en 11 escenas |
| Resolución y FPS | 1920 × 1080, 30 FPS; clips de 10 o 15 s según escenario | 1920 × 1080, 24 FPS; clips de 1 a 20 s | Cámaras RGB de 2 MP; promedio aproximado de 20 FPS | Calidad y frecuencia variables; versiones HD y reducidas, entre 2 y 30 FPS |
| Clases o entidades relevantes | Persona, montacargas, estanterías, cajas y elementos del almacén según escenario | Persona, montacargas y ocho clases de conducta: tránsito por pasillo, intervención en equipos, estado de panel y carga segura o sobrecarga | Montacargas, pallets, contenedores, barriles, cajas y portacargas | Personas, vehículos y actividades de interacción persona–vehículo |
| Anotaciones | Bounding boxes 2D y 3D, segmentación de instancia, profundidad, parámetros de cámara, metadatos y seed reproducible | Etiqueta de comportamiento a nivel de clip. El artículo informa bounding boxes en una selección de frames, pero el espejo público revisado documenta principalmente clasificación de video y no identidades persistentes | Bounding boxes 2D, visibilidad, identificación de entidad y pose 3D derivada de captura de movimiento | Tracks completos de objetos móviles, tipos de objeto y anotaciones de actividades según la versión |
| Utilidad para detección | Alta: contiene explícitamente persona y montacargas con anotaciones ricas | Media: dominio real y objetos relevantes, pero la distribución pública necesita verificación adicional para confirmar las anotaciones por frame disponibles | Media para maquinaria industrial; no contiene personas como entidad objetivo | Media para persona y vehículos genéricos; baja correspondencia con montacargas |
| Utilidad para tracking | Alta: video continuo, vistas sincronizadas y anotaciones temporales | Baja a media: existe continuidad temporal, pero no se documentan IDs de tracking en el paquete público revisado | Alta para entidades logísticas; fue evaluado con ByteTrack, BoT-SORT y SiamMOT | Alta como benchmark general de tracking de objetos móviles |
| Licencia o acuerdo | OpenMDW-1.1 | CC BY 4.0 para el dataset publicado en Mendeley | No se encontró una licencia explícita en el repositorio público; debe confirmarse antes de reutilizar el contenido | Acuerdo de uso VIRAT; exige proteger PII y restringe la redistribución |
| Facilidad de acceso | Metadatos pequeños y streaming por shards WebDataset; el escenario completo es demasiado grande para el equipo actual | Alta: clips MP4 individuales disponibles; el espejo permite evitar la descarga total | Baja: el repositorio consultado contiene herramientas y calibración, pero no presenta claramente el payload completo ni su licencia | Media: acceso público sujeto a aceptación del acuerdo de uso |
| Representatividad | Alta para la interacción objetivo; limitada por ser simulación | Alta por provenir de una fábrica real; limitada a una instalación y dos cámaras | Alta para maquinaria y operación logística real; baja para interacción persona–equipo | Alta para vigilancia real; baja para el dominio industrial de Operix |
| Limitaciones principales | Brecha simulación–realidad, gran volumen, shards de unos 5 GiB e iluminación sintética | No representa explícitamente una condición de proximidad persona–montacargas; clases y protocolos dependen de la instalación | No incluye personas como objetivo y falta confirmar licencia y disponibilidad completa | No es un entorno de almacén, no identifica montacargas y tiene condiciones de uso más restrictivas |

## Evaluación por candidato

### NVIDIA PhysicalAI SDG-Warehouse

Es el candidato con mayor correspondencia directa con el PoC: ofrece video continuo
de una interacción persona–montacargas, permite reproducir cada run mediante su seed
y dispone de anotaciones útiles para futuras evaluaciones. El escenario es sintético,
por lo que no representa por sí solo la variabilidad de una instalación real. El acceso
por metadatos y streaming permite utilizar muestras acotadas sin descargar los 549 GiB
del escenario.

### Video Dataset for Safe and Unsafe Behaviours

Es el contraste principal porque contiene video real de una planta industrial, personas,
montacargas y tomas de vigilancia. Sus clips son cortos e individualmente accesibles.
Las clases relacionadas con montacargas describen carga segura o sobrecarga, no una
interacción de proximidad con personas. Las anotaciones documentadas en el espejo son
principalmente etiquetas de comportamiento por clip, por lo que su utilidad directa para
evaluar tracking es menor que la de NVIDIA.

### TOMIE Dataset

Es una referencia complementaria para tracking de maquinaria: se grabó en un almacén
experimental real con seis cámaras y contiene identificadores y poses de entidades. No
incluye personas como entidad objetivo y el repositorio público consultado no declara
claramente la licencia ni distribuye de forma evidente todo el contenido. Estas
limitaciones impiden seleccionarlo como muestra base, aunque sigue siendo útil como
antecedente técnico.

### VIRAT Video Dataset

VIRAT contiene video real, actividad persona–vehículo y tracks completos, pero sus
escenas exteriores y vehículos genéricos tienen menor correspondencia con el escenario
industrial de Operix. Además, su acuerdo de uso exige controles adicionales sobre PII y
redistribución. Se descarta para el PoC base, sin negar su valor como benchmark general.

## Resultado de OP-16

La investigación identifica y documenta dos candidatos aplicables: NVIDIA PhysicalAI
SDG-Warehouse y Video Dataset for Safe and Unsafe Behaviours. NVIDIA presenta el mejor
ajuste al escenario persona–equipo móvil y a las necesidades de detección y tracking;
el segundo dataset aporta el contraste de video industrial real. TOMIE complementa el
análisis de tracking industrial y VIRAT se descarta por su menor ajuste al dominio.

Esta evidencia habilita la decisión formal de datos de OP-18. La selección final y su
justificación se mantienen en la evidencia correspondiente a esa tarea.

## Fuentes

- NVIDIA PhysicalAI SDG-Warehouse: https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes
- OpenMDW-1.1: https://openmdw.ai/license/1-1/
- Video Dataset for Safe and Unsafe Behaviours, fuente original: https://data.mendeley.com/datasets/xjmtb22pff/1
- Video Dataset for Safe and Unsafe Behaviours, espejo con clips individuales: https://huggingface.co/datasets/Voxel51/Safe_and_Unsafe_Behaviours
- TOMIE, artículo: https://doi.org/10.1186/s13640-024-00623-6
- TOMIE, repositorio: https://github.com/FLW-TUDO/TOMIE-Dataset
- VIRAT Video Dataset: https://viratdata.org/
