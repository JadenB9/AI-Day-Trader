"""
Connection testing utilities for Alpaca and Claude APIs.
Run these tests before starting the trading engine.
"""
import asyncio
from typing import Dict, Any, Tuple
from datetime import datetime
import structlog

from config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


async def test_alpaca_connection() -> Tuple[bool, Dict[str, Any]]:
    """
    Test Alpaca API connection and return account info.

    Returns:
        Tuple of (success, result_dict)
    """
    from src.execution.alpaca_broker import get_broker

    try:
        broker = get_broker()
        account = await broker.get_account()

        result = {
            "connected": True,
            "equity": account['equity'],
            "cash": account['cash'],
            "buying_power": account['buying_power'],
            "trading_blocked": account.get('trading_blocked', False),
            "mode": settings.alpaca.trading_mode.value,
            "timestamp": datetime.now().isoformat()
        }

        logger.info("alpaca_connection_ok", **result)
        return True, result

    except Exception as e:
        result = {
            "connected": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        logger.error("alpaca_connection_failed", error=str(e))
        return False, result


async def test_claude_connection() -> Tuple[bool, Dict[str, Any]]:
    """
    Test Claude API connection with a simple request.

    Returns:
        Tuple of (success, result_dict)
    """
    from src.ai.claude_client import get_claude_client

    try:
        client = get_claude_client()

        # Simple test message
        response = await client.complete(
            system_prompt="You are a helpful assistant.",
            user_prompt="Reply with just 'OK' to confirm the connection works.",
            use_web_search=False,
            max_tokens=10
        )

        result = {
            "connected": True,
            "model": settings.anthropic.model,
            "tokens_used": response.get('tokens_used', 0),
            "response_time_ms": response.get('response_time_ms', 0),
            "web_search_enabled": settings.ai.enable_web_search,
            "timestamp": datetime.now().isoformat()
        }

        logger.info("claude_connection_ok", **result)
        return True, result

    except Exception as e:
        result = {
            "connected": False,
            "error": str(e),
            "model": settings.anthropic.model,
            "timestamp": datetime.now().isoformat()
        }
        logger.error("claude_connection_failed", error=str(e))
        return False, result


async def test_claude_web_search() -> Tuple[bool, Dict[str, Any]]:
    """
    Test Claude API with web search enabled.

    Returns:
        Tuple of (success, result_dict)
    """
    from src.ai.claude_client import get_claude_client

    if not settings.ai.enable_web_search:
        return True, {"skipped": True, "reason": "Web search disabled in settings"}

    try:
        client = get_claude_client()

        # Test with web search
        response = await client.complete(
            system_prompt="You are a financial analyst.",
            user_prompt="What is the current price of SPY? Just give the number.",
            use_web_search=True,
            max_tokens=50
        )

        result = {
            "connected": True,
            "web_search_working": True,
            "tokens_used": response.get('tokens_used', 0),
            "response_time_ms": response.get('response_time_ms', 0),
            "response_preview": response.get('content', '')[:100],
            "timestamp": datetime.now().isoformat()
        }

        logger.info("claude_web_search_ok", **result)
        return True, result

    except Exception as e:
        result = {
            "connected": False,
            "web_search_working": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        logger.error("claude_web_search_failed", error=str(e))
        return False, result


async def test_all_connections() -> Dict[str, Any]:
    """
    Run all connection tests.

    Returns:
        Full test results dict
    """
    logger.info("starting_connection_tests")

    # Run tests
    alpaca_ok, alpaca_result = await test_alpaca_connection()
    claude_ok, claude_result = await test_claude_connection()

    # Only test web search if basic Claude works
    if claude_ok and settings.ai.enable_web_search:
        web_ok, web_result = await test_claude_web_search()
    else:
        web_ok, web_result = True, {"skipped": True}

    all_ok = alpaca_ok and claude_ok

    results = {
        "all_passed": all_ok,
        "alpaca": alpaca_result,
        "claude": claude_result,
        "claude_web_search": web_result,
        "timestamp": datetime.now().isoformat()
    }

    if all_ok:
        logger.info("all_connection_tests_passed")
    else:
        logger.error("connection_tests_failed", results=results)

    return results


def run_connection_tests() -> Dict[str, Any]:
    """Synchronous wrapper for running connection tests"""
    return asyncio.run(test_all_connections())
