# Control de POP liviano · Distribuidora del Valle (DDV)

## Versión corregida: colores y reconocimiento flexible

- **Tema claro real:** se eliminó la regla que ponía textos blancos en la barra lateral sobre controles blancos. La configuración `.streamlit/config.toml` fija `base = "light"`; los títulos, tablas, selectores y métricas utilizan letras oscuras y fondo claro.
- **Comparación inteligente por descripción:** incorpora `fuzzy_match.py`, que compara nombres de la foto con los nombres, hojas, grupos, formatos y alias del Excel. Admite pequeñas diferencias en letras y números de las dimensiones (por ejemplo `AFÍCME`/`AFICHE` o `2OX3O`/`20X30`).
- **Semáforos de revisión:** muestra el porcentaje de similitud textual, las dos alternativas más cercanas y alertas sobre material/campaña/medida diferente. Los nombres ambiguos no se enlazan automáticamente.
- **Cantidades siempre exactas:** un remito de 358 contra Excel 350 da **sobrante de 8**, incluso si el texto matchea perfectamente. Si el OCR cree que `S20` representa `520`, lo propone para revisar pero NO lo carga en cantidad recibida.
- Se mantienen los selectores separados de **carga** y **visualización** Q3/Q4, los resultados Q3 preexistentes, los respaldos JSON y la carga de nuevas fotos por trimestre.
- Para aplicar esta versión subí también el **archivo nuevo `fuzzy_match.py`** y el `requirements.txt` actualizado (instala RapidFuzz).

### Si el sitio sigue mostrando el tema anterior

Después del *Commit changes*, esperá al nuevo deploy de Streamlit Community Cloud y **recargá la página con Ctrl+F5** en el navegador. En el panel de administración de Streamlit podés reiniciar la aplicación si el deploy no se ejecuta.

### Revisión del OCR

Después de pulsar «Leer remito», abrí «Lectura OCR» del mismo período y revisá las columnas **Cantidad**, **Material Excel**, **Similitud %**, **Excel sugerido**, **Diferencia tentativa**, **Alertas del match** y **Otras opciones**. Algunas filas quedan sin asignar si el texto está borroso o hay materiales muy parecidos. Es intencional: completar a ciegas crearía falsas coincidencias.

Ejecutar pruebas: `python -m unittest discover -s tests -v` (24 pruebas).

---

Aplicación para **GitHub + Streamlit Community Cloud**, con **Q3 2026 precargado** y **Q4 2026** listo para cargar. Cada período tiene Excel, fotografías, lectura OCR, correcciones y resultados completamente separados.

## Funcionalidad principal

- Dos selectores independientes: **Período de carga** y **Período de visualización**. Elegir Q3 para cargar fotos no borra ni altera Q4.
- **Q3 2026 listo al abrir:** catálogo real de 100 columnas DDV, 95.590 unidades asignadas y 93.750 unidades transcriptas provisoriamente del remito anterior (70 coincidencias, 1 diferencia, 3 pendientes). **No están certificadas**: la foto era de lectura difícil.
- En Q3, podés **subir una imagen nueva** del remito y elegir **Reemplazar cantidades anteriores**. Después se revisa la tabla OCR y se aplica a Q3.
- Si el documento viene en páginas distintas, podés **Agregar páginas al remito actual**. Solo debe usarse para páginas no contabilizadas. La misma carga no se suma dos veces por accidente.
- **Q4 2026:** elegí Q4 en «Período de carga», aplicá el Excel nuevo y luego el remito Q4 (foto o PDF, hasta 3 páginas por lectura).
- Comparación de cada material con la fila **Distribuidora del Valle S.A.**, en **todas las hojas, incluidas ocultas**, sin mezclar los totales de las demás distribuidoras.
- Tabla de materiales por pestaña y estado (Coincide, Faltante, Sobrante, Pendiente), gráficos, cambios manuales, nombres personalizados, exportación CSV.
- Podés agregar nuevos trimestres, por ejemplo Q1 2027, desde el lateral.
- **Historial JSON global:** descarga todas las asignaciones extraídas, cantidades OCR aplicadas, nombres y estados de Q3 y Q4; permite restaurarlos en sesiones futuras, incluso sin volver a subir los Excel. No contiene las fotos ni los Excel originales.

