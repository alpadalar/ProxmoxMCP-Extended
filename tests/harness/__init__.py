"""Fixture-driven fake of the proxmoxer API for tests (test-only, never packaged)."""

from .fake_proxmox import Call, FakeProxmox, FakeResource, UnmockedCallError, load_fixture

__all__ = ["Call", "FakeProxmox", "FakeResource", "UnmockedCallError", "load_fixture"]
