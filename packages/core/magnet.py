from urllib.parse import parse_qs, urlparse


def extract_info_hash(magnet_uri: str) -> str:
    """Return infohash (hex) from magnet URI."""
    parsed = urlparse(magnet_uri)
    if parsed.scheme != "magnet":
        raise ValueError("Invalid magnet scheme")
    query = parse_qs(parsed.query)
    xts = query.get("xt") or []
    for xt in xts:
        if xt.startswith("urn:btih:"):
            return xt.split(":", 2)[-1].lower()
    raise ValueError("Missing btih in magnet URI")
