# 📝 Historial de Cambios — Revelador Nikon

## Versión Mejorada (Noviembre 2026)

### 0. Corrección Crítica de Calidad Fotográfica (Calibración Base y Rango Dinámico)
* **Calibración Fotográfica Base (`ev_base`)**:
  * **Causa raíz del problema detectado**: LibRaw entrega las cuentas analógicas del sensor en espacio lineal sin escalar (`gamma=(1, 1), no_auto_bright=True`). En un sensor Nikon de 14 bits, la ganancia base entre las cuentas puras del sensor y el gris medio fotográfico es de aproximadamente +1.6 a +2.4 EV. En el código original, el autor intentó parchear esto forzando una fórmula artificial de `+2.5 EV` y sombras a `+60` en todas las fotos (lo que provocaba el lavado y ruido marrón). Al desactivar esa sobreexposición descontrolada para tomas nocturnas, la ausencia de ganancia base provocó que tomas nocturnas cayeran a valores cercanos a cero absoluto (salían completamente negras, como la foto de la niña con el gorro).
  * **Solución definitiva**: Se implementó el cálculo y aplicación directa de la ganancia base de cámara (`calcular_ev_base` en `revelador/revelado.py`), midiendo de forma ultrarrápida contra la referencia real de la cámara. Al normalizar el RAW lineal en la carga, `exposicion = 0.0` coincide ahora de forma matemáticamente exacta con la exposición medida por la cámara.
* **Opción `preferir_jpg_camara` para parejas RAW+JPEG**:
  * Nuevo ajuste en `config.ini`: si disparas en RAW+JPEG y deseas aprovechar directamente la imagen revelada por el procesador EXPEED de Nikon (con Active D-Lighting y Picture Control de fábrica), basta con activar `preferir_jpg_camara = si`.
* **Preservación del Balance de Blancos de Cámara**:
  * Se eliminó el recálculo agresivo de "mundo gris" que convertía el cielo azul en marrón rojizo y arruinaba las luces cálidas de tungsteno.
  * Ahora se respeta por defecto el balance de blancos calculado por el procesador EXPEED de Nikon (`temperatura = 0.0, matiz = 0.0`).
* **Detección inteligente de escenas nocturnas / clave baja**:
  * Ahora el algoritmo detecta escenas nocturnas y de alto contraste (`es_nocturna`), manteniendo la exposición fiel en 0.0 EV y las sombras firmes (0 a +5 máx.), logrando que la noche conserve su atmósfera sin ruido.
* **Curva Tonal S-Curve estilo Nikon Picture Control**:
  * Se sustituyó la curva plana por una respuesta fotográfica en S con pie de sombra (`y ** 1.8`) que asegura que el negro profundo sea 0.0 puro (abrigo negro, fondo nocturno), recuperando la pegada, el contraste y la profundidad visual.
* **Brillo natural de luces navideñas y farolas**:
  * Se eliminó el aplastamiento de altas luces (`-85`) y la compresión agresiva en medios tonos. Las bombillas y fuentes de luz vuelven a brillar a blanco puro (255) con calidez y destello natural.
* **Claridad (CLAHE) selectiva en medios tonos**:
  * CLAHE se aplica ahora mediante una máscara de campana (`sin(L * π)^1.5`): aplica nitidez en rostros, pelo y ropa, pero **0% en sombras profundas**, eliminando el aspecto "sucio" y el grano amplificado en zonas oscuras.
* **Protección de ruido en sombras para ISOs altos**:
  * La intensidad/vibrance y el enfoque ahora se atenúan en sombras (`L < 15`) para no amplificar el ruido de crominancia en tomas nocturnas.
* **Invalidación de caché de versiones previas (`v2_calibrado`)**:
  * Se actualizó la firma de revelado (`_firma_revelado`) para asegurar que cualquier foto exportada anteriormente con la fórmula rota sea re-evaluada y re-exportada con la calidad calibrada correcta.

