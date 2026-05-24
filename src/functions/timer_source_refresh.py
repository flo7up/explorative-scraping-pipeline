import logging

import azure.functions as func

from src.pipeline.agents.discovery_agent import screen_sources
from src.pipeline.config import load_config
from src.pipeline.source_registry import due_source_pages

bp = func.Blueprint()
logger = logging.getLogger(__name__)


@bp.timer_trigger(schedule="%SOURCE_REFRESH_CRON%", arg_name="timer", run_on_startup=False, use_monitor=True)
def timer_source_refresh(timer: func.TimerRequest) -> None:
    config = load_config()
    for source in due_source_pages(limit=10):
        try:
            screen_sources(
                [source["url"]],
                config.sourceDiscovery.maxLinksPerSource,
                config,
                search_queries=[],
                search_provider="none",
            )
        except Exception as exc:
            logger.exception("Scheduled source refresh failed for %s: %s", source.get("url"), exc)