## Publicar o actualizar en GitHub

1. Abrí tu repositorio de GitHub que contiene la versión anterior del tablero POP. Si todavía no existe, creá uno **privado**.
2. **Reemplazá o subí los archivos de este ZIP**, respetando subcarpetas: `app.py`, `pop_core.py`, `ocr_core.py`, `period_store.py`, `requirements.txt`, `packages.txt`, `.streamlit/config.toml` y `data/q3_2026_preliminar.json`.
3. Hacé *Commit changes* en la rama que usás para publicar, generalmente `main`.
4. Si ya tenías la app creada en <https://share.streamlit.io/>, se redepliega con el cambio. Si no, creá una app con **`app.py`** como archivo de inicio.
5. Streamlit Cloud instala automáticamente Tesseract por `packages.txt` para leer las imágenes. No necesitás contratar API de visión.

**No subir el Excel original ni las fotos al repositorio.** El proyecto **sí incluye una extracción de DDV de Q3** como `data/q3_2026_preliminar.json`, porque pediste ver Q3 de entrada. Esta extracción contiene cantidades y descripciones comerciales internas: por eso, **mantener el repositorio privado** y verificar quién puede acceder a la aplicación.

## Uso diario

1. Seleccioná **Q3 2026** o **Q4 2026** en «Período de carga».
2. Subí el Excel, si ese período todavía no tiene uno. En Q3 ya hay catálogo precargado, por lo que podés omitirlo.
3. Subí las fotos o PDF del remito. Elegí **Reemplazar** o **Agregar páginas**, según corresponda.
4. Presioná **Leer remito para este período**.
5. En la pestaña **Lectura OCR**, corregí cualquier cifra errónea y asigná cada material. Luego presioná **Aplicar revisión a este período**.
6. Elegí el período que te interese en «Período de visualización». Revisá el resumen y las diferencias por material/hoja.
7. Confirmá el remito completo solo cuando hayas verificado todas sus páginas. Descargá el CSV y el **historial JSON**.

## Persistencia y límites

Streamlit Community Cloud **no es almacenamiento permanente**. Los cambios viven en la sesión: al cerrar, cambiar de navegador o reiniciar el servidor puede perderse el avance. Al terminar cada sesión, usá **Descargar historial Q3 / Q4 (JSON)** y la próxima vez **Restaurar historial guardado**. El catálogo inicial Q3 siempre aparece precargado incluso sin restaurar, pero tus cambios posteriores a Q3 deben restaurarse desde JSON.

El OCR de fotos borrosas puede confundir cantidades. Ni un match sugerido ni una cifra OCR constituyen un control de recepción validado. Un material sin lectura permanece como **pendiente**, no se marca cero automáticamente. Si cerrás el remito completo, los materiales no registrados se consideran faltantes.

## Ejecutar localmente

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Requiere Python 3.11 o superior y Tesseract instalado con `spa` y `eng` para OCR local. `packages.txt` se encarga de esto al publicar en Streamlit Cloud.

## Estructura del proyecto

| Archivo | Uso |
| --- | --- |
| `fuzzy_match.py` | Similitud de nombres de POP, errores OCR, formatos y prevención de falsos positivos |
| `app.py` | Tablero multitrimestre con carga y visualización independientes |
| `pop_core.py` | Extracción DDV de Excel, comparación por material y CSV |
| `ocr_core.py` | OCR Tesseract para fotos/PDF |
| `period_store.py` | Estado por período, consolidación y backup/restore JSON |
| `data/q3_2026_preliminar.json` | Catálogo DDV real y remito preliminar Q3; sin fotos |
| `requirements.txt`, `packages.txt` | Dependencias para Streamlit Community Cloud |
| `tests/` | Pruebas de conciliación, integridad del Q3 y aislamiento Q3/Q4 |
