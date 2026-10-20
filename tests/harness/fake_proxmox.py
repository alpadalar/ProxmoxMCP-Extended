"""Path-routed fake of the proxmoxer ``ProxmoxAPI`` object.

proxmoxer builds URLs from call chains: attribute access appends a segment and calling a
resource with an argument appends ``str(arg)``. ``FakeProxmox`` mirrors that, so
``fake.nodes("pve1").qemu(100).status.current.get()`` resolves to the path
``nodes/pve1/qemu/100/status/current`` and is answered from a canned route table.

Fixtures (``data/pve8.json``, ``data/pve9.json``) are flat JSON objects keyed
``"METHOD path"`` (``*`` matches one segment). The two files carry the same shapes and
differ in the ``GET version`` payload (8.x vs 9.x), which is the hook Phase 4 uses for
PVE-version specific behaviour. They contain example values only.

Unlike MagicMock, an unmatched route raises ``UnmockedCallError``; every call is recorded
(before any error is raised) so tests can prove which requests did or did not happen.
"""
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"

_METHOD_ALIASES = {"create": "POST", "set": "PUT"}
_MUTATING = {"POST", "PUT", "DELETE"}
_TOP_LEVEL = {"nodes", "cluster", "version", "storage", "access", "pools"}


class UnmockedCallError(AssertionError):
    """A Proxmox call reached the fake without a canned response."""


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)


def load_fixture(name: str) -> dict[str, Any]:
    """Load ``tests/harness/data/<name>.json``."""
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


class FakeResource:
    """One node in a proxmoxer-style call chain."""

    def __init__(self, fake: "FakeProxmox", segments: tuple[str, ...]):
        self._fake = fake
        self._segments = segments

    def __getattr__(self, name: str) -> "FakeResource":
        if name.startswith("_"):
            raise AttributeError(name)
        return FakeResource(self._fake, self._segments + (name,))

    def __call__(self, arg: Any) -> "FakeResource":
        return FakeResource(self._fake, self._segments + (str(arg),))

    def _do(self, method: str, params: dict[str, Any]) -> Any:
        return self._fake._dispatch(method, "/".join(self._segments), params)

    def get(self, **params: Any) -> Any:
        return self._do("GET", params)

    def post(self, **params: Any) -> Any:
        return self._do("POST", params)

    def put(self, **params: Any) -> Any:
        return self._do("PUT", params)

    def delete(self, **params: Any) -> Any:
        return self._do("DELETE", params)

    create = post
    set = put


class FakeProxmox:
    """Canned, recording stand-in for ``ProxmoxAPI``."""

    def __init__(self, routes: dict[str, Any] | None = None):
        self._routes: dict[str, Any] = dict(routes or {})
        self._errors: dict[str, BaseException] = {}
        self.calls: list[Call] = []

    def __getattr__(self, name: str) -> FakeResource:
        if name in _TOP_LEVEL:
            return FakeResource(self, (name,))
        raise AttributeError(name)

    # -- configuration -------------------------------------------------
    def set(self, method: str, path: str, value: Any) -> None:  # noqa: A003
        """Override (or add) the response for a route; may be a callable(params, segments)."""
        self._routes[f"{method.upper()} {path}"] = value
        self._errors.pop(f"{method.upper()} {path}", None)

    def fail(self, method: str, path: str, exc: BaseException) -> None:
        """Make a route raise ``exc``."""
        self._errors[f"{method.upper()} {path}"] = exc

    # -- recording -----------------------------------------------------
    def mutating_calls(self) -> list[Call]:
        return [c for c in self.calls if c.method in _MUTATING]

    def reset_calls(self) -> None:
        self.calls.clear()

    def assert_no_calls(self) -> None:
        if self.calls:
            listing = ", ".join(f"{c.method} {c.path}" for c in self.calls)
            raise AssertionError(f"expected no Proxmox calls, got: {listing}")

    # -- routing -------------------------------------------------------
    @staticmethod
    def _match(table: dict[str, Any], method: str, path: str) -> tuple[str, Any] | None:
        key = f"{method} {path}"
        if key in table:
            return key, table[key]
        segs = path.split("/")
        best: tuple[int, str] | None = None
        for k in table:
            m, _, pattern = k.partition(" ")
            if m != method:
                continue
            psegs = pattern.split("/")
            if len(psegs) != len(segs):
                continue
            if all(p == "*" or p == s for p, s in zip(psegs, segs, strict=True)):
                literals = sum(1 for p in psegs if p != "*")
                if best is None or literals > best[0]:
                    best = (literals, k)
        if best is None:
            return None
        return best[1], table[best[1]]

    def _dispatch(self, method: str, path: str, params: dict[str, Any]) -> Any:
        method = _METHOD_ALIASES.get(method.lower(), method.upper())
        self.calls.append(Call(method, path, dict(params)))
        err = self._match(self._errors, method, path)
        if err is not None:
            raise err[1]
        found = self._match(self._routes, method, path)
        if found is None:
            raise UnmockedCallError(f"unmocked Proxmox call: {method} {path} params={params}")
        value = found[1]
        if callable(value):
            return _call(value, params, path.split("/"))
        return json.loads(json.dumps(value))  # deep copy so tests cannot mutate fixtures


def _call(fn: Callable[..., Any], params: dict[str, Any], segments: list[str]) -> Any:
    return fn(params, segments)
