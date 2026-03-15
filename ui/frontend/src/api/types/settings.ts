export type SettingsCapabilityState = "READY" | "PARTIAL" | "NOT_IMPLEMENTED";

export interface SettingsSectionField {
  key: string;
  label: string;
  valueType: string;
  value: string;
  present: boolean;
  secret?: boolean;
  editable: boolean;
  source: string;
}

export interface SettingsCapability {
  id: string;
  title: string;
  state: SettingsCapabilityState;
  summary: string;
  details: string;
  blocking: boolean;
}

export interface SettingsSection {
  id: string;
  title: string;
  description: string;
  state: SettingsCapabilityState;
  summary: string;
  fields: SettingsSectionField[];
}

export interface SettingsOverviewResponse {
  generatedAt: string;
  schemaVersion: string;
  capabilityState: SettingsCapabilityState;
  summary: string;
  capabilities: SettingsCapability[];
  sections: SettingsSection[];
}

export interface SettingsSchemaField {
  key: string;
  label: string;
  valueType: string;
  secret: boolean;
  editable: boolean;
  source: string;
}

export interface SettingsSchemaSection {
  id: string;
  title: string;
  description: string;
  fields: SettingsSchemaField[];
}

export interface SettingsSchemaResponse {
  schemaVersion: string;
  sections: SettingsSchemaSection[];
}
