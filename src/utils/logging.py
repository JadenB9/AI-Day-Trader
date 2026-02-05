"""
Structured logging setup using structlog.
"""
import logging
import sys
from pathlib import Path
from typing import Optional
import structlog
from structlog.typing import EventDict


def add_log_level(logger, method_name, event_dict: EventDict) -> EventDict:
    """Add log level to event dict"""
    event_dict["level"] = method_name.upper()
    return event_dict


def setup_logging(
    level: str = "INFO",
    format: str = "json",
    log_file: Optional[str] = None
) -> None:
    """
    Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format ('json' or 'console')
        log_file: Optional file path for logging
    """
    # Ensure log directory exists
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Configure stdlib logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create handlers
    handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        handlers.append(file_handler)

    for handler in handlers:
        root_logger.addHandler(handler)

    # Configure structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if format == "json":
        # JSON format for production
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ]
    else:
        # Console format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance"""
    return structlog.get_logger(name)


# Convenience functions
def log_trade(
    action: str,
    symbol: str,
    quantity: int,
    price: float,
    **kwargs
) -> None:
    """Log trade activity"""
    logger = get_logger("trades")
    logger.info(
        "trade",
        action=action,
        symbol=symbol,
        quantity=quantity,
        price=price,
        **kwargs
    )


def log_signal(
    strategy: str,
    symbol: str,
    direction: str,
    confidence: float,
    **kwargs
) -> None:
    """Log signal generation"""
    logger = get_logger("signals")
    logger.info(
        "signal",
        strategy=strategy,
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        **kwargs
    )


def log_ai_decision(
    symbol: str,
    decision: str,
    reasoning: str,
    **kwargs
) -> None:
    """Log AI decision"""
    logger = get_logger("ai")
    logger.info(
        "ai_decision",
        symbol=symbol,
        decision=decision,
        reasoning=reasoning[:200] if reasoning else "",
        **kwargs
    )


def log_risk_event(
    event_type: str,
    current: float,
    limit: float,
    **kwargs
) -> None:
    """Log risk management event"""
    logger = get_logger("risk")
    logger.warning(
        "risk_event",
        event_type=event_type,
        current=current,
        limit=limit,
        **kwargs
    )
