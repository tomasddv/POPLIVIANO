# Control de POP liviano · DDV · Q3 / Q4

Tablero en **Streamlit** para el control trimestral del POP liviano de **Distribuidora del Valle S.A.**. Listo para subir a GitHub y desplegar en Streamlit Community Cloud.

## Novedades de esta entrega

1. **Galería fotográfica de POP**: se procesaron las imágenes realmente incrustadas en el Excel Q3 original. Hay **98 imágenes vinculadas a los 100 materiales DDV**. El ZIP incluye miniaturas y asignaciones, sin necesidad de volver a cargar el Excel Q3. En Q4 la app intentará obtener automáticamente las imágenes incrustadas de su Excel. Si faltan, se pueden subir manualmente desde la pestaña **🖼️ Galería de POP**.
2. **Cada ficha** presenta fotografía, nombre de material, hoja del Excel, cantidad asignada DDV, cantidad del remito, estado y diferencia. Permite filtros por marca/hoja, estado, búsqueda de texto y páginas de 12 fichas para una carga ágil.
3. **📑 Remitos registrados**: historial de cada remito o grupo de páginas subido, fecha, nombres de los archivos, modo de carga (reemplazo, páginas adicionales o **nuevo remito**), páginas, renglones reconocidos, renglones confirmados y su estado. Conserva una copia comprimida de las fotos/PDF rasterizado de cada remito.
4. **Guardado automático al realizar una operación**: al cargar Excel, subir remitos, aplicar revisión OCR, hacer correcciones, marcar el remito como completo, editar nombres, añadir un período o añadir fotos de POP. **La permanencia en Streamlit Cloud requiere configurar un repositorio de datos GitHub privado, como se describe abajo.**
5. Siguen funcionando Q3 precargado, Q4 por cargar, el OCR tolerante a pequeños errores de texto, los controles exactos de cantidades, los selectores separados para carga y visualización y la exportación CSV/JSON.

## IMPORTANTE: configurar guardado duradero en la nube

El disco de **Streamlit Community Cloud NO es permanente**. Guardar en archivos locales o `st.session_state` no basta. Para que al cerrar y volver a abrir la web se recupere todo, esta versión guarda el historial y las fotos en **un segundo repositorio privado de GitHub**, distinto del repositorio que ejecuta la aplicación. Es necesario configurar la conexión **una sola vez**.

### Paso 1 — Repositorio privado exclusivo para datos

1. En GitHub, elegí **New repository**.
2. Nombre sugerido: `registro-pop-liviano-ddv`.
3. Marcá **Private**. Creá el repositorio con `README.md` inicial (para que exista la rama `main`).
4. Este repositorio debe ser **distinto** del repositorio de la app, para evitar un *redeploy* de Streamlit en cada guardado.

### Paso 2 — Crear credencial (token)

1. En GitHub, abrí **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Seleccioná **Only select repositories** y elegí **solo** el repositorio privado de datos.
3. En **Repository permissions**, otorgá a **Contents: Read and write** (los permisos necesarios de Metadata se otorgan automáticamente).
4. Copiá el token y tratálo como una contraseña. No lo subas a GitHub ni lo pegues en `app.py`.

### Paso 3 — Secrets de Streamlit Cloud

Abrí la aplicación desplegada en Streamlit Community Cloud y entrá en **App settings / Settings → Secrets**. Pegá lo siguiente con **tus valores**:

```toml
DATA_GITHUB_REPO = "TU_USUARIO/registro-pop-liviano-ddv"
DATA_GITHUB_TOKEN = "TU_TOKEN_GITHUB"
DATA_GITHUB_BRANCH = "main"
APP_PASSWORD = "TU_CONTRASENA_DE_ACCESO"
```

`APP_PASSWORD` es opcional técnicamente pero **muy recomendable**: sin contraseña, cualquiera que acceda a la URL pública de Streamlit podría ver o cambiar información del tablero. No compartas esa contraseña ni el token en el repositorio.

En la barra lateral debe aparecer **«☁️ Guardado permanente activo · GitHub privado»**. Si aparece un error de GitHub, no des por guardados los cambios hasta corregirlo. El repositorio de datos contendrá:

