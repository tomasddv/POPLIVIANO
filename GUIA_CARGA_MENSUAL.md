# POP liviano DDV — carga múltiple y consolidado mensual

## 1. Qué cambió

El tablero ahora admite **varios archivos Excel (.xlsx) y varios archivos PDF/fotografías** dentro de un mismo mes y muestra un consolidado único de las cantidades asignadas a **Distribuidora del Valle S.A.** y las cantidades registradas en los remitos. Se mantienen los estados históricos **Q3 2026** y **Q4 2026** por separado. Los meses se presentan con el identificador `AAAA-MM` (por ejemplo, `2026-10`).

En la barra lateral hay **dos selectores independientes**: el mes/período de carga y el mes/período de resultados. Utilizá **📅 Crear un mes para consolidar** si aún no aparece. Elegí el mes de destino antes de subir los archivos. Los datos de octubre no se mezclarán con los de septiembre o noviembre.

## 2. Cargar y sumar varios Excel

1. En **📥 Mes / período de carga**, seleccioná el mes.
2. En **1 · Subir VARIOS Excel de asignación del mes**, seleccioná uno o varios `.xlsx` (hasta **15 archivos por lote**).
3. Elegí **Sumar Excel de entregas nuevas al consolidado** y presioná **📚 Consolidar Excel del período**.
4. Se mostrará el número de Excel registrados y el total DDV. Podés repetir la carga durante el mes para sumar nuevos lotes.
5. En **📑 Remitos registrados**, verás también el historial de Excel, las unidades DDV incorporadas y cuántas referencias se sumaron a las existentes.

**Muy importante:** el modo *Sumar* sirve para archivos de **lotes adicionales** de materiales. Si recibís una nueva versión del mismo Excel que ya incluye las cantidades anteriores, **no la sumes**: duplicarías la asignación. En ese caso usá **Reemplazar la asignación consolidada del período**; esa operación reinicia también remitos y controles físicos de **ese mismo mes**. Descargá un respaldo previo si tenés dudas.

Los materiales se unen cuando tienen una identidad suficientemente precisa (hoja, columna y descripción); si dos columnas distintas del **mismo archivo** tienen igual descripción, se conservan como **dos referencias independientes**. Las situaciones ambiguas se señalan para revisión. Solo se consideran cantidades asignadas a DDV, incluso en las hojas ocultas del Excel; no se suman otros distribuidores.

El sistema reconoce y **rechaza la misma copia binaria de un Excel**, aunque cambie el nombre del archivo.

## 3. Cargar varios remitos y fotos

1. Dentro del mismo mes, en **2 · Subir VARIAS imágenes / PDF del mes**, seleccioná varias fotos, varios PDF o ambos.
2. Se pueden leer **hasta 20 páginas por lote** (suma de páginas de todos los PDF e imágenes). Para más páginas, dividí la carga en varios lotes.
3. En **Qué hacer con la nueva lectura**, seleccioná **Agregar un remito nuevo al período** cuando sea otro documento. Si es una continuación, seleccioná **Agregar páginas al remito actual**. En ambos casos se suman los materiales al consolidado anterior.
4. Presioná **🔎 Leer remito para este período**. El tablero guardará un registro de los nombres de archivo, la fecha, las imágenes comprimidas y las lecturas OCR pendientes de validar.
5. En la solapa **📷 Lectura OCR**, corregí los números dudosos, seleccioná el POP correcto (también por foto) y presioná **✅ Aplicar revisión a este período**. **La suma se consolida al aplicar la revisión**, no solo al subir el archivo.
6. Volvé a cargar otro remito nuevo y repetí los pasos.

**Importante:** no vuelvas a agregar el mismo PDF o foto. La app bloquea **archivos exactamente idénticos por contenido**, aunque hayan sido renombrados. Un PDF reescaneado o fotografiado de nuevo podría no ser exactamente idéntico, por lo que debés revisar el **número de remito** y el historial para evitar sumarlo dos veces.

**La cifra original del remito y los errores OCR se conservan**. Las cifras heredadas de filas anteriores deben verificarse; no se certifica automáticamente una recepción por el mero hecho de haber reconocido la foto.

## 4. Consultar el consolidado mensual

En **📊 Mes / período de resultados**, elegí el mes. La pestaña **📊 Resumen** muestra las unidades DDV asignadas de todos los Excel sumados, las unidades leídas/aplicadas de todos los remitos, y las diferencias. La **planilla visual** conserva las fotos de POP con sus cantidades asignadas, originales y conciliadas. Siguen disponibles la galería y la tilde verde **Verificado físicamente**, que no reescribe los datos originales.

Los históricos Q3 y Q4 permanecen accesibles en la lista; son **períodos independientes** de los nuevos meses.

## 5. Guardado permanente en Streamlit Cloud

La persistencia en la nube funciona solo si ya configuraste el repositorio **privado** de datos en GitHub, con estos Secrets de Streamlit:

```toml
DATA_GITHUB_REPO = "USUARIO/repositorio-privado-datos"
DATA_GITHUB_TOKEN = "TOKEN_CON_CONTENTS_READ_WRITE"
DATA_GITHUB_BRANCH = "main"
APP_PASSWORD = "CONTRASENA_OPCIONAL_PERO_RECOMENDADA"
```

**Nunca subas los Secrets al repositorio de código.** El mismo repositorio privado de datos existente seguirá guardando los controles; no hace falta crear otro.

También podés descargar el **historial completo en JSON** y un **ZIP de imágenes** de cada período. El JSON incluye los meses nuevos y los registros de los archivos Excel, pero no conserva los `.xlsx` originales ni las fotografías. Conservá ambos respaldos si no tenés GitHub privado configurado.

## 6. Actualizar GitHub

Subí al repositorio **de la aplicación** todos los archivos de este paquete y hacé **Commit changes**, en particular:

- `app.py`, `period_store.py`, `monthly_core.py` (nuevo), `ocr_core.py`, `pop_core.py`.
- `data/`, `.streamlit/config.toml`, `requirements.txt`, `packages.txt` y los demás módulos.

No borres ni sobrescribas manualmente el repositorio privado de datos. Este paquete contiene el Q3 inicial, pero si ya guardaste avances en GitHub privado, el programa recuperará los avances existentes al iniciar.

## Verificación

Se probaron las operaciones de consolidación, rechazo de duplicados, recuperación de estados mensuales y compatibilidad de la lógica histórica. También se comprobó contra el Excel Q3 adjunto que el lector conserva las 100 referencias del archivo y solo 73 con asignación positiva a DDV (95.590 unidades). La interfaz todavía no se ha verificado sobre el despliegue real de Streamlit Cloud.
