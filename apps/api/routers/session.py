from fastapi import APIRouter, Depends

from apps.api import schemas
from apps.api.deps import get_principal

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/verify", response_model=schemas.VerifyResponse)
def verify_session(principal=Depends(get_principal)) -> schemas.VerifyResponse:
    return schemas.VerifyResponse(
        token_hash=principal.token_hash,
        role=principal.role,
        display_name=principal.display_name,
        scope_team_id=principal.scope_team_id,
    )
