# AI Onboarding Agent

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Agente conversacional que evalúa candidatos a partir de una entrevista
asíncrona grabada (tipo **Hireflix**) y de los documentos adjuntos (CV,
certificados, referencias). Construido con **LangGraph**.

El pipeline transcribe el video, extrae el texto de los documentos,
puntúa competencias, detecta inconsistencias CV-entrevista y produce un
reporte estructurado con recomendación de contratación.

El repo es framework-first: los servicios externos (transcripción, OCR,
LLM) vienen **mockeados por defecto**, para que puedas clonarlo y
correrlo end-to-end sin ninguna API key.

## 👀 Live demo

**Live demo**: https://ai-onboarding-agent-phi.vercel.app

La demo en [`demo/`](demo/) es un HTML estático que simula el flujo
completo: eliges un candidato (3 ficticios con perfiles muy distintos),
pulsas *Analizar* y ves el pipeline ejecutarse paso a paso hasta
generar el reporte con recomendación. Toggle ES|EN incluido.

## Arquitectura

El pipeline es un grafo LangGraph lineal con 7 nodos:

```
ingest → transcribe → extract_documents → analyze_answers
       → verify_documents → score_candidate → generate_report → END
```

| Nodo                | Qué hace                                                                          |
|---------------------|-----------------------------------------------------------------------------------|
| `ingest`            | Valida que llegan candidato, video y documentos                                   |
| `transcribe`        | Convierte la grabación a texto (mock · Whisper / AssemblyAI / Hireflix webhook)   |
| `extract_documents` | Extrae texto de cada PDF/imagen (mock · Azure Form Recognizer / Textract / pypdf) |
| `analyze_answers`   | LLM puntúa 6 competencias leyendo el transcript                                   |
| `verify_documents`  | LLM compara cada documento con el perfil + transcript                             |
| `score_candidate`   | Agrega competencias y penaliza por red flags                                      |
| `generate_report`   | Produce el `OnboardingReport` final con recomendación                             |

Las recomendaciones posibles son `strong_hire`, `hire`,
`hire_with_caveats` y `no_hire`.

## Cómo lo pruebo en local

```bash
git clone https://github.com/mflorgar/ai-onboarding-agent.git
cd ai-onboarding-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Ejecuta el pipeline sobre un candidato ficticio
python -m src.main ana_garcia --pretty
python -m src.main marco_silva --pretty
python -m src.main laura_mendez --pretty
```

La salida es un JSON con el reporte completo: competencias, findings
por documento, red flags, score global y recomendación.

## Candidatos de prueba

Tres perfiles que cubren los tres escenarios principales:

| ID             | Rol                   | Score | Recomendación        |
|----------------|-----------------------|-------|----------------------|
| `ana_garcia`   | Senior Data Engineer  | 8.5   | strong_hire          |
| `marco_silva`  | Marketing Manager     | 5.8   | hire_with_caveats    |
| `laura_mendez` | Product Designer      | 0.5   | no_hire              |

Los transcripts y CVs de cada uno están en `data/candidates/<id>/`.

## Tests

```bash
pytest
```

Cubre el pipeline end-to-end para los tres candidatos, verifica rangos
de score, presencia de competencias y detección de red flags.

## Estructura

```
ai-onboarding-agent/
├── src/
│   ├── agent/
│   │   ├── graph.py        # cableado LangGraph
│   │   ├── nodes.py        # 7 node functions
│   │   └── states.py       # TypedDict del estado
│   ├── services/
│   │   ├── transcriber.py  # mock + interfaz para Whisper/Hireflix
│   │   ├── document_extractor.py
│   │   └── llm.py          # mock determinista que puntúa y verifica
│   ├── models.py           # pydantic: CandidateProfile, OnboardingReport, etc.
│   └── main.py             # CLI
├── data/candidates/        # 3 candidatos ficticios
├── tests/
├── demo/                   # demo web estática para Vercel
│   ├── index.html
│   └── vercel.json
├── requirements.txt
└── README.md
```

## Deploy de la demo web

Importar este repo en Vercel con **Root Directory = `demo`**. Detalles
en [`demo/README.md`](demo/README.md).

## Roadmap

- [ ] Backend Gemini real (`src/services/llm.py`) con tool calling
- [ ] Integración con Hireflix webhook
- [ ] Extractor real para PDF (`pypdf`) y DOCX (`python-docx`)
- [ ] Rama condicional en el grafo: re-interview si score borderline
- [ ] Human-in-the-loop: pausar el grafo antes del reporte para revisión

## Licencia

MIT.

---

Hecha por [María Flores](https://linkedin.com/in/mariafloresgarcia) · 2026
