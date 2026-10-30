# NUEVO — Consolidación mensual de múltiples Excel y remitos

Este proyecto permite crear y seleccionar meses (`2026-10`, `2026-11`, etc.),
subir **hasta 15 Excel por lote** y **hasta 20 páginas de remitos o fotografías
por lote**. Podés realizar múltiples cargas durante el mes y consultar
las sumas en la planilla visual de Resumen. Las asignaciones Excel se agregan
solo para lotes nuevos, y los remitos se agregan después de revisar el OCR.

- Los Excel se consolidan **exclusivamente para Distribuidora del Valle S.A.**;
  otros distribuidores y POP con asignación DDV cero no se contabilizan.
- Un archivo idéntico se bloquea por huella digital (SHA-256) para evitar
  duplicados, aun si cambia el nombre. Se conservan los registros por archivo.
- Q3/Q4 históricos siguen disponibles, sin mezclar sus cifras con un mes nuevo.
- La vista Resumen mantiene las fotografías reales de los POP, las cantidades,
  la diferencia y la verificación física en verde.
- Para mantener los datos tras cerrar Streamlit Cloud sigue siendo obligatorio
  el repositorio privado de datos configurado en Secrets.

**Uso detallado y precauciones:** leer `GUIA_CARGA_MENSUAL.md`.

---

# Actualización de OCR: lectura por posición (29/10/2026)

Esta versión corrige el reconocimiento de los remitos fotografiados sin exigir fotos nuevas.

- **Cantidad y descripción en una misma línea:** en lugar de depender solo del texto plano de Tesseract, utiliza las coordenadas de las palabras para reconstruir cada renglón. Evita que el número quede aislado y el material aparezca sin cantidad.
- **Dos columnas independientes:** tanto en imágenes como en PDF digital, la reconstrucción se hace por columna. Las cantidades no se heredan de la columna opuesta.
- **Dígitos dudosos:** un texto como `q 410 Sticker EDF` o `pe 6820 MINI CENEFA` conserva `410` o `6820` como **cantidad sugerida para verificar** y limpia la descripción para facilitar el match. Una cifra dudosa corta la herencia desde la fila anterior; no se acepta en silencio.
- **Cantidad heredada:** si la fila no tiene número impreso, propone la última cifra explícita de esa misma columna/página. Indica el origen y exige revisión antes de cerrar el período.
- **Match con DDV:** se consideran como catálogo operativo únicamente materiales con asignación positiva en la fila de Distribuidora del Valle. Se mantiene la búsqueda por equivalencias de campaña, marcas y medidas, y el aviso de materiales fuera de alcance.
- **Fotografías:** la calidad del texto puede ser suficiente para una persona y aun así fallar OCR. Las lecturas dudosas siguen necesitando aprobación; el software no modifica el valor original del remito ni fuerza cantidades a coincidir con el Excel.

### Reemplazo en GitHub

Subí **todo el contenido de este ZIP** al repositorio de la aplicación y realizá Commit changes. Los cambios principales están en `ocr_core.py`, `ocr_layout.py` (nuevo), `pop_core.py` y `fuzzy_match.py`. Mantené el repositorio privado de datos y los Secrets tal como están; no los reemplaces. Después de desplegar, seleccioná Q3 para carga, volvé a procesar las imágenes y revisá las propuestas antes de pulsar «Aplicar revisión a este período». **Reprocesar no elimina el historial anterior salvo que confirmes un reemplazo.**

---

# NUEVO — Planilla visual de POP en la primera solapa «📊 Resumen»

La pestaña inicial ahora muestra, **antes del gráfico y las tablas anteriores**, una
matriz tipo Excel: **un material por columna**, **foto real encima** y, debajo,
filas separadas con **Asignado DDV**, **Remito original**, **Remito conciliado**,
**Diferencia** y **Estado**. El identificador de la hoja y la celda del Excel
permite rastrear el POP a su ubicación de origen.

- Seleccioná Q3 o Q4 en **Período de visualización**; la matriz usa únicamente
  los materiales de DDV correspondientes al trimestre elegido.
