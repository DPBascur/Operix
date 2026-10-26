# Datos de demostración de NVIDIA

Los clips de `assets/demo/` proceden del dataset de terceros
**NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes**, proveedor
NVIDIA, revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`.
Se incluyen para reproducir y demostrar el prototipo Operix; no son material
original ni propiedad de Operix.

- Dataset: https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes
- Licencia indicada para el dataset: **OpenMDW-1.1**.
- Texto oficial de la licencia: https://openmdw.ai/license/1-1/
- Se conserva el mismo contenido textual de la licencia OpenMDW-1.1 en [LICENSE-OpenMDW-1.1.txt](LICENSE-OpenMDW-1.1.txt), obtenido del [texto plano oficial](https://raw.githubusercontent.com/OpenMDW/OpenMDW/refs/heads/main/1.1/LICENSE.OpenMDW-1.1); los saltos de línea pueden diferir.

| Escenario y uso | Archivo incluido | Origen y SHA-256 |
| --- | --- | --- |
| `forklift_human_nearmiss`, entrada de OP-34, cámara `ceiling_00`, 300 frames | [forklift_human_nearmiss_ceiling00.mp4](../../assets/demo/forklift_human_nearmiss_ceiling00.mp4) | `001e53453441935632ae_run_1_seed_1288693302.ceiling_00.rgb.mp4`; `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B` |
| `warehouse_fire`, entrada de OP-35/60/61, cámara `ceiling_04`, 277 frames | [warehouse_fire_ceiling04.mp4](../../assets/demo/warehouse_fire_ceiling04.mp4) | `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4`; `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |
| `warehouse_fire`, resultado visual de Operix documentado en OP-60/61 | [warehouse_fire_ceiling04_operix_annotated.mp4](../../assets/demo/warehouse_fire_ceiling04_operix_annotated.mp4) | Video anotado con los cuadros del clip anterior; `EA5B640009071D63D7EC756690E4437182C6DBCDD468CFE78DB0E4757735811A` |

La atribución de los datos de entrada y del material visual subyacente corresponde
al proveedor del dataset. Los pesos del modelo, los JSONL de ejecución y otros
artefactos locales no se incluyen aquí.

## Demo actual del candidato v0.2.0

La [captura actual](../../assets/demo/v0.2.0/analysis-result.png) contiene
píxeles derivados de `warehouse_box_pickup`, archivo de entrada
`008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4`, cámara `cam_00`;
SHA-256 del input:
`eabf44d7abe50d1bf4824f238a9f0ac9ddc29419e10d66b89c6a92cb1b98329c`.
Ese input y el video de QA no se redistribuyen en Git. Los píxeles NVIDIA
visibles en la captura conservan la atribución y licencia OpenMDW-1.1 indicada
arriba. La UI y superposiciones pertenecen al prototipo Operix, sin atribuirle la
autoría del material sintético subyacente. No son registros de una empresa ni
validación industrial. Identidad del input, captura y videos externos de QA:
[recibo de demo](../../assets/demo/v0.2.0/metadata.json).
