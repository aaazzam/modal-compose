"""The example dev-box: clones modal-labs/modal-client to hack on.

The `GitHub` layer clones the repo into the image at build time and refreshes
it with `git pull` each time a sandbox starts; its `workdir` defaults to
/workspace/modal-client. The `install` build step editable-installs the client
(it lives under `py/` in that monorepo). `registry.py` discovers this module
and registers the `box` defined here under the name `modal`. (An absolute
`import modal` below resolves to the real package, not this module.)

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

from modal_compose import DevBox, GitHub

client = GitHub(repo="modal-labs/modal-client")


def install(image: Image) -> Image:
    py = f"{client.workdir}/py"
    return image.uv_pip_install(py, extra_options="-e").run_commands(
        f"uv pip install --system -r {py}/requirements.protos.txt",
        f"cd {py} && python compile_protos.py --skip-mypy",
    )


box = DevBox("modal", layers=[client], build=install)
