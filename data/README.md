# Datos del reporte de movimientos

## Procedencia

| Aspecto | Detalle |
|---|---|
| Tipo de datos | Datos **simulados** con la estructura de un registro de viajes de bicicletas públicas. **No son viajes reales de Ecobici** |
| Responsable | Autor/a del trabajo |
| Procedimiento de obtención | Se generan con `python -m src.generar_muestra` (NumPy, semilla 2026). El mismo script escribe `viajes.csv` y `viajes.json` con idéntico contenido |
| Fecha de creación | 21/10/2026 |
| Licencia / condiciones de uso | Sin datos personales ni sensibles; uso libre con fines académicos |

## Archivos

- `viajes.csv` y `viajes.json`: el mismo contenido en dos formatos. El JSON es una lista de objetos
  (uno por viaje) y `null` indica un valor faltante; en el CSV un valor faltante es un campo vacío.

## Unidad de análisis

- **Entrada:** cada fila es un **viaje** (una salida de una estación y una llegada a otra).
- **Salida:** cada fila del reporte es una **estación** dentro de un período solicitado.

## Variables de la entrada

| Variable | Regla |
|---|---|
| `viaje_id` | `V` seguida de 5 dígitos (por ejemplo `V00001`); único |
| `inicio` | fecha y hora de salida, formato `AAAA-MM-DD HH:MM:SS`, que exista en el calendario |
| `fin` | fecha y hora de llegada, mismo formato; debe ser **posterior** al inicio |
| `estacion_origen` | código de 3 dígitos (por ejemplo `001`); no puede faltar |
| `estacion_destino` | código de 3 dígitos; no puede faltar |

Los códigos de estación son **texto**: se conserva el cero inicial (`001`, no `1`). Por eso la
aplicación lee todas las columnas como texto y convierte los tipos al validar.

## Cantidad de observaciones

413 filas: **400 viajes correctos** (12 estaciones, del lunes 14 al domingo 20 de septiembre de 2026)
y 13 registros con errores deliberados. Supera el mínimo de 50 observaciones y 3 variables pedido
en la consigna.

## Registros inválidos incluidos a propósito

Identificador con mala forma y duplicado, fecha con otro formato, fechas inexistentes (30 de
febrero, 31 de septiembre), fin anterior o igual al inicio, estación de origen o destino
faltante o con mala forma, y fin o inicio faltantes.

## Limitaciones

Los datos son sintéticos: sirven para probar la aplicación y no permiten sacar conclusiones sobre
la operación real de Ecobici. Los viajes se sortean con probabilidades distintas por estación,
pero sin geografía ni lógica de reposición. Para usar datos públicos reales habría que adaptar los
nombres de columnas y el formato de fecha a los del archivo elegido.
