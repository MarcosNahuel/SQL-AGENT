# SQL Agent Frontend

Modern React dashboard for SQL Agent - An intelligent analytics assistant with real-time AI-powered insights.

## Features

- Dark theme UI with Tailwind CSS
- Real-time SSE streaming with AI SDK v5
- Interactive KPI cards and charts (Recharts)
- Agent timeline visualization
- Suggested questions

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **Charts**: Recharts
- **Icons**: Lucide React
- **Validation**: Zod v4

## Installation

1. Install dependencies:
```bash
npm install
```

2. Configure environment:
```bash
cp .env.example .env.local
# Edit .env.local if needed
```

3. Run development server:
```bash
npm run dev
```

App runs at http://localhost:3000

## Project Structure

```
app/
  page.tsx           # Main chat + dashboard page
  layout.tsx         # Root layout
  globals.css        # Global styles
components/
  DashboardRenderer.tsx  # Dashboard container
  ChartRenderer.tsx      # Chart components
  KPICard.tsx            # KPI display cards
  AgentTimeline.tsx      # Processing timeline
lib/
  streamParts.ts     # SSE validation schemas
  types.ts           # TypeScript types
  utils.ts           # Utility functions
```

## Backend Connection

This frontend connects to the SQL Agent Backend at `http://localhost:8000`. Make sure the backend is running before starting the frontend.

## License

MIT
