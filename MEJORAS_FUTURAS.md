# 📋 Mejoras Futuras y Hoja de Ruta — Revelador Nikon

Este documento recopila el estado de las mejoras implementadas y las propuestas pendientes para el proyecto, detallando su objetivo, diseño técnico e instrucciones para su implementación cuando se decida abordarlas.

---

## 1. Interfaz Web y Experiencia de Usuario (UI/UX) — ✅ IMPLEMENTADO

- [x] **1.1 Histograma Interactivo en Tiempo Real**:
  - Implementado en `#canvasHist` con renderizado de curvas RGB y canal de Luminancia directamente en el cliente a partir del búfer del preview en canvas (< 1 ms de latencia, sin carga en el backend).
- [x] **1.2 Comparador Antes / Después tipo Cortina (Split-Screen Slider)**:
  - Implementado con el botón `🌓 Cortina` y divisor interactivo `#separadorCortina`. Permite contrastar de un vistazo la versión neutra de cámara con los ajustes aplicados.
- [x] **1.3 Zoom al 100% (1:1 Pixel a Pixel)**:
  - Implementado con el botón `🔍 Lupa 1:1` y el endpoint `/api/recorte`. Proporciona inspección de nitidez a resolución real (130 ms de respuesta) para verificar foco crítico en ojos y pestañas.
- [x] **1.4 Avisos de Recorte de Exposición (Clipping Warnings / Zebras)**:
  - Implementado con el botón `⚠️ Zebras` y badges de porcentaje (`#clipAltas`, `#clipSombras`). Muestra altas luces quemadas en rojo puro y sombras empastadas en azul cobalto.
- [x] **1.5 Copiar y Pegar Ajustes (Individual y por Grupo)**:
  - Implementado con botones `📋 Copiar`, `📌 Pegar` y `👥 En toda la ráfaga` mediante el endpoint `/api/ajustes/lote`.
- [x] **1.6 Presets Rápidos de Revelado**:
  - Implementados selectores de 1 clic: *Neutro, Retrato Suave, Paisaje Vívido, B&N Dramático, Hora Dorada y Noche Limpia*.
- [x] **1.7 Panel Gráfico de Ajustes Completo (Settings Modal)**:
  - Permite configurar carpetas, calidad JPEG/WebP, TIFF16, demosaicing, corrección de aberraciones, parámetros de IA con test interactivo y rendimiento sin tocar código ni `config.ini`.
- [x] **1.8 Atajos de Teclado Profesionales**:
  - Navegación con `◄/►`, lupa con `Espacio`, cortina con `C`, zebras con `Z`, elegir con `P`, presets con `1-6`, exportar con `E`, y ayuda con `?`.
- [x] **1.9 Filtros Dinámicos y Búsqueda en Vivo**:
  - Pestañas rápidas para filtrar por todas, elegidas (★), ráfagas (👥), reveladas (✓) y buscador instantáneo de archivos.

---

## 2. Formatos y Robustez de Software — ✅ IMPLEMENTADO

- [x] **2.1 Exportación a WebP**:
  - Implementado soporte para `formato_salida = webp | jpeg | ambos` en `config.ini` y `revelador/revelado.py` (`guardar_webp()`) con incrustación de perfil ICC sRGB y calidad ajustable (`calidad_webp = 90`). Reduce entre un 30% y un 45% el tamaño de archivo manteniendo la misma calidad percibida.
- [x] **2.2 Batería de Pruebas Unitarias Automatizadas**:
  - Implementada suite en `tests/` con 23 pruebas automáticas cubriendo espacios de color, transformaciones tonales sRGB lineal/gamma, configuración atómica, pipeline de streaming, IA y API Web Flask. Ejecutable con `python -m unittest discover tests`.
- [x] **2.3 Pipeline Asíncrono de IA (Streaming Continuo GPU/CPU)**:
  - Desacoplamiento productor-consumidor (`concurrencia = 2` por defecto): alimenta la GPU sin tiempos muertos mientras los 4 hilos de CPU revelan RAWs en paralelo.
