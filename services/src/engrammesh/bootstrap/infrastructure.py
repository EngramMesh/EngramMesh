"""Default bootstrap implementations for memory application ports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import final
from uuid import uuid4

from engrammesh.bootstrap.auth.context import current_principal
from engrammesh.bootstrap.auth.ports import TokenVerifierPort
from engrammesh.bootstrap.auth.token_verifiers import (
    JwksTokenVerifier,
    StaticDevTokenVerifier,
)
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError, Environment
from engrammesh.modules.memory.application.process_inbox_event import (
    ProcessInboxEventHandler,
)
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    MemoryAuthorizationPort,
    OutboxEventPublisher,
)
from engrammesh.modules.runtime.ports import (
    RuntimeAuthorizationPort,
    RuntimeAuthorizationRequest,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import EventId, ExecutionId, MemoryId


@final
class SystemUtcClock:
    async def now(self) -> datetime:
        return datetime.now(UTC)


@final
class UuidMemoryIdentityPort:
    async def new_memory_id(self) -> MemoryId:
        return MemoryId(uuid4())

    async def new_event_id(self) -> EventId:
        return EventId(uuid4())


@final
class LoggingOutboxEventPublisher:
    """In-process publisher that records dispatched events for tests."""

    __slots__ = ("_published",)

    def __init__(self) -> None:
        self._published: list[EventEnvelope] = []

    @property
    def published(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._published)

    async def publish(self, event: EventEnvelope) -> None:
        self._published.append(event)


@final
class InboxOutboxEventPublisher:
    """Dispatch outbox events through inbox processing then a delegate."""

    __slots__ = ("_delegate", "_inbox_handler")

    def __init__(
        self,
        *,
        inbox_handler: ProcessInboxEventHandler,
        delegate: OutboxEventPublisher,
    ) -> None:
        self._inbox_handler = inbox_handler
        self._delegate = delegate

    async def publish(self, event: EventEnvelope) -> None:
        await self._inbox_handler.handle(event)
        await self._delegate.publish(event)


@final
class EnvironmentGatedMemoryAuthorization:
    __slots__ = ("_environment",)

    def __init__(self, environment: Environment) -> None:
        self._environment = environment

    async def authorize(self, request: AuthorizationRequest) -> bool:
        del request
        return self._environment in {
            Environment.DEVELOPMENT,
            Environment.TEST,
        }


@final
class TenantScopedMemoryAuthorization:
    async def authorize(self, request: AuthorizationRequest) -> bool:
        principal = current_principal()
        return (
            request.actor_id == principal.actor_id
            and request.scope.tenant_id == principal.tenant_id
        )


def create_memory_authorization(settings: AppSettings) -> MemoryAuthorizationPort:
    if settings.oidc.enabled:
        return TenantScopedMemoryAuthorization()
    return EnvironmentGatedMemoryAuthorization(settings.environment)


@final
class EnvironmentGatedRuntimeAuthorization:
    __slots__ = ("_environment",)

    def __init__(self, environment: Environment) -> None:
        self._environment = environment

    async def authorize(self, request: RuntimeAuthorizationRequest) -> bool:
        del request
        return self._environment in {
            Environment.DEVELOPMENT,
            Environment.TEST,
        }


@final
class TenantScopedRuntimeAuthorization:
    async def authorize(self, request: RuntimeAuthorizationRequest) -> bool:
        principal = current_principal()
        return (
            request.actor_id == principal.actor_id
            and request.scope.tenant_id == principal.tenant_id
        )


@final
class UuidRuntimeIdentityPort:
    async def new_execution_id(self) -> ExecutionId:
        return ExecutionId(uuid4())


def create_runtime_authorization(settings: AppSettings) -> RuntimeAuthorizationPort:
    if settings.oidc.enabled:
        return TenantScopedRuntimeAuthorization()
    return EnvironmentGatedRuntimeAuthorization(settings.environment)


def create_token_verifier(settings: AppSettings) -> TokenVerifierPort | None:
    oidc = settings.oidc
    if not oidc.enabled:
        return None
    if (
        settings.environment in {Environment.DEVELOPMENT, Environment.TEST}
        and oidc.dev_signing_key is not None
    ):
        return StaticDevTokenVerifier(
            issuer=oidc.issuer or "https://dev.engrammesh.test",
            signing_key=oidc.dev_signing_key.get_secret_value(),
            actor_claim=oidc.actor_claim,
            tenant_claim=oidc.tenant_claim,
            audience=oidc.audience,
        )
    if oidc.jwks_uri:
        return JwksTokenVerifier(
            issuer=oidc.issuer,
            jwks_uri=oidc.jwks_uri,
            actor_claim=oidc.actor_claim,
            tenant_claim=oidc.tenant_claim,
            audience=oidc.audience,
        )
    raise ConfigurationError(
        "oidc_misconfigured",
        "OIDC is enabled but no verifier can be constructed",
    )
