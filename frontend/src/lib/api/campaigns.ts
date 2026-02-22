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
  StorySummaryResponse,
  CampaignListResponse,
} from './types';

export async function setupAuto(req: SetupAutoRequest): Promise<SetupAutoResponse> {
  return apiFetch<SetupAutoResponse>('/v2/setup/auto', {
    method: 'POST',
    body: JSON.stringify(req),
  }, 180_000);
}

export async function patchCharacterName(
  campaignId: string,
  playerId: string,
  name: string,
): Promise<{ ok: boolean; name: string }> {
  return apiFetch(`/v2/campaigns/${campaignId}/character`, {
    method: 'PATCH',
    body: JSON.stringify({ player_id: playerId, name }),
  });
}

export async function runTurn(
  campaignId: string,
  playerId: string,
  userInput: string,
  debug: boolean = false,
  intent?: import("./types").Intent,
  structuredIntent?: import("./types").StructuredIntent | null,
): Promise<TurnResponse> {
  const req: TurnRequest = intent
    ? { intent, user_input: userInput, debug }
    : { user_input: userInput, debug };
  if (structuredIntent) {
    req.structured_intent = structuredIntent;
  }
  return apiFetch<TurnResponse>(
    `/v2/campaigns/${campaignId}/turn?player_id=${encodeURIComponent(playerId)}`,
    { method: 'POST', body: JSON.stringify(req) },
    180_000
  );
}

/**
 * Phase 1.3: Preview how the router will classify free text input.
 * Lightweight call — no turn executed, just classification preview.
 */
export interface ClassifyResult {
  route: string;           // TALK | MECHANIC | META
  action_class: string;    // DIALOGUE_ONLY | DIALOGUE_WITH_ACTION | PHYSICAL_ACTION | META
  requires_resolution: boolean;
  confidence: number;
  rationale_short: string;
}

export async function classifyIntent(
  campaignId: string,
  userInput: string,
): Promise<ClassifyResult> {
  return apiFetch<ClassifyResult>(
    `/v2/campaigns/${campaignId}/classify`,
    { method: 'POST', body: JSON.stringify({ user_input: userInput }) },
    5_000,
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

export async function getStorySummary(
  campaignId: string
): Promise<StorySummaryResponse> {
  return apiFetch<StorySummaryResponse>(
    `/v2/campaigns/${campaignId}/summary`
  );
}

export async function listCampaigns(
  limit: number = 100,
  offset: number = 0,
): Promise<CampaignListResponse> {
  return apiFetch<CampaignListResponse>(
    `/v2/campaigns?limit=${limit}&offset=${offset}`
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
  character_legacy?: Record<string, unknown>;
  character_legacy_id?: number | null;
  player_profile_id?: string | null;
  saga_id?: string | null;
  saga_chapter?: number | null;
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

export async function rewindCampaign(
  campaignId: string,
  toTurn: number,
): Promise<{ rewound_to: number; turns_deleted: number; previous_turn: number }> {
  return apiFetch(
    `/v2/campaigns/${campaignId}/rewind?to_turn=${toTurn}`,
    { method: 'POST' },
    30_000
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

// ── V9.0: Campaign Settings (Novel-Length Story) ─────────────────────

export interface CampaignSettings {
  narrator_mode: 'concise' | 'novel' | 'epic';
  cloud_preset: 'local' | 'budget' | 'balanced' | 'quality' | 'cloud_all' | 'deepseek' | 'custom';
  custom_preset_id?: string | null;
  preferred_provider?: string | null;
  agent_overrides?: Record<string, { provider: string; model: string }> | null;
}

export async function getCampaignSettings(
  campaignId: string
): Promise<CampaignSettings> {
  return apiFetch<CampaignSettings>(
    `/v2/campaigns/${encodeURIComponent(campaignId)}/settings`
  );
}

export async function patchCampaignSettings(
  campaignId: string,
  settings: Partial<CampaignSettings>
): Promise<CampaignSettings> {
  return apiFetch<CampaignSettings>(
    `/v2/campaigns/${encodeURIComponent(campaignId)}/settings`,
    { method: 'PATCH', body: JSON.stringify(settings) }
  );
}

// ── V12.0: Cloud Provider Management ─────────────────────────────────

export interface ProviderStatus {
  provider_id: string;
  label: string;
  has_key: boolean;
  key_source: 'db' | 'env' | null;
  key_preview: string;
  models: { id: string; label: string; tier: string }[];
}

export interface TestResult {
  ok: boolean;
  latency_ms: number;
  error: string | null;
  model_used: string | null;
}

export interface Preset {
  id: string;
  name: string;
  description: string;
  role_configs: Record<string, { provider?: string; model?: string; tier?: string }>;
  is_system: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ResolvedRoleConfig {
  provider: string;
  model: string;
  source: 'override' | 'preset' | 'env' | 'default';
}

export async function getProviders(): Promise<ProviderStatus[]> {
  return apiFetch<ProviderStatus[]>('/v2/settings/providers');
}

export async function setProviderKey(
  providerId: string,
  apiKey: string
): Promise<ProviderStatus> {
  return apiFetch<ProviderStatus>(
    `/v2/settings/providers/${encodeURIComponent(providerId)}/key`,
    { method: 'PUT', body: JSON.stringify({ api_key: apiKey }) }
  );
}

export async function removeProviderKey(
  providerId: string
): Promise<ProviderStatus> {
  return apiFetch<ProviderStatus>(
    `/v2/settings/providers/${encodeURIComponent(providerId)}/key`,
    { method: 'DELETE' }
  );
}

export async function testProvider(
  providerId: string
): Promise<TestResult> {
  return apiFetch<TestResult>(
    `/v2/settings/providers/${encodeURIComponent(providerId)}/test`,
    { method: 'POST' },
    35_000
  );
}

export async function getPresets(): Promise<Preset[]> {
  return apiFetch<Preset[]>('/v2/settings/presets');
}

export async function createPreset(
  name: string,
  description: string,
  roleConfigs: Record<string, { provider: string; model: string }>
): Promise<Preset> {
  return apiFetch<Preset>('/v2/settings/presets', {
    method: 'POST',
    body: JSON.stringify({ name, description, role_configs: roleConfigs }),
  });
}

export async function updatePreset(
  presetId: string,
  updates: { name?: string; description?: string; role_configs?: Record<string, { provider: string; model: string }> }
): Promise<Preset> {
  return apiFetch<Preset>(
    `/v2/settings/presets/${encodeURIComponent(presetId)}`,
    { method: 'PUT', body: JSON.stringify(updates) }
  );
}

export async function deletePreset(presetId: string): Promise<void> {
  await apiFetch(`/v2/settings/presets/${encodeURIComponent(presetId)}`, {
    method: 'DELETE',
  });
}

export async function getResolvedConfig(
  campaignId: string
): Promise<{ campaign_id: string; roles: Record<string, ResolvedRoleConfig> }> {
  return apiFetch(
    `/v2/settings/campaigns/${encodeURIComponent(campaignId)}/resolved_config`
  );
}
