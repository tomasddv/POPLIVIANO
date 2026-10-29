# Control POP liviano — Distribuidora del Valle

Tablero web en **Streamlit**, apto para desplegar desde **GitHub** en Streamlit Community Cloud. Se creó para **Q4 2026**, pero se puede reutilizar con los Excel de asignación de próximos trimestres. **El repositorio no incluye archivos empresariales ni el remito Q3**.

## Qué hace

1. Permite cargar el **Excel de asignación Q4** (`.xlsx`) con varias hojas, incluso ocultas.
2. Busca únicamente la fila **Distribuidora del Valle S.A.** en cada hoja y extrae cantidades por material/columna. No toma cifras de otros distribuidores.
3. Permite subir **1 a 3 fotografías** (`JPG`, `PNG`, `WEBP`) o un **PDF** de remito (hasta 3 páginas totales).
4. Lee las imágenes con **Tesseract OCR instalado en el servidor**. Separa las dos columnas de los remitos GS y detecta cantidades/descripciones.
5. Sugiere correspondencias entre texto del remito y columnas del Excel. Como ciertos productos se parecen entre sí y los OCR pueden equivocarse, **el usuario verifica cantidades y asignaciones**. Las ambiguas quedan sin asignar.
6. Calcula **Coincide / Faltante / Sobrante / Pendiente**, presenta gráficos por hoja, permite ingresar cantidades manualmente y exporta CSV.
7. Descarga un **respaldo JSON** de cada trimestre y un **diccionario JSON** para nombrar materiales que en el Excel solo figuran por medidas.

### Importante sobre la lectura automática

El OCR **no es infalible**. El tablero no puede garantizar que el número detectado en una foto sea el número real, especialmente en remitos borrosos. Solo toma como datos revisados las cantidades que apliques desde la tabla de OCR. El archivo de origen debe contener la fila de DDV. La falta de una asignación en un renglón se trata como *pendiente*, no como entrega cero, hasta que se confirme el remito completo.

Las columnas de Excel en que los encabezados son genéricos (por ejemplo `20x30`) pueden necesitar identificación manual. Los nombres personalizados ayudan a futuras lecturas del mismo Excel.

## Publicarlo con GitHub y Streamlit Community Cloud

1. Creá un repositorio nuevo en **GitHub** (recomendado privado si tiene referencias empresariales) y subí los archivos de esta carpeta **respetando las subcarpetas**.
2. En <https://share.streamlit.io/> ingresá con GitHub y elegí **Create app / Deploy**.
3. Seleccioná el repositorio, rama `main` y archivo principal **`app.py`**.
4. Elegí **Deploy**. Streamlit instala las dependencias en `requirements.txt` y Tesseract mediante `packages.txt`.
5. Abrí el enlace de tu aplicación. Cargá el Excel **GS Q4** y las imágenes del remito **Q4**, y pulsá **Leer e interpretar remito**.
6. Revisá y aplicá cada línea del OCR; filtrá diferencias, comprobá los materiales, descargá el CSV y guardá un respaldo JSON.

**GitHub Pages por sí solo no ejecuta Python ni OCR.** GitHub aloja el código y Streamlit Cloud ejecuta el tablero. No hace falta una clave API ni pagar un servicio de IA; el OCR corre localmente dentro del servidor de Streamlit.

## Ejecutar en Windows

Instalá Python 3.11+, [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) con idiomas `spa` y `eng`, y ejecutá:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

En Windows agregá Tesseract al `PATH`; si no aparece, agregá la ruta de `tesseract.exe` en la configuración de tu entorno.

## Privacidad, uso de nube y persistencia

- No se utiliza OCR externo ni se envían archivos a un proveedor de IA; se procesan dentro de la sesión del servidor.
- No guardes archivos Excel, fotos de remito, CSV ni respaldos dentro del repositorio. `.gitignore` impide incorporarlos accidentalmente con `git add` en una carpeta de trabajo normal.
- Una app pública podría ser utilizada por otras personas. Configurá controles de acceso si la información es privada.
- El avance está en memoria de la sesión, **no** en una base de datos; ante reinicios puede perderse. Descargá el **respaldo JSON** al terminar y restauralo con el mismo Excel.

## Archivos

- `app.py`: aplicación interactiva.
- `pop_core.py`: lectura de Excel, similitudes entre materiales, conciliación y exportación.
- `ocr_core.py`: procesamiento de fotografías y PDF mediante Tesseract.
- `requirements.txt`: dependencias de Python.
- `packages.txt`: Tesseract y sus idiomas para desplegar en Linux.
- `.streamlit/config.toml`: tema y tamaño de archivos.
- `tests/test_core.py`: pruebas unitarias de lógica de matching y conciliación.
