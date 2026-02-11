/**
 * Era pack API endpoints.
 */
import { apiFetch } from './client';
import type { EraBackground, EraLocation } from './types';

export async function getEraBackgrounds(
  eraId: string
): Promise<{ era_id: string; backgrounds: EraBackground[] }> {
  return apiFetch(`/v2/era/${encodeURIComponent(eraId)}/backgrounds`);
}

export async function getEraLocations(
  eraId: string
): Promise<{ era_id: string; locations: EraLocation[] }> {
  return apiFetch(`/v2/era/${encodeURIComponent(eraId)}/locations`);
}
