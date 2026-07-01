import pandas as pd
import re

# Read current config to get existing universe
with open('src/otm_naked/config.py', 'r') as f:
    config_text = f.read()

# Parse Watchlist.csv
df = pd.read_csv('HILO-IV Seller/Watchlist.csv', skiprows=1)
# Filter out valid symbols
symbols_to_add = [s.strip() for s in df['Symbol'].dropna().unique() if isinstance(s, str) and str(s).isalpha()]

# Add to universe
match = re.search(r'OTM_NAKED_UNIVERSE:\s*List\[str\]\s*=\s*\[(.*?)\]', config_text, re.DOTALL)
if match:
    existing_universe = [s.strip().strip('"\'') for s in match.group(1).split(',')]
    existing_universe = [s for s in existing_universe if s and not s.startswith('#')]
    
    # Merge and deduplicate
    all_symbols = sorted(list(set(existing_universe + symbols_to_add)))
    print(f'Total symbols: {len(all_symbols)}')
    
    # Format new list
    new_universe_str = 'OTM_NAKED_UNIVERSE: List[str] = [\n    '
    for i, sym in enumerate(all_symbols):
        new_universe_str += f'"{sym}", '
        if (i + 1) % 8 == 0:
            new_universe_str += '\n    '
    new_universe_str += '\n]'
    
    config_text = config_text[:match.start()] + new_universe_str + config_text[match.end():]

# Update OTM_NAKED_SECTORS. For simplicity, just add new symbols as 'UNKNOWN' if they don't exist.
match_sec = re.search(r'OTM_NAKED_SECTORS:\s*Dict\[str,\s*str\]\s*=\s*\{(.*?)\}', config_text, re.DOTALL)
if match_sec:
    existing_sectors = match_sec.group(1)
    # Parse existing
    sector_dict = {}
    for item in existing_sectors.split(','):
        if ':' in item:
            k, v = item.split(':')
            # Remove comments inline
            k = k.split('#')[0].strip().strip('"\'')
            v = v.split('#')[0].strip().strip('"\'')
            if k and v:
                sector_dict[k] = v
    
    for sym in all_symbols:
        if sym not in sector_dict:
            sector_dict[sym] = 'OTHER'
            
    # Format new dict
    new_sec_str = 'OTM_NAKED_SECTORS: Dict[str, str] = {\n    '
    for i, (sym, sec) in enumerate(sector_dict.items()):
        new_sec_str += f'"{sym}": "{sec}", '
        if (i + 1) % 4 == 0:
            new_sec_str += '\n    '
    new_sec_str += '\n}'
    
    config_text = config_text[:match_sec.start()] + new_sec_str + config_text[match_sec.end():]

with open('src/otm_naked/config.py', 'w') as f:
    f.write(config_text)

print('Updated config.py')
