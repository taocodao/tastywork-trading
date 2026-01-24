#!/usr/bin/env python
"""
Earnings Scanner CLI
====================

Discover and rank stocks with upcoming earnings for calendar spread trading.

Usage:
    python run_scanner.py                    # Scan next 14 days, show top 10
    python run_scanner.py --days 7 --top 5   # Next 7 days, top 5
    python run_scanner.py --no-ib            # Without IB Gateway
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="🎯 AI-Powered Earnings Scanner for Calendar Spreads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_scanner.py                  # Scan all, show top 10
  python run_scanner.py --days 7         # Only next 7 days
  python run_scanner.py --top 5          # Show top 5 only
  python run_scanner.py --no-ib --top 3  # Without IB, top 3
        """
    )
    
    parser.add_argument(
        "--days", type=int, default=14,
        help="Days ahead to scan for earnings (default: 14)"
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Show top N opportunities (default: 10)"
    )
    parser.add_argument(
        "--no-ib", action="store_true",
        help="Disable IB Gateway (use mock data)"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Disable Perplexity caching"
    )
    parser.add_argument(
        "--min-score", type=float, default=20,
        help="Minimum score threshold (default: 20)"
    )
    parser.add_argument(
        "--publish", action="store_true",
        help="Publish signals to WebSocket for frontend"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    import logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    print("\n" + "=" * 70)
    print("🎯 EARNINGS SCANNER - AI-Powered Opportunity Discovery")
    print("=" * 70)
    print(f"  Looking ahead: {args.days} days")
    print(f"  Show top: {args.top} opportunities")
    print(f"  IB Gateway: {'Enabled' if not args.no_ib else 'Disabled'}")
    print(f"  Publish signals: {'Yes' if args.publish else 'No'}")
    print(f"  Min score: {args.min_score}")
    print("=" * 70 + "\n")
    
    try:
        from src.earnings_intelligence.scanner import EarningsScanner
        
        scanner = EarningsScanner(
            use_ib=not args.no_ib,
            use_cache=not args.no_cache
        )
        
        opportunities = scanner.scan(
            days_ahead=args.days,
            min_score=args.min_score
        )
        
        # Show top N
        top_opps = opportunities[:args.top]
        scanner.print_opportunities(top_opps)
        
        # Publish signals if requested
        if args.publish and opportunities:
            print("\n📡 Publishing signals to frontend...")
            try:
                from signal_publisher import publish_earnings_signals
                published = publish_earnings_signals(opportunities, max_signals=args.top)
                print(f"✅ Published {published} signals to WebSocket")
            except Exception as e:
                print(f"⚠️ Publish failed: {e}")
        
        # Summary
        if opportunities:
            approve_count = sum(1 for o in opportunities if o.decision == "APPROVE")
            reduce_count = sum(1 for o in opportunities if o.decision == "REDUCE_SIZE")
            reject_count = sum(1 for o in opportunities if o.decision == "REJECT")
            
            print(f"\n📊 SUMMARY")
            print(f"  Total scanned: {len(opportunities)}")
            print(f"  ✓ APPROVE: {approve_count}")
            print(f"  ⚠ REDUCE_SIZE: {reduce_count}")
            print(f"  ✗ REJECT: {reject_count}")
            
            if top_opps:
                best = top_opps[0]
                print(f"\n🏆 TOP PICK: {best.symbol}")
                print(f"   Days to earnings: {best.days_to_earnings}")
                print(f"   Predicted class: {best.predicted_class} ({best.confidence:.0f}% confidence)")
                print(f"   Strategy: {best.strategy}")
                print(f"   Score: {best.score}")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure you're in the project directory and dependencies are installed.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

