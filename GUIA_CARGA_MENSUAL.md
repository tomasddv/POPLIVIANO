# Guía rápida · remito revisado en Excel

**Ejemplo 1:** remito `00015743` del `17/06/2026`. Cargalo en junio (`2026-06`) si controlás por mes; si trabajás con la base histórica Q3, podés cargarlo en Q3 con `Reemplazar cantidades anteriores` para sustituir la lectura preliminar precargada.

**Ejemplo 2:** remito `00016228` del `17/07/2026`. Cargalo en julio (`2026-07`). Nunca sumes ambos documentos en el mismo mes; Q3 histórico permite asociarlos al control trimestral por decisión manual.

1. Revisar las hojas `REMITO`: comparar el PDF original con `DESCRIPCION POP` y `CANTIDAD`. Amarillo indica la cifra heredada; rojo indica ausencia de cifra. Las líneas sin cifra quedaron inicialmente `INCLUIR=NO`.
2. Si una línea sin cifra sí debe incluirse, completar `CANTIDAD` y cambiar `INCLUIR` a `SI`. No ingresar 0 solo para ocultar una fila.
3. Guardar los Excel. En la barra lateral de Streamlit, elegir **período de carga** y subir los **Excel de asignación** en el paso 1 (si aún no existen).
4. En el paso 2 cargar uno o varios **Excel de remito revisados**. Marcar la casilla de confirmación y presionar **Preparar conciliación**.
5. Abrir **Revisión Excel de remitos** y comprobar las propuestas de *Material Excel*. Cambiar cualquiera que no corresponda con el selector visual de fotografías.
6. Pulsar **Aplicar revisión**. El consolidado se refleja en **Resumen**, manteniendo el original y las verificaciones físicas verdes.
7. Nuevos remitos del mismo mes: agregar otro Excel y repetir. Los números de remito ya importados se bloquean para no duplicar totales.

**Importante:** para corregir un remito que ya se cargó y consolidó, el reemplazo afecta **todas las cantidades de remitos de ese período**. Antes de reemplazar, guardá un respaldo del historial y volvé a subir todos los remitos que deban seguir vigentes.
