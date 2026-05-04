# Arquitectura del Sistema de Sugerencia Automática de FAQs

## Visión general

Este prototipo está diseñado como una arquitectura de microservicios ligera, modular y orientada a CPU. No incluye frontend y se apoya en modelos de código abierto para mantener costos bajos y permitir ejecución local.

## Servicios principales

1. **Ingest Service** (`ingest_service.py`)
   - Extrae conversaciones históricas de PostgreSQL.
   - Normaliza contenido JSON de `chat_messages`.
   - Genera un archivo intermedio `data/conversations.jsonl` con pares `user_text` / `assistant_text`.

2. **Embedding Service** (`embed_service.py`)
   - Expone un endpoint de embedding semántico.
   - Usa el modelo local `sentence-transformers/all-MiniLM-L6-v2`.
   - Optimizado para ejecución en CPU.

3. **Suggestion Service** (`suggestion_service.py`)
   - Consume los pares procesados y genera clusters de preguntas recurrentes.
   - Propone FAQs representativas con respuestas sugeridas.
   - Evalúa calidad con métricas como `silhouette_score`.
   - Guarda el resultado en `data/faq_suggestions.json`.

4. **Validation Service** (`validation_service.py`)
   - Expone un endpoint para validación humana.
   - Registra aprobaciones/rechazos en `data/faq_validations.json`.

5. **Scheduler** (`scheduler.py`)
   - Orquesta la ejecución periódica del pipeline.
   - Ejecuta ingesta y generación de sugerencias cada 24 horas.

## Flujo de datos

1. El servicio de ingestión lee la tabla `chat_messages`.
2. Extrae mensajes de usuario y empareja con la respuesta del asistente.
3. Guarda los pares en `data/conversations.jsonl`.
4. El servicio de sugerencias lee esos pares y calcula embeddings locales.
5. Se realiza clustering para agrupar patrones semánticos.
6. Se generan propuestas de FAQ y se persisten en `data/faq_suggestions.json`.
7. El servicio de validación permite revisiones humanas sobre cada sugerencia.

## Modelo NLP seleccionado

- Modelo: `sentence-transformers/all-MiniLM-L6-v2`
- Características:
  - CPU-friendly.
  - Open source.
  - Rápido para inferencia en texto corto.
  - Adecuado para embeddings semánticos y clustering.

## Buenas prácticas implementadas

- Separación de responsabilidades por servicio.
- Estructura modular con utilidades compartidas (`faq_common.py`).
- Uso de `FastAPI` para APIs livianas y testeables.
- Manejo de datos intermedios con archivos JSONL/JSON.
- Job programado con `APScheduler`.
- Ajuste de clústeres para no crear demasiadas categorías cuando hay pocos datos.

## Extensiones futuras

- Reemplazar KMeans por DBSCAN/HDBSCAN si se desea descubrir patrones no lineales.
- Añadir un microservicio de revisión automática que actualice un repositorio de FAQs aprobado.
- Implementar `docker-compose` para desplegar cada servicio en contenedores separados.

## Cómo ejecutar

1. Instalar dependencias:
   ```bash
   sudo apt install -y python3-psycopg2 python3-dotenv
   pip3 install -r requirements.txt
   ```
2. Iniciar servicios en terminales separados:
   ```bash
   python3 ingest_service.py
   python3 embed_service.py
   python3 suggestion_service.py
   python3 validation_service.py
   ```
3. Ejecutar el scheduler:
   ```bash
   python3 scheduler.py
   ```
