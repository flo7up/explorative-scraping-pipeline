import json
import logging

import azure.functions as func

from src.pipeline.agents.discovery_agent import screen_sources
from src.pipeline.config import load_config

bp = func.Blueprint()
logger = logging.getLogger(__name__)


@bp.route(route="screen-sources", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def http_screen_sources(req: func.HttpRequest) -> func.HttpResponse:
    try:
        config = load_config()
        body = req.get_json() if req.get_body() else {}
        urls = body.get("urls") or config.sourceDiscovery.seedUrls
        max_links = int(body.get("maxLinks") or config.sourceDiscovery.maxLinksPerSource)
        queries = body.get("queries") if "queries" in body else None
        search_provider = body.get("searchProvider") or None
        search_diagnostics: list[dict] = []
        queued = [
            candidate.model_dump()
            for candidate in screen_sources(
                urls,
                max_links,
                config,
                search_queries=queries,
                search_provider=search_provider,
                search_diagnostics=search_diagnostics,
            )
        ]

        payload = {"queued": queued, "count": len(queued)}
        if search_diagnostics:
            payload["searchDiagnostics"] = search_diagnostics
        return func.HttpResponse(json.dumps(payload), mimetype="application/json")
    except Exception as exc:
        logger.exception("Source screening failed: %s", exc)
        return func.HttpResponse(json.dumps({"error": str(exc)}), status_code=500, mimetype="application/json")
