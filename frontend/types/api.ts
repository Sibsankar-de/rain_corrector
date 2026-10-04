/**
 * Domain types mirroring the backend Pydantic schemas.
 *
 * Kept hand-written rather than generated so the frontend contract is explicit
 * and reviewable. Field names match the API exactly; see docs/api/README.md.
 */

export type Severity = "none" | "light" | "moderate" | "heavy" | "very_heavy" | "extreme";

export type ForecastStatus = "pending" | "issued" | "verified" | "partially_verified" | "expired";

export type ModelStatus = "candidate" | "validated" | "active" | "archived" | "rejected";

export type VerificationStatus = "pending_observation" | "verified" | "missing_observation";

export type AlertSeverity = "info" | "warning" | "severe" | "critical";

export type AlertStatus = "open" | "acknowledged" | "resolved";

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}

export interface Region {
  id: number;
  code: string;
  name: string;
  level: string;
}

export interface DistrictSummary {
  id: number;
  code: string;
  name: string;
  region_id: number;
  centroid_lat: number;
  centroid_lon: number;
  population: number | null;
}

export interface DistrictDetail extends DistrictSummary {
  bbox_min_lat: number | null;
  bbox_min_lon: number | null;
  bbox_max_lat: number | null;
  bbox_max_lon: number | null;
  area_sq_km: number | null;
  geometry_geojson: string | null;
  region: Region | null;
  station_count: number | null;
}

export interface Station {
  id: number;
  code: string;
  name: string;
  district_id: number;
  latitude: number;
  longitude: number;
  elevation_m: number | null;
  is_active: boolean;
}

export interface Forecast {
  id: number;
  run_id: number;
  district_id: number;
  target_time: string;
  lead_time_hours: number;
  predicted_rainfall_mm: number;
  predicted_probability: number | null;
  lower_bound_mm: number | null;
  upper_bound_mm: number | null;
  severity: Severity;
  status: ForecastStatus;
  issued_at: string;
  model_version: string;
  district: DistrictSummary | null;
}

export interface ForecastValue {
  id: number;
  step_index: number;
  step_start: string;
  step_end: string;
  lead_hours: number;
  predicted_rainfall_mm: number;
  lower_bound_mm: number | null;
  upper_bound_mm: number | null;
}

export interface ForecastDetail extends Forecast {
  feature_inputs: Record<string, unknown>;
  values: ForecastValue[];
}

export interface ForecastRun {
  id: number;
  run_uid: string;
  model_version: string;
  issued_at: string;
  horizon_hours: number;
  step_hours: number;
  valid_from: string;
  valid_to: string;
  generator: string;
  forecast_count: number | null;
}

export interface LegendEntry {
  label: string;
  severity: Severity;
  color: string;
  min_mm: number;
  max_mm: number | null;
}

export interface VerificationResult {
  id: number;
  forecast_id: number;
  status: VerificationStatus;
  observed_rainfall_mm: number | null;
  forecast_rainfall_mm: number;
  error_mm: number | null;
  absolute_error_mm: number | null;
  bias_mm: number | null;
  rmse_mm: number | null;
  nash_sutcliffe: number | null;
  brier_score: number | null;
  hit: boolean | null;
  false_alarm: boolean | null;
  missed: boolean | null;
  correct_negatives: boolean | null;
  observed_at: string | null;
  verified_at: string | null;
}

export interface MetricGroup {
  sample_size: number;
  mean_error_mm: number;
  mean_absolute_error_mm: number;
  rmse_mm: number;
  bias_mm: number;
}

export interface VerificationMetrics {
  sample_size: number;
  mean_error_mm: number;
  mean_absolute_error_mm: number;
  rmse_mm: number;
  bias_mm: number;
  nash_sutcliffe: number | null;
  brier_score: number | null;
  hit_rate: number | null;
  false_alarm_ratio: number | null;
  detection_score: number | null;
  critical_success_index: number | null;
  by_lead_bucket: Record<string, MetricGroup>;
  by_severity: Record<string, MetricGroup>;
  computed_at: string;
}

export interface ModelVersion {
  id: number;
  model_name: string;
  version: string;
  status: ModelStatus;
  framework_version: string;
  features: string[];
  metrics: Record<string, unknown>;
  hyperparameters: Record<string, unknown>;
  training_data_start: string | null;
  training_data_end: string | null;
  trained_at: string;
  activated_at: string | null;
  notes: string | null;
}

export interface TrainingRun {
  id: number;
  run_id: string;
  status: string;
  best_model_name: string | null;
  best_metrics: Record<string, unknown>;
  baseline_metrics: Record<string, unknown>;
  candidate_results: Record<string, unknown>;
  dataset_rows: number | null;
  created_model_version: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
}

export interface ModelVersionDetail extends ModelVersion {
  artifact_path: string;
  training_run_id: number | null;
  archived_at: string | null;
}

export interface Alert {
  id: number;
  district_id: number;
  district_name: string | null;
  forecast_id: number | null;
  severity: AlertSeverity;
  status: AlertStatus;
  alert_type: string;
  title: string;
  message: string;
  threshold_mm: number;
  observed_value_mm: number | null;
  valid_from: string;
  valid_to: string;
  created_at: string;
}

export interface StatusSnapshot {
  forecasts_issued: number;
  forecasts_verified: number;
  forecasts_pending: number;
  latest_observation: string | null;
  evaluated_at: string;
}

export interface PlatformSummary {
  forecasts_last_7d: number;
  districts_at_risk: number;
  open_alerts: number;
  observed_rainfall_mm_7d: number;
}

export interface SeverityDistribution {
  severity: Severity;
  count: number;
  mean_rainfall_mm: number;
}

export interface DistrictRiskItem {
  district_id: number;
  code: string;
  name: string;
  latitude: number;
  longitude: number;
  predicted_rainfall_mm: number;
  upper_bound_mm: number | null;
  severity: Severity;
  target_time: string;
}

export interface ObservedRainfallItem {
  observed_at: string;
  mean_rainfall_mm: number;
  total_rainfall_mm: number;
}

export interface TimeseriesPoint {
  timestamp: string;
  value: number;
  lower: number | null;
  upper: number | null;
}

export interface ActiveAlertItem {
  id: number;
  district_id: number;
  district_name: string | null;
  severity: AlertSeverity;
  title: string;
  message: string;
  valid_from: string;
  valid_to: string;
}

export interface ModelHealthItem {
  model_name: string;
  version: string;
  status: ModelStatus;
  trained_at: string;
  mae_mm: number | null;
  rmse_mm: number | null;
  sample_size: number;
  is_loaded: boolean;
}

export interface DashboardOverview {
  generated_at: string;
  active_model_version: string | null;
  model_loaded_version: string | null;
  latest_forecast_run: string | null;
  latest_forecast_issued_at: string | null;
  status: StatusSnapshot;
  summary: PlatformSummary;
  verification: VerificationMetrics;
  severity_distribution: SeverityDistribution[];
  top_risk_districts: DistrictRiskItem[];
  observed_rainfall_series: ObservedRainfallItem[];
  forecast_vs_observed_series: TimeseriesPoint[];
  alerts: ActiveAlertItem[];
  legend: LegendEntry[];
  models: ModelHealthItem[];
  meta: Record<string, unknown>;
}
