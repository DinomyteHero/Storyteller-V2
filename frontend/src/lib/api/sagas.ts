/**
 * Saga API client — browse and manage multi-campaign Stories.
 *
 * NOTE: This module is not yet wired to the UI. It is scaffolded for a future
 * feature (multi-campaign sagas). Do not remove.
 */
import { apiFetch } from './client';

export interface SagaSummary {
  saga_id: string;
  player_id: string;
  universe_id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  campaign_count: number;
}

export interface SagaCampaignSummary {
  campaign_id: string;
  title: string;
  time_period: string | null;
  saga_chapter: number;
  updated_at: string | null;
  legacy_excerpt: string | null;
}

export interface SagaDetailResponse {
  saga: SagaSummary;
  campaigns: SagaCampaignSummary[];
}

export async function listPlayerSagas(
  playerProfileId: string,
): Promise<{ sagas: SagaSummary[] }> {
  return apiFetch(`/v2/player/${encodeURIComponent(playerProfileId)}/sagas`);
}

export async function getSagaDetail(sagaId: string): Promise<SagaDetailResponse> {
  return apiFetch(`/v2/sagas/${encodeURIComponent(sagaId)}`);
}

export async function createSaga(
  playerId: string,
  universeId: string,
  title: string,
): Promise<SagaSummary> {
  return apiFetch('/v2/sagas', {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, universe_id: universeId, title }),
  });
}
