#!/usr/bin/env python3
"""Fix NEW_JEDI_ORDER facts.yaml schema."""

import yaml
from pathlib import Path

facts_file = Path(__file__).parent.parent / "data" / "static" / "era_packs" / "new_jedi_order" / "facts.yaml"

with open(facts_file, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

# Transform each fact
fixed_count = 0
for i, fact in enumerate(data.get('facts', [])):
    # Generate ID from subject if missing
    if 'id' not in fact:
        subject = fact.get('subject', f'unknown_{i}')
        fact_id = f"fact-njo-{subject.lower().replace(' ', '_').replace('_', '-')}"
        fact['id'] = fact_id
        fixed_count += 1

    # Remove 'context' field (not in model)
    if 'context' in fact:
        del fact['context']
        fixed_count += 1

# Write back
with open(facts_file, 'w', encoding='utf-8') as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f"Fixed {fixed_count} issues in facts.yaml ({len(data.get('facts', []))} total facts)")
