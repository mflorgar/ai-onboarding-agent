# Demo — AI Onboarding Agent

Demo interactiva del pipeline de revisión de candidatos.

El visitante elige uno de los 3 candidatos ficticios, pulsa *Analizar*
y ve cómo el agente:

1. Recibe video + documentos
2. Transcribe el video
3. Extrae texto de los documentos
4. Evalúa 6 competencias vía LLM
5. Verifica los documentos contra el transcript
6. Calcula el score global
7. Genera el reporte final con recomendación

Incluye barras de competencias, verificación por documento, red flags
con severidad y un fragmento del transcript. Toggle ES|EN.

## Deploy en Vercel

Esta carpeta se despliega **sola**, sin tocar el Python del repo padre.

En [vercel.com/new](https://vercel.com/new):

1. **Framework Preset**: `Other`
2. **Root Directory**: `demo` ← clave
3. Build Command: vacío
4. Output Directory: vacío
5. Deploy

## Probar en local

```bash
cd ai-onboarding-agent/demo
python3 -m http.server 8000
# abrir http://localhost:8000
```
