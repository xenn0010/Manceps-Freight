"""Tenant isolation by construction.

A firm's data lives in its own database `firm_<tenant>`. The only way to obtain that database is
`TenantDb.for_principal`, which reads the tenant from an authenticated `Principal`; there is no API that accepts a
tenant string from a request. Platform collections that hold rows for many firms are reached through `PlatformRepo`,
which injects `tenant_id` into every filter and insert and refuses anything naming another tenant.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, get_args

from .mongo import Doc, MongoClientT, MongoCollection, MongoDb

DB_PREFIX = "firm_"
TENANT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
TENANT_FIELD = "tenant_id"

Role: TypeAlias = Literal["owner", "dispatcher", "viewer", "carrier", "driver", "system"]
PrincipalKind: TypeAlias = Literal["user", "scoped", "system"]
ROLES: frozenset[str] = frozenset(get_args(Role))
PRINCIPAL_KINDS: frozenset[str] = frozenset(get_args(PrincipalKind))

TENANT_SCOPED_COLLECTIONS: frozenset[str] = frozenset({
    "memberships", "invitations", "sessions", "scoped_links", "idempotency_keys",
})
UPDATE_OPERATORS_WITH_FIELDS = ("$set", "$setOnInsert", "$unset", "$rename", "$inc", "$push", "$addToSet")

Sort: TypeAlias = Sequence[tuple[str, int]]


class TenantError(RuntimeError):
    """A tenant id is missing, invalid, or a query tried to cross tenants."""


def validate_tenant_id(tenant_id: str) -> str:
    """Check a tenant id is a safe lowercase slug (same rule as the hermes-freight plugin).

    Args:
        tenant_id: Proposed id, e.g. "apex-freight".

    Returns:
        The id unchanged.

    Raises:
        TenantError: If the id is not 3 to 32 chars of [a-z0-9-] starting with a letter and not ending with '-'.
    """
    if not TENANT_PATTERN.fullmatch(tenant_id):
        raise TenantError(f"invalid tenant id {tenant_id!r}")
    return tenant_id


@dataclass(frozen=True)
class Principal:
    """An authenticated caller. The tenant comes from the verified token, never from request data."""

    user_id: str
    tenant_id: str | None
    role: Role
    session_id: str | None
    kind: PrincipalKind

    def __post_init__(self) -> None:
        """Validate the tenant id, role and kind.

        Raises:
            TenantError: If the tenant id is invalid.
            ValueError: If the role or kind is unknown or the user id is empty.
        """
        if self.tenant_id is not None:
            validate_tenant_id(self.tenant_id)
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")
        if self.kind not in PRINCIPAL_KINDS:
            raise ValueError(f"unknown principal kind {self.kind!r}")
        if not self.user_id:
            raise ValueError("principal user_id is empty")


def _firm_tenant(principal: Principal) -> str:
    """Return the principal's firm id or refuse.

    Args:
        principal: Authenticated caller.

    Returns:
        The validated tenant id.

    Raises:
        TypeError: If given anything other than a Principal.
        TenantError: If the principal has no firm yet.
    """
    if not isinstance(principal, Principal):  # pyright: ignore[reportUnnecessaryIsInstance]  # runtime guard
        raise TypeError("a Principal is required; tenant strings are not accepted")
    if principal.tenant_id is None:
        raise TenantError("this principal has no active firm")
    return validate_tenant_id(principal.tenant_id)


class TenantDb:
    """Hands out firm databases, keyed only by an authenticated principal."""

    def __init__(self, client: MongoClientT) -> None:
        """Wrap a MongoDB client.

        Args:
            client: Shared client for the cluster holding firm databases.
        """
        self._client = client

    def for_principal(self, principal: Principal) -> MongoDb:
        """Return the principal's firm database.

        Args:
            principal: Authenticated caller.

        Returns:
            The `firm_<tenant>` database.

        Raises:
            TypeError: If given anything other than a Principal.
            TenantError: If the principal has no firm or an invalid tenant id.
        """
        tenant_id = _firm_tenant(principal)
        return self._client[DB_PREFIX + tenant_id.replace("-", "_")]


def _check_no_foreign_tenant(value: Any, tenant_id: str) -> None:
    """Walk a filter and refuse any tenant_id condition other than equality with our tenant.

    Args:
        value: Filter (or part of one).
        tenant_id: The repo's tenant.

    Raises:
        TenantError: If another tenant (or an operator on tenant_id) appears.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            if key == TENANT_FIELD and item != tenant_id:
                raise TenantError("query names another tenant")
            _check_no_foreign_tenant(item, tenant_id)
    elif isinstance(value, list | tuple):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            _check_no_foreign_tenant(item, tenant_id)


