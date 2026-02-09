
import json

mermaid1 = """graph TB
    subgraph CONTANGO ["CONTANGO: Front IV < Back IV ~85pct of days"]
        C1["Market is CALM"] --> C2["Underlying moves slowly"]
        C2 --> C3["Short leg theta decays<br/>predictably at 7-14 DTE"]
        C3 --> C4["Long leg retains<br/>value at 45-60 DTE"]
        C4 --> C5["73pct Win Rate<br/>Avg PnL: +39"]
    end
    subgraph BACKWARDATION ["BACKWARDATION: Front IV > Back IV ~7pct of days"]
        B1["Market in CRISIS"] --> B2["Underlying gaps 3-5pct daily"]
        B2 --> B3["Short leg goes ITM<br/>Gamma explodes"]
        B3 --> B4["IV EXPANDS further<br/>not collapse"]
        B4 --> B5["19pct Win Rate<br/>Avg PnL: -155"]
    end
"""

create_mermaid_diagram(mermaid1, 'contango_vs_backwardation.png', width=1200, height=700)
with open('contango_vs_backwardation.png.meta.json', 'w') as f:
    json.dump({"caption": "Why Contango Wins vs Backwardation Loses for Diagonal Spreads", "description": "Side-by-side flow showing contango leads to predictable theta decay and profits while backwardation causes gamma explosions and losses"}, f)

mermaid2 = """graph TD
    A["Price: $100<br/>You sell $103 Call<br/>7 DTE, Delta 0.30"] --> B{"What happens<br/>in 7 days?"}
    B -->|"CONTANGO scenario<br/>Stock moves to $101"| C["Short call expires<br/>worthless at $103"]
    B -->|"BACKWARDATION scenario<br/>Stock gaps to $108"| D["Short call now $5 ITM<br/>You owe $500 per contract"]
    C --> E["You keep full premium<br/>~$50-80 per contract<br/>PROFIT"]
    D --> F["Long leg gained ~$300<br/>Short leg lost ~$500<br/>NET LOSS: -$200"]
    F --> G["Plus: IV expanded<br/>New short calls MORE<br/>expensive to buy back"]
"""

create_mermaid_diagram(mermaid2, 'concrete_example.png', width=1200, height=700)
with open('concrete_example.png.meta.json', 'w') as f:
    json.dump({"caption": "Concrete Example: Same Diagonal Spread in Two Different Regimes", "description": "Shows how the same diagonal spread produces opposite outcomes depending on market regime"}, f)

mermaid3 = """graph LR
    subgraph PIPELINE ["REVISED SIGNAL PIPELINE"]
        A["Market Data<br/>31 ETFs"] --> B["Circuit Breaker<br/>VIX minus VXV"]
        B -->|"Below 0.5<br/>SAFE"| C["Universe Scanner<br/>Liquidity Filter"]
        B -->|"Above 0.5<br/>STRESS"| X["HALT<br/>No New Trades"]
        C --> D["Direction Predictor<br/>RSI/BB/MA"]
        D --> E["Strike Selector<br/>Delta 0.75/0.30"]
        E --> F["Position Sizer<br/>Quarter Kelly"]
        F --> G["EXECUTE TRADE"]
        G --> H["ML Roll Optimizer<br/>PPO Agent"]
        H -->|"HOLD"| H
        H -->|"ROLL"| I["Roll Short Leg"]
        H -->|"EXIT"| J["Close Position"]
    end
"""

create_mermaid_diagram(mermaid3, 'revised_pipeline.png', width=1400, height=500)
with open('revised_pipeline.png.meta.json', 'w') as f:
    json.dump({"caption": "Revised Implementation Pipeline with Circuit Breaker and ML Roll Optimizer", "description": "Complete signal generation pipeline showing circuit breaker, universe scanner, signal generation, position sizing, and ML-driven exit management"}, f)

print("All diagrams created")
