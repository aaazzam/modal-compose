from __future__ import annotations

from collections.abc import ItemsView, Iterator, Sequence

from modal import Image, Secret

from .devbox import DevBox


def default_base_image() -> Image:
    return Image.debian_slim().apt_install(
        "git", "ripgrep", "curl", "ca-certificates", "jq"
    )


class Registry:
    """The named dev-boxes available to launch, plus what they share.

    `base_image` seeds every box's image build and `common_secrets` are
    injected into every sandbox. `add(box)` registers a box under its own
    name; lookup is dict-like (`registry["name"]`, `in`, iteration).
    """

    def __init__(
        self,
        base_image: Image | None = None,
        common_secrets: Sequence[Secret] = (),
    ) -> None:
        self._boxes: dict[str, DevBox] = {}
        self.base_image: Image = (
            base_image if base_image is not None else default_base_image()
        )
        self.common_secrets: tuple[Secret, ...] = tuple(common_secrets)

    def add(self, box: DevBox) -> DevBox:
        if box.name in self._boxes:
            raise ValueError(f"a dev-box named {box.name!r} is already registered")
        self._boxes[box.name] = box
        return box

    def names(self) -> tuple[str, ...]:
        return tuple(self._boxes)

    def items(self) -> ItemsView[str, DevBox]:
        return self._boxes.items()

    def image_for(self, name: str) -> Image:
        return self[name].image(self.base_image)

    def __getitem__(self, name: str) -> DevBox:
        try:
            return self._boxes[name]
        except KeyError:
            known = ", ".join(self._boxes) or "none"
            raise KeyError(
                f"no dev-box named {name!r} is registered (registered: {known})"
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._boxes

    def __iter__(self) -> Iterator[str]:
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)
