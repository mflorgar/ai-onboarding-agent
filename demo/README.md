# Demo — AI Onboarding Agent

Frontend interactivo del pipeline. Llama a `/api/analyze` (función
Python serverless en Vercel) que **ejecuta el grafo LangGraph real**
con backend Gemini si hay `GEMINI_API_KEY`, o mock determinista si no.

## Qué muestra

- **3 candidatos preset** (Ana / Marco / Laura) que cubren los tres
  caminos del grafo.
- **Custom candidate**: pega tu propio transcript y mira cómo el LLM lo
  puntúa en directo. El default seedeado cae en la zona *borderline*
  (5.5–6.5) → activa la rama condicional `deep_dive`.
- **Pipeline animado** con los 8 nodos del grafo. Si el score no es
  borderline, `deep_dive` aparece en gris (saltado), no animado.
- **Reporte completo**: recomendación, score, competencias con barras,
  verificación documental, red flags por severidad, follow-ups (cuando
  pasa por `deep_dive`) y meta-strip con `backend`, `latency_ms` y si la
  rama condicional se activó.
- **Panel de límites y sesgos** debajo del reporte.
- **Badge live/mock/offline** en el header — refleja el estado real del
  backend.
- Toggle ES|EN para toda la UI estática.

## Despliegue en Vercel

> Diferencia con la versión anterior: el **Root Directory ahora es la
> raíz del repo** (no `demo/`), porque la función serverless vive en
> `api/analyze.py` y necesita importar `src/`.

1. En Vercel → Project Settings → **Root Directory: `.`**
2. **Framework Preset:** `Other`. Build/output vacíos.
3. **Environment variables:** `GEMINI_API_KEY` (opcional). Sin ella, el
   backend cae al mock determinista y el badge muestra `live · mock`
   en vez de `live · gemini`.
4. Deploy.

`vercel.json` (en raíz) hace el rewrite `/` → `/demo/index.html` y
empaqueta `src/` + `data/candidates/` con la función.

## Probar en local

El frontend solo (sin backend) cae al modo offline con datos
precocinados — útil para iterar CSS:

```bash
cd ai-onboarding-agent/demo
python3 -m http.server 8000
# abrir http://localhost:8000
```

Para probar el flujo completo (frontend + función serverless) en local
sin desplegar, instala el CLI de Vercel:

```bash
npm i -g vercel
cd ai-onboarding-agent
vercel dev
# abrir el URL que imprime; /api/analyze ya estará vivo
```