### 1. Rendimiento y Procesamiento en Paralelo
* **Análisis y generación de miniaturas multihilo**:
  * Implementado en [`Proyecto.analizar()`](file:///d:/revelador_nikon/revelador/proceso.py#L77) usando `concurrent.futures.ThreadPoolExecutor`.
  * La lectura de miniaturas RAW, cálculo de histogramas, detección de nitidez y huella dhash ahora se distribuye en paralelo entre los núcleos de la CPU (`trabajadores_analisis`, por defecto hasta 8 hilos).
* **Exportación y revelado RAW por lotes en paralelo**:
  * Implementado en [`Proyecto.ejecutar()`](file:///d:/revelador_nikon/revelador/proceso.py#L380) con gestión segura de estado (`threading.Lock`).
  * Los RAW a resolución completa se revelan en paralelo aprovechando procesadores multinúcleo (`trabajadores`, con detección inteligente según núcleos y memoria disponible, limitado de forma segura a 4 para prevenir saturación de RAM).
* **Gestión rigurosa de memoria (`gc.collect`)**:
  * Tras cada revelado a resolución completa se liberan explícitamente los buffers de memoria lineal en float32 y se fuerza la recolección de basura, permitiendo procesar sin problemas sensores Nikon de alta resolución (D850, Z7, Z8, Z9 de 45-50 megapíxeles).
* **Control mediante CLI**:
  * Nuevo parámetro `-j / --trabajadores` en `revelar.py procesar` para especificar manualmente los procesos concurrentes.

---

### 2. Calidad de Revelado RAW y Ciencia del Color
* **Algoritmo de Demosaicing (Interpolación cromática) configurable**:
  * Se sustituye la interpolación fija por soporte para algoritmos avanzados de LibRaw:
    * `AAHD` (por defecto): *Artifact-Free Adaptive Homogeneity-Directed*, elimina patrones de falsos colores y moiré en detalles finos.
    * `AHD`: Algoritmo clásico contrastado.
    * `DCB`: Máximo detalle con 2 pases de corrección y realce de color.
    * `DHT`: Gran detalle y alta velocidad.
    * `VNG`: Interpolación suave ideal para tomas con ISO muy elevado.
  * Se añade un pase de filtro mediano (`median_filter_passes=1`) tras el demosaicing para limpiar artefactos de color.
* **Corrección automática de aberraciones cromáticas y halos púrpuras**:
  * Nueva función `corregir_aberraciones_cromaticas()` en [`revelado.py`](file:///d:/revelador_nikon/revelador/revelado.py#L248).
  * Detecta bordes de alto contraste con sobreexposición (como ramas a contraluz o reflejos metálicos) y atenúa automáticamente los halos púrpuras y cianes sin afectar la saturación del resto de la escena.
* **Consistencia de Claridad (CLAHE dependiente de la escala)**:
  * El tamaño de rejilla de CLAHE ahora es adaptativo (`tx = max(4, min(64, int(round(w / 160.0))))`).
  * Esto asegura que el microcontraste se perciba exactamente igual en la vista previa del navegador que en el archivo final exportado a 24-45 megapíxeles.
* **Incrustación de Perfil de Color ICC sRGB**:
  * Las imágenes JPEG exportadas ahora incluyen el perfil ICC estándar sRGB generado mediante `PIL.ImageCms`.
  * Garantiza fidelidad de color uniforme en navegadores, teléfonos móviles, monitores de amplia gama (DCI-P3) y visores de Windows.
* **Compresión LZW sin pérdidas para TIFF de 16 bits**:
  * Los archivos `.tif` ahora se guardan con compresión LZW (`cv2.IMWRITE_TIFF_COMPRESSION_LZW`), reduciendo su tamaño en disco aproximadamente un 50% sin ninguna pérdida de calidad.
* **Detección del Picture Control de Nikon**:
  * Parser en [`archivos.py`](file:///d:/revelador_nikon/revelador/archivos.py#L68) que extrae de los MakerNotes del RAW el perfil configurado en la cámara (*Standard, Neutral, Vivid, Portrait, Landscape, Flat, Monochrome*).
  * Este dato se refleja en el tooltip de la interfaz web y se incluye en la columna `picture_control` del `informe.csv`.

---

### 3. Configuración (`config.ini`)
Se añaden las siguientes opciones:
* `[revelado] formato_salida = jpeg` (opciones: `jpeg`, `webp`, `ambos`)
* `[revelado] calidad_webp = 90`
* `[revelado] preferir_jpg_camara = no`
* `[revelado] demosaic = aahd`
* `[revelado] corregir_aberraciones = si`
* `[revelado] incrustar_icc = si`
* `[rendimiento] trabajadores = 0`
* `[rendimiento] trabajadores_analisis = 0`

---

### 4. Interfaz de Revelado Interactiva (UI/UX)
* **Histograma RGB y Luminancia en Tiempo Real**:
  * Canvas interactivo (`#canvasHist`) integrado directamente sobre los deslizadores de ajuste.
  * Muestra curvas de los canales Rojo, Verde, Azul y Luminancia superpuestas con modo semitransparente.
  * Cálculo ultra-rápido en cliente (< 1 ms de latencia) a partir del búfer de la vista previa, actualizándose instantáneamente mientras el usuario desliza los controles sin recargar la red.
* **Comparador Antes / Después tipo Cortina (Split-Screen)**:
  * Nuevo modo activable con el botón `🌓 Cortina`.
  * Divide la pantalla con un divisor vertical arrastrable (`#separadorCortina`): a la izquierda muestra la versión original/neutra y a la derecha la imagen con los ajustes aplicados, facilitando el juicio crítico.
* **Lupa de Enfoque 1:1 a Resolución Completa (Pixel-to-Pixel)**:
  * Nuevo botón `🔍 1:1 Loupe` en la barra superior del visor.
  * Al hacer clic en cualquier parte de la foto (ojos, pestañas, detalles finos), se abre un modal con un recorte al 100% de resolución real servido en ~130 ms por el endpoint `/api/recorte`.
* **Avisos de Recorte de Exposición (Clipping Warnings / Zebras)**:
  * Nuevo botón `⚠️ Zebras` y badges de control de exposición:
    * `#clipAltas`: Notifica en rojo si existen altas luces quemadas (> 254).
    * `#clipSombras`: Notifica en azul si existen sombras empastadas (< 2).
  * Al activar el modo, la vista previa colorea en rojo puro las altas luces perdidas y en azul cobalto los negros sin detalle.
* **Copiar y Pegar Ajustes de Revelado (Individual y Grupal)**:
  * Botones `📋 Copiar`, `📥 Pegar` y `👥 Pegar en ráfaga`.
  * Permite clonar la configuración de revelado personalizada de una foto y aplicarla a otra individualmente o propagarla a todas las fotos de la misma serie/ráfaga mediante `/api/ajustes/lote`.
* **Presets Rápidos de Revelado con 1 Clic**:
  * Botones preconfigurados para aplicar estilos fotográficos inmediatos:
    * `Neutro`: Restablece los valores estándar de la cámara.
    * `Retrato`: Contraste suave, microcontraste atenuado en piel y calidez natural.
    * `Paisaje`: Mayor contraste, vibrance, claridad y altas luces recuperadas.
    * `B&N`: Blanco y negro dramático con negros profundos y claridad acentuada.
    * `Hora Dorada`: Calidez dorada (+temperatura, matiz ámbar, altas luces suaves).
    * `Noche Limpia`: Exposición neutral sin ruido en sombras y luces brillantes preservadas.

---

### 5. Formatos y Robustez de Software
* **Exportación a formato WebP**:
  * Nueva función `guardar_webp` con incrustación de perfil ICC sRGB y calidad configurable.
  * Reduce entre un 30% y un 45% el tamaño de las imágenes respecto al JPEG manteniendo idéntica fidelidad visual.
  * Configurable en `config.ini` mediante `formato_salida = webp | jpeg | ambos`.
* **Batería de Pruebas Unitarias Automatizadas**:
  * Creada carpeta `tests/` con 14 pruebas automáticas:
    * `tests/test_color.py`: Conversiones de espacio de color sRGB lineal y no lineal, recorte de alertas.
    * `tests/test_config.py`: Validación de tipos y rangos de configuración.
    * `tests/test_revelado.py`: Flujo de revelado y curvas tonales fotográficas.
    * `tests/test_archivos.py`: Rotaciones EXIF, parser de Picture Control de Nikon y dataclasses.
  * Ejecutable en cualquier momento con `.venv\Scripts\python.exe -m unittest discover tests`.

---

### 6. Optimización del Pipeline Asíncrono de IA (Streaming Continuo GPU/CPU)
* **Diagnóstico del cuello de botella previo**:
  * El revelado unía de forma sincrónica la llamada a la IA con el renderizado completo de la imagen en cada hilo (`[ Petición IA ] -> [ 10s CPU RAW demosaic ]`).
  * Con 4 trabajadores de CPU, los 4 hilos disparaban 4 peticiones simultáneas con visión a la GPU (provocando colas y sobrecarga de VRAM en el servidor local), y luego durante los 10 segundos de cálculo intensivo de CPU, la GPU quedaba totalmente desocupada al 0% sin recibir trabajo.
* **Nueva Arquitectura Productor-Consumidor (Pipeline Desacoplado)**:
  * **Productores IA**: Trabajan con concurrencia controlada (`concurrencia = 2` por defecto) calculando y afinando los ajustes fotográficos en un flujo ininterrumpido.
  * **Búfer intermedio regulado**: En cuanto la IA genera los ajustes de una foto, la deposita en la cola de revelado y pasa inmediatamente a la siguiente foto sin esperar a la CPU.
  * **Consumidores CPU**: Los 4 hilos de exportación toman de forma inmediata las fotos listas y ejecutan el revelado completo a 24-45 MP sin pausas de red ni tiempos muertos de inferencia.
  * **Resultado**: La GPU trabaja a un ritmo óptimo continuo de 2 en 2 (`2, 2, 2, 2...`) sin picos excesivos de VRAM ni valles de inactividad de 10 segundos.
* **Control y Configuración**:
  * Nuevo ajuste `concurrencia = 2` en `config.ini` bajo la sección `[ia]`.
  * Nuevo parámetro de línea de comandos `--ia-concurrencia` en `revelar.py procesar`.
  * Trazabilidad en logs: Ahora cada respuesta de la IA detalla el nombre del archivo al que corresponde (`IA: ajustes recibidos en 1.1s para _DSC1090.NEF`).

---

### 7. Rediseño Visual Studio Pro y Panel de Ajustes Gráfico Integrado
* **Rediseño Visual Completo (Preparación para GitHub)**:
  * Sustitución de la interfaz básica por un diseño oscuro profesional de grado comercial (**Studio Pro Dark Theme**): paleta obsidiana/pizarra con toques dorados Nikon (`#f59e0b`), bordes sutiles y efectos de elevación/sombra.
  * Selector de carpeta moderno con estilo pill y breadcrumb interactivo.
  * Indicador en vivo de estado de la IA con punto pulsante de color (verde activo / gris desconectado).
  * Barra de herramientas con pestañas de filtrado dinámico (`Todas`, `★ Solo elegidas`, `👥 Ráfagas`, `✓ Reveladas`) y caja de búsqueda en tiempo real.
  * Tarjetas de foto con chips flotantes de metadatos, tipo de archivo (`RAW+JPG`, `NEF`), badge dorado de elegida y checkmark de exportación.
  * Editor lateral categorizado en 3 secciones ergonómicas:
    1. ☀️ **Luz y Rango Dinámico** (Exposición, Contraste, Altas Luces, Sombras, Blancos, Negros).
    2. 🎨 **Color y Balance** (Temperatura, Matiz, Intensidad, Saturación).
    3. 🔍 **Detalle y Nitidez** (Claridad, Enfoque, Reducción de Ruido).
  * Deslizadores personalizados con pista de degradado, indicador numérico en vivo y doble clic para restablecer al valor automático.
  * Barra superior en el editor con metadatos EXIF fotográficos (modelo de cámara, Picture Control, apertura, obturación, ISO y focal).
  * Atajos de teclado profesionales: navegación con flechas `◄/►`, `Espacio` para lupa 1:1, `C` para cortina, `Z` para zebras, `P` para marcar elegida, `E` para exportar, `1-6` para presets rápidos, `Esc` para cerrar y `?` para ver la ayuda.
  * Sistema de notificaciones flotantes (Toast) para confirmación de acciones.
* **Panel Gráfico de «Ajustes» (Sin necesidad de tocar código ni archivos ini)**:
  * Nuevo diálogo modal de configuración dividido en 5 pestañas:
    1. *📁 Carpetas & Salida*: Rutas, selector de formato (`JPEG`, `WebP` o `Ambos`), sliders de calidad (70-100), TIFF 16-bit y sidecars `.xmp`.
    2. *📸 Revelado & Color*: Selector de algoritmo demosaic de LibRaw con descripciones, corrección de aberraciones cromáticas, perfil ICC sRGB, preferencia de JPEG procesado por cámara y sliders de intensidad y resolución.
    3. *🤖 Inteligencia Artificial*: Activación, URL de API, modelo, concurrencia (1-4), modo de imagen, opción de razonamiento y botón interactivo **«⚡ Probar Conexión con IA Ahora»**.
    4. *⚡ Rendimiento*: Hilos de exportación CPU e hilos de análisis de miniaturas.
    5. *🎯 Agrupación & Ráfagas*: Tiempos máximos de ráfaga, umbral de similitud visual y pesos de nitidez, ruido y ojos.
  * Los cambios se validan y guardan atómicamente en `config.ini` preservando todos los comentarios del archivo original y aplicándose en tiempo de ejecución sin reiniciar el servidor.
* **Preparación para Repositorio Abierto en GitHub**:
  * Creado archivo `.gitignore` optimizado para proyectos fotográficos y Python.
  * Creada licencia `LICENSE` (MIT).
  * `README.md` reescrito con insignias (badges), diseño de arquitectura, guías de instalación y comandos.
  * 23 pruebas unitarias automatizadas pasando al 100%.

---

### 8. Pulido Visual de Ajustes, YuNet, Clasificación de Escena, Metadatos XMP y Viñeteo (Noviembre 2026 - Fase 3)
* **Corrección de Interfaz en Modal de Ajustes (Scroll y Switches)**:
  * **Switches de alternancia corregidos**: Se corrigió el selector CSS `.cfg-field label { flex: 1; }` que estiraba los conmutadores a barras horizontales gigantes de 350px. Ahora los switches son pastillas compactas y simétricas de 44x24px con transiciones suaves.
  * **Restauración del Scroll y rueda del ratón**: Se solucionó el bloqueo de desplazamiento flexbox (`min-height: 0` en contenedores anidados) y se añadió reenvío de rueda de ratón para que el usuario pueda desplazarse cómodamente con la rueda desde cualquier parte del modal. Se aumentó la visibilidad y contraste de la barra de scroll.
* **Sustitución de Haar Cascades por YuNet OpenCV DNN (Mejora 3.1)**:
  * Integrada red neuronal ligera YuNet (`face_detection_yunet_2023mar.onnx`, 232 KB) mediante `cv2.FaceDetectorYN`.
  * Detección de rostros en 360°, perfiles y ángulos inclinados con predicción directa de puntos clave faciales (ojos y distancias de apertura) sin falsos positivos. Con fallback transparente a Haar Cascades en caso de no disponer del modelo.
* **Clasificación Semántica de Escena con IA Local (Mejora 3.2)**:
  * Cuando la IA está activa, el Vision LLM local clasifica la toma en categorías (`retrato`, `paisaje`, `noche`, `evento`, `arquitectura`, `macro`, `fauna`) en la misma pasada de inferencia (0 latencia extra).
  * La categoría se refleja con una etiqueta flotante en las tarjetas de foto, en el visor de metadatos EXIF y en el `informe.csv`.
* **Etiquetado Semántico y Metadatos IPTC / Dublin Core en XMP (Mejora 3.3)**:
  * Inclusión automática de etiquetas semánticas descriptivas en los sidecars `.xmp` mediante los estándares `<dc:subject><rdf:Bag><rdf:li>...</rdf:li></rdf:Bag></dc:subject>` y `<lr:hierarchicalSubject>`.
  * Total compatibilidad con Adobe Lightroom, Bridge, DigiKam y Apple Photos para filtrado instantáneo por palabras clave.
* **Control y Compensación de Viñeteo Fotográfico (Mejora 3.4)**:
  * Nuevo control fotográfico de Viñeteo (`vineteo`, rango -100 a +100) en el panel de ajuste y motor de revelado.
  * Valores positivos compensan la caída de luz periférica en las esquinas de objetivos angulares o muy luminosos; valores negativos añaden un viñeteo artístico sutil para concentrar la mirada en el sujeto.
  * Exportación del ajuste a Adobe Camera Raw mediante `crs:PostCropVignetteAmount`.
  * Integrado en los estilos rápidos (*Retrato: -12, Paisaje: +10, B&N: -18, etc.*).
* **Suite de Pruebas Unitarias Ampliada**:
  * 27 pruebas automáticas pasando al 100% cubriendo YuNet, viñeteo, generación XMP con metadatos Dublin Core y tags de IA.

---

### 9. Modal de Edición de Gran Formato, Precisión 1:1 en Lupa y Visualización Progresiva en Tiempo Real (Noviembre 2026 - Fase 4)
* **Modal de Edición Inmersivo de Gran Formato (96vw × 94vh)**:
  * Sustitución del antiguo panel lateral derecho estrecho (480px, que limitaba la foto a 290px de alto) por un modal cinematográfico a pantalla casi completa.
  * Área de lienzo fotográfico dominante (hasta 1300×750px de vista previa con proxies a 1600px de resolución) para evaluar enfoque, grano y balance con máxima comodidad.
  * Cabecera de navegación con contador (`Foto X de Y`), botones de navegación `◄/►`, atajos de teclado y acciones directas.
  * Barra de herramientas flotante sobre la foto con accesos rápidos para modo Cortina antes/después, Zebras de recorte de sombras/altas luces, Lupa 1:1 al 100% del sensor, Mantener Neutro temporal y apertura de la imagen revelada a resolución completa.
  * Pie de foto con histograma RGB+Luminancia en vivo, alertas de recorte y chips EXIF con cámara, lente, apertura, obturación, ISO, caras detectadas y etiquetas semánticas de IA.
  * Panel lateral derecho de 380px con desplazamiento independiente para paleta de estilos rápidos y deslizadores de Luz, Color y Detalle.
* **Calibración Subpíxel y Corrección de Orientación en Lupa 1:1**:
  * **Causa raíz de coordenadas erróneas**:
    1. *Doble rotación*: En OpenCV 4.x, `cv2.imdecode` rota automáticamente las imágenes JPEG con metadatos EXIF de orientación. La función `recorte_1a1()` aplicaba posteriormente una segunda rotación manual, provocando desfases de 90° o 180° en fotos verticales.
    2. *Desfase por letterbox (`object-fit: contain`)*: Calcular las coordenadas dividiendo directamente `(clientX - boundingBox.left) / boundingBox.width` incluía las bandas negras verticales u horizontales generadas al adaptar la relación de aspecto de la foto a la ventana.
  * **Solución**:
    1. Se aplica `cv2.IMREAD_IGNORE_ORIENTATION` en la lectura a resolución completa y se valida la orientación geométrica final contra las dimensiones del proxy.
    2. Se implementó `getImgRelativeCoords(e, img)` en el frontend, calculando con exactitud subpíxel los márgenes `(offsetX, offsetY)` reales de la imagen dentro del elemento `<img>`.
    3. Al hacer clic en cualquier punto (ej. el iris de un ojo), la lupa 1:1 muestra con precisión micrométrica el recorte del sensor al 100%, con retícula roja de centrado.
* **Visualización Progresiva en Tiempo Real (Streaming de Fotos en Galería)**:
  * Se eliminó la espera con pantalla vacía durante el análisis de carpetas grandes (ej. 285 fotos).
  * En el endpoint `/api/grupos`, mientras el análisis multihilo está en ejecución (`p.ocupado`), el servidor expone grupos provisionales individuales para cada toma analizada hasta el momento.
  * En el frontend, el bucle `sondear()` detecta el avance de fotos analizadas (`p.hecho`) y actualiza la cuadrícula de forma suave e incremental. Las fotos aparecen en la pantalla tan pronto como su miniatura e histograma son leídos del disco o tarjeta SD.
  * Indicador de estado visual interactivo con animación pulsante indicando el recuento de fotos analizadas en vivo.
* **Soporte de Atajo `Escape` Unificado**:
  * La tecla `Escape` cierra de forma ordenada y jerárquica la lupa 1:1, los modales de atajos, ajustes de configuración o el editor de fotos grande según cuál se encuentre activo.
* **Reparación Integral del Modo Cortina Antes / Después**:
  * **Causa raíz del fallo**:
    1. *Inversión de capas CSS*: `#vistaAntes` (original) tenía `position: absolute` y se ubicaba después de `#vista` en el DOM, provocando que se pintara encima de `#vista`. Como `#vistaAntes` no tenía `clip-path`, tapaba completamente la foto editada (`#vista`), impidiendo ver los cambios en cualquier posición.
    2. *Desincronización geométrica*: `#separadorCortina` se posicionaba en `%` relativo a todo el contenedor (`#wrapVista`, ~1400px), mientras que el `clip-path` de `#vista` operaba en `%` relativo a la foto (ej. 900px), desalineando la línea divisoria respecto al corte de la imagen.
    3. *Falta de precarga y bloqueo por arrastre nativo*: Al pulsar Cortina, la imagen neutra se pedía de forma asíncrona dejando un hueco negro transitorio. Además, al arrastrar con el ratón se activaba el arrastre nativo de archivos de imagen de HTML5 cancelando los eventos `mousemove`.
  * **Solución aplicada**:
    1. Reestructuración de capas: `#vista` (revelada) se sitúa encima con `z-index: 2` y `clip-path` dinámico; `#vistaAntes` (original) se sitúa debajo con `z-index: 1`.
    2. Sincronización subpíxel: `aplicarCortina()` calcula los límites reales de la foto (`photoLeft`, `photoTop`, `vRect.width`, `vRect.height`). El separador y `#vistaAntes` se anclan con precisión milimétrica al marco de la foto.
    3. Precarga inmediata en memoria (`precargarNeutro`): al abrir cualquier foto en el editor, la versión neutra se precarga en segundo plano; al pulsar `C` o el botón «🌓 Cortina», el comparador se activa en 0 ms sin esperas ni parpadeos.
    4. Arrastre fluido y soporte táctil: soporte para clic y arrastre con ratón o pantallas táctiles, cambio automático a cursor `ew-resize` y prevención de arrastre nativo (`draggable="false"`).
    5. Optimización del botón «Mantén: neutro»: ahora utiliza el buffer precargado para alternar instantáneamente al mantener pulsado el ratón.

---

### 10. Documentación y Futuro
* Actualizado [`MEJORAS_FUTURAS.md`](file:///d:/revelador_nikon/MEJORAS_FUTURAS.md) actualizando el progreso y detallando las especificaciones de IA avanzada y aclaraciones sobre LUTs 3D y DNG Lineal.
* Actualizado [`README.md`](file:///d:/revelador_nikon/README.md) con las nuevas capacidades y parámetros.

