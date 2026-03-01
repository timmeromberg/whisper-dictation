"""Tests for local_setup security helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import whisper_dic.local_setup as local_setup
from whisper_dic.local_setup import (
    _assert_integrity,
    _parse_sha256_digest,
    _resolve_hf_revision,
    _resolve_model_checksums,
)


class TestParseSha256Digest:
    def test_accepts_prefixed_digest(self) -> None:
        digest = "sha256:" + ("a" * 64)
        assert _parse_sha256_digest(digest) == ("a" * 64)

    def test_accepts_plain_digest(self) -> None:
        digest = "b" * 64
        assert _parse_sha256_digest(digest) == digest

    def test_rejects_invalid_digest(self) -> None:
        assert _parse_sha256_digest("not-a-digest") is None


class TestAssertIntegrity:
    def test_raises_on_mismatch(self) -> None:
        expected = "a" * 64
        actual = "b" * 64
        try:
            _assert_integrity("artifact.bin", expected, actual)
            raised = False
        except RuntimeError:
            raised = True
        assert raised

    def test_allows_missing_when_opted_in(self, monkeypatch) -> None:
        monkeypatch.setenv("WHISPER_DIC_ALLOW_INSECURE_DOWNLOADS", "1")
        _assert_integrity("artifact.bin", None, "c" * 64)


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class TestHfRevisionResolution:
    def test_resolves_valid_sha(self, monkeypatch) -> None:
        monkeypatch.setattr(
            local_setup.httpx,
            "get",
            lambda *args, **kwargs: _FakeResponse({"sha": "a" * 40}),
        )
        assert _resolve_hf_revision() == "a" * 40

    def test_rejects_invalid_sha(self, monkeypatch) -> None:
        monkeypatch.setattr(
            local_setup.httpx,
            "get",
            lambda *args, **kwargs: _FakeResponse({"sha": "main"}),
        )
        with pytest.raises(RuntimeError):
            _resolve_hf_revision()

    def test_checksums_resolve_from_specific_revision(self, monkeypatch) -> None:
        calls: list[str] = []

        def _fake_get(url: str, *args, **kwargs) -> _FakeResponse:
            calls.append(url)
            return _FakeResponse(
                [
                    {"path": "ggml-tiny.bin", "lfs": {"oid": "sha256:" + ("b" * 64)}},
                    {"path": "README.md", "lfs": {}},
                ]
            )

        monkeypatch.setattr(local_setup.httpx, "get", _fake_get)
        checksums = _resolve_model_checksums("c" * 40)
        assert checksums["ggml-tiny.bin"] == "b" * 64
        assert calls and "/tree/" + ("c" * 40) in calls[0]

    def test_download_model_uses_pinned_revision_url(self, monkeypatch, tmp_path: Path) -> None:
        revision = "d" * 40
        monkeypatch.setattr(local_setup, "_resolve_hf_revision", lambda: revision)
        monkeypatch.setattr(local_setup, "_resolve_model_checksums", lambda rev: {"ggml-tiny.bin": "e" * 64})
        seen: dict[str, str] = {}

        def _fake_download(url: str, dest: Path, label: str, expected_sha256: str | None = None) -> None:
            seen["url"] = url
            seen["sha"] = str(expected_sha256)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-model")

        monkeypatch.setattr(local_setup, "_download_file", _fake_download)
        out = local_setup._download_model(tmp_path, "tiny")
        assert out.name == "ggml-tiny.bin"
        assert seen["url"].endswith(f"/{revision}/ggml-tiny.bin")
        assert seen["sha"] == "e" * 64
