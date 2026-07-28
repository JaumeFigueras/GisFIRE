#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alembic support for *replaceable* database objects.

Alembic thinks in terms of tables and columns, which it can diff. A view has no
diffable state: it is a definition that is either there or not, and changing it
means dropping the old one and creating the new one. Alembic offers no
``op.create_view()`` for that, so this module adds one, following the
`replaceable objects
<https://alembic.sqlalchemy.org/en/latest/cookbook.html#replaceable-objects>`_
recipe from the Alembic cookbook.

A view is described by a :class:`ReplaceableObject` — a name and the body of its
``SELECT`` — and three operations become available to migrations that import
this module:

.. code-block:: python

   from src.data_model.replaceable import ReplaceableObject

   my_view = ReplaceableObject("v_something", "SELECT ...")

   def upgrade() -> None:
       op.create_view(my_view)

   def downgrade() -> None:
       op.drop_view(my_view)

and, when a later revision changes an existing view:

.. code-block:: python

   def upgrade() -> None:
       op.replace_view(my_view, replaces="a1b2c3d4e5f6.my_view")

   def downgrade() -> None:
       op.replace_view(my_view, replace_with="a1b2c3d4e5f6.my_view")

The ``replaces`` / ``replace_with`` identifier is ``<revision>.<variable name>``:
Alembic loads that revision's module and reads the :class:`ReplaceableObject`
from it, which is why **each revision keeps its own copy of the SQL** rather than
importing a shared, mutable definition. A migration has to stay a faithful
snapshot of the schema as it was, and it cannot do that if the definition it
applies changes underneath it.

.. note::

   Autogenerate does not know about any of this. Views are invisible to it —
   Alembic reflects tables only — so it will never propose creating, dropping or
   updating one. The upside is that a view can never turn into a spurious
   ``drop_table`` in a generated revision; the downside is that every view change
   is written by hand.

.. warning::

   PostgreSQL records a dependency from a view to every column it selects, so
   while a view exists an ``ALTER TABLE ... ALTER COLUMN ... TYPE`` or a
   ``DROP COLUMN`` on one of those columns fails. A revision that changes such a
   column has to ``op.drop_view()`` first and ``op.create_view()`` again at the
   end, carrying its own copies of the definitions as above.
"""

from __future__ import annotations

from alembic.operations import MigrateOperation
from alembic.operations import Operations


class ReplaceableObject:
    """A schema object defined by a body of SQL, created and dropped as a whole.

    Parameters
    ----------
    name : str
        Name of the object in the database, as it appears after ``CREATE VIEW``.
    sqltext : str
        The object's definition — for a view, the ``SELECT`` that follows ``AS``.

    Attributes
    ----------
    name : str
        Name of the object in the database.
    sqltext : str
        The object's definition.
    """

    def __init__(self, name: str, sqltext: str) -> None:
        self.name = name
        self.sqltext = sqltext

    def __repr__(self) -> str:
        return f"ReplaceableObject(name={self.name!r})"


class ReversibleOp(MigrateOperation):
    """Base class for an operation that knows how to undo itself.

    Parameters
    ----------
    target : ReplaceableObject
        The object the operation acts on.

    Attributes
    ----------
    target : ReplaceableObject
        The object the operation acts on.
    """

    def __init__(self, target: ReplaceableObject) -> None:
        self.target = target

    @classmethod
    def invoke_for_target(cls, operations: Operations, target: ReplaceableObject):
        """Run this operation against ``target``.

        This is what ``op.create_view(obj)`` and ``op.drop_view(obj)`` call.

        Parameters
        ----------
        operations : alembic.operations.Operations
            The migration's operations proxy, i.e. ``op``.
        target : ReplaceableObject
            The object to create or drop.
        """
        return operations.invoke(cls(target))

    def reverse(self) -> ReversibleOp:
        """Return the operation that undoes this one.

        Returns
        -------
        ReversibleOp
            The inverse operation.
        """
        raise NotImplementedError()

    @classmethod
    def _get_object_from_version(cls, operations: Operations, ident: str) -> ReplaceableObject:
        """Load a :class:`ReplaceableObject` defined in another revision.

        Parameters
        ----------
        operations : alembic.operations.Operations
            The migration's operations proxy, i.e. ``op``.
        ident : str
            ``<revision>.<variable name>``, naming the module-level variable of
            the revision that holds the definition.

        Returns
        -------
        ReplaceableObject
            The object as that revision defined it.
        """
        version, objname = ident.split(".")
        module = operations.get_context().script.get_revision(version).module
        return getattr(module, objname)

    @classmethod
    def replace(
        cls,
        operations: Operations,
        target: ReplaceableObject,
        replaces: str | None = None,
        replace_with: str | None = None,
    ) -> None:
        """Swap one definition of an object for another.

        Exactly one of ``replaces`` and ``replace_with`` must be given: the first
        for an ``upgrade()``, which drops the older definition and creates
        ``target``; the second for the matching ``downgrade()``, which drops
        ``target`` and puts the older definition back.

        Parameters
        ----------
        operations : alembic.operations.Operations
            The migration's operations proxy, i.e. ``op``.
        target : ReplaceableObject
            The definition this revision introduces.
        replaces : str or None
            ``<revision>.<variable name>`` of the definition being superseded.
        replace_with : str or None
            ``<revision>.<variable name>`` of the definition to restore.

        Raises
        ------
        TypeError
            If neither ``replaces`` nor ``replace_with`` is given.
        """
        if replaces:
            old_obj = cls._get_object_from_version(operations, replaces)
            drop_old = cls(old_obj).reverse()
            create_new = cls(target)
        elif replace_with:
            old_obj = cls._get_object_from_version(operations, replace_with)
            drop_old = cls(target).reverse()
            create_new = cls(old_obj)
        else:
            raise TypeError("replaces or replace_with is required")

        operations.invoke(drop_old)
        operations.invoke(create_new)


@Operations.register_operation("create_view", "invoke_for_target")
@Operations.register_operation("replace_view", "replace")
class CreateViewOp(ReversibleOp):
    """``op.create_view(view)`` — create a view, dropping it on the way back."""

    def reverse(self) -> ReversibleOp:
        """Return the :class:`DropViewOp` that undoes this creation."""
        return DropViewOp(self.target)


@Operations.register_operation("drop_view", "invoke_for_target")
class DropViewOp(ReversibleOp):
    """``op.drop_view(view)`` — drop a view, creating it again on the way back."""

    def reverse(self) -> ReversibleOp:
        """Return the :class:`CreateViewOp` that undoes this drop."""
        return CreateViewOp(self.target)


@Operations.implementation_for(CreateViewOp)
def create_view(operations: Operations, operation: CreateViewOp) -> None:
    """Emit the ``CREATE VIEW`` for :class:`CreateViewOp`."""
    operations.execute(f"CREATE VIEW {operation.target.name} AS {operation.target.sqltext}")


@Operations.implementation_for(DropViewOp)
def drop_view(operations: Operations, operation: DropViewOp) -> None:
    """Emit the ``DROP VIEW`` for :class:`DropViewOp`."""
    operations.execute(f"DROP VIEW {operation.target.name}")