- `pop_ddv/registro.json`: asignaciones extraídas, cantidades registradas, correcciones, historial y estado por trimestre.
- `pop_ddv/assets/Q3_2026.zip`, `Q4_2026.zip`, etc.: fotos de POP y páginas de remitos ya comprimidas.

### Si todavía no configuraste el repositorio de datos

El programa funciona en una computadora con almacenamiento local `.local_store`, pero **en Streamlit Cloud estos archivos se pueden perder después de un reinicio, redeploy o hibernación**. Aparecerá una advertencia; para la persistencia solicitada se debe activar GitHub. También podés descargar respaldos JSON y ZIP de imágenes por período.

## Cómo usar el tablero

1. Seleccioná **Período de carga**: Q3 2026, Q4 2026 u otro trimestre.
2. Q3 ya tiene el Excel, catálogo, imágenes y lectura provisional. En Q4 subí el Excel correspondiente; el sistema lee solamente filas DDV (incluidas hojas ocultas) y extrae las imágenes si están incrustadas.
3. Elegí una de las operaciones: **Reemplazar cantidades anteriores**, **Agregar páginas al remito actual**, o **Agregar un remito nuevo al período**. Agregar suma cantidades; reemplazar las sustituye al confirmar.
4. Subí fotos o un PDF de hasta tres páginas, pulsá **Leer remito**. La nueva carga se registra en el historial como *OCR pendiente* y las fotos quedan guardadas. No vuelvas a cargar el mismo remito en modo «Agregar».
5. En **📷 Lectura OCR**, revisá cantidades dudosas y seleccioná los materiales adecuados. Pulsá **Aplicar revisión**. Las cantidades se cotejan **exactamente**; la tolerancia de letras y números mal reconocidos se aplica **al nombre del material**, no al conteo de unidades.
6. En **🖼️ Galería de POP**, compará la imagen, la asignación y la cantidad del remito. Si falta una imagen, asignala desde la galería.
7. En **📑 Remitos registrados**, verificá si se cargó un nuevo remito y revisá sus fotos.
8. Los cambios se guardan automáticamente cuando se confirman, si GitHub está configurado. Opcionalmente usá **Guardar cambios pendientes**.

## Actualizar código en tu repositorio GitHub

Subí el contenido descomprimido de este ZIP al repositorio **de la aplicación** y elegí Commit Changes. Conservá la estructura y agregá todos los nuevos archivos:

- `app.py`, `period_store.py`, `media_core.py`, `persistence.py` y módulos existentes de OCR/conciliación.
- `data/q3_2026_preliminar.json`, `data/q3_gallery.zip`, `data/q3_pop_map.json` (imágenes Q3 precargadas).
- `.streamlit/config.toml`, `requirements.txt`, `packages.txt`, `tests/`.

**Nunca subas `.streamlit/secrets.toml` real ni el contenido de `.local_store`.** El ejemplo `.streamlit/secrets.toml.example` contiene solo marcadores; sirve para copiar la estructura de Secrets. Para información comercial sensible, mantené los repositorios privados y restringí el acceso al tablero.

## Seguridad, límites y verificación

- El OCR en fotografías borrosas puede confundir cifras o campañas. Cada resultado se revisa manualmente antes de validar una recepción. Los nombres aproximados no autorizan a igualar cantidades.
- Las 98 imágenes Q3 se asociaron a la columna de Excel de cada material a partir de sus anclajes internos. Las dos fichas sin imagen permiten carga manual. Confirmá visualmente las campañas si las plantillas Q4 son distintas.
- Los registros históricos originales del remito Q3 contienen una lectura **provisional**, no una recepción certificada.
- Los respaldos JSON conservan valores e historial, pero las imágenes se respaldan por separado en ZIP. La configuración remota guarda ambos.
- El servidor de GitHub debe aceptar los cambios (si aparece una alerta de error no se marca el guardado como exitoso). Los repositorios de datos separados evitan que cada registro active un redespliegue de la aplicación.
- Pruebas de lógica: `python -m unittest discover -s tests -v`. No se realizó un despliegue real en tu cuenta de Streamlit Cloud durante esta entrega.

## Ejecutar localmente

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Para leer fotos en local, instalá Tesseract OCR con idiomas `spa` y `eng`. En Streamlit Cloud lo solicita `packages.txt`.