- [x] **2.4 Preparación para Repositorio Abierto en GitHub**:
  - Creados `.gitignore`, `LICENSE` (MIT) y `README.md` profesional con badges y guías completas.

---

## 3. Inteligencia y Óptica Avanzada (Fase 3) — ✅ IMPLEMENTADO

- [x] **3.1 Sustitución de Haar Cascades por YuNet (OpenCV DNN)**:
  - Implementado con `cv2.FaceDetectorYN` y el modelo oficial `revelador/modelos/face_detection_yunet_2023mar.onnx` (232 KB).
  - Detección precisa de rostros en cualquier orientación (360°, perfiles, inclinaciones) y cálculo de puntos clave faciales para medir ojos abiertos con precisión superior sin falsos positivos. Fallback automático a Haar si no se detecta el modelo.
- [x] **3.2 Clasificación Semántica de Escena con Qwen Local (Solo si la IA está activa)**:
  - En la pasada de inferencia visual, el modelo clasifica la toma en `retrato`, `paisaje`, `noche`, `evento`, `arquitectura`, `macro` o `fauna`.
  - Visible en la interfaz con badges en las tarjetas de foto, en el visor de metadatos EXIF y registrado en `informe.csv`.
- [x] **3.3 Etiquetado Semántico y Metadatos IPTC / Dublin Core**:
  - Escritura de palabras clave y categoría directamente en los archivos de metadatos `.xmp` bajo los esquemas `<dc:subject>` y `<lr:hierarchicalSubject>`.
  - Compatible de forma nativa con Adobe Lightroom, Bridge, DigiKam y Apple Photos para filtrado y búsqueda instantánea.
- [x] **3.4 Corrección y Control de Viñeteo de Objetivos**:
  - Nuevo deslizador y ajuste `vineteo` (-100 a +100) en el motor fotográfico con fórmula de caída radial cuadrática vectorizada (`r^2`).
  - Permite compensar la viñeta periférica en aperturas amplias o aplicar un oscurecimiento artístico periférico suave. Guardado en `.xmp` mediante `crs:PostCropVignetteAmount`.

---

## 4. Propuestas en Evaluación — ⏳ PENDIENTE / EN EVALUACIÓN

### 4.1 Soporte de LUTs 3D (.cube) para Emulación de Película Analógica
* **Evaluación técnica**:
  * El motor actual utiliza emulación matemática de curvas Picture Control de Nikon (estándar, neutro, vívido, retrato, monocromo, hora dorada, noche limpia) con transformaciones nativas sRGB lineal/gamma de alto rendimiento.
  * La interpolación trilineal de archivos `.cube` añadiría dependencias externas pesadas o ralentizaciones en CPU sin aportar mejoras sustanciales frente a las curvas tonales fotográficas calibradas actuales. Se mantiene en reserva si surge demanda específica de emulaciones analógicas concretas (Kodak Portra, Fuji Velvia).

### 4.2 Exportación a DNG Lineal de 16 bits
* **Evaluación técnica**:
  * Un DNG lineal contiene datos demosaicados en el contenedor RAW de Adobe.
  * Revelador Nikon ya proporciona una solución superior y no propietaria:
    1. **TIFF de 16 bits sin pérdidas** (con compresión LZW) para edición de máxima profundidad en Photoshop / Capture One.
    2. **Sidecars `.xmp` universales** para Adobe Lightroom y Camera Raw que enlazan con el NEF original preservando la flexibilidad completa del sensor.
  * Generar archivos DNG binarios válidos requeriría obligar al usuario a instalar Adobe DNG Converter (aplicación cerrada de 600 MB en Windows) o librerías TIFF/EP complejas con riesgo de incompatibilidades en perfiles de color de cámaras recientes. Se considera completamente cubierto por la exportación TIFF-16 + XMP.
