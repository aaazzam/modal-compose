"""The modal-compose exception hierarchy.

Every error the library raises deliberately derives from `ModalComposeError`,
so `except ModalComposeError` catches anything modal-compose itself decided to
raise. Leaf types also derive from the builtin exception a caller would
naturally expect (`KeyError` for a missing registry entry, `ValueError` for a
bad argument), so existing `except` clauses keep working.
"""

from __future__ import annotations


class ModalComposeError(Exception):
    """Base class for every error modal-compose raises deliberately."""


class InvalidRepoError(ModalComposeError, ValueError):
    """A GitHub repo reference could not be normalized to `owner/name`."""


class BoxNotRegisteredError(ModalComposeError, KeyError):
    """A dev-box name was looked up in a registry that does not contain it."""

    def __str__(self) -> str:
        return Exception.__str__(self)


class DuplicateBoxError(ModalComposeError, ValueError):
    """A dev-box was added to a registry under an already-registered name."""


class NotOurSandboxError(ModalComposeError, ValueError):
    """A sandbox id did not come from this server's registry."""


class GitHubAppNotInstalledError(ModalComposeError, LookupError):
    """The GitHub App is not installed on the requested account."""


class SandboxCommandError(ModalComposeError, RuntimeError):
    """A command run inside a sandbox exited with a non-zero status."""
