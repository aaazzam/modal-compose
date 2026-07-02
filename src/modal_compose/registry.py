from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from modal import Image, Secret

from .devbox import DevBox


def default_base_image() -> Image:
    return Image.debian_slim().apt_install(
        "git", "ripgrep", "curl", "ca-certificates", "jq"
    )


class Registry(Mapping[str, DevBox]):
    """The named dev-boxes available to launch, plus what they share.

    `name` is the registry's namespace on Modal: it names the Modal app that
    sandboxes run in and prefixes every published image
    (`image_name_for("api")` -> `"<name>-api"`), so two registries in one
    workspace never collide. `base_image` seeds every box's image build and
    `common_secrets` are injected into every sandbox.

    `add(box)` registers a box under its own name; lookup is a full read-only
    mapping (`registry["name"]`, `in`, iteration, `.get`, `.items`, ...).
    """

    def __init__(
        self,
        name: str = "modal-compose",
        *,
        base_image: Image | None = None,
        common_secrets: Sequence[Secret] = (),
    ) -> None:
        if not name:
            raise ValueError("Registry name must be a non-empty string")
        self.name = name
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

    def image_for(self, name: str) -> Image:
        return self[name].image(self.base_image)

    def image_name_for(self, name: str) -> str:
        return f"{self.name}-{self[name].name}"

    def __getitem__(self, name: str) -> DevBox:
        try:
            return self._boxes[name]
        except KeyError:
            known = ", ".join(self._boxes) or "none"
            raise KeyError(
                f"no dev-box named {name!r} is registered (registered: {known})"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)
