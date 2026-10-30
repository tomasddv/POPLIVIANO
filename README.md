# Control POP Liviano · Distribuidora del Valle

## Nueva versión: el remito se controla en Excel antes de importarlo

El tablero mantiene la asignación DDV (Excel de referencia), la galería de fotografías de cada POP, las verificaciones físicas con tilde verde, los filtros por Q3/Q4 o mes y el guardado de historial. **Ya no utiliza la lectura de fotografías para sumar unidades automáticamente.**

### Flujo de trabajo

1. **Opcional: convertir foto/PDF a Excel BORRADOR.** En la barra lateral, abrí `0 · Convertir fotografía/PDF a Excel (borrador)`, subí las páginas de un único remito, escribí número y fecha y descargá el `.xlsx`. La calidad del OCR puede ser imperfecta.
2. **Revisar Excel.** Compará el borrador con la foto/PDF, corregí `DESCRIPCION POP`, `CANTIDAD`, y `INCLUIR` (SI/NO). Cantidades sin lectura aparecen en rojo y se excluyen hasta corregirlas. Las cantidades heredadas se destacan y siempre requieren revisión.
3. **Cargar asignación DDV.** En `1 · Subir VARIOS Excel de asignación del mes`, subí los archivos que definan lo que se debe recibir. Solo se incluyen los materiales asignados a DDV. No sumes snapshots acumulativos.
4. **Cargar remitos corregidos.** En `2 · Excel de remitos revisados`, subí uno o varios `.xlsx` con pestaña `REMITO`; marcá la casilla de revisión y presioná `Preparar conciliación desde los Excel revisados`.
5. **Confirmar las correspondencias.** En la solapa `Revisión Excel de remitos`, verificá que `Material Excel` corresponda a la descripción; si hay dudas, usá el selector con fotografías. Presioná `Aplicar revisión a este período` para sumar cantidades.
6. **Ver resultados.** En `Resumen` se muestra asignado vs. remito original vs. conciliado; en `Galería` se puede marcar la verificación física. El valor original de la recepción no se borra.

### Formato mínimo de remito Excel

Hoja `REMITO` (se aceptan múltiples hojas con estructura equivalente):

- `REMITO`: número de remito, p. ej. `00015743`.
- `FECHA`: `AAAA-MM-DD` (o `DD/MM/AAAA`).
- `DESCRIPCION POP`: nombre del material tal como aparece en el remito.
- `CANTIDAD`: unidades enteras (no se sustituye con la cantidad asignada).
- `INCLUIR`: `SI` o `NO`, opcional. `NO` excluye la fila de la importación sin borrarla del Excel.
- Opcionales: `COLUMNA`, `FILA`, `ORIGEN CANTIDAD`, `OBSERVACIONES`, `REFERENCIA`.

Cada archivo puede tener varias páginas del **mismo remito** como filas o varias hojas. Para evitar duplicaciones, un mismo número de remito no se puede volver a sumar al período; para corregirlo, utilizá `Reemplazar cantidades anteriores` (que reemplaza las recepciones de ese período completo).

### Consolidación mensual

- Creá/seleccioná un mes `AAAA-MM` en la barra lateral. Los Excel de remito deben tener fecha de ese mismo mes; Q3 y Q4 son históricos independientes.
- Podés incorporar **hasta 15 Excel de asignación** y **20 Excel de remitos por lote**, y después sumar más.
- Dos remitos con el mismo número no se suman dos veces, aunque sus archivos tengan nombres distintos.
- Si seleccionás Q3 2026, el primer reemplazo de remitos revisados sustituye el registro provisional precargado (para evitar doble contabilización).

### Almacenamiento en la nube

Para que los datos sobrevivan a un reinicio de Streamlit Cloud, configurá el repositorio **privado** de datos con Secrets:

```toml
DATA_GITHUB_REPO = "usuario/repositorio-privado-de-datos"
DATA_GITHUB_TOKEN = "TOKEN_PRIVADO_CON_PERMISO_CONTENTS_WRITE"
DATA_GITHUB_BRANCH = "main"
APP_PASSWORD = "CONTRASENA_OPCIONAL"
```

No subas el token al repositorio público. Se preserva la compatibilidad con respaldos de versiones previas; también podés exportar el JSON de todos los períodos.

### Desplegar o actualizar en GitHub

Subí el contenido **de este ZIP** a la raíz del repositorio de la aplicación (no al repositorio privado de datos) y hacé Commit. Conservá `.streamlit/`, `data/`, `app.py`, `remito_excel.py`, `convertidor_remitos.py`, `period_store.py`, `requirements.txt` y los demás módulos. En Streamlit Community Cloud, la entrada es `app.py`.

### Alcance y límites

Los archivos Excel editados son la fuente controlada de la recepción. El *match* texto/POP sigue siendo aproximado y se revisa antes de aplicar. La conversión opcional imagen → borrador todavía usa OCR y **no certifica cantidades**. La aplicación muestra solo el catálogo con asignación DDV positiva; otros renglones del remito pueden permanecer en el Excel con `INCLUIR=NO` para auditoría.

No se ha comprobado el despliegue en la cuenta Streamlit Cloud del usuario. Las pruebas de módulos y conciliación sí se ejecutaron en entorno local.

## Compatibilidad con Q4 2026 · V12 (corrección del importador)

La aplicación admite tanto el formato GS Q3 como el archivo **`Q4. Asignacion Pop Liviano V12 - Compartido con Regiones.xlsx`**, sin tener que modificar el Excel:

- **Q3:** materiales en distintas filas superiores, identificadas por encabezados `CANTIDAD`.
- **Q4 V12:** nombres de materiales en **fila 2**, asignaciones de **Distribuidora del Valle S.A. en fila 142** (columna **D**), cantidades por material a partir de la columna **E**. La fila 6 contiene totales nacionales **que NO se usan** como asignación DDV.
- Las hojas de administración (`INICIO`, `CONTROL`, `REGLAS`, `PEGAR ASIGNACION`, `MAESTRO`) se ignoran. Se siguen leyendo las hojas ocultas con asignaciones POP reales cuando corresponda (ej. Q3).
- Q4 incluye la hoja `SEMILIVIANOS`: el importador la conserva porque está asignada a DDV. Si querés ver únicamente POP liviano, filtrá las hojas en el Resumen y excluí esa categoría.
- La lectura de fotografías de POP evita procesar las hojas administrativas de gran tamaño.

### Validación con el Q4 V12 recibido

El lector recuperó **129 columnas/referencias del catálogo**, de las que **100 tienen cantidad positiva para DDV**, por un total de **133.559 unidades**. De ellas, `SEMILIVIANOS` representa **16 referencias y 488 unidades**; el resto de las hojas suma **84 referencias y 133.071 unidades**. Se vincularon imágenes incrustadas a **95 de las 100** referencias positivas. Los totales son lectura de asignaciones, **no unidades recibidas ni conciliadas con remitos**.

El total Q3 original permanece en **95.590 unidades, 73 referencias positivas**. La validación automatizada se realizó en el entorno local; es necesario desplegar en Streamlit Cloud para verificar la visualización remota.
