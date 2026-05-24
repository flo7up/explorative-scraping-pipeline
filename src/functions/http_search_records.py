import json

import azure.functions as func

from src.pipeline import cosmos

bp = func.Blueprint()

PUBLIC_RECORD_FIELDS = [
    "id",
    "PartitionKey",
    "recordType",
    "title",
    "summary",
    "sourceUrl",
    "organization",
    "useCaseType",
    "industry",
    "technologies",
    "rawFields",
    "normalizedSourceUrl",
    "sourceUrlHash",
    "embeddingProfile",
    "embeddingStatus",
    "duplicateReview",
    "groundedness",
    "status",
    "confidence",
    "createdAt",
    "updatedAt",
]


def _parse_limit(value: str | None) -> int:
    if not value:
        return 25
    try:
        limit = int(value)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if limit < 1:
        raise ValueError("limit must be greater than 0")
    return min(limit, 100)


def _include_embedding(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _select_clause(include_embedding: bool) -> str:
    fields = PUBLIC_RECORD_FIELDS + (["embedding"] if include_embedding else [])
    return ", ".join(f"c.{field}" for field in fields)


@bp.route(route="records", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def http_search_records(req: func.HttpRequest) -> func.HttpResponse:
    try:
        query = (req.params.get("q") or "").strip()
        limit = _parse_limit(req.params.get("limit"))
    except ValueError as exc:
        return func.HttpResponse(json.dumps({"error": str(exc)}), status_code=400, mimetype="application/json")

    select_clause = _select_clause(_include_embedding(req.params.get("includeEmbedding")))

    if query:
        sql = f"SELECT TOP @limit {select_clause} FROM c WHERE c.PartitionKey = @pk AND (CONTAINS(c.title, @q, true) OR CONTAINS(c.summary, @q, true))"
        params = [
            {"name": "@limit", "value": limit},
            {"name": "@pk", "value": "record"},
            {"name": "@q", "value": query},
        ]
    else:
        sql = f"SELECT TOP @limit {select_clause} FROM c WHERE c.PartitionKey = @pk"
        params = [{"name": "@limit", "value": limit}, {"name": "@pk", "value": "record"}]

    items = cosmos.query("records", sql, parameters=params, enable_cross_partition_query=False, partition_key="record")
    return func.HttpResponse(json.dumps({"items": items, "count": len(items)}), mimetype="application/json")
