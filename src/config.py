from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class NotificationConfig(BaseModel):
    max_items_per_message: int = 10


class OpenAIConfig(BaseModel):
    enabled: bool = True
    model: str = "gpt-5-nano"
    summary_language: str = "pt-BR"
    max_summaries_per_run: int = 0
    reasoning_effort: str = "low"
    max_output_tokens: int = 1200


class SourceConfig(BaseModel):
    enabled: bool = True
    lookback_days: int = 3


class AppConfig(BaseModel):
    max_results_per_source: int = 20
    languages_priority: list[str] = Field(default_factory=lambda: ["en", "pt"])
    queries: list[str] = Field(default_factory=list)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)

    def get_source_config(self, source_name: str) -> SourceConfig:
        return self.sources.get(source_name, SourceConfig())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return AppConfig.model_validate(data)
