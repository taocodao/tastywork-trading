
try:
    from src.earnings_intelligence.client import PerplexityClient
    client = PerplexityClient()
    print("Querying Perplexity...")
    answer = client.query("Show me code to authenticate with tastytrade python sdk using a refresh token only.")
    print("\nANSWER:")
    print(answer)
except Exception as e:
    print(f"Error: {e}")
