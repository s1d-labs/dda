"""TLS and HTTP session for dda.gov.in.

dda.gov.in has two TLS quirks that stop a normal client:

1. It needs legacy TLS renegotiation. OpenSSL 3.x refuses it by default
   ("unsafe legacy renegotiation disabled"). We enable OP_LEGACY_SERVER_CONNECT.
   This is a compatibility option, not a downgrade: certificate verification
   stays ON.
2. It serves an incomplete certificate chain: the leaf (CN=dda.gov.in) is issued
   by "GlobalSign GCC R46 OV TLS CA 2025", but the server does not send that
   intermediate. Its root (GlobalSign Root R46) is already trusted. We ship the
   intermediate in certs/ and append it to the certifi bundle, so the chain
   verifies properly.

The result is a fully verified HTTPS connection. We never disable verification.
"""
import os
import ssl
import tempfile

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from urllib3.util.retry import Retry

OP_LEGACY_SERVER_CONNECT = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
_HERE = os.path.dirname(os.path.abspath(__file__))
INTERMEDIATE = os.path.join(_HERE, "certs", "globalsign_gccr46_ov_2025.pem")

_BUNDLE_CACHE = None


def ca_bundle():
    """Path to a CA bundle = certifi + the DDA intermediate. Built once per process."""
    global _BUNDLE_CACHE
    if _BUNDLE_CACHE and os.path.exists(_BUNDLE_CACHE):
        return _BUNDLE_CACHE
    data = open(certifi.where(), "rb").read()
    if os.path.exists(INTERMEDIATE):
        data += b"\n" + open(INTERMEDIATE, "rb").read()
    fd, path = tempfile.mkstemp(prefix="dda_ca_", suffix=".pem")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    _BUNDLE_CACHE = path
    return path


def _ssl_context():
    ctx = create_urllib3_context()
    ctx.options |= OP_LEGACY_SERVER_CONNECT          # legacy renegotiation (compatibility only)
    ctx.load_verify_locations(ca_bundle())           # verification stays ON, with the full chain
    return ctx


class LegacyTLSAdapter(HTTPAdapter):
    """requests adapter that enables legacy renegotiation and the completed chain,
    for both direct and proxied (CONNECT) connections."""

    def init_poolmanager(self, *a, **k):
        k["ssl_context"] = _ssl_context()
        return super().init_poolmanager(*a, **k)

    def proxy_manager_for(self, *a, **k):
        k["ssl_context"] = _ssl_context()
        return super().proxy_manager_for(*a, **k)


UA = "s1d-labs scraper (+https://github.com/s1d-labs/dda)"


def make_session(retries=2):
    """A requests Session wired for dda.gov.in. The hub/proxy env vars
    (HTTPS_PROXY/HTTP_PROXY) are picked up by requests automatically."""
    s = requests.Session()
    retry = Retry(total=retries, connect=retries, read=retries, backoff_factor=0.8,
                  status_forcelist=(500, 502, 504), allowed_methods=("GET", "HEAD"))
    adapter = LegacyTLSAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = UA
    return s