class PlatformRepo:
    """Platform collections confined to one tenant: tenant_id is injected into every filter and insert."""

    def __init__(self, db: MongoDb, tenant_id: str) -> None:
        """Bind the repo to a tenant.

        Args:
            db: Platform database.
            tenant_id: Tenant to confine every operation to.

        Raises:
            TenantError: If the tenant id is invalid.
        """
        self._db = db
        self.tenant_id = validate_tenant_id(tenant_id)

    @classmethod
    def for_principal(cls, db: MongoDb, principal: Principal) -> PlatformRepo:
        """Build a repo for the principal's firm.

        Args:
            db: Platform database.
            principal: Authenticated caller.

        Returns:
            The repo.

        Raises:
            TypeError: If given anything other than a Principal.
            TenantError: If the principal has no firm.
        """
        return cls(db, _firm_tenant(principal))

    def _collection(self, name: str) -> MongoCollection:
        """Return a tenant-keyed platform collection.

        Args:
            name: Collection name.

        Returns:
            The collection.

        Raises:
            ValueError: If the collection is not tenant-keyed.
        """
        if name not in TENANT_SCOPED_COLLECTIONS:
            raise ValueError(f"platform collection {name!r} is not tenant-scoped")
        return self._db[name]

    def _filter(self, query: Mapping[str, Any]) -> Doc:
        """Return the filter with the tenant injected.

        Args:
            query: Caller's filter.

        Returns:
            A new filter including tenant_id.

        Raises:
            TenantError: If the filter names another tenant.
        """
        _check_no_foreign_tenant(query, self.tenant_id)
        return {**query, TENANT_FIELD: self.tenant_id}

    def _check_update(self, update: Mapping[str, Any]) -> None:
        """Refuse updates that would move or remove the tenant key.

        Args:
            update: Update document.

        Raises:
            TenantError: If tenant_id is modified.
        """
        for operator in UPDATE_OPERATORS_WITH_FIELDS:
            fields = update.get(operator)
            if isinstance(fields, Mapping) and TENANT_FIELD in fields:
                if operator in ("$set", "$setOnInsert") and fields[TENANT_FIELD] == self.tenant_id:
                    continue
                raise TenantError("updates may not change tenant_id")

    def find_one(self, collection: str, query: Mapping[str, Any]) -> Doc | None:
        """Find one document of this tenant.

        Args:
            collection: Collection name.
            query: Filter.

        Returns:
            The document or None.

        Raises:
            TenantError: If the filter names another tenant.
            ValueError: If the collection is not tenant-scoped.
        """
        return self._collection(collection).find_one(self._filter(query))

    def find(self, collection: str, query: Mapping[str, Any], sort: Sort | None = None,
             limit: int = 0) -> list[Doc]:
        """Find documents of this tenant.

        Args:
            collection: Collection name.
            query: Filter.
            sort: Optional sort keys.
            limit: Maximum documents (0 = no limit).

        Returns:
            Matching documents.

        Raises:
            TenantError: If the filter names another tenant.
            ValueError: If the collection is not tenant-scoped.
        """
        cursor = self._collection(collection).find(self._filter(query), limit=limit)
        if sort:
            cursor = cursor.sort(list(sort))
        return list(cursor)

    def count_documents(self, collection: str, query: Mapping[str, Any]) -> int:
        """Count documents of this tenant.

        Args:
            collection: Collection name.
            query: Filter.

        Returns:
            The count.

        Raises:
            TenantError: If the filter names another tenant.
            ValueError: If the collection is not tenant-scoped.
        """
        return self._collection(collection).count_documents(self._filter(query))

    def insert_one(self, collection: str, doc: Mapping[str, Any]) -> Any:
        """Insert a document stamped with this tenant.

        Args:
            collection: Collection name.
            doc: Document.

        Returns:
            The inserted id.

        Raises:
            TenantError: If the document names another tenant.
            ValueError: If the collection is not tenant-scoped.
            pymongo.errors.DuplicateKeyError: On a unique index violation.
        """
        if doc.get(TENANT_FIELD, self.tenant_id) != self.tenant_id:
            raise TenantError("document names another tenant")
        return self._collection(collection).insert_one({**doc, TENANT_FIELD: self.tenant_id}).inserted_id

    def update_one(self, collection: str, query: Mapping[str, Any], update: Mapping[str, Any],
                   upsert: bool = False) -> int:
        """Update one document of this tenant.

        Args:
            collection: Collection name.
            query: Filter.
            update: Update operators.
            upsert: Insert when nothing matches (the tenant is copied from the filter).

        Returns:
            Number of documents matched.

        Raises:
            TenantError: If the filter or update crosses tenants.
            ValueError: If the collection is not tenant-scoped.
        """
        self._check_update(update)
        result = self._collection(collection).update_one(self._filter(query), dict(update), upsert=upsert)
        return result.matched_count

    def update_many(self, collection: str, query: Mapping[str, Any], update: Mapping[str, Any]) -> int:
        """Update every matching document of this tenant.

        Args:
            collection: Collection name.
            query: Filter.
            update: Update operators.

        Returns:
            Number of documents modified.

        Raises:
            TenantError: If the filter or update crosses tenants.
            ValueError: If the collection is not tenant-scoped.
        """
        self._check_update(update)
        return self._collection(collection).update_many(self._filter(query), dict(update)).modified_count

    def delete_one(self, collection: str, query: Mapping[str, Any]) -> int:
        """Delete one document of this tenant.

        Args:
            collection: Collection name.
            query: Filter.

        Returns:
            Number deleted.

        Raises:
            TenantError: If the filter names another tenant.
            ValueError: If the collection is not tenant-scoped.
        """
        return self._collection(collection).delete_one(self._filter(query)).deleted_count

    def delete_many(self, collection: str, query: Mapping[str, Any]) -> int:
        """Delete documents of this tenant.

        Args:
            collection: Collection name.
            query: Filter.

        Returns:
            Number deleted.

        Raises:
            TenantError: If the filter names another tenant.
            ValueError: If the collection is not tenant-scoped.
        """
        return self._collection(collection).delete_many(self._filter(query)).deleted_count
