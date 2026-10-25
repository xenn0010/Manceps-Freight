"""Shared MongoDB type aliases so every module agrees on document and handle types."""

from __future__ import annotations

from typing import Any, TypeAlias

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

Doc: TypeAlias = dict[str, Any]
MongoClientT: TypeAlias = MongoClient[Doc]
MongoDb: TypeAlias = Database[Doc]
MongoCollection: TypeAlias = Collection[Doc]
