# Downshift web

Next.js UI for Downshift: results page (cost vs quality), harness diff, run view, "Open PR" and "Run optimization".

```bash
cp .env.example .env.local   # API_URL=http://localhost:8000
npm install
npm run dev                  # http://localhost:3000
```

The browser reaches the API through the `/api/*` rewrite, so only `API_URL` needs to be set.
