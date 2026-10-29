# Weather-aware Django routing core

This folder is a drop-in Django app containing:

- `models.py`: `Route` and ordered `Checkpoint` models.
- `services.py`: pure-Python weather/load risk evaluation and route ranking.
- `external_services.py`: Mapbox geocoding/directions and OpenWeather clients.
- `route_planning.py`: checkpoint sampling, forecast enrichment, and response assembly.
- `serializers.py`, `views.py`, and `urls.py`: the DRF API contract.
- `tests/`: threshold, provider parsing, sampling, and orchestration tests.

## Integration

Copy the `routing` folder into the Django project and install the runtime
dependencies:

```shell
python -m pip install Django djangorestframework
```

Add `"rest_framework"` and `"routing"` to `INSTALLED_APPS`, include the app URLs
at the project root, then create the model migrations:

```python
# project/urls.py
from django.urls import include, path

urlpatterns = [
    path("", include("routing.urls")),
]
```

```shell
python manage.py makemigrations routing
python manage.py migrate
```

This exposes `POST /api/routes/calculate/`.

## Provider configuration

Set these secrets in the server environment; never send them from React:

```text
MAPBOX_ACCESS_TOKEN=...
OPENWEATHER_API_KEY=...
ROUTING_MOCK_MODE=auto
```

`MAPBOX_API_KEY` is accepted as an alias for `MAPBOX_ACCESS_TOKEN`.

### Local mock fallback

`ROUTING_MOCK_MODE` controls provider-free development:

- `auto` (default): use live providers when both keys exist, use deterministic
  mock data when a key is missing, and fall back when a provider explicitly
  rejects a credential with an authentication response.
- `always`: never call Mapbox or OpenWeather; always return mock data.
- `never`: require valid live credentials. Use this setting in production.

Mock mode returns three distinct geometries, ETA-spaced checkpoints, realistic
weather measurements, one recommended route, alternatives with elevated risk,
and a No Travel rejection. Responses include `data_source: "mock"`, a
`mock_reason`, and the `X-Routing-Data-Source: mock` header. Live responses use
`data_source: "live"`. Provider timeouts and non-authentication failures do not
silently fall back in `auto` mode.

See `.env.example` for optional settings. The default checkpoint interval is 50
miles; set `ROUTE_CHECKPOINT_INTERVAL_MILES=25` for denser sampling. The code
reads the process environment directly, so loading a local `.env` file is the
responsibility of the deployment platform or a package such as `django-environ`.

OpenWeather One Call hourly forecasts have a finite time horizon. The endpoint
returns HTTP 422 when a checkpoint ETA is not close to an available hourly
forecast instead of silently applying weather from the wrong time.

## API request

```http
POST /api/routes/calculate/
Content-Type: application/json

{
  "origin": "Chicago, IL",
  "destination": "Detroit, MI",
  "departure_time": "2026-11-02T08:00:00-06:00",
  "load_weight_lb": 36000
}
```

The success response contains exactly three route candidates, GeoJSON
`LineString` coordinates, total distance/duration, arrival time, all sampled
checkpoints, their ETA/weather/risk breakdowns, the ranking metrics, and a
`decision` object explaining why each route was recommended, ranked behind the
winner, or rejected. `recommended_route_id` is `null` when all three candidates
contain No Travel conditions.

Provider failures use a stable error envelope:

```json
{
  "error": {
    "code": "provider_error",
    "detail": "A routing or weather provider failed. Please retry later."
  }
}
```

Mapbox may legitimately find fewer than two alternatives for some origin and
destination pairs. Because this endpoint's contract requires three routes, that
case returns HTTP 502 with `error.code = "insufficient_routes"`.

## API flow

1. Forward-geocode origin and destination through Mapbox Geocoding v6.
2. Request the primary route plus up to two alternatives with full GeoJSON and
   distance/duration annotations.
3. Sample each route at the configured mileage interval and interpolate each ETA
   from the segment durations.
4. Fetch the closest OpenWeather hourly forecast for every checkpoint. Wind is
   requested in mph; rain and snow are converted from mm/hour to inches/hour.
5. Call `recommend_best_route`, exclude No Travel routes, and return the ordered
   comparison and explanation.

The wrapper deliberately does not save temporary provider data. If route history
is required, add persistence after confirming that the provider account and data
license permit the intended storage.

## Existing model-based usage

Store each route's weather forecast on its checkpoints for the checkpoint ETA.
`segment_distance_miles` is the length of road after that checkpoint for which
the forecast applies; set it to `0` on the destination checkpoint.

```python
from routing.models import Route
from routing.services import recommend_best_route_models

routes = Route.objects.prefetch_related("checkpoints").filter(
    id__in=candidate_route_ids,
)
result = recommend_best_route_models(routes, load_weight_lb=36_000)

if result.recommended is None:
    # Tell the React client that all candidates contain a No Travel condition.
    ...
else:
    best_route = result.recommended
    print(best_route.route_id, best_route.ranking_key)
```

The four-part `ranking_key` is, in order: Severe miles, High miles,
distance-weighted average risk, and ETA-derived travel seconds. Any route with a
No Travel checkpoint is reported in `evaluations` but excluded from selection.

## Boundary and policy decisions

- Shared boundary values enter the higher category: `0.25` in/hr rain is High,
  `1.0` in/hr snow is High, and so on.
- Rain at exactly `1.00` in/hr and snow at exactly `3.0` in/hr remain Severe,
  because the supplied No Travel rules use `>` for those values.
- The rule “45–54 mph + 30,000 lb” is implemented as `>= 30,000 lb`. If the
  requirement truly means exactly 30,000 lb, change that comparison in
  `calculate_checkpoint_risk`.
- A No Travel result from wind, rain, or snow makes the entire route ineligible.
