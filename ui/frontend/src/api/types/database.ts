import type { HealthState } from "./common";

export interface DatabaseConnectivityOverview {
  status: HealthState;
  summary: string;
  details: string;
  host: string | null;
  port: number | null;
  databaseName: string | null;
  accessWorks: boolean;
  error: string | null;
  engine: string | null;
  serverVersion: string | null;
  serverVersionNum: string | null;
  serverVersionRaw: string | null;
  serverVersionError: string | null;
}

export interface DatabaseImmichOverview {
  status: HealthState;
  summary: string;
  details: string;
  productVersionCurrent: string | null;
  productVersionConfidence: string;
  productVersionSource: string;
  supportStatus: string;
  schemaGenerationKey: string | null;
  riskFlags: string[];
  notes: string[];
}

export interface DatabaseCompatibilityOverview {
  status: HealthState;
  summary: string;
  details: string;
  testedAgainstImmichVersion: string;
}

export interface DatabaseRelatedFindingsOverview {
  status: HealthState;
  summary: string;
  details: string;
  route: string;
}

export interface DatabaseOverviewResponse {
  generatedAt: string;
  connectivity: DatabaseConnectivityOverview;
  immich: DatabaseImmichOverview;
  compatibility: DatabaseCompatibilityOverview;
  relatedFindings: DatabaseRelatedFindingsOverview;
  testedAgainstImmichVersion: string;
}