- Filtrá por **hoja/familia del Excel**, **estado** o **texto** y navegá entre
  páginas de 4, 6, 8 o 12 POP. En pantallas angostas la matriz admite desplazamiento
  horizontal y mantiene visibles los nombres de las filas.
- Por defecto se ven POP asignados a DDV y los que tienen registro de remito;
  también podés activar **Incluir POP sin asignación a DDV** para inspeccionar
  todo el catálogo de la planilla.
- Si ya marcaste una **verificación física** en la galería, su columna se muestra
  verde, la cantidad conciliada será la asignada y la cantidad original del
  remito permanecerá visible para auditoría.
- Si un POP no tiene imagen, aparece **Sin imagen de POP**. Podés incorporar esa
  foto en la pestaña **🖼️ Galería de POP**.
- Esta vista es **de consulta**: no duplica cifras, no modifica los resultados
  y no requiere cambios en el repositorio de datos existente.

## Actualización desde GitHub

Subí **todos los archivos de este ZIP** al repositorio de la aplicación (respetá
los directorios `.streamlit/` y `data/`). **Incluí el nuevo módulo
`visual_summary.py`**, además de `app.py`. Hacé *Commit changes* y luego
actualizá la aplicación en Streamlit Cloud. **No reemplaces ni borres el segundo
repositorio privado de datos.** Los `Secrets` siguen funcionando como antes.

---

> **CORRECCIÓN 29/10/2026 — Error TypeError al abrir Resultados Q3**
>
> Si veías un error en `physical_checks.py`, línea 82, causado por una versión
> antigua de `pop_core.py`, este paquete ya lo corrige. La conciliación ahora
> funciona tanto con la firma de cuatro argumentos como con la más nueva.
> **Reemplazá todos los archivos del repositorio de la app por los de este ZIP**, especialmente
> `app.py`, `physical_checks.py` y `pop_core.py`; no modifiques el repositorio
> privado usado para guardar datos. Los Q3/Q4 existentes, las fotos, las
> tildes verdes y el historial de remitos se conservan.
> Tras subir los archivos, esperá a que Streamlit termine el despliegue y
> actualizá la página con **Ctrl+F5**.

# Novedad: selector visual de materiales en Lectura OCR

En la pestaña **📷 Lectura OCR** sigue disponible la columna **Material Excel** con
su lista desplegable tradicional. Como las opciones de un `SelectboxColumn` de
Streamlit no admiten miniaturas dentro de la lista, se añadió debajo de la tabla
el panel **🖼️ Elegir material por su foto**:

1. Seleccioná el **renglón del remito** (se muestra su texto OCR y cantidad).
2. Buscá un POP por nombre, medida, campaña o marca; también podés filtrar por
   hoja del Excel y elegir **Solo con foto**.
3. El panel prioriza los materiales sugeridos por el OCR y muestra sus imágenes
   reales extraídas del Excel de ese trimestre (o las cargadas en la galería),
   la descripción, la hoja y la cantidad asignada a DDV.
4. Presioná **✓ Seleccionar POP** en la ficha correcta: la elección aparecerá
   inmediatamente en la columna **Material Excel** de ese renglón.
5. Revisá/corregí la cantidad del remito en la tabla y presioná **✅ Aplicar
   revisión a este período** para guardar los cambios del control.

**Seguridad de la conciliación:** elegir una fotografía no copia cantidades del
Excel en el campo del remito. Si el OCR no leyó una cifra, esa cifra sigue
pendiente hasta que alguien la complete. La sugerencia OCR original se conserva
para auditoría. La aplicación mantiene el tema claro con letras negras.

Si Q4 no trae fotografías incrustadas, se pueden cargar desde **🖼️ Galería de
POP → Asignar o reemplazar la imagen de un POP**. Solo aparece una miniatura
cuando existe una foto vinculada al material.

## Actualización en GitHub

Reemplazá los archivos de tu aplicación por los de este paquete (no el repositorio
privado donde se guardan los registros). Es obligatorio subir `visual_match.py`
junto con el nuevo `app.py`, las carpetas `data/` y `.streamlit/`, y los demás
módulos. Hacé **Commit changes**; Streamlit Cloud volverá a desplegar la app.
Las credenciales de GitHub siguen en **Secrets** y nunca deben subirse al repo.

