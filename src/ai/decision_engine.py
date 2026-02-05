"""
AI Decision Engine.
Synthesizes strategy signals with AI evaluation.
"""
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog

from config.settings import get_settings
from src.ai.claude_client import get_claude_client, ClaudeClient
from src.ai.prompt_templates import (
    TRADE_ANALYSIS_SYSTEM,
    build_trade_context,
    parse_ai_response
)
from src.strategies.base import Signal, SignalDirection
from src.data.models.market_snapshot import MarketSnapshot
from src.core.event_bus import get_event_bus, EventType, Event
from src.core.exceptions import AIError, AITimeoutError

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class AIDecision:
    """Result of AI trade evaluation"""
    signal: Signal
    decision: str  # APPROVE, REJECT, MODIFY
    confidence: int  # 0-100
    reasoning: str
    modifications: Dict
    web_search_used: bool
    response_time_ms: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_approved(self) -> bool:
        return self.decision == "APPROVE"

    @property
    def is_rejected(self) -> bool:
        return self.decision == "REJECT"

    @property
    def is_modified(self) -> bool:
        return self.decision == "MODIFY"


class DecisionCache:
    """Simple cache for AI decisions to avoid duplicate calls"""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, AIDecision] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def get(self, symbol: str, strategy: str) -> Optional[AIDecision]:
        """Get cached decision if not expired"""
        key = f"{symbol}_{strategy}"
        if key in self._cache:
            decision = self._cache[key]
            if datetime.now() - decision.timestamp < self._ttl:
                return decision
            else:
                del self._cache[key]
        return None

    def set(self, symbol: str, strategy: str, decision: AIDecision) -> None:
        """Cache a decision"""
        key = f"{symbol}_{strategy}"
        self._cache[key] = decision

    def clear(self, symbol: str = None) -> None:
        """Clear cache for symbol or all"""
        if symbol:
            keys_to_remove = [k for k in self._cache if k.startswith(symbol)]
            for k in keys_to_remove:
                del self._cache[k]
        else:
            self._cache.clear()


