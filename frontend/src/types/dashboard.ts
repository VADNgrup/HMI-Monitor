export interface KvmSource {
  id: string;
  name: string;
  host: string;
  port: number;
  enabled: boolean;
  poll_seconds: number;
  last_polled_at?: string;
}

export interface Screen {
  id: string;
  name: string;
  ignored?: boolean;
}

export interface Indicator {
  indicator_label?: string;
  display_name?: string;
  metric?: string;
  metric_key?: string;
  value_type?: string;
  last_value?: string | number;
  unit?: string;
}

export interface Entity {
  id: string;
  display_name: string;
  entity_type?: string;
  region?: string;
  indicators?: Record<string, Indicator>;
  metrics?: Record<string, Indicator>;
}

export interface LogEntry {
  log_id: string;
  recorded_at: string;
  entity_name?: string;
  entity_key?: string;
  metric?: string;
  value?: string | number;
  value_type?: string;
  unit?: string;
}

export interface QueueStats {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

export interface Preview {
  snapshot_id: string;
  created_at: string;
  image_url: string;
}
