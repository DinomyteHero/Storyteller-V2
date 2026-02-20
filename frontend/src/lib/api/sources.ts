/**
 * Lore Source API client — manage reference material collections (V11.0).
 */
import { apiFetch } from './client';

export interface LoreSourceEntry {
  id: string;
  name: string;
  setting_id: string;
  period_id: string;
  file_count: number;
  chunk_count: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface LoreSourceListResponse {
  items: LoreSourceEntry[];
}

export async function listSources(): Promise<LoreSourceListResponse> {
  return apiFetch('/v2/library/sources');
}

export async function createSource(
  name: string,
  settingId: string = '',
  periodId: string = '',
): Promise<LoreSourceEntry> {
  return apiFetch('/v2/library/sources', {
    method: 'POST',
    body: JSON.stringify({ name, setting_id: settingId, period_id: periodId }),
  });
}

export async function deleteSource(
  sourceId: string,
): Promise<{ deleted: boolean; source_id: string; chunks_removed: number }> {
  return apiFetch(`/v2/library/sources/${encodeURIComponent(sourceId)}`, {
    method: 'DELETE',
  });
}
