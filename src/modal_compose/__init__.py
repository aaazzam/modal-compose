from .layer import Layer, Repo
from .remote import GitHubRemote, Remote


def main() -> None:
    print("Hello from modal-compose!")


__all__ = ["GitHubRemote", "Layer", "Remote", "Repo", "main"]
