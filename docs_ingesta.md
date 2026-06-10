# 📚 Documentación técnica: Módulo de Ingesta (`src/ingestion/`)

> Documento generado para la rama `feature/data-ingestion` — Andrés  
> Cubre: `extractors.py`, `chunking.py` y la librería elegida para cada parte.

---

## Índice

1. [Visión general del flujo](#1-visión-general-del-flujo)
2. [Librería de extracción: PyMuPDF](#2-librería-de-extracción-pymupdf)
3. [extractors.py — ProtocolExtractor](#3-extractorspy--protocolextractor)
   - [extract_text()](#31-extract_text)
   - [clean_text()](#32-clean_text)
4. [Librería de chunking: Recursive Character Splitter propio](#4-librería-de-chunking-recursive-character-splitter-propio)
5. [chunking.py — clases y lógica](#5-chunkingpy--clases-y-lógica)
   - [DocumentChunk](#51-documentchunk)
   - [_RecursiveCharacterSplitter](#52-_recursivecharactersplitter)
   - [ProtocolChunker](#53-protocolchunker)
6. [Flujo completo de ejecución](#6-flujo-completo-de-ejecución)
7. [Resultado: estructura del JSON de salida](#7-resultado-estructura-del-json-de-salida)
8. [Decisiones de diseño](#8-decisiones-de-diseño)

---

## 1. Visión general del flujo

```
data/raw/*.pdf
      │
      ▼
 ProtocolExtractor.extract_text()   ← PyMuPDF lee el PDF página a página
      │  texto crudo (string)
      ▼
 ProtocolExtractor.clean_text()     ← 5 capas de limpieza con regex
      │  texto limpio (string)
      ▼
 ProtocolChunker.chunk_text()       ← detecta fases + Recursive Splitter
      │  List[DocumentChunk]
      ▼
 ProtocolChunker.save_chunks()      ← serializa a JSON con Pydantic
      │
      ▼
data/processed/protocolos_chunks.json   ← listo para Salvador (pgvector)
```

---

## 2. Librería de extracción: PyMuPDF

### ¿Qué es?

**PyMuPDF** (nombre de paquete en PyPI: `pymupdf`, nombre de importación: `fitz`) es un wrapper en C/Python sobre la biblioteca **MuPDF**, que es el motor PDF más utilizado en producción (también lo usa Firefox y otros navegadores para renderizar PDFs).

```
pip install pymupdf>=1.24.0
```

### ¿Por qué se eligió sobre las alternativas?

| Librería | Velocidad | Calidad de texto | PDFs mixtos/escaneados | Peso |
|---|---|---|---|---|
| **PyMuPDF** ✅ | Muy alta (C nativo) | Excelente, respeta layout | Sí, con heurísticas | Liviana |
| `pdfplumber` | Media | Buena, orientada a tablas | Limitado | Media |
| `pypdf` | Media | Básica, problemas con encoding | No | Liviana |
| `pdfminer.six` | Baja | Buena | Limitado | Media |

PyMuPDF fue elegida porque:
- Es la **más rápida** para procesar muchos PDFs (importante cuando se procesan 191 páginas de 7 documentos)
- Maneja bien los PDFs del gobierno argentino, que mezclan texto real con imágenes y layouts complejos
- La API es simple y directa
- No tiene dependencias pesadas

### Cómo se importa

```python
import fitz  # así se llama el módulo de PyMuPDF al importarlo
```

El nombre `fitz` es un homenaje histórico al creador de MuPDF. En el código hay un `try/except` para que si PyMuPDF no está instalado, el módulo no rompa la PoC de los demás integrantes del equipo.

---

## 3. `extractors.py` — `ProtocolExtractor`

Archivo: [`src/ingestion/extractors.py`](../src/ingestion/extractors.py)

### 3.1 `extract_text()`

```python
def extract_text(self, pdf_path: str) -> str:
```

**Qué hace paso a paso:**

```
1. Verifica si el archivo existe
       │
       ├── NO → devuelve el texto mock (protocolo simulado)
       │         permite que el resto del equipo siga sin PDFs
       │
       └── SÍ → abre el PDF con fitz.open()
                     │
                     └── itera cada página con page.get_text("text")
                               │
                               └── acumula solo páginas con contenido
                                   y concatena con "\n"
```

**El argumento `"text"` de `page.get_text()`** le indica a PyMuPDF que extraiga el texto en orden de lectura natural (de arriba a abajo, de izquierda a derecha), que es el modo más útil para documentos de protocolo.

PyMuPDF también soporta otros modos como `"html"`, `"dict"` (con coordenadas de cada palabra), `"blocks"` (párrafos), pero para este caso el modo `"text"` es suficiente y más limpio.

**Manejo de errores:** si el PDF está dañado o encriptado, el `try/except` captura la excepción y devuelve string vacío en vez de romper el pipeline.

---

### 3.2 `clean_text()`

```python
def clean_text(self, raw_text: str) -> str:
```

El texto crudo de los PDFs gubernamentales viene lleno de ruido: números de página, headers repetidos, secciones judiciales, ligaduras unicode mal codificadas, etc. `clean_text` aplica **5 capas de limpieza en orden**:

---

#### Capa 1 — Eliminar secciones judiciales/periciales

```python
judicial_patterns = [
    r'INFORMACI[OÓ]N JUDICIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
    r'PRESERVACI[OÓ]N DE PRUEBAS.*?',
    r'CADENA DE CUSTODIA.*?',
    r'PERITOS?[:\s].*?',
    r'ACTUACI[OÓ]N PERICIAL.*?',
    r'DECLARACI[OÓ]N TESTIMONIAL.*?',
    r'INSTRUCCI[OÓ]N JUDICIAL.*?',
    r'FALLO JUDICIAL.*?',
    r'EXPEDIENTE\s+N[°º]?\s*\d+.*?',
]
```

**Por qué:** el asistente es para respuesta rápida a emergencias, no para asistencia legal. Los protocolos oficiales argentinos incluyen secciones sobre preservación de evidencia, actuación pericial y procedimientos judiciales que son irrelevantes (y potencialmente confusas) para un socorrista en el momento del siniestro.

**Cómo funciona el regex:** `.*?(?=\n[A-Z...]{4,}:|\Z)` usa **lookahead** para borrar desde el encabezado de la sección hasta el inicio de la siguiente sección en mayúsculas (o hasta el final del documento). El flag `re.DOTALL` hace que `.` también capture saltos de línea, permitiendo borrar bloques completos de texto.

La clase de caracteres `[OÓ]` en `INFORMACI[OÓ]N` cubre tanto la versión con tilde como sin ella, porque los PDFs no siempre están bien codificados.

---

#### Capa 2 — Artefactos comunes de PDFs

Elimina ruido visual que PyMuPDF extrae literalmente del documento:

| Patrón | Qué elimina | Ejemplo |
|---|---|---|
| `[-–]\s*\d{1,4}\s*[-–]` | Numeración de página con guiones | `- 12 -` |
| `[Pp]ágina\s+\d+\s+de\s+\d+` | Pie de página con número | `Página 3 de 45` |
| `^\s*\d{1,4}\s*$` | Número solo en una línea | `7` |
| `https?://\S+` | URLs en pies de página | `https://www.argentina.gob.ar/...` |
| `\S+@\S+\.\S+` | Correos electrónicos | `info@ministerio.gob.ar` |
| `^[\s\-_=*]{3,}$` | Separadores visuales | `─────────────` |

---

#### Capa 3 — Ligaduras y caracteres unicode problemáticos

Los PDFs usan ciertas combinaciones de letras como **caracteres únicos** (ligaduras tipográficas). PyMuPDF las extrae tal cual, pero los modelos de embeddings no las reconocen correctamente.

```python
unicode_replacements = {
    '\ufb01': 'fi',   # ﬁ → fi  (la más común en PDFs)
    '\ufb02': 'fl',   # ﬂ → fl
    '\u2019': "'",    # comilla tipográfica derecha
    '\u2018': "'",    # comilla tipográfica izquierda
    '\u201c': '"',
    '\u201d': '"',
    '\u2013': '-',    # guión en (–)
    '\u2014': '-',    # guión em (—)
    '\u00a0': ' ',    # espacio no separable (invisible pero rompe tokenización)
    '\u2022': '-',    # viñeta (•)
}
```

> [!NOTE]
> El espacio no separable (`\u00a0`) es especialmente peligroso porque visualmente parece un espacio normal pero los tokenizadores de LLMs y modelos de embeddings lo tratan como un carácter distinto, rompiendo las palabras.

---

#### Capa 4 — Eliminación de headers/footers repetidos

Los documentos oficiales tienen encabezados institucionales que se repiten en cada página (ej. `"MINISTERIO DE SEGURIDAD - PROVINCIA DE BUENOS AIRES"`). Estos son muy ruidosos para el RAG porque no aportan información semántica.

```python
line_counts = Counter(ln.strip() for ln in lines if len(ln.strip()) > 10)
repeated_lines = {ln for ln, count in line_counts.items() if count >= 3}
```

**Estrategia:** cualquier línea de más de 10 caracteres que aparezca **3 o más veces** en el documento se considera header/footer y se elimina. El umbral de 10 caracteres evita falsos positivos con palabras cortas comunes como "Artículo" o "Ver".

---

#### Capa 5 — Normalización de espacios

```python
cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)   # máximo 2 saltos consecutivos
cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)    # espacios múltiples → uno
cleaned = '\n'.join(ln.strip() for ln in cleaned.split('\n'))  # trim por línea
```

Deja el texto en un estado limpio y consistente antes de pasar al chunker.

---

## 4. Librería de chunking: Recursive Character Splitter propio

### El problema del chunking

No se puede pasar el texto completo de un PDF al modelo de embeddings porque:
- Los modelos tienen límite de tokens (generalmente 512 o 8192)
- Los fragmentos muy largos "diluyen" la información importante
- El RAG necesita recuperar fragmentos precisos y relevantes, no documentos enteros

### ¿Por qué no usar LangChain o llama-index?

Se descartaron porque:
- LangChain instala **más de 30 dependencias transitivas** y pesa ~200 MB
- Llama-index es aún más pesado
- El algoritmo de `RecursiveCharacterTextSplitter` de LangChain es conceptualmente simple y se puede replicar en ~60 líneas de Python puro

### ¿Qué es el Recursive Character Splitter?

Es el algoritmo de chunking **más robusto para texto no estructurado**. A diferencia de dividir simplemente cada N caracteres (que puede cortar en medio de una oración), este algoritmo respeta la estructura semántica del texto usando una jerarquía de separadores:

```
Nivel 1: "\n\n"  (párrafos)       ← intenta dividir aquí primero
Nivel 2: "\n"    (líneas)         ← si el párrafo es muy largo
Nivel 3: ". "    (oraciones)      ← si la línea es muy larga
Nivel 4: " "     (palabras)       ← si la oración es muy larga
Nivel 5: ""      (caracteres)     ← último recurso
```

**Principio:** prefiere siempre el separador más "grande" (semánticamente más relevante). Solo baja al siguiente nivel si el fragmento resultante todavía excede `chunk_size`.

---

## 5. `chunking.py` — clases y lógica

Archivo: [`src/ingestion/chunking.py`](../src/ingestion/chunking.py)

### 5.1 `DocumentChunk`

```python
class DocumentChunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    fase_protocolo: str = Field(default="GENERAL")
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

Modelo Pydantic que representa un fragmento procesado. Campos:

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `str` (UUID4) | Identificador único generado automáticamente. Sirve como clave primaria cuando Salvador inserte en pgvector. |
| `text` | `str` | El texto del fragmento, ya limpio. |
| `fase_protocolo` | `str` | La fase del protocolo a la que pertenece este chunk. Está **también** en `metadata` para que Salvador pueda filtrarlo directamente en el modelo sin parsear el dict. |
| `metadata` | `Dict[str, Any]` | Metadatos adicionales: `source`, `pdf_path`, `fase_protocolo`, `chunk_index`, `total_chunks_in_phase`. |

> [!IMPORTANT]
> El campo `fase_protocolo` se agregó al modelo Pydantic (no solo en `metadata`) para que el equipo de retrieval pueda hacer filtros directos: `chunk.fase_protocolo == "PROTEGER"` sin tener que acceder a `chunk.metadata["fase_protocolo"]`.

---

### 5.2 `_RecursiveCharacterSplitter`

Clase interna (prefijo `_` indica uso interno, no forma parte del contrato público).

```python
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
```

Tiene dos métodos principales:

#### `_split_recursive(text, separators)`

```
texto de entrada
      │
      ├── ¿tiene "\n\n"? → divide por párrafos
      │         │
      │         └── ¿algún párrafo > chunk_size?
      │                   │
      │                   └── recurse con ["\n", ". ", " ", ""]
      │
      └── ¿no tiene separador actual? → corta por carácter
```

Cada fragmento resultante se acumula en una lista plana. Si el fragmento cabe en `chunk_size`, se agrega directo. Si no, se subdivide recursivamente con el siguiente separador.

#### `_merge_with_overlap(chunks)`

Después de dividir, muchos fragmentos quedan muy pequeños (una oración suelta, por ejemplo). Esta función los **fusiona de izquierda a derecha** hasta que el acumulado alcance `chunk_size`. Cuando no caben más, cierra el chunk actual y empieza uno nuevo **añadiendo los últimos `chunk_overlap` caracteres** del chunk anterior al inicio del siguiente.

```
chunk_overlap = 50 caracteres

chunk 1: "...el socorrista debe verificar que la escena esté asegurada."
                                            ┌──── últimos 50 chars ────┐
chunk 2: "...escena esté asegurada. Luego proceder a asistir al herido..."
         └── overlap ──┘
```

El overlap garantiza que el contexto no se pierda en los bordes de los chunks, lo que es crítico para que el RAG recupere respuestas coherentes.

---

### 5.3 `ProtocolChunker`

La clase pública que orquesta todo el proceso de chunking.

#### `PHASE_MARKERS`

Un listado de tuplas `(nombre_de_fase, patron_regex)` calibradas con los documentos reales:

```
Categoría                  │ Fases detectadas
───────────────────────────┼────────────────────────────────────────
Mock / protocolo tipo      │ TOMA DE CONOCIMIENTO, ARRIBO, INTERVENCION
Metodología PAS            │ PROTEGER, ALERTAR, SOCORRER
Primeros auxilios          │ EVALUACION VICTIMA, RCP
Documentos institucionales │ PROCEDIMIENTO, GESTION EMERGENCIA, RECURSOS
```

Los patrones usan clases de caracteres como `[OÓ]` para cubrir variantes con/sin tilde, dado que los PDFs gubernamentales no siempre respetan el encoding UTF-8 correctamente.

---

#### `chunk_text()` — el algoritmo en 4 pasos

```
texto limpio de entrada
        │
        ▼
Paso 1: Recorrer PHASE_MARKERS con re.search()
        Guardar (posición_en_texto, nombre_de_fase) para cada match
        Evitar duplicados (si "PROTEGER" matchea dos variantes, se toma solo la primera)
        Ordenar por posición de aparición
        │
        ├── ¿Se encontraron fases?
        │         │
        │         ▼
        │   Paso 2: Segmentar el texto
        │   Para cada fase: texto[inicio_fase : inicio_siguiente_fase]
        │         │
        │         ▼
        │   Paso 3: Aplicar _RecursiveCharacterSplitter sobre cada segmento
        │   Cada sub-chunk hereda la fase_protocolo de su segmento
        │         │
        │         ▼
        │   → List[DocumentChunk] con fases asignadas
        │
        └── ¿No se encontraron fases?
                  │
                  ▼
            Paso 4: Fallback — aplicar splitter al texto completo
            Todos los chunks reciben fase_protocolo = "GENERAL"
```

#### `save_chunks()`

Serializa la lista de `DocumentChunk` a JSON usando `model_dump()` de Pydantic v2, garantizando que todos los campos (incluido el UUID) sean serializables. Crea el directorio `data/processed/` si no existe.

---

## 6. Flujo completo de ejecución

Al correr `python src/ingestion/chunking.py` con `PYTHONPATH=.`:

```
data/raw/
├── 734369234-anexo-12-plan...pdf   (45 págs → 59.286 chars → 98 chunks)
├── Documento152.pdf                (42 págs → 55.070 chars → 100 chunks)
├── educacionvial_mar2019...pdf     (12 págs → 16.826 chars → 21 chunks)
├── GUIA-DE-PRIMEROS-AUXILIOS...pdf (38 págs → 50.301 chars → 79 chunks)
├── Guía Siniestros Viales VF.pdf   (31 págs → 25.394 chars → 32 chunks)
├── mini-guia-reanimacion...pdf     (13 págs →  8.570 chars → 19 chunks)
└── Ministerio de seguridad GBA.pdf (10 págs → 12.090 chars → 23 chunks)

Total: 191 páginas → 372 chunks → data/processed/protocolos_chunks.json
```

Distribución de fases detectadas:
- `PROCEDIMIENTO`: 307 chunks
- `RECURSOS`: 46 chunks
- `GENERAL` (sin marcador): 19 chunks

---

## 7. Resultado: estructura del JSON de salida

Cada elemento del array en `data/processed/protocolos_chunks.json` tiene esta estructura:

```json
{
    "id": "f3a2b1c4-...",
    "text": "El equipo de emergencia debe verificar que la escena...",
    "fase_protocolo": "PROCEDIMIENTO",
    "metadata": {
        "source": "Ministerio de seguridad GBA.pdf",
        "pdf_path": "data/raw/Ministerio de seguridad GBA.pdf",
        "fase_protocolo": "PROCEDIMIENTO",
        "chunk_index": 2,
        "total_chunks_in_phase": 23
    }
}
```

Este formato es el contrato con Salvador: puede leer el JSON, generar embeddings de `text` e insertar en pgvector usando `id` como clave primaria y `fase_protocolo` como columna de metadato para filtros.

---

## 8. Decisiones de diseño

### ¿Por qué no usar LangChain para el splitter?

LangChain instala más de 30 paquetes y pesa ~200 MB. El algoritmo del `RecursiveCharacterTextSplitter` es conceptualmente simple (unos 60 líneas de lógica real). Implementarlo en Python puro no agrega ninguna dependencia al proyecto y produce resultados idénticos.

### ¿Por qué `fase_protocolo` está tanto en `DocumentChunk` como en `metadata`?

- En `DocumentChunk`: permite acceso directo `chunk.fase_protocolo` sin parsear dicts. Facilita el trabajo de Salvador para filtrar por fase al insertar en pgvector.
- En `metadata`: mantiene el contrato original del equipo donde todos los metadatos adicionales van en ese dict. No se rompe ninguna firma existente.

### ¿Por qué el fallback mock se mantiene?

Si PyMuPDF no está instalado o el archivo no existe, `extract_text()` devuelve el texto simulado original. Esto permite que el evaluador del equipo (`tests_eval/evaluator.py`) siga corriendo en la máquina de cualquier integrante aunque no tenga los PDFs o la librería instalada.

### ¿Por qué el import de `fitz` está dentro de un `try/except`?

Por la misma razón del fallback mock: no queremos que un `ImportError` rompa el pipeline completo. El módulo anuncia claramente qué instalar si falta, pero deja el resto del sistema operativo.

---

## 9. Cómo probar el módulo desde bash

> Todos los comandos se ejecutan desde la raíz del proyecto (`Asistente_de_emergencias/`).  
> Si usás PowerShell en Windows, reemplazá `export` por `$env:VARIABLE="valor"`.

### Configuración inicial (una sola vez)

```bash
# Crear y activar entorno virtual
python -m venv venv
source venv/Scripts/activate        # Windows bash/Git Bash
# source venv/bin/activate          # Linux / macOS

# Instalar dependencias
pip install -r requirements.txt
```

> [!NOTE]
> `psycopg2-binary` y `pgvector` pueden mostrar warnings si no tenés PostgreSQL instalado — es normal, son dependencias de Salvador y no afectan tu módulo.

---

### Prueba 1 — Solo el extractor

Ve el texto limpiado de cada PDF impreso en consola (primeros 500 chars por documento).

```bash
export PYTHONPATH="."
export PYTHONIOENCODING="utf-8"
python src/ingestion/extractors.py
```

Salida esperada por cada PDF:
```
============================================================
Procesando: data/raw/<nombre>.pdf
[Extractor] Procesando '<nombre>' — N páginas.
[Extractor] Texto crudo extraído: XXXXX caracteres.
Caracteres tras limpieza: XXXXX
--- Primeros 500 chars ---
...texto limpio...
```

---

### Prueba 2 — Pipeline completo (extracción + limpieza + chunking + guardado)

Genera los archivos en `data/processed/`.

```bash
export PYTHONPATH="."
export PYTHONIOENCODING="utf-8"
python src/ingestion/chunking.py
```

Salida esperada:
```
[Main] Procesando: <nombre>.pdf
[Extractor] Procesando '<nombre>' — N páginas.
[Main]   Texto limpio guardado -> 'data/processed/clean/<nombre>_clean.txt' (XXXXX chars)
[Main]   Chunks generados -> NN
...
[Chunker] Se han guardado 372 fragmentos en 'data/processed/protocolos_chunks.json'.

[Main] Distribucion por fase:
  GENERAL: 19 chunks
  PROCEDIMIENTO: 307 chunks
  RECURSOS: 46 chunks
```

Archivos generados:
```
data/processed/
├── protocolos_chunks.json          ← todos los chunks en JSON
└── clean/
    ├── <nombre>_clean.txt          ← texto limpio de cada PDF
    └── ...
```

---

### Prueba 3 — Inspeccionar el texto limpio de un PDF

```bash
# Ver los primeros 2000 caracteres del texto limpio de la guía de siniestros
cat "data/processed/clean/Guía Siniestros Viales VF_clean.txt" | head -c 2000

# O con less para navegar interactivamente
less "data/processed/clean/Ministerio de seguridad GBA_clean.txt"
```

---

### Prueba 4 — Inspeccionar el JSON de chunks

```bash
# Cantidad total de chunks
python -c "
import json
with open('data/processed/protocolos_chunks.json', encoding='utf-8') as f:
    chunks = json.load(f)
print(f'Total chunks: {len(chunks)}')
"

# Ver los primeros 3 chunks con detalle
python -c "
import json
with open('data/processed/protocolos_chunks.json', encoding='utf-8') as f:
    chunks = json.load(f)
for c in chunks[:3]:
    print('---')
    print('id:            ', c['id'])
    print('fase_protocolo:', c['fase_protocolo'])
    print('fuente:        ', c['metadata']['source'])
    print('chunk_index:   ', c['metadata']['chunk_index'])
    print('texto (200c):  ', c['text'][:200])
    print()
"

# Contar chunks por fase
python -c "
import json
from collections import Counter
with open('data/processed/protocolos_chunks.json', encoding='utf-8') as f:
    chunks = json.load(f)
fases = Counter(c['fase_protocolo'] for c in chunks)
for fase, n in fases.most_common():
    print(f'{n:>4}  {fase}')
"

# Ver chunks de una fase específica (ej. PROCEDIMIENTO)
python -c "
import json
with open('data/processed/protocolos_chunks.json', encoding='utf-8') as f:
    chunks = json.load(f)
filtrados = [c for c in chunks if c['fase_protocolo'] == 'PROCEDIMIENTO']
print(f'Chunks de PROCEDIMIENTO: {len(filtrados)}')
print(filtrados[0]['text'][:500])
"
```

---

### Prueba 5 — Evaluador del equipo (no romper contratos)

Verifica que tus cambios no rompieron ningún contrato con el resto del equipo.

```bash
export PYTHONPATH="."
export PYTHONIOENCODING="utf-8"
python tests_eval/evaluator.py
```

Resultado esperado:
```
Número de casos evaluados: 5
Latencia promedio:          ~4000 ms
Precisión de Guardrails:   100.0% (5/5)
Precisión de Respuestas:    100.0% (5/5)
```

> [!IMPORTANT]
> Si algún test falla antes del merge, revisá que no hayas modificado los nombres de `extract_text()`, `clean_text()`, `chunk_text()` o `save_chunks()`.

---

### Prueba 6 — Verificar que PyMuPDF está instalado

```bash
python -c "import fitz; print('PyMuPDF OK, version:', fitz.__version__)"
```

---

*Documentación generada para la rama `feature/data-ingestion`. Para preguntas o ajustes, contactar a Andrés antes del merge.*
