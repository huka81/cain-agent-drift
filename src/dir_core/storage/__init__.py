"""
dir_core.storage — pluggable persistence layer for DIR modules.

Quick start::

    from dir_core.storage import sqlite_storage, memory_storage

    # All modules backed by a single SQLite file
    stores = sqlite_storage("data/my_app.db")
    registry = AgentRegistry(storage=stores.agent_registry)
    context  = ContextStore(storage=stores.context)

    # Fully in-memory (great for unit tests)
    stores = memory_storage()

Custom backend example::

    from dir_core.storage.base import AgentRegistryStorage

    class MyPostgresAgentStorage:
        def init_schema(self) -> None: ...
        def upsert_agent(self, agent_id, contract_json, priority,
                         status, agent_version, session_token) -> None: ...
        # ... implement all methods of AgentRegistryStorage

    registry = AgentRegistry(storage=MyPostgresAgentStorage())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .base import (
    AgentRegistryStorage,
    AuditStore,
    ContextStorage,
    DecisionAuditStorage,
    DecisionLedgerStorage,
    EscalationStorage,
    IdempotencyStorage,
    IntentRetryStorage,
    LifecycleStorage,
    ResourceContentionError,
    ResourceLockStorage,
    SagaStorage,
    StorageError,
)
from .memory import (
    MemoryAgentRegistryStorage,
    MemoryContextStorage,
    MemoryDecisionAuditStorage,
    MemoryDecisionLedgerStorage,
    MemoryEscalationStorage,
    MemoryIdempotencyStorage,
    MemoryIntentRetryStorage,
    MemoryLifecycleStorage,
    MemoryResourceLockStorage,
    MemorySagaStorage,
)
from .json_util import dumps_json_dict
from .sqlite import (
    SqliteAgentRegistryStorage,
    SqliteConnectionOptions,
    SqliteContextStorage,
    SqliteDecisionAuditStorage,
    SqliteDecisionLedgerStorage,
    SqliteEscalationStorage,
    SqliteIdempotencyStorage,
    SqliteIntentRetryStorage,
    SqliteLifecycleStorage,
    SqliteResourceLockStorage,
    SqliteSagaStorage,
    ensure_db,
)


@dataclass
class StorageBundle:
    """Holds one storage backend instance per dir_core module.

    Use :func:`sqlite_storage` or :func:`memory_storage` to obtain a bundle,
    or construct one manually to mix backends.
    """

    agent_registry: AgentRegistryStorage
    context: ContextStorage
    idempotency: IdempotencyStorage
    decision_audit: DecisionAuditStorage
    decision_ledger: DecisionLedgerStorage
    saga: SagaStorage
    resource_lock: ResourceLockStorage
    intent_retry: IntentRetryStorage
    escalation: EscalationStorage
    lifecycle: LifecycleStorage


def sqlite_storage(
    db_path: str,
    *,
    connection_options: Optional[SqliteConnectionOptions] = None,
) -> StorageBundle:
    """Return a :class:`StorageBundle` where every module is backed by one SQLite file.

    Args:
        db_path: Path to the SQLite database file (created if absent).
        connection_options: Optional pragmas applied to each connection; defaults
            preserve SQLite's existing connection settings.
    """
    return StorageBundle(
        agent_registry=SqliteAgentRegistryStorage(db_path, connection_options),
        context=SqliteContextStorage(db_path, connection_options),
        idempotency=SqliteIdempotencyStorage(db_path, connection_options),
        decision_audit=SqliteDecisionAuditStorage(db_path, connection_options),
        decision_ledger=SqliteDecisionLedgerStorage(db_path, connection_options),
        saga=SqliteSagaStorage(db_path, connection_options),
        resource_lock=SqliteResourceLockStorage(db_path, connection_options),
        intent_retry=SqliteIntentRetryStorage(db_path, connection_options),
        escalation=SqliteEscalationStorage(db_path, connection_options),
        lifecycle=SqliteLifecycleStorage(db_path, connection_options),
    )


def memory_storage() -> StorageBundle:
    """Return a :class:`StorageBundle` backed entirely in process memory.

    No data survives process exit. Useful for tests and ephemeral pipelines.
    """
    return StorageBundle(
        agent_registry=MemoryAgentRegistryStorage(),
        context=MemoryContextStorage(),
        idempotency=MemoryIdempotencyStorage(),
        decision_audit=MemoryDecisionAuditStorage(),
        decision_ledger=MemoryDecisionLedgerStorage(),
        saga=MemorySagaStorage(),
        resource_lock=MemoryResourceLockStorage(),
        intent_retry=MemoryIntentRetryStorage(),
        escalation=MemoryEscalationStorage(),
        lifecycle=MemoryLifecycleStorage(),
    )


__all__ = [
    # Protocols / ABCs
    "AgentRegistryStorage",
    "AuditStore",
    "ContextStorage",
    "DecisionAuditStorage",
    "DecisionLedgerStorage",
    "IdempotencyStorage",
    "SagaStorage",
    "ResourceLockStorage",
    "IntentRetryStorage",
    "EscalationStorage",
    "LifecycleStorage",
    # Exceptions
    "StorageError",
    "ResourceContentionError",
    # SQLite helpers
    "ensure_db",
    "SqliteConnectionOptions",
    "dumps_json_dict",
    # SQLite backends
    "SqliteAgentRegistryStorage",
    "SqliteContextStorage",
    "SqliteDecisionAuditStorage",
    "SqliteDecisionLedgerStorage",
    "SqliteIdempotencyStorage",
    "SqliteSagaStorage",
    "SqliteResourceLockStorage",
    "SqliteIntentRetryStorage",
    "SqliteEscalationStorage",
    "SqliteLifecycleStorage",
    # Memory backends
    "MemoryAgentRegistryStorage",
    "MemoryContextStorage",
    "MemoryDecisionAuditStorage",
    "MemoryDecisionLedgerStorage",
    "MemoryIdempotencyStorage",
    "MemorySagaStorage",
    "MemoryResourceLockStorage",
    "MemoryIntentRetryStorage",
    "MemoryEscalationStorage",
    "MemoryLifecycleStorage",
    # Bundles & factories
    "StorageBundle",
    "sqlite_storage",
    "memory_storage",
]
