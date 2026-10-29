# HaulCast React frontend

Vite + React + TypeScript frontend for the Django endpoint:

```text
POST /api/routes/calculate/
```

## Stack

- React 19 and TypeScript
- Vite
- Tailwind CSS v4 through the first-party Vite plugin
- Axios
- Leaflet and React Leaflet

## Run locally

```shell
npm install
npm run dev
```

By default, Vite proxies `/api` to `http://localhost:8000`. Copy `.env.example`
to `.env.local` to change the development backend or use a separate API origin:

```text
VITE_DEV_PROXY_TARGET=http://localhost:8000
VITE_API_BASE_URL=
VITE_API_TIMEOUT_MS=120000
```

When the frontend and Django are deployed on different origins, set
`VITE_API_BASE_URL` at build time and configure Django CORS for the exact frontend
origin. Do not use a wildcard CORS origin for an authenticated deployment.

## Build

```shell
npm run typecheck
npm run build
npm run preview
```

The production output is written to `dist/`.

## Component structure

```text
src/
├── api/
│   └── routes.ts               Axios client and normalized error messages
├── components/
│   ├── ForecastSlider.tsx      0–48 hour time control and animation
│   ├── RouteForm.tsx           Origin, destination, departure, and load input
│   ├── SummaryPanel.tsx        Ranking, recommendation, and rejection reasons
│   ├── WeatherMap.tsx          Routes, checkpoints, popups, and risk halos
│   └── icons.tsx               Small local SVG icon set
├── types/
│   └── routing.ts              Exact DRF request/response contract
├── utils/
│   └── format.ts               Formatting and risk/route color tokens
├── App.tsx                     Request and selection state orchestration
├── main.tsx                    React entry point and Leaflet CSS
└── styles.css                  Tailwind theme plus Leaflet/range styling
```

## Forecast-slider data semantics

The existing Django response includes one weather forecast per checkpoint,
selected for that checkpoint's route ETA. It does not contain a separate forecast
for every checkpoint at every hour from 0 through 48. The slider therefore moves
through the trip window and emphasizes ETA-aligned checkpoint forecasts nearest
the selected hour. It does not synthesize weather values the API did not return.

For a true fixed-location 49-frame animation, extend each checkpoint with an
optional `hourly_forecasts` array from the backend; the map can then select the
reading matching the slider hour without exposing weather-provider keys in the
browser.
