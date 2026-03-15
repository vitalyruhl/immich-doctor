export interface SettingsSectionField {
  key: string;
  label: string;
  value: string;
  secret?: boolean;
}

export interface SettingsSection {
  id: string;
  title: string;
  description: string;
  fields: SettingsSectionField[];
}

export interface SettingsResponse {
  sections: SettingsSection[];
  mocked: boolean;
}
