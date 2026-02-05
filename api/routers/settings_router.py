"""
Settings router - GET/PATCH all configuration parameters.
"""
import os
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from config.settings import get_settings, reload_settings
from api.schemas.models import SettingsCategory, SettingsUpdate, SettingsResponse

router = APIRouter()
settings = get_settings()


def _settings_to_dict(settings_obj) -> Dict[str, Any]:
    """Convert settings object to dict, masking sensitive values"""
    result = {}
    for key, value in settings_obj.model_dump().items():
        # Mask API keys and secrets
        if 'key' in key.lower() or 'secret' in key.lower() or 'password' in key.lower():
            result[key] = "***" if value else ""
        else:
            result[key] = value
    return result


@router.get("", response_model=SettingsResponse)
async def get_all_settings():
    """Get all settings grouped by category"""
    s = get_settings()
    return {
        "alpaca": _settings_to_dict(s.alpaca),
        "anthropic": _settings_to_dict(s.anthropic),
        "scanner": _settings_to_dict(s.scanner),
        "position_sizing": _settings_to_dict(s.position_sizing),
        "stops": _settings_to_dict(s.stops),
        "portfolio": _settings_to_dict(s.portfolio),
        "ai": _settings_to_dict(s.ai),
        "trading_hours": _settings_to_dict(s.trading_hours),
        "crypto": _settings_to_dict(s.crypto),
        "hft": _settings_to_dict(s.hft),
        "dashboard": _settings_to_dict(s.dashboard),
    }


@router.get("/{category}")
async def get_category_settings(category: SettingsCategory):
    """Get settings for a specific category"""
    s = get_settings()

    category_map = {
        SettingsCategory.ALPACA: s.alpaca,
        SettingsCategory.ANTHROPIC: s.anthropic,
        SettingsCategory.SCANNER: s.scanner,
        SettingsCategory.POSITION_SIZING: s.position_sizing,
        SettingsCategory.STOPS: s.stops,
        SettingsCategory.PORTFOLIO: s.portfolio,
        SettingsCategory.AI: s.ai,
        SettingsCategory.TRADING_HOURS: s.trading_hours,
        SettingsCategory.CRYPTO: s.crypto,
        SettingsCategory.HFT: s.hft,
        SettingsCategory.DASHBOARD: s.dashboard,
    }

    if category not in category_map:
        raise HTTPException(status_code=404, detail=f"Category {category} not found")

    return _settings_to_dict(category_map[category])


@router.patch("/{category}")
async def update_category_settings(category: SettingsCategory, update: SettingsUpdate):
    """
    Update settings for a category.
    Note: Changes are applied to environment variables and require reload.
    """
    prefix_map = {
        SettingsCategory.ALPACA: "ALPACA_",
        SettingsCategory.ANTHROPIC: "ANTHROPIC_",
        SettingsCategory.SCANNER: "SCANNER_",
        SettingsCategory.POSITION_SIZING: "SIZING_",
        SettingsCategory.STOPS: "STOP_",
        SettingsCategory.PORTFOLIO: "PORTFOLIO_",
        SettingsCategory.AI: "AI_",
        SettingsCategory.TRADING_HOURS: "HOURS_",
        SettingsCategory.CRYPTO: "CRYPTO_",
        SettingsCategory.HFT: "HFT_",
        SettingsCategory.DASHBOARD: "DASHBOARD_",
    }

    prefix = prefix_map.get(category)
    if not prefix:
        raise HTTPException(status_code=404, detail=f"Category {category} not found")

    # Update env vars
    for key, value in update.settings.items():
        env_key = f"{prefix}{key.upper()}"

        # Skip secret fields
        if 'key' in key.lower() or 'secret' in key.lower():
            if value == "***":
                continue

        # Convert value to string for env
        if isinstance(value, bool):
            os.environ[env_key] = str(value).lower()
        elif isinstance(value, list):
            os.environ[env_key] = ",".join(str(v) for v in value)
        else:
            os.environ[env_key] = str(value)

    # Reload settings
    reload_settings()

    return {"status": "updated", "category": category.value}


@router.post("/reload")
async def reload_all_settings():
    """Force reload all settings from environment"""
    reload_settings()
    return {"status": "reloaded"}
