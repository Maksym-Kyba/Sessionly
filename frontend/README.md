# Sessionly Frontend

The Sessionly web interface for psychologists and their clients, built with Next.js (App Router),
React, TypeScript and Tailwind CSS.

User-facing text is written in Ukrainian, because the product targets psychologists and clients in
Ukraine. Code, comments and documentation are written in English.

## Prerequisites

- Node.js 20 or newer
- npm

## Run Locally

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

The application is available at http://localhost:3000.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the development server with hot reloading |
| `npm run build` | Build the production bundle |
| `npm run start` | Serve the production build |
| `npm run lint` | Check the code with ESLint |

## Configuration

Next.js reads environment variables from `frontend/.env.local`, which is not committed.

| Variable | Purpose | Local value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the Sessionly backend API | `http://localhost:8000` |

## Project Structure

```
frontend/
├── public/              # Static assets
└── src/
    ├── app/             # Routes, layouts and global styles (Next.js App Router)
    ├── components/ui/   # Shared UI components: Button, Badge, Card, TextField, Logo
    └── utils/           # Small framework-independent helpers
```

## Design System

Design tokens are defined in `src/app/globals.css` with the Tailwind CSS `@theme` directive:

- **Colours:** soft mint (`mint-50` to `mint-300`) and white, with charcoal (`ink`) for text and
  primary actions. Google sign-in and sign-up buttons use `mint-300`.
- **Fonts:** Pangolin for headings (`font-display`) and Nunito for body text (`font-sans`), both
  loaded through `next/font` with Cyrillic support.

The `/styleguide` page shows every token and shared component in one place.
