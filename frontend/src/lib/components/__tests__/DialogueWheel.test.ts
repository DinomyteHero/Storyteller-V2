import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import DialogueWheel from '$lib/components/choices/DialogueWheel.svelte';
import type { ActionSuggestion, PlayerResponse } from '$lib/api/types';

function makePlayerResponses(): PlayerResponse[] {
  return [
    {
      id: 'r3',
      display_text: 'Threaten the guard captain.',
      action: { type: 'say', intent: 'threaten', target: null, tone: 'RENEGADE' },
      risk_level: 'DANGEROUS',
      consequence_hint: 'Violence may follow.',
      tone_tag: 'RENEGADE',
      meaning_tag: 'make_demand',
    },
    {
      id: 'r1',
      display_text: 'Offer help to stabilize the crowd.',
      action: { type: 'do', intent: 'help', target: null, tone: 'PARAGON' },
      risk_level: 'SAFE',
      consequence_hint: 'People remember kindness.',
      tone_tag: 'PARAGON',
      meaning_tag: 'offer_alliance',
    },
    {
      id: 'r4',
      display_text: 'Hold back and observe.',
      action: { type: 'do', intent: 'observe', target: null, tone: 'NEUTRAL' },
      risk_level: 'SAFE',
      consequence_hint: 'You gather context.',
      tone_tag: 'NEUTRAL',
      meaning_tag: 'deflect',
    },
    {
      id: 'r2',
      display_text: 'Ask who ordered the lockdown.',
      action: { type: 'say', intent: 'ask', target: null, tone: 'INVESTIGATE' },
      risk_level: 'RISKY',
      consequence_hint: 'The truth might sting.',
      tone_tag: 'INVESTIGATE',
      meaning_tag: 'seek_history',
    },
  ];
}

function makeSuggestedActions(): ActionSuggestion[] {
  return [
    {
      label: 'Push into the checkpoint',
      intent_text: 'I push forward.',
      category: 'COMMIT',
      risk_level: 'DANGEROUS',
      strategy_tag: 'AGGRESSIVE',
      tone_tag: 'RENEGADE',
      intent_style: 'forceful',
      consequence_hint: 'Guards react immediately.',
      companion_reactions: {},
      risk_factors: [],
    },
    {
      label: 'Question the sentries',
      intent_text: 'I ask what happened.',
      category: 'SOCIAL',
      risk_level: 'SAFE',
      strategy_tag: 'CURIOUS',
      tone_tag: 'INVESTIGATE',
      intent_style: 'calm',
      consequence_hint: 'You learn what changed.',
      companion_reactions: {},
      risk_factors: [],
    },
  ];
}

describe('DialogueWheel', () => {
  it('renders four KOTOR tones in sorted order from player responses', () => {
    render(DialogueWheel, {
      playerResponses: makePlayerResponses(),
      suggestedActions: [],
      choiceAnimKey: 1,
      onChoice: vi.fn(),
    });

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    expect(buttons[0].textContent).toContain('Offer help to stabilize the crowd.');
    expect(buttons[1].textContent).toContain('Ask who ordered the lockdown.');
    expect(buttons[2].textContent).toContain('Threaten the guard captain.');
    expect(buttons[3].textContent).toContain('Hold back and observe.');
  });

  it('falls back to suggested actions when player responses are absent', () => {
    render(DialogueWheel, {
      playerResponses: [],
      suggestedActions: makeSuggestedActions(),
      choiceAnimKey: 1,
      onChoice: vi.fn(),
    });

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0].textContent).toContain('Question the sentries');
    expect(buttons[1].textContent).toContain('Push into the checkpoint');
  });

  it('invokes onChoice with user input and label on click', async () => {
    const onChoice = vi.fn();
    render(DialogueWheel, {
      playerResponses: makePlayerResponses(),
      suggestedActions: [],
      choiceAnimKey: 1,
      onChoice,
    });

    await fireEvent.click(screen.getByRole('button', { name: /Offer help to stabilize the crowd/i }));
    expect(onChoice).toHaveBeenCalledTimes(1);
    expect(onChoice).toHaveBeenCalledWith(
      'Offer help to stabilize the crowd.',
      'Offer help to stabilize the crowd.',
    );
  });

  it('renders tone classes and numeric shortcut badges', () => {
    render(DialogueWheel, {
      playerResponses: makePlayerResponses(),
      suggestedActions: [],
      choiceAnimKey: 1,
      onChoice: vi.fn(),
    });

    const buttons = screen.getAllByRole('button');
    expect(buttons[0].className).toContain('tone-paragon');
    expect(buttons[1].className).toContain('tone-investigate');
    expect(buttons[2].className).toContain('tone-renegade');
    expect(buttons[3].className).toContain('tone-neutral');
    expect(screen.getByLabelText('Press 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Press 2')).toBeInTheDocument();
    expect(screen.getByLabelText('Press 3')).toBeInTheDocument();
    expect(screen.getByLabelText('Press 4')).toBeInTheDocument();
  });
});
