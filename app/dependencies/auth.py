
from typing import Optional, Sequence

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.constants import ALL_ROLES, ROLE_ADMIN
from app.utils.security import decode_access_token


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Return the authenticated user if a valid token exists.
    Public pages may use this dependency without requiring login.
    """
    token = None

    auth_header = request.headers.get("Authorization", "")

    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    payload = decode_access_token(token)

    if not payload:
        return None

    user_id = payload.get("sub")

    if not user_id or not str(user_id).isdigit():
        return None

    user = (
        db.query(User)
        .filter(User.id == int(user_id))
        .first()
    )

    if user is None or user.status != "Active":
        return None

    # Never trust the role stored inside a potentially stale token.
    # Read the current role from the database instead.
    return user


def _is_html_request(request: Request) -> bool:
    """Determine whether the request is intended to render a webpage."""
    accept = request.headers.get("accept", "")
    return (
        "text/html" in accept.lower()
        and not request.url.path.startswith("/api/")
    )


def get_current_user(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Require an authenticated user."""
    if current_user is None:
        if _is_html_request(request):
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={
                    "Location": f"/login?next={request.url.path}"
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return current_user


def require_role(allowed_roles: Sequence[str]):
    """
    Create a dependency that restricts access to specified user roles.

    Example:
        Depends(require_role(["admin"]))
    """
    allowed = {role.strip().lower() for role in allowed_roles}

    invalid_roles = allowed - set(ALL_ROLES)

    if invalid_roles:
        raise ValueError(
            f"Unknown role(s) configured: {sorted(invalid_roles)}"
        )

    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        current_role = (current_user.role or "").lower()

        if current_role not in allowed:
            if _is_html_request(request):
                destination = (
                    "/admin/login?error=Access+denied"
                    if ROLE_ADMIN in allowed
                    else "/login?error=Access+denied"
                )

                raise HTTPException(
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={"Location": destination},
                )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        return current_user

    return role_checker
