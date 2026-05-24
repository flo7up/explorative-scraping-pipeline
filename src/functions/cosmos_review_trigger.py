import logging

import azure.functions as func

from src.pipeline.agents.review_agent import review_item
from src.pipeline.config import load_config

bp = func.Blueprint()
logger = logging.getLogger(__name__)


@bp.cosmos_db_trigger(
    arg_name="documents",
    database_name="%COSMOS_DATABASE_NAME%",
    container_name="ReviewQueue",
    connection="CosmosDBConnection",
    lease_container_name="ReviewQueueLeases",
    create_lease_container_if_not_exists=True,
)
def cosmos_review_trigger(documents: func.DocumentList) -> None:
    config = load_config()
    for document in documents:
        item = dict(document)
        try:
            review_item(item, config)
        except Exception as exc:
            logger.exception("Review failed: %s", exc)
