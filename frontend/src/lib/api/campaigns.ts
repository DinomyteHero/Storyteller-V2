/**
 * Campaign API endpoints.
 */
import { apiFetch } from './client';
import type {
  SetupAutoRequest,
  SetupAutoResponse,
  TurnRequest,
  TurnResponse,
  Intent,
  TranscriptResponse,
} from './types';

export async function setupAuto(req: SetupAutoRequest): Promise<SetupAutoResponse> {
  return apiFetch<SetupAutoResponse>('/v2/setup/auto', {
    method: 'POST',
    body: JSON.stringify(req),
  }, 180_000);
}

export async function runTurn(
  campaignId: string,
  playerId: string,
  userInput: string,
  debug: boolean = false,
  intent?: Intent
): Promise<TurnResponse> {
  const req: TurnRequest = { user_input: userInput, debug, intent };
  return apiFetch<TurnResponse>(
    `/v2/campaigns/${campaignId}/turn?player_id=${encodeURIComponent(playerId)}`,
    { method: 'POST', body: JSON.stringify(req) },
    180_000
  );
}

export async function getState(
  campaignId: string,
  playerId: string
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(
    `/v2/campaigns/${campaignId}/state?player_id=${encodeURIComponent(playerId)}`
  );
}

export async function getTranscript(
  campaignId: string,
  limit: number = 100
): Promise<TranscriptResponse> {
  return apiFetch<TranscriptResponse>(
    `/v2/campaigns/${campaignId}/transcript?limit=${limit}`
  );
}

export async function getWorldState(
  campaignId: string
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(
    `/v2/campaigns/${campaignId}/world_state`
  );
}

export async function getRumors(
  campaignId: string,
  limit: number = 5
): Promise<{ campaign_id: string; rumors: string[] }> {
  return apiFetch(`/v2/campaigns/${campaignId}/rumors?limit=${limit}`);
}

export interface CompanionPreview {
  id: string;
  name: string;
  species: string;
  archetype: string;
  motivation: string;
  voice_belief: string;
}

export async function getEraCompanions(
  eraId: string
): Promise<{ era_id: string; companions: CompanionPreview[] }> {
  return apiFetch(`/v2/era/${encodeURIComponent(eraId)}/companions`);
}