class AIDecisionEngine:
    """
    AI-powered trade decision engine.
    Evaluates signals based on threshold criteria.
    Uses web search for real-time market context.
    """

    def __init__(self):
        self._client = get_claude_client()
        self._event_bus = get_event_bus()
        self._cache = DecisionCache(settings.ai.cache_decisions_seconds)

        # Thresholds from settings
        self.confidence_threshold = settings.ai.confidence_threshold
        self.position_size_threshold = settings.ai.position_size_threshold
        self.enable_web_search = settings.ai.enable_web_search

        # Stats
        self._decisions_made = 0
        self._approvals = 0
        self._rejections = 0
        self._modifications = 0

    async def should_evaluate(self, signal: Signal) -> bool:
        """
        Determine if signal should be sent to AI for evaluation.

        AI is called only for:
        1. High confidence signals (> threshold)
        2. Large position sizes (> threshold)
        3. Unusual conditions (VIX spike, conflicting signals)

        This keeps execution fast for routine trades.
        """
        # High confidence -> AI validation
        if signal.confidence >= self.confidence_threshold:
            logger.debug(
                "ai_trigger_confidence",
                symbol=signal.symbol,
                confidence=signal.confidence
            )
            return True

        # Large position -> AI review
        if signal.suggested_size_pct and signal.suggested_size_pct >= self.position_size_threshold:
            logger.debug(
                "ai_trigger_size",
                symbol=signal.symbol,
                size=signal.suggested_size_pct
            )
            return True

        # Otherwise, skip AI for faster execution
        return False

    async def evaluate(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        portfolio_state: Dict = None,
        force: bool = False
    ) -> AIDecision:
        """
        Evaluate a trading signal with AI.

        Args:
            signal: Signal to evaluate
            snapshot: Current market data
            portfolio_state: Portfolio context
            force: Force evaluation even if cached

        Returns:
            AIDecision with approval/rejection/modification
        """
        # Check cache
        if not force:
            cached = self._cache.get(signal.symbol, signal.strategy)
            if cached:
                logger.debug("ai_cache_hit", symbol=signal.symbol)
                return cached

        # Build context
        context = build_trade_context(signal, snapshot, portfolio_state)

        try:
            # Call AI
            response = await self._client.complete(
                system_prompt=TRADE_ANALYSIS_SYSTEM,
                user_prompt=context,
                use_web_search=self.enable_web_search
            )

            # Parse response
            parsed = parse_ai_response(response['content'])

            # Create decision
            decision = AIDecision(
                signal=signal,
                decision=parsed['decision'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                modifications=parsed['modifications'],
                web_search_used=response.get('web_search_used', False),
                response_time_ms=response.get('response_time_ms', 0)
            )

            # Update stats
            self._decisions_made += 1
            if decision.is_approved:
                self._approvals += 1
            elif decision.is_rejected:
                self._rejections += 1
            else:
                self._modifications += 1

            # Cache
            self._cache.set(signal.symbol, signal.strategy, decision)

            # Emit event
            await self._emit_decision_event(decision)

            logger.info(
                "ai_decision",
                symbol=signal.symbol,
                strategy=signal.strategy,
                decision=decision.decision,
                confidence=decision.confidence,
                response_time_ms=decision.response_time_ms
            )

            return decision

        except AITimeoutError:
            logger.warning("ai_timeout", symbol=signal.symbol)
            # On timeout, approve with low confidence
            return AIDecision(
                signal=signal,
                decision="APPROVE",
                confidence=50,
                reasoning="AI timeout - defaulting to low-confidence approval",
                modifications={},
                web_search_used=False,
                response_time_ms=0
            )

        except AIError as e:
            logger.error("ai_error", symbol=signal.symbol, error=str(e))
            # On error, reject for safety
            return AIDecision(
                signal=signal,
                decision="REJECT",
                confidence=0,
                reasoning=f"AI error: {str(e)}",
                modifications={},
                web_search_used=False,
                response_time_ms=0
            )

    async def evaluate_batch(
        self,
        signals: List[Signal],
        snapshots: Dict[str, MarketSnapshot],
        portfolio_state: Dict = None
    ) -> List[AIDecision]:
        """Evaluate multiple signals concurrently"""
        tasks = []

        for signal in signals:
            snapshot = snapshots.get(signal.symbol)
            if snapshot:
                task = self.evaluate(signal, snapshot, portfolio_state)
                tasks.append(task)

        if tasks:
            return await asyncio.gather(*tasks)
        return []

    async def _emit_decision_event(self, decision: AIDecision) -> None:
        """Emit AI decision event"""
        await self._event_bus.publish(Event(
            type=EventType.AI_DECISION_RESPONSE,
            data={
                'symbol': decision.signal.symbol,
                'strategy': decision.signal.strategy,
                'decision': decision.decision,
                'confidence': decision.confidence,
                'reasoning': decision.reasoning
            },
            source="ai_decision_engine"
        ))

    def apply_modifications(self, signal: Signal, decision: AIDecision) -> Signal:
        """
        Apply AI modifications to a signal.
        Returns modified signal.
        """
        if not decision.is_modified or not decision.modifications:
            return signal

        mods = decision.modifications

        # Create modified signal (copy with updates)
        modified = Signal(
            symbol=signal.symbol,
            direction=signal.direction,
            signal_type=signal.signal_type,
            strategy=signal.strategy,
            timestamp=signal.timestamp,
            confidence=signal.confidence,
            strength=signal.strength,
            entry_price=mods.get('entry', signal.entry_price),
            stop_loss=mods.get('stop_loss', signal.stop_loss),
            take_profit=mods.get('take_profit', signal.take_profit),
            suggested_size_pct=signal.suggested_size_pct,
            reasoning=f"{signal.reasoning} [AI modified: {decision.reasoning}]",
            indicators_used=signal.indicators_used,
            market_context=signal.market_context,
            signal_id=signal.signal_id,
            correlation_id=signal.correlation_id,
            valid_until=signal.valid_until
        )

        # Apply size modifier
        if 'size_multiplier' in mods and modified.suggested_size_pct:
            modified.suggested_size_pct *= mods['size_multiplier']

        return modified

    def clear_cache(self, symbol: str = None) -> None:
        """Clear decision cache"""
        self._cache.clear(symbol)

    @property
    def stats(self) -> Dict:
        """Get engine statistics"""
        return {
            'total_decisions': self._decisions_made,
            'approvals': self._approvals,
            'rejections': self._rejections,
            'modifications': self._modifications,
            'approval_rate': self._approvals / self._decisions_made if self._decisions_made > 0 else 0,
            'client_stats': self._client.stats
        }


# Singleton
_engine: Optional[AIDecisionEngine] = None


def get_decision_engine() -> AIDecisionEngine:
    """Get or create decision engine singleton"""
    global _engine
    if _engine is None:
        _engine = AIDecisionEngine()
    return _engine
