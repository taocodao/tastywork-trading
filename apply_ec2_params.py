"""
apply_ec2_params.py
====================
Reads the optimized parameter JSON files produced by the EC2 optimizer
and patches them into diagonal_strategy/config.py (TQQQ_DIAGONAL_PARAMS).

Usage:
    python apply_ec2_params.py [--dry-run] [--data-dir data]

Options:
    --dry-run     Show what would be applied without modifying config.py
    --data-dir    Directory containing optimized_params_*.json (default: data)
"""

import argparse
import json
import os
import re
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REGIMES      = ['LOW_VOL', 'NORMAL', 'HIGH_VOL']
CONFIG_PATH  = os.path.join(os.path.dirname(__file__), 'diagonal_strategy', 'config.py')

# Keys that come from the optimizer and map into TQQQ_DIAGONAL_PARAMS
PARAM_MAP = {
    'anchor_dte':              'anchor_dte',
    'anchor_delta':            'anchor_delta',
    'hedge_dte':               'hedge_dte',
    'hedge_delta':             'hedge_delta',
    'anchor_profit_target_pct':'anchor_profit_target_pct',
    'anchor_stop_loss_mult':   'anchor_stop_loss_mult',
    'hedge_close_decay_pct':   'hedge_close_decay_pct',
    'max_naked_hours':         'max_naked_hours',
}


def load_optimized_params(data_dir: str) -> dict:
    """Load all available regime param files from data_dir."""
    results = {}
    for regime in REGIMES:
        path = os.path.join(data_dir, f'optimized_params_{regime}.json')
        if not os.path.exists(path):
            logger.warning(f"  {regime}: no param file found at {path} — skipping")
            continue
        with open(path) as f:
            raw = json.load(f)
        # Strip internal scoring keys (prefixed with '_')
        params = {k: v for k, v in raw.items() if not k.startswith('_')}
        results[regime] = params
        logger.info(f"  Loaded {regime}: {json.dumps(params)}")
    return results


def apply_to_config(optimized: dict, dry_run: bool = False):
    """
    Patch TQQQ_DIAGONAL_PARAMS in config.py by rewriting the file.
    Preserves all other config values unchanged.
    """
    with open(CONFIG_PATH, 'r') as f:
        source = f.read()

    # Parse current config to compare
    sys.path.insert(0, os.path.dirname(CONFIG_PATH) + '/..')
    import diagonal_strategy.config as cfg
    current_params = cfg.TQQQ_DIAGONAL_PARAMS

    for regime, new_vals in optimized.items():
        if regime not in current_params:
            logger.warning(f"  {regime} not in current config — skipping")
            continue

        for optimizer_key, config_key in PARAM_MAP.items():
            if optimizer_key not in new_vals:
                continue
            old_val = current_params[regime].get(config_key)
            new_val = new_vals[optimizer_key]

            if old_val == new_val:
                continue

            logger.info(f"  {regime}.{config_key}: {old_val} → {new_val}")

            if not dry_run:
                # Replace the value in the source string using a regex
                # Matches: 'key': old_value  inside a regime block
                # We locate the regime section first, then the key within it
                pattern = (
                    r"('" + regime + r"':\s*\{[^}]*?'"
                    + re.escape(config_key) + r"':\s*)"
                    + re.escape(str(old_val))
                )
                replacement = r'\g<1>' + str(new_val)
                new_source = re.sub(pattern, replacement, source, flags=re.DOTALL)
                if new_source == source:
                    logger.warning(f"    Could not find pattern for {regime}.{config_key} — manual edit needed")
                else:
                    source = new_source

    if dry_run:
        logger.info("DRY RUN complete — no files modified.")
    else:
        with open(CONFIG_PATH, 'w') as f:
            f.write(source)
        logger.info(f"config.py updated successfully.")


def main():
    parser = argparse.ArgumentParser(description="Apply EC2 optimizer results to config.py")
    parser.add_argument('--dry-run',  action='store_true', help='Show changes without writing')
    parser.add_argument('--data-dir', default='data',      help='Directory with optimized_params_*.json')
    args = parser.parse_args()

    logger.info(f"Reading optimized params from: {args.data_dir}/")
    optimized = load_optimized_params(args.data_dir)

    if not optimized:
        logger.error("No param files found. Nothing to apply. Is the EC2 optimizer finished?")
        sys.exit(1)

    logger.info(f"\nApplying to {CONFIG_PATH}" + (" (DRY RUN)" if args.dry_run else ""))
    apply_to_config(optimized, dry_run=args.dry_run)

    if not args.dry_run:
        print("\n✅ Done! Restart the live scanner to use the new parameters.")
        print("   To verify: python -c \"from diagonal_strategy.config import TQQQ_DIAGONAL_PARAMS; import json; print(json.dumps(TQQQ_DIAGONAL_PARAMS, indent=2))\"")


if __name__ == '__main__':
    main()
