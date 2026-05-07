import socket

import pytest

from scripts.rust_gateway_prod_shadow_preflight import validate_prod_shadow_urls


@pytest.fixture(autouse=True)
def _stable_prod_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host.endswith(".wisdoverse.dev"):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 0),
                )
            ]
        raise socket.gaierror(f"test DNS does not know {host}")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_accepts_distinct_non_local_urls() -> None:
    assert (
        validate_prod_shadow_urls(
            "gateway.wisdoverse.dev",
            "https://gateway.wisdoverse.dev",
            "https://rust-gateway.wisdoverse.dev",
        )
        == []
    )


def test_rejects_missing_local_or_identical_urls() -> None:
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "",
        "https://rust-gateway.wisdoverse.dev",
    ) == [
        "LEGACY_GATEWAY_URL is required"
    ]
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "http://127.0.0.1:8080",
        "https://rust-gateway.wisdoverse.dev",
    ) == ["LEGACY_GATEWAY_URL must use https for production gateway evidence"]
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "http://gateway.wisdoverse.dev",
        "https://rust-gateway.wisdoverse.dev",
    ) == ["LEGACY_GATEWAY_URL must use https for production gateway evidence"]
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "https://gateway.wisdoverse.dev",
        "https://192.168.1.10:18080",
    ) == ["RUST_GATEWAY_URL must not point to local, private, or non-global hosts"]
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "https://gateway.wisdoverse.dev",
        "https://rust-gateway.127.0.0.1.nip.io",
    ) == ["RUST_GATEWAY_URL must not point to local, private, or non-global hosts"]
    assert validate_prod_shadow_urls(
        "gateway.example.com",
        "https://gateway.example.com",
        "https://rust-gateway.wisdoverse.dev",
    ) == ["LEGACY_GATEWAY_URL must not point to placeholder or documentation-only hosts"]
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        "https://gateway.wisdoverse.dev",
        "https://gateway.wisdoverse.dev",
    ) == ["LEGACY_GATEWAY_URL and RUST_GATEWAY_URL must differ"]


@pytest.mark.parametrize(
    ("legacy_url", "rust_url", "expected_error"),
    [
        (
            "https://gateway.wisdoverse.dev/api",
            "https://rust-gateway.wisdoverse.dev",
            "LEGACY_GATEWAY_URL must be a base URL without path, query, or fragment",
        ),
        (
            "https://gateway.wisdoverse.dev",
            "https://rust-gateway.wisdoverse.dev?mode=shadow",
            "RUST_GATEWAY_URL must be a base URL without path, query, or fragment",
        ),
        (
            "https://gateway.wisdoverse.dev",
            "https://rust-gateway.wisdoverse.dev#ready",
            "RUST_GATEWAY_URL must be a base URL without path, query, or fragment",
        ),
    ],
)
def test_rejects_urls_with_path_query_or_fragment(
    legacy_url: str,
    rust_url: str,
    expected_error: str,
) -> None:
    assert validate_prod_shadow_urls(
        "gateway.wisdoverse.dev",
        legacy_url,
        rust_url,
    ) == [expected_error]


def test_rejects_missing_or_mismatched_gateway_host() -> None:
    assert validate_prod_shadow_urls(
        "",
        "https://gateway.wisdoverse.dev",
        "https://rust-gateway.wisdoverse.dev",
    ) == ["GATEWAY_HOST is required"]
    assert validate_prod_shadow_urls(
        "other-gateway.wisdoverse.dev",
        "https://gateway.wisdoverse.dev",
        "https://rust-gateway.wisdoverse.dev",
    ) == ["GATEWAY_HOST must match the host portion of LEGACY_GATEWAY_URL"]
