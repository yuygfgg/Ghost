from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from apps.api import schemas
from apps.api.deps import get_principal, get_db, require_roles
from packages.core.auth import Role
from packages.db import ensure_build_state
from packages.worker.build import run_build_pipeline

router = APIRouter(prefix="/build", tags=["build"])


@router.get("/status", response_model=schemas.BuildStateResponse)
def get_status(session: Session = Depends(get_db), principal=Depends(get_principal)):
    state = ensure_build_state(session)
    return schemas.BuildStateResponse.model_validate(state)


@router.post("/trigger", response_model=schemas.BuildStateResponse)
def trigger_build(
    background: BackgroundTasks,
    reason: str | None = None,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.ADMIN)),
) -> schemas.BuildStateResponse:
    state = ensure_build_state(session)
    state.pending_changes = True
    state.pending_reason = reason or "Manual trigger"
    state.last_error = None
    session.add(state)
    session.commit()
    session.refresh(state)
    # Run build in background to avoid blocking request.
    background.add_task(run_build_pipeline, True)
    return schemas.BuildStateResponse.model_validate(state)
