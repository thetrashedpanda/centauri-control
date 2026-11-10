export interface OpenFilamentSensorData {
  schema_version: number;
  device: {
    firmware_version: string;
    chip_family: string;
    mac: string;
    ip: string;
    uptime_seconds: number;
  };
  filament: {
    runout: boolean;
    stopped: boolean;
    movement_pulses: number;
    hard_jam_percent: number;
    soft_jam_percent: number;
    telemetry_available: boolean;
    grace_active: boolean;
    current_deficit_mm: number;
    expected_filament_mm: number;
    actual_filament_mm: number;
    expected_rate_mm_per_sec: number;
    actual_rate_mm_per_sec: number;
  };
  printer: {
    connected: boolean;
    is_printing: boolean;
    print_status: number;
    progress_percent: number;
    current_layer: number;
    total_layer: number;
  };
}

export interface IntegrationStatus {
  integration_id: "openfilamentsensor";
  printer_id: string;
  enabled: boolean;
  connected: boolean;
  base_url: string;
  last_seen: string | null;
  error: string | null;
  data: OpenFilamentSensorData | null;
}

export interface IntegrationPrinterConfig {
  enabled: boolean;
  base_url: string;
  status: IntegrationStatus | null;
}

export interface IntegrationCatalogEntry {
  id: "openfilamentsensor";
  name: string;
  version: string;
  description: string;
  category: string;
  supports_printer_binding: boolean;
  enabled_printers: number;
  printers: Record<string, IntegrationPrinterConfig>;
}

export interface IntegrationCatalogResponse {
  integrations: IntegrationCatalogEntry[];
}
