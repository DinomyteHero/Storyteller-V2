/**
 * Library API client: book ingestion, world browsing, and EraForge.
 */
import { apiFetch, BASE_URL } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BookEntry {
  id: string;
  filename: string;
  status: string; // pending | running | complete | failed
  setting_id: string;
  period_id: string;
  chunk_count: number;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface BookListResponse {
  items: BookEntry[];
}

export interface IngestJobResponse {
  job_id: string;
  filename: string;
  status: string;
}

export interface IngestStatusResponse {
  job_id: string;
  status: string;
  chunk_count: number;
  error_message: string | null;
}

export interface EraForgePeriodProposal {
  period_id: string;
  display_name: string;
  time_period: string;
  summary: string;
  tone: string;
  key_conflicts: string[];
}

export interface EraForgeSuggestResponse {
  setting_id: string;
  setting_name: string;
  setting_genre: string;
  periods: EraForgePeriodProposal[];
}

export interface EraForgeGenerateResponse {
  setting_id: string;
  period_id: string;
  display_name: string;
  version: number;
  pack_id: number;
  backgrounds_count: number;
  species_count: number;
  canon_characters_count: number;
}

export interface GeneratedPackEntry {
  id: number;
  setting_id: string;
  period_id: string;
  display_name: string;
  summary: string;
  version: number;
  source_prompt: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Library endpoints
// ---------------------------------------------------------------------------

export async function getBooks(): Promise<BookListResponse> {
  return apiFetch('/v2/library/books');
}

export async function uploadBook(
  file: File,
  settingId: string = '',
  periodId: string = '',
): Promise<IngestJobResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('setting_id', settingId);
  formData.append('period_id', periodId);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const response = await fetch(`${BASE_URL}/v2/library/ingest`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
      // No Content-Type header — browser sets multipart boundary automatically
    });

    if (!response.ok) {
      const body = await response.json().catch(() => response.statusText);
      throw new Error(`Upload failed: ${JSON.stringify(body)}`);
    }

    return (await response.json()) as IngestJobResponse;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getJobStatus(jobId: string): Promise<IngestStatusResponse> {
  return apiFetch(`/v2/library/ingest/${encodeURIComponent(jobId)}/status`);
}

// ---------------------------------------------------------------------------
// EraForge endpoints (reuse existing backend)
// ---------------------------------------------------------------------------

export async function suggestPeriods(settingPrompt: string): Promise<EraForgeSuggestResponse> {
  return apiFetch('/v2/eraforge/suggest', {
    method: 'POST',
    body: JSON.stringify({ setting_prompt: settingPrompt }),
  });
}

export async function generatePack(params: {
  setting_id: string;
  setting_name: string;
  setting_genre: string;
  period_id: string;
  display_name: string;
  time_period: string;
  summary: string;
  tone?: string;
  key_conflicts?: string[];
  source_prompt?: string;
}): Promise<EraForgeGenerateResponse> {
  return apiFetch('/v2/eraforge/generate', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getGeneratedPacks(): Promise<{ packs: GeneratedPackEntry[] }> {
  return apiFetch('/v2/eraforge/packs');
}
