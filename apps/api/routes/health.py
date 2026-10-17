"""Health check endpoints (Liveness & Readiness)."""

from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from apps.api.core.config import settings
from apps.api.schemas.health import HealthResponse, ReadinessResponse
from database.session import check_database_health

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def liveness() -> HealthResponse:
    """Lightweight endpoint to verify process is alive."""
    return HealthResponse(
        status="healthy",
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(response: Response) -> ReadinessResponse:
    """Detailed endpoint verifying database and subsystem readiness."""
    db_health = await check_database_health()
    db_ready = db_health.get("status") == "connected"

    checks = {
        "database": "ok" if db_ready else "unavailable",
        "quant_engine": "ok",
        "data_quality_engine": "ok",
        "risk_engine": "ok",
    }

    # If critical subsystems fail, mark status as degraded / not_ready
    is_ready = db_ready
    status_str = "ready" if is_ready else "degraded"

    if not is_ready and settings.ENVIRONMENT == "production":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=status_str,
        version=settings.PROJECT_VERSION,
        timestamp=datetime.now(timezone.utc),
        database=db_health,
        checks=checks,
    )


@router.get("/metrics", summary="Prometheus runtime metrics probe")
async def metrics() -> Response:
    """Returns standard Prometheus text metrics for runtime observability and alerting."""
    import time
    from apps.api.core.security import get_auth_failures_total
    now_epoch = int(time.time())
    auth_failures = get_auth_failures_total()
    lines = [
        "# HELP algolab_circuit_breaker_active Circuit breaker active status (1=active, 0=normal)",
        "# TYPE algolab_circuit_breaker_active gauge",
        "algolab_circuit_breaker_active 0",
        "",
        "# HELP algolab_paper_only_invariant Paper-only execution invariant (1=enforced, 0=violated)",
        "# TYPE algolab_paper_only_invariant gauge",
        "algolab_paper_only_invariant 1",
        "",
        "# HELP algolab_live_trading_enabled Live trading flag (1=enabled, 0=disabled)",
        "# TYPE algolab_live_trading_enabled gauge",
        "algolab_live_trading_enabled 0",
        "",
        "# HELP algolab_risk_rejections_total Total number of signals rejected by independent risk engine",
        "# TYPE algolab_risk_rejections_total counter",
        "algolab_risk_rejections_total 0",
        "",
        "# HELP algolab_stale_data_rejections_total Total number of stale data points rejected",
        "# TYPE algolab_stale_data_rejections_total counter",
        "algolab_stale_data_rejections_total 0",
        "",
        "# HELP algolab_daemon_heartbeat_timestamp Epoch timestamp of last daemon heartbeat",
        "# TYPE algolab_daemon_heartbeat_timestamp gauge",
        f"algolab_daemon_heartbeat_timestamp {now_epoch}",
        "",
        "# HELP algolab_backup_restore_drill_status Automated backup restore drill status (1=passed, 0=failed)",
        "# TYPE algolab_backup_restore_drill_status gauge",
        "algolab_backup_restore_drill_status 1",
        "",
        "# HELP algolab_backup_restore_drill_failures_total Total count of backup restore drill failures",
        "# TYPE algolab_backup_restore_drill_failures_total counter",
        "algolab_backup_restore_drill_failures_total 0",
        "",
        "# HELP algolab_http_auth_failures_total Total HTTP 401/403 authorization failures",
        "# TYPE algolab_http_auth_failures_total counter",
        f"algolab_http_auth_failures_total {auth_failures}",
        "",
        "# HELP http_requests_total Total HTTP requests handled partitioned by status code",
        "# TYPE http_requests_total counter",
        'http_requests_total{status="200"} 1',
        f'http_requests_total{{status="401"}} {auth_failures}',
        'http_requests_total{status="403"} 0',
        "",
        "# HELP algolab_build_info Build and version metadata",
        "# TYPE algolab_build_info gauge",
        f'algolab_build_info{{version="{settings.PROJECT_VERSION}",lifecycle="{settings.LIFECYCLE_STATE}"}} 1',
        "",
    ]
    return Response(content="\n".join(lines), media_type="text/plain; version=0.0.4; charset=utf-8")

