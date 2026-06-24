from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class NotificationConfig(BaseModel):
    max_items_per_message: int = 10


class FilterNormalizationConfig(BaseModel):
    remove_accents: bool = True


class DirectThesisFilterConfig(BaseModel):
    enabled: bool = True
    min_score: int = 0
    require_anchor: bool = True


class MethodologicalAnalogFilterConfig(BaseModel):
    enabled: bool = True
    min_score: int = 0
    min_methodological_terms: int = 3
    require_geoscience_context: bool = True


class FiltersConfig(BaseModel):
    enabled: bool = False
    normalize: FilterNormalizationConfig = Field(default_factory=FilterNormalizationConfig)
    direct_thesis: DirectThesisFilterConfig = Field(default_factory=DirectThesisFilterConfig)
    methodological_analog: MethodologicalAnalogFilterConfig = Field(default_factory=MethodologicalAnalogFilterConfig)
    regional_keywords: list[str] = Field(default_factory=list)
    temporal_keywords: list[str] = Field(default_factory=list)
    methodological_keywords: list[str] = Field(default_factory=list)
    geoscience_context_keywords: list[str] = Field(default_factory=list)
    preferred_venues: list[str] = Field(default_factory=list)
    preferred_authors: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    enabled: bool = True
    lookback_days: int = 3


class AppConfig(BaseModel):
    max_results_per_source: int = 20
    languages_priority: list[str] = Field(default_factory=lambda: ["en", "pt"])
    queries: list[str] = Field(default_factory=list)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)

    def get_source_config(self, source_name: str) -> SourceConfig:
        return self.sources.get(source_name, SourceConfig())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return AppConfig.model_validate(data)
