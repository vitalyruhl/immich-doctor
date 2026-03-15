# immich-doctor UI Frontend

## Local development

Install dependencies:

```bash
npm install
```

Start the Vite dev server:

```bash
npm run dev
```

Build the app:

```bash
npm run build
```

## Environment

Optional Vite environment values:

```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_USE_MOCK_API=true
```

`VITE_USE_MOCK_API=true` enables a clearly labeled `[MOCKED!]` mode for local UI
foundation work only. It must not be treated as real backend truth.