---

# Control de POP liviano · DDV · Q3 / Q4

Tablero en **Streamlit** para el control trimestral del POP liviano de **Distribuidora del Valle S.A.**. Listo para subir a GitHub y desplegar en Streamlit Community Cloud.

## NUEVA: verificación física por POP y todas las fuentes negras

En **🖼️ Galería de POP**, para cada material **Pendiente**, **Faltante** o **Sobrante** aparece el botón **✅ Verificado físicamente**. Usalo **solo después de revisar presencialmente el material**. Al pulsarlo:

- La tarjeta se pone **verde** y muestra una tilde de **verificación física**.
- La cantidad **conciliada** pasa a ser exactamente la **cantidad asignada a DDV en el Excel** y la diferencia pasa a cero.
- La **cantidad original leída en el remito permanece guardada**: NO se altera el dato de origen ni se reescribe el Excel. Ejemplo: remito 80, asignado 100 → conciliado 100, original 80, diferencia 0.
- Se guarda un evento con fecha UTC, material y cantidades. Los cambios se guardan en el repositorio remoto de datos si configuraste Secrets.
- La tarjeta queda visible en los filtros de diferencias mediante el **estado original** y también en **Verificados físicamente**.
- El botón **↶ Deshacer control físico** anula la aprobación, restaura automáticamente la comparación original y deja registro de la reversión.
- Si una nueva lectura OCR o una corrección manual cambia ese material, se **invalida solo la aprobación afectada** para exigir una nueva revisión física. Al borrar el control trimestral, se invalidan todas las verificaciones de ese período.

Los **textos de toda la app son negros**, incluidos barra lateral, botones, tarjetas, menús, tablas, gráficos y formularios. Se forzó el tema claro para evitar blanco sobre blanco.

La pestaña **🧾 Control por material** distingue entre `Remito original` (editable), `Conciliado` (derivado) y `Control físico`. El CSV exporta ambos valores y la fecha de verificación. El respaldo JSON conserva las aprobaciones y los eventos para Q3/Q4 y nuevos períodos.

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
5. En **📷 Lectura OCR**, revisá cantidades dudosas y seleccioná los materiales adecuados. Pulsá **Aplicar revisión**. Las cantidades se cotejan **exactamente** antes del control físico; la tolerancia de errores OCR se aplica **al nombre del material**, no al conteo de unidades. Solo el botón de verificación **manual** modifica la cantidad conciliada.
6. En **🖼️ Galería de POP**, compará imagen, asignación y remito. Si falta o sobra material o está pendiente, tras verificarlo presencialmente pulsá **✅ Verificado físicamente**. La ficha se pone verde, la cantidad conciliada se ajusta a la asignada y el original queda registrado. Si necesitás revertirlo, pulsá **↶ Deshacer control físico**. Si falta una imagen, asignala desde la galería.
7. En **📑 Remitos registrados**, verificá si se cargó un nuevo remito y revisá sus fotos.
8. Los cambios se guardan automáticamente cuando se confirman, si GitHub está configurado. Opcionalmente usá **Guardar cambios pendientes**.

## Actualizar código en tu repositorio GitHub

Subí el contenido descomprimido de este ZIP al repositorio **de la aplicación** y elegí Commit Changes. Conservá la estructura y agregá todos los nuevos archivos:

- `app.py`, `period_store.py`, **`physical_checks.py`**, `pop_core.py`, `media_core.py`, `persistence.py` y módulos existentes de OCR/conciliación.
- `data/q3_2026_preliminar.json`, `data/q3_gallery.zip`, `data/q3_pop_map.json` (imágenes Q3 precargadas).
- `.streamlit/config.toml`, `requirements.txt`, `packages.txt`, `tests/`.

**Nunca subas `.streamlit/secrets.toml` real ni el contenido de `.local_store`.** El ejemplo `.streamlit/secrets.toml.example` contiene solo marcadores; sirve para copiar la estructura de Secrets. Para información comercial sensible, mantené los repositorios privados y restringí el acceso al tablero.

## Seguridad, límites y verificación

