# AI Onboarding Agent

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/langgraph-conditional%20branch-7755aa)
![Gemini](https://img.shields.io/badge/gemini-structured%20outputs-4285F4)
![License](https://img.shields.io/badge/license-MIT-green)

> Una persona reclutadora gasta entre 6 y 10 minutos por candidato viendo
> entrevistas asíncronas y cruzando lo que dicen con lo que pone en el
> CV. Este agente lo hace en menos de un minuto y, sobre todo, **detecta
> inconsistencias entre transcript y documentos** que un humano apurado
> deja pasar.

🔴 **Live demo:** [ai-onboarding-agent-phi.vercel.app](https://ai-onboarding-agent-phi.vercel.app)
— corre **Gemini real con structured outputs** sobre LangGraph en una
función serverless de Vercel.

![demo screenshot placeholder — pega aquí un GIF cuando lo grabes](https://via.placeholder.com/1200x600.png?text=AI+Onboarding+Agent+%C2%B7+demo+GIF)

## Qué hace

Recibe la grabación transcrita de una entrevista asíncrona tipo
**Hireflix** y los documentos del candidato (CV, certificados,
referencias). Devuelve un reporte tipado con:

- **6 competencias** puntuadas 0–10 con evidencia citada del transcript
- **Verificación documento por documento** contra lo dicho en la entrevista
- **Red flags** clasificadas por severidad (`low | medium | high`)
- **Score global** y recomendación final ∈ `strong_hire | hire | hire_with_caveats | no_hire`
- Para candidatos *borderline*: **2-3 preguntas de seguimiento** generadas por la rama condicional `deep_dive` para usar en una segunda ronda

## Arquitectura

```mermaid
flowchart LR
    A[ingest] --> B[transcribe]
    B --> C[extract_documents]
    C --> D[analyze_answers]
    D --> E[verify_documents]
    E --> F[score_candidate]
    F -->|score &isin; [5.5, 6.5]| G[deep_dive]
    F -->|otherwise| H[generate_report]
    G --> H
    H --> Z((END))

    style G fill:#FBF3E6,stroke:#E9D3A9
    style F fill:#fff,stroke:#7BA69F
```

| Nodo                | Qué hace                                                                          |
|---------------------|-----------------------------------------------------------------------------------|
| `ingest`            | Valida que llegan candidato, video y documentos                                   |
| `transcribe`        | Convierte la grabación a texto (mock · Whisper / AssemblyAI / Hireflix webhook)   |
| `extract_documents` | Extrae texto de cada PDF/imagen (mock · Azure Form Recognizer / Textract / pypdf) |
| `analyze_answers`   | LLM puntúa 6 competencias leyendo el transcript                                   |
| `verify_documents`  | LLM compara cada documento con el perfil + transcript                             |
| `score_candidate`   | Agrega competencias, penaliza por red flags, decide la rama                       |
| **`deep_dive`** ⭑   | **Solo si el score cae en [5.5, 6.5]**: genera follow-up questions                |
| `generate_report`   | Produce el `OnboardingReport` final con recomendación                             |

## ¿Por qué LangGraph y no un script lineal?

Tres razones concretas en este repo:

1. **Ramificación condicional.** [`src/agent/graph.py`](src/agent/graph.py)
   define una *conditional edge* desde `score_candidate`: candidatos
   *borderline* (score entre 5.5 y 6.5) se ruta por un nodo
   `deep_dive` que llama al LLM para producir 2-3 preguntas de
   seguimiento; el resto va directo a `generate_report`. Un script
   `for nodo in pasos` no expresa esto.
2. **Human-in-the-loop opcional.**
   `build_graph(human_in_the_loop=True)` compila el grafo con un
   `MemorySaver` y `interrupt_before=["generate_report"]`. La persona
   reclutadora puede revisar competencias y red flags antes de que el
   agente decida la recomendación. Resume con el mismo `thread_id`.
3. **Estado tipado y observable.** Cada nodo muta un
   [`OnboardingState`](src/agent/states.py) (TypedDict) — fácil de
   serializar para LangSmith, fácil de testear nodo a nodo.

## Live demo

[ai-onboarding-agent-phi.vercel.app](https://ai-onboarding-agent-phi.vercel.app)
ejecuta el grafo en una función serverless ([api/analyze.py](api/analyze.py))
con **Gemini real** vía `google-genai` y `response_schema` (structured
outputs → pydantic, sin parseo de JSON manual).

El demo:

- Selecciona uno de los 3 candidatos preset (Ana / Marco / Laura) o pulsa **Custom** para pegar tu propio transcript
- Pulsa *Analizar* → el frontend hace `POST /api/analyze` con el `candidate_id` o el transcript inline
- La función carga el transcript y los documentos del candidato, construye el grafo LangGraph, lo ejecuta y devuelve el `OnboardingReport`
- El demo anima el pipeline en directo, marca **rama `deep_dive` activada/omitida** según la respuesta y renderiza el reporte con latencia real

Un badge en el header indica el modo:

| Badge        | Significado                                                  |
|--------------|--------------------------------------------------------------|
| `live · gemini` | API serverless responde + `GEMINI_API_KEY` configurada    |
| `live · mock`   | API responde pero sin clave → backend determinista        |
| `offline`       | API no alcanzable → fallback a datos precocinados         |

## Cómo lo pruebo en local

```bash
git clone https://github.com/mflorgar/ai-onboarding-agent.git
cd ai-onboarding-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Modo mock (zero-config, sin API key)
python -m src.main ana_garcia --pretty
python -m src.main marco_silva --pretty   # → dispara deep_dive
python -m src.main laura_mendez --pretty
```

Salida: JSON tipado con competencias, findings por documento, red flags,
score, recomendación y — si pasó por `deep_dive` — `follow_up_questions`.

### Modo Gemini real

```bash
export GEMINI_API_KEY=...
LLM_PROVIDER=gemini python -m src.main marco_silva --pretty
```

El backend Gemini ([`src/services/llm.py`](src/services/llm.py)) usa
`response_schema` para que `analyze_transcript`, `verify_documents` y
`propose_followups` devuelvan **objetos pydantic ya tipados**, no
strings JSON que haya que parsear.

## Candidatos de prueba

Los 3 candidatos preset cubren los tres caminos del grafo:

| ID             | Rol                   | Score  | Recomendación        | Pasa por `deep_dive` |
|----------------|-----------------------|--------|----------------------|----------------------|
| `ana_garcia`   | Senior Data Engineer  | ~8.5   | `strong_hire`        | ❌                   |
| `marco_silva`  | Marketing Manager     | ~5.8   | `hire_with_caveats`  | ✅                   |
| `laura_mendez` | Product Designer      | ~0.5   | `no_hire`            | ❌                   |

Las fixtures (transcripts y documentos en texto) están en
[`data/candidates/<id>/`](data/candidates/).

## Tests

```bash
pytest
```

11 tests cubren: pipeline end-to-end para los 3 candidatos, rangos de
score, presencia de competencias, detección de red flags, y la
**rama condicional** (`deep_dive` se dispara *sólo* en borderline).

## Estructura

```
ai-onboarding-agent/
├── api/
│   └── analyze.py             # Vercel serverless: runs the graph end-to-end
├── src/
│   ├── agent/
│   │   ├── graph.py           # cableado LangGraph + conditional edge + HIL flag
│   │   ├── nodes.py           # 8 node functions incl. deep_dive
│   │   └── states.py          # TypedDict del estado
│   ├── services/
│   │   ├── transcriber.py     # mock + interfaz para Whisper/Hireflix
│   │   ├── document_extractor.py
│   │   └── llm.py             # mock + Gemini backend con response_schema
│   ├── models.py              # pydantic: CandidateProfile, OnboardingReport, etc.
│   └── main.py                # CLI
├── data/candidates/           # 3 candidatos ficticios
├── demo/
│   └── index.html             # demo SPA (ES|EN, deep_dive viz, bias panel)
├── tests/
├── vercel.json                # rewrite + función serverless
└── requirements.txt
```

## Despliegue en Vercel

1. **Root Directory: `.`** (la raíz del repo, no `demo/`)
2. **Framework Preset:** `Other`. Build/output vacíos.
3. Variable de entorno: `GEMINI_API_KEY` (opcional; sin ella el backend
   cae al mock determinista y el badge muestra `live · mock`).

`vercel.json` ya hace el rewrite de `/` → `/demo/index.html` y monta
`api/analyze.py` con `includeFiles` para que la función pueda leer
`src/` y `data/candidates/`.

## Límites y sesgos

Esto es **decision support**, no un decisor. Antes de cualquier uso real:

- **Disparate impact.** El LLM puede premiar patrones de discurso correlacionados con género, lengua materna o nivel educativo. Audita resultados por grupo demográfico antes de validar el sistema.
- **Anclaje.** Mostrar la recomendación antes de que la persona reclutadora forme su propia opinión sesga al panel. Activa `human_in_the_loop=True` y haz que la revisión humana ocurra antes del nodo `generate_report`.
- **Errores de transcripción.** Los modelos ASR introducen ruido sistemático en acentos no estándar; el score hereda esos errores.
- **Forgery.** El agente no verifica firmas criptográficas en certificados. La consistencia es semántica, no de autenticidad.
- **Supervisión humana.** Bajo regímenes como la EU AI Act, los sistemas de hiring son alto riesgo y exigen explicabilidad y supervisión humana documentada.

Toda recomendación tiene que ser validada por una persona antes de
afectar a un candidato.

## Roadmap

- [ ] Reemplazar el mock de transcripción con Whisper API o webhook de Hireflix
- [ ] Extractor real para PDF (`pypdf`) y DOCX (`python-docx`)
- [ ] Persistencia de runs (SQLite + checkpointer LangGraph) para auditoría
- [ ] Panel de auditoría de bias por grupo demográfico
- [ ] Multi-turn deep_dive: el follow-up genera otra ronda de scoring

## Licencia

MIT.

---

Hecha por [María Flores](https://linkedin.com/in/mariafloresgarcia) · 2026
