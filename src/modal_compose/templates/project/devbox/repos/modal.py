"""The example repo: a dev-box that clones modal-labs/modal-client to hack on.

The layer's `source` is a `GitHubRemote`, so the repo is cloned into the image
at build time and refreshed with `git pull` each time a sandbox starts. The
build editable-installs the client (it lives under `py/` in that monorepo).
`registry.py` mounts the `repo` defined here under the name `modal`. (An
absolute `import modal` below resolves to the real package, not this module.)

modal-client generates its protobuf bindings rather than committing them, so a
bare editable install leaves `import modal` failing on `modal_proto.api_pb2`.
After the install the build therefore installs the proto-compile dependencies
from the cloned `py/requirements.protos.txt` (uv is on `$PATH` in the build
image, so a `run_commands` step with `uv pip install --system` works on the
in-image file; `uv_pip_install(requirements=...)` would only read the local
build context) and runs `compile_protos.py --skip-mypy` from `py/`. The
generated bindings land in `py/modal_proto/`, where the editable install's
import finder resolves `modal_proto.api_pb2` for an in-sandbox `import modal`.
"""

from __future__ import annotations

from modal import Image

from modal_compose.layer import Layer, LayerContext, Repo
from modal_compose.remote import GitHubRemote

layer = Layer(
    name="modal",
    source=GitHubRemote(
        repo="modal-labs/modal-client", working_directory="/workspace/modal-client"
    ),
)


@layer.build
def install(image: Image, ctx: LayerContext) -> Image:
    py = f"{ctx.working_directory}/py"
    return image.uv_pip_install(py, extra_options="-e").run_commands(
        f"uv pip install --system -r {py}/requirements.protos.txt",
        f"cd {py} && python compile_protos.py --skip-mypy",
    )


repo = Repo(layers=[layer])
