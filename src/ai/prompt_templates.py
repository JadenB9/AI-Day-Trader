"""
Prompt templates for AI decision engine.
"""
from typing import Dict, Any
from src.strategies.base import Signal, SignalDirection


TRADE_ANALYSIS_SYSTEM = """You are an expert day trader AI assistant analyzing potential scalping trades.
Your role is to quickly validate or reject trade signals based on:
1. Technical indicator alignment
2. Risk/reward profile
3. Market conditions and sentiment
4. Recent news that may affect the trade

You must be decisive and concise. This is scalping - quick decisions matter.

IMPORTANT RULES:
- Only APPROVE trades with clear edge and proper risk/reward
- REJECT trades with conflicting signals or poor timing
- MODIFY to suggest better entries, stops, or size adjustments
- Never approve trades just because a strategy triggered - verify confluence

Response MUST follow this exact format:
DECISION: [APPROVE|REJECT|MODIFY]
CONFIDENCE: [0-100]
REASONING: [2-3 sentences explaining the decision]
MODIFICATIONS: [Only if MODIFY - specify: entry, stop, target, or size changes]"""


def build_trade_context(
    signal: Signal,
    snapshot: 'MarketSnapshot',
    portfolio_state: Dict = None
) -> str:
    """
    Build comprehensive context for AI trade analysis.

    Args:
        signal: Trading signal to analyze
        snapshot: Current market snapshot
        portfolio_state: Current portfolio info

    Returns:
        Formatted context string
    """
    context_parts = []

    # Signal info
    context_parts.append(f"""TRADE SIGNAL ANALYSIS REQUEST
Symbol: {signal.symbol}
Direction: {signal.direction.value.upper()}
Strategy: {signal.strategy}
Signal Confidence: {signal.confidence:.1%}
Signal Strength: {signal.strength.value}
""")

    # Price levels
    context_parts.append(f"""PROPOSED TRADE:
Entry: ${signal.entry_price:.2f}
Stop Loss: ${signal.stop_loss:.2f}
Take Profit: ${signal.take_profit:.2f}
Risk/Reward: {signal.risk_reward_ratio:.2f}:1 (if available)
""")

    # Current market data
    context_parts.append(f"""CURRENT MARKET DATA:
Last Price: ${snapshot.last_price:.2f}
Bid/Ask: ${snapshot.bid:.2f} / ${snapshot.ask:.2f}
Day Change: {snapshot.day_change_pct:.2f}%
Gap: {snapshot.gap_pct:.2f}%
Day Range: ${snapshot.day_low:.2f} - ${snapshot.day_high:.2f}
Volume: {snapshot.day_volume:,}
""")

    # Indicators
    if signal.indicators_used:
        ind_lines = []
        for name, value in signal.indicators_used.items():
            if isinstance(value, float):
                ind_lines.append(f"  {name}: {value:.2f}")
            else:
                ind_lines.append(f"  {name}: {value}")

        context_parts.append("KEY INDICATORS:\n" + "\n".join(ind_lines))

    # Strategy reasoning
    if signal.reasoning:
        context_parts.append(f"""STRATEGY REASONING:
{signal.reasoning}
""")

    # Portfolio context
    if portfolio_state:
        context_parts.append(f"""PORTFOLIO CONTEXT:
Equity: ${portfolio_state.get('equity', 0):,.0f}
Open Positions: {portfolio_state.get('position_count', 0)}
Daily P&L: {portfolio_state.get('daily_pnl_pct', 0):.2%}
Portfolio Heat: {portfolio_state.get('portfolio_heat', 0):.1%}
""")

    # News
    if snapshot.recent_news:
        news_lines = []
        for news in snapshot.recent_news[:3]:
            headline = news.get('headline', '')[:100]
            news_lines.append(f"  - {headline}")
        context_parts.append("RECENT NEWS:\n" + "\n".join(news_lines))

    # Final instruction
    context_parts.append("""
ANALYZE this trade setup and provide your decision.
Consider: indicator confluence, risk/reward, market conditions, and timing.
Be decisive - this is a scalping trade that needs quick execution or rejection.""")

    return "\n".join(context_parts)


def build_market_scan_context(
    symbols: list,
    top_opportunities: list
) -> str:
    """Build context for market scanning/opportunity finding"""
    context = f"""MARKET SCAN ANALYSIS

Analyzing {len(symbols)} symbols for trading opportunities.

TOP SCANNER RESULTS:
"""
    for i, opp in enumerate(top_opportunities[:10], 1):
        context += f"""
{i}. {opp.get('symbol')}
   Gap: {opp.get('gap_pct', 0):.1f}%
   RVOL: {opp.get('relative_volume', 1):.1f}x
   Score: {opp.get('score', 0):.0f}
"""

    context += """
Which symbols look most promising for scalping today?
Consider gaps, volume, and momentum patterns.
List top 5 with brief rationale for each."""

    return context


def parse_ai_response(response_text: str) -> Dict[str, Any]:
    """
    Parse AI response into structured format.

    Expected format:
    DECISION: APPROVE/REJECT/MODIFY
    CONFIDENCE: 0-100
    REASONING: text
    MODIFICATIONS: optional modifications
    """
    result = {
        'decision': 'REJECT',
        'confidence': 0,
        'reasoning': '',
        'modifications': {},
        'raw_response': response_text
    }

    lines = response_text.strip().split('\n')

    for line in lines:
        line = line.strip()

        if line.startswith('DECISION:'):
            decision = line.replace('DECISION:', '').strip().upper()
            if decision in ['APPROVE', 'REJECT', 'MODIFY']:
                result['decision'] = decision

        elif line.startswith('CONFIDENCE:'):
            try:
                conf_str = line.replace('CONFIDENCE:', '').strip()
                conf_str = conf_str.replace('%', '')
                result['confidence'] = int(conf_str)
            except:
                pass

        elif line.startswith('REASONING:'):
            result['reasoning'] = line.replace('REASONING:', '').strip()

        elif line.startswith('MODIFICATIONS:'):
            mods_text = line.replace('MODIFICATIONS:', '').strip()
            result['modifications'] = _parse_modifications(mods_text)

    # Try to extract reasoning from remaining text if not found
    if not result['reasoning'] and len(lines) > 3:
        for line in lines[3:]:
            if line.strip() and not line.startswith(('DECISION', 'CONFIDENCE', 'MODIFICATIONS')):
                result['reasoning'] = line.strip()
                break

    return result


def _parse_modifications(mods_text: str) -> Dict:
    """Parse modification suggestions"""
    mods = {}

    text_lower = mods_text.lower()

    # Look for specific modifications
    if 'stop' in text_lower:
        # Try to extract stop value
        import re
        stop_match = re.search(r'stop[:\s]*\$?([\d.]+)', text_lower)
        if stop_match:
            try:
                mods['stop_loss'] = float(stop_match.group(1))
            except:
                pass

    if 'target' in text_lower or 'take profit' in text_lower:
        import re
        target_match = re.search(r'(?:target|take profit)[:\s]*\$?([\d.]+)', text_lower)
        if target_match:
            try:
                mods['take_profit'] = float(target_match.group(1))
            except:
                pass

    if 'size' in text_lower or 'reduce' in text_lower:
        if 'half' in text_lower or '50%' in text_lower:
            mods['size_multiplier'] = 0.5
        elif 'quarter' in text_lower or '25%' in text_lower:
            mods['size_multiplier'] = 0.25

    return mods


# Import at end to avoid circular
from src.data.models.market_snapshot import MarketSnapshot
