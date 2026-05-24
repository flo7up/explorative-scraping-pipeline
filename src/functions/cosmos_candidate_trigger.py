import logging

import azure.functions as func

from src.pipeline.agents.extraction_agent import process_candidate
from src.pipeline.config import load_config

bp = func.Blueprint()
logger = logging.getLogger(__name__)


@bp.cosmos_db_trigger(
    arg_name="documents",
    database_name="%COSMOS_DATABASE_NAME%",
    container_name="CandidateQueue",
    connection="CosmosDBConnection",
    lease_container_name="CandidateQueueLeases",
    create_lease_container_if_not_exists=True,
)
def cosmos_candidate_trigger(documents: func.DocumentList) -> None:
    config = load_config()
    for document in documents:
        candidate = dict(document)
        try:
            process_candidate(candidate, config)
        except Exception as exc:
            logger.exception("Candidate processing failed: %s", exc)
