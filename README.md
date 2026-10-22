# Reporte operativo de movimientos de Ecobici

**Programación Orientada a Datos – Licenciatura en Ciencia de Datos – UCA 2026**
**Trabajo Práctico 2 **
**Alumna:**Ernestina Berthet

## 1. Problema

Quien revisa la operación de una red de bicicletas necesita consolidar salidas y llegadas por estación
y período. Los registros incompletos o inconsistentes pueden alterar los balances.

## 2. Usuario y solución propuesta

**Usuario:** persona que analiza la operación de la red y necesita un reporte repetible por
estación y franja temporal.

**Solución:** una aplicación de consola en Python que:

1. carga viajes desde un archivo CSV o JSON;
2. valida cada registro y aparta los inválidos con el motivo del rechazo;
3. selecciona los viajes cuyo **inicio** cae dentro del período pedido;
4. registra, para cada viaje seleccionado, una **salida** en la estación de origen y una
   **llegada** en la de destino;
5. genera un reporte por estación con salidas, llegadas y **balance neto** (llegadas − salidas).

## 3. Alcance de la primera versión

**Incluye:** lectura de CSV y JSON, validación con registro de rechazos, selección de período por
inicio del viaje, balance por estación, pruebas automatizadas, exportación del reporte y un gráfico.

**No incluye:** stock de bicicletas disponible (el balance no tiene inventario inicial ni
reposiciones), duración o distancia de los viajes, ni interfaz gráfica o web.

## 4. Estructura prevista

```text
tp2-apellido/
|-- README.md
|-- requirements.txt
|-- .gitignore
|-- src/
|-- tests/
|-- data/
`-- outputs/
```


