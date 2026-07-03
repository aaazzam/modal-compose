from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator, Mapping, Sequence

from modal import App, Image, Secret

from .devbox import DevBox
from .errors import BoxNotRegisteredError, DuplicateBoxError


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

    `add(box)` registers a box under its own name and `discover(package)`
    registers every box defined in a package's modules; lookup is a full
    read-only mapping (`registry["name"]`, `in`, iteration, `.get`, `.items`,
    ...). `build(name, app)` builds and publishes a box's prebaked image.
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

    def __repr__(self) -> str:
        boxes = ", ".join(self._boxes) or "empty"
        return f"Registry({self.name!r}, boxes=[{boxes}])"

    def add(self, box: DevBox) -> DevBox:
        if box.name in self._boxes:
            raise DuplicateBoxError(
                f"a dev-box named {box.name!r} is already registered"
            )
        self._boxes[box.name] = box
        return box

    def discover(self, package: str) -> list[DevBox]:
        """Import every module in `package` and register the `DevBox`es it defines.

        Modules whose names start with an underscore are skipped; modules are
        imported in sorted-name order and each module-level `DevBox` is added
        in its declaration order. A box object that is already registered
        (say, imported into a second module) is skipped, so re-exports are
        harmless; two distinct boxes sharing a name still raise
        `DuplicateBoxError`. Returns the newly registered boxes.
        """
        root = importlib.import_module(package)
        paths = getattr(root, "__path__", None)
        if paths is None:
            raise ModuleNotFoundError(
                f"{package!r} is a module, not a package; "
                "discover() scans a package of dev-box modules"
            )
        added: list[DevBox] = []
        for info in sorted(pkgutil.iter_modules(paths), key=lambda info: info.name):
            if info.name.startswith("_"):
                continue
            module = importlib.import_module(f"{package}.{info.name}")
            for value in vars(module).values():
                if isinstance(value, DevBox) and not any(
                    existing is value for existing in self._boxes.values()
                ):
                    added.append(self.add(value))
        return added

    def build(self, name: str, app: App) -> Image:
        """Build and publish `name`'s image under its namespaced name.

        The box's image is built in `app` and published as
        `image_name_for(name)`; any sidecar images are built too so launches
        don't pay for them. This is the one build-and-publish path — the CLI's
        `build` command and the scaffolded prebake cron both call it.
        """
        box = self[name]
        built = box.image(self.base_image).build(app)
        built.publish(self.image_name_for(name))
        for spec in box.sidecars:
            spec.image.build(app)
        return built

    def image_for(self, name: str) -> Image:
        return self[name].image(self.base_image)

    def image_name_for(self, name: str) -> str:
        return f"{self.name}-{self[name].name}"

    def __getitem__(self, name: str) -> DevBox:
        try:
            return self._boxes[name]
        except KeyError:
            known = ", ".join(self._boxes) or "none"
            raise BoxNotRegisteredError(
                f"no dev-box named {name!r} is registered (registered: {known})"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)
