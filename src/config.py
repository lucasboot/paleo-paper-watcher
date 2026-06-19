from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class SourceConfig(BaseModel):
    enabled: bool = True
    lookback_days: int = 30
    max_results: int = 25


class AppConfig(BaseModel):
    queries: list[str] = Field(default_factory=list)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)

    def get_source_config(self, source_name: str) -> SourceConfig:
        return self.sources.get(source_name, SourceConfig())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return AppConfig.model_validate(data)
