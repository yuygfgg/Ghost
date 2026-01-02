from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api import schemas
from apps.api.deps import get_db, get_principal, require_roles
from packages.core.auth import Role
from packages.db import Category, Resource, ensure_build_state

router = APIRouter(prefix="/categories", tags=["categories"])


def _mark_pending(session: Session, reason: str) -> None:
    state = ensure_build_state(session)
    state.pending_changes = True
    state.pending_reason = reason
    session.add(state)


@router.get("/tree", response_model=list[schemas.CategoryResponse])
def get_tree(session: Session = Depends(get_db), principal=Depends(get_principal)):
    categories = (
        session.query(Category).order_by(Category.root_id, Category.sort_order).all()
    )
    return [schemas.CategoryResponse.model_validate(cat) for cat in categories]


@router.post(
    "", response_model=schemas.CategoryResponse, status_code=status.HTTP_201_CREATED
)
def create_category(
    payload: schemas.CategoryCreate,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER, Role.ADMIN)),
):
    parent = session.get(Category, payload.parent_id) if payload.parent_id else None
    category = Category(
        name=payload.name,
        slug=payload.slug,
        parent_id=payload.parent_id,
        root_id=parent.root_id if parent else 0,
        sort_order=payload.sort_order,
    )
    session.add(category)
    session.flush()
    if category.root_id == 0:
        category.root_id = category.id
    _mark_pending(session, "Category created")
    session.commit()
    session.refresh(category)
    return schemas.CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=schemas.CategoryResponse)
def update_category(
    category_id: int,
    payload: schemas.CategoryUpdate,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER, Role.ADMIN)),
):
    category = session.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    if payload.name is not None:
        category.name = payload.name
    if payload.slug is not None:
        category.slug = payload.slug
    if payload.sort_order is not None:
        category.sort_order = payload.sort_order
    if payload.parent_id is not None and payload.parent_id != category.parent_id:
        parent = session.get(Category, payload.parent_id) if payload.parent_id else None
        if payload.parent_id and not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Parent not found"
            )
        category.parent_id = payload.parent_id
        category.root_id = parent.root_id if parent else category.id
    _mark_pending(session, "Category updated")
    session.commit()
    session.refresh(category)
    return schemas.CategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER, Role.ADMIN)),
):
    category = session.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    children_count = (
        session.query(Category).filter(Category.parent_id == category_id).count()
    )
    if children_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Category not empty"
        )
    has_resource = (
        session.query(Resource).filter(Resource.category_id == category_id).first()
    )
    if has_resource:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Category in use"
        )
    session.delete(category)
    _mark_pending(session, "Category deleted")
    session.commit()
    return None