- El OCR en fotografías borrosas puede confundir cifras o campañas. Cada resultado se revisa manualmente antes de validar una recepción. Los nombres aproximados no autorizan a igualar cantidades.
- Las 98 imágenes Q3 se asociaron a la columna de Excel de cada material a partir de sus anclajes internos. Las dos fichas sin imagen permiten carga manual. Confirmá visualmente las campañas si las plantillas Q4 son distintas.
- Los registros históricos originales del remito Q3 contienen una lectura **provisional**, no una recepción certificada.
- Los respaldos JSON conservan valores e historial, pero las imágenes se respaldan por separado en ZIP. La configuración remota guarda ambos.
- El servidor de GitHub debe aceptar los cambios (si aparece una alerta de error no se marca el guardado como exitoso). Los repositorios de datos separados evitan que cada registro active un redespliegue de la aplicación.
- Pruebas de lógica (incluidas verificaciones físicas y auditoría): `python -m unittest discover -s tests -v`. No se realizó un despliegue real en tu cuenta de Streamlit Cloud durante esta entrega.

## Ejecutar localmente

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Para leer fotos en local, instalá Tesseract OCR con idiomas `spa` y `eng`. En Streamlit Cloud lo solicita `packages.txt`.

## Actualización: selector visual solo con filas sin asignar y contraste corregido

- El desplegable **«1 · Elegí solo una fila SIN ASIGNAR del remito»** incluye únicamente filas OCR sin material elegido y no marcadas como «Ignorar». Las filas que ya tienen Material Excel asociado quedan fuera de esta lista.
- Al presionar **«✓ Seleccionar POP»** debajo de una imagen, el renglón desaparece inmediatamente del desplegable y se selecciona otra fila pendiente; el OCR y la cantidad original quedan intactos.
- Cuando no quedan pendientes, aparece un mensaje verde y la tabla principal sigue mostrando todas las filas para revisiones o correcciones. Si una fila vuelve a «(sin asignar)» en la tabla, reaparece en la lista.
- Se reforzó el tema de **fondo blanco y letras negras en listas desplegables**, incluidos los menús que Streamlit muestra fuera del contenedor principal (portales BaseWeb). No se requiere editar los secretos de GitHub.
- **Para guardar definitivamente los cambios en el trimestre**, seguí utilizando el botón «Aplicar revisión a este período». Elegir una fotografía actualiza el borrador del OCR, no modifica las asignaciones del Excel.



## Actualización: alcance DDV, alias y cantidad compartida

- **Catálogo operativo**: solo columnas con cantidad positiva en la fila de Distribuidora del Valle. Q3: 73 materiales y 95.590 unidades. El catálogo de origen completo permanece en los respaldos para auditoría. No se aplica un filtro literal por palabra `PATAGONIA` porque algunos materiales genéricos compartidos tienen cantidad asignada a DDV sin llevar esa palabra en el título.
- **Nombres comerciales**: `AO` se reconoce como Andes Origen Oro. Los AFICHES de oferta `REG VARIAS` pueden coincidir con referencias DDV positivas del grupo genérico compartido en Q3. Si dos modelos tienen igual nombre y medida se dejan para selección por fotografía.
- **Cantidad compartida**: en líneas de material sin cifra expresa se copia provisionalmente la última cifra explícita de la misma columna/página OCR, mostrando `Origen cantidad`. Se debe revisar al aplicar la lectura; esta operación no equivale a un conteo físico. La cifra heredada no cruza páginas ni columnas.
- **Fuera de asignación**: un material cuyo mejor match es una referencia con DDV=0, y con evidencia textual suficiente, se marca `Ignorar` por defecto en Lectura OCR, pero aparece en una lista de auditoría y se puede corregir. Por ejemplo, Q3 `Quilmes Mundial 20x30` figura con DDV=0 aunque el remito pueda mostrar 40 por continuidad.
- **Datos previos**: no se borran remitos ni verificaciones almacenadas. El filtro se aplica a la visualización y conciliación, también para períodos recuperados. Para recalcular una foto ya procesada con la nueva regla de continuidad hay que volver a subirla como **Reemplazar cantidades anteriores**, no como remito adicional.
