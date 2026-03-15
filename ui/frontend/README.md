# immich-doctor UI Frontend

## Local development

### 1. Install dependencies

```bash
uv sync --dev
cd ui/frontend
npm install
```

### 2. Start the backend API for dashboard health

```bash
uv run uvicorn immich_doctor.api.app:create_api_app --factory --reload --host 127.0.0.1 --port 8000
```

The frontend uses `/api` by default and the Vite dev server proxies that path to
`http://127.0.0.1:8000`.

### 3. Start the frontend

```bash
npm run dev
```

### 4. Build the app

```bash
npm run build
```

## Environment

Optional Vite environment values:

```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_BACKEND_PROXY_TARGET=http://127.0.0.1:8000
VITE_USE_MOCK_API=true
```

Recommended local setup:

- keep `VITE_API_BASE_URL` unset
- run the backend on `127.0.0.1:8000`
- let Vite proxy `/api` requests to the backend

`VITE_USE_MOCK_API=true` enables a clearly labeled `[MOCKED!]` mode for local UI
foundation work only. It must not be treated as real backend truth.

Without mock mode, the dashboard now requests the real backend endpoint:

```text
GET /api/health/overview
```
