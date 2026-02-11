import { apiFetch } from './client';

export interface ContentCatalogEntry {
  setting_id: string;
  setting_display_name: string;
  period_id: string;
  period_display_name: string;
  legacy_era_id: string;
  source: string;
  summary: string;
  playable: boolean;
  playability_reasons: string[];
  locations_count: number;
  backgrounds_count: number;
  companions_count: number;
  quests_count: number;
}

export interface ContentCatalogResponse {
  items: ContentCatalogEntry[];
}

export interface ContentDefaultResponse {
  setting_id: string;
  period_id: string;
  legacy_era_id: string;
}

export async function getContentCatalog(): Promise<ContentCatalogResponse> {
  return apiFetch('/v2/content/catalog');
}

export async function getContentDefault(): Promise<ContentDefaultResponse> {
  return apiFetch('/v2/content/default');
}
