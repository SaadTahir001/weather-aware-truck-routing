export type RiskLevel = "Low" | "Moderate" | "High" | "Severe" | "No Travel";

export interface Coordinate {
  longitude: number;
  latitude: number;
}

export interface WeatherReading {
  forecast_time: string;
  wind_mph: number;
  rain_in_per_hour: number;
  snow_in_per_hour: number;
  temperature_f: number | null;
  description: string;
}

export interface RiskBreakdown {
  wind: RiskLevel;
  rain: RiskLevel;
  snow: RiskLevel;
  overall: RiskLevel;
}

export interface ForecastTimelineEntry {
  hour_offset: number;
  weather: WeatherReading;
  risk: RiskBreakdown;
}

export interface Checkpoint {
  sequence: number;
  coordinate: Coordinate;
  eta: string;
  segment_distance_miles: number;
  weather: WeatherReading;
  risk: RiskBreakdown;
  forecast_timeline: ForecastTimelineEntry[];
}

export interface RouteRanking {
  severe_miles: number;
  high_miles: number;
  average_risk: number;
  travel_seconds: number;
}

export type DecisionStatus = "recommended" | "not_recommended" | "rejected";

export interface RouteDecision {
  status: DecisionStatus;
  reason: string;
}

export interface RouteResult {
  id: string;
  name: string;
  geometry: {
    type: "LineString";
    coordinates: [number, number][];
  };
  distance_miles: number;
  duration_seconds: number;
  arrival_time: string;
  eligible: boolean;
  ranking: RouteRanking;
  decision: RouteDecision;
  checkpoints: Checkpoint[];
}

export interface ResolvedLocation {
  query: string;
  display_name: string;
  coordinate: Coordinate;
}

export interface RouteCalculationRequest {
  origin: string;
  destination: string;
  departure_time: string;
  load_weight_lb: number;
}

export interface RouteCalculationResponse {
  data_source: "live" | "mock";
  mock_reason: string | null;
  request: RouteCalculationRequest;
  resolved_locations: {
    origin: ResolvedLocation;
    destination: ResolvedLocation;
  };
  recommended_route_id: string | null;
  recommendation_summary: string;
  ranking_hierarchy: string[];
  routes: RouteResult[];
}

export interface ApiErrorEnvelope {
  error?: {
    code?: string;
    detail?: string;
  };
  [field: string]: unknown;
}
