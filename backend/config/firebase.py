from collections.abc import Mapping
from functools import partial
from typing import Annotated, Any, cast

import firebase_admin
from fastapi import Depends, Request
from firebase_admin import auth, credentials, messaging
from starlette.concurrency import run_in_threadpool

from backend.config.settings import Settings, get_settings

FIREBASE_APP_NAME = "nutrifood"


class FirebaseService:
    """Async facade over the synchronous Firebase Admin SDK."""

    def __init__(self, app: object) -> None:
        self._app = app
        self._closed = False

    async def verify_id_token(self, id_token: str) -> Mapping[str, Any]:
        """Verify signature, standard claims, account status, and revocation."""
        verify_token = partial(
            auth.verify_id_token,
            id_token,
            app=self._app,
            check_revoked=True,
        )
        return cast(Mapping[str, Any], await run_in_threadpool(verify_token))

    async def send(self, message: messaging.Message, *, dry_run: bool = False) -> str:
        """Send an FCM message without blocking the application's event loop."""
        send_message = partial(
            messaging.send,
            message,
            dry_run=dry_run,
            app=self._app,
        )
        return cast(str, await run_in_threadpool(send_message))

    async def send_notification(
        self,
        *,
        fid: str,
        title: str,
        body: str,
        data: Mapping[str, str] | None = None,
        image_url: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """Build and send a notification to one Firebase installation."""
        message = messaging.Message(
            fid=fid,
            notification=messaging.Notification(
                title=title,
                body=body,
                image=image_url,
            ),
            data=dict(data) if data is not None else None,
        )
        return await self.send(message, dry_run=dry_run)

    def close(self) -> None:
        """Release the Firebase app owned by this service."""
        if self._closed:
            return
        firebase_admin.delete_app(self._app)
        self._closed = True


def create_firebase_service(settings: Settings | None = None) -> FirebaseService:
    """Initialize an isolated Firebase app from configured or default credentials."""
    resolved_settings = settings or get_settings()
    credential = (
        credentials.Certificate(str(resolved_settings.firebase_credentials_path))
        if resolved_settings.firebase_credentials_path is not None
        else credentials.ApplicationDefault()
    )
    options = (
        {"projectId": resolved_settings.firebase_project_id}
        if resolved_settings.firebase_project_id is not None
        else None
    )
    app = firebase_admin.initialize_app(
        credential=credential,
        options=options,
        name=FIREBASE_APP_NAME,
    )
    return FirebaseService(app)


def get_firebase_service(request: Request) -> FirebaseService:
    return cast(FirebaseService, request.app.state.firebase_service)


FirebaseServiceDependency = Annotated[
    FirebaseService,
    Depends(get_firebase_service),
]
