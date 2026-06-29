from __future__ import annotations

from collections.abc import ItemsView, Iterator

from modal import Image, Secret

from .layer import Repo


class Registry:
    def __init__(
        self,
        base_image: Image | None = None,
        common_secrets: set[Secret] | None = None,
    ) -> None:
        self._repos: dict[str, Repo] = {}
        self.base_image: Image = (
            base_image if base_image is not None else Image.debian_slim().apt_install("git", "ripgrep")
        )
        self.common_secrets: set[Secret] = (
            set() if common_secrets is None else set(common_secrets)
        )

    def mount(self, name: str, repo: Repo) -> Repo:
        if name in self._repos:
            raise ValueError(f"{name!r} is already mounted")
        self._repos[name] = repo
        return repo

    def names(self) -> tuple[str, ...]:
        return tuple(self._repos)

    def items(self) -> ItemsView[str, Repo]:
        return self._repos.items()

    def image_for(self, name: str) -> Image:
        return self[name].get_image(self.base_image)

    def __getitem__(self, name: str) -> Repo:
        return self._repos[name]

    def __contains__(self, name: object) -> bool:
        return name in self._repos

    def __iter__(self) -> Iterator[str]:
        return iter(self._repos)

    def __len__(self) -> int:
        return len(self._repos)
