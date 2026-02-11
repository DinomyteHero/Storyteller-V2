#!/usr/bin/env python3
"""Fix NEW_JEDI_ORDER rumors.yaml schema."""

import yaml
from pathlib import Path

rumors_file = Path(__file__).parent.parent / "data" / "static" / "era_packs" / "new_jedi_order" / "rumors.yaml"

with open(rumors_file, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

# Transform each rumor
for rumor in data.get('rumors', []):
    # Rename 'content' to 'text'
    if 'content' in rumor:
        rumor['text'] = rumor.pop('content')

    # Map 'reliability' to 'credibility'
    if 'reliability' in rumor:
        reliability = rumor.pop('reliability')
        # Map to allowed values: confirmed, likely, rumor
        mapping = {
            'high': 'likely',
            'medium': 'rumor',
            'low': 'rumor',  # Low reliability = rumor
        }
        rumor['credibility'] = mapping.get(reliability, 'rumor')

    # Convert 'hooks' to 'tags'
    if 'hooks' in rumor:
        rumor['tags'] = rumor.pop('hooks')

    # Remove 'source' (not in model)
    if 'source' in rumor:
        del rumor['source']

# Write back
with open(rumors_file, 'w', encoding='utf-8') as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f"Fixed {len(data.get('rumors', []))} rumors in {rumors_file}")
