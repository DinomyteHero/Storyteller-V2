/**
 * Campaign API endpoints.
 */
import { apiFetch } from './client';
import type {
  SetupAutoRequest,
  SetupAutoResponse,
  TurnRequest,
  TurnResponse,
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
  intent?: import("./types").Intent
): Promise<TurnResponse> {
  const req: TurnRequest = intent ? { intent, user_input: userInput, debug } : { user_input: userInput, debug };
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

export interface CompleteCampaignResponse {
  status: string;
  legacy_id: string;
  campaign_id: string;
  recommended_next_scale: string;
  next_campaign_pitch: string;
}

export async function completeCampaign(
  campaignId: string,
  outcomeSummary: string = '',
  characterFate: string = ''
): Promise<CompleteCampaignResponse> {
  return apiFetch<CompleteCampaignResponse>(
    `/v2/campaigns/${campaignId}/complete`,
    {
      method: 'POST',
      body: JSON.stringify({
        outcome_summary: outcomeSummary,
        character_fate: characterFate,
      }),
    },
    60_000
  );
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
