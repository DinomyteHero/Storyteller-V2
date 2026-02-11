#!/usr/bin/env python3
"""Fix LEGACY era pack access_points schema."""

import yaml
from pathlib import Path

locations_file = Path(__file__).parent.parent / "data" / "static" / "era_packs" / "legacy" / "locations.yaml"

with open(locations_file, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

fixed_count = 0
for location in data.get('locations', []):
    if 'access_points' in location:
        new_access_points = []
        for i, ap in enumerate(location['access_points']):
            # Transform old schema to new schema
            new_ap = {}

            # Generate ID from name or index
            if 'name' in ap:
                ap_id = ap['name'].lower().replace(' ', '_').replace('-', '_')
                new_ap['id'] = f"{location.get('id', 'loc')}_{ap_id}"
            else:
                new_ap['id'] = f"{location.get('id', 'loc')}_access_{i}"

            # Map security_modifier to visibility
            if 'security_modifier' in ap:
                security = ap['security_modifier']
                if security >= 15:
                    new_ap['visibility'] = 'restricted'
                elif security >= 10:
                    new_ap['visibility'] = 'public'
                else:
                    new_ap['visibility'] = 'hidden'
            else:
                new_ap['visibility'] = 'public'

            # Default type
            new_ap['type'] = 'door'

            # Add bypass_methods if description suggests stealth/tech
            desc = ap.get('description', '').lower()
            bypass_methods = []
            if 'stealth' in desc or 'hidden' in desc or 'secret' in desc:
                bypass_methods.append('stealth')
            if 'hack' in desc or 'tech' in desc or 'slice' in desc:
                bypass_methods.append('tech')
            if 'bribe' in desc or 'convince' in desc:
                bypass_methods.append('social')
            if bypass_methods:
                new_ap['bypass_methods'] = bypass_methods

            new_access_points.append(new_ap)
            fixed_count += 1

        location['access_points'] = new_access_points

# Write back
with open(locations_file, 'w', encoding='utf-8') as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f"Fixed {fixed_count} access points in {len(data.get('locations', []))} locations")
