"""Signature verification (FR-002) and permission-level authorization (FR-003).

research.md/H2: author_association alone is too coarse — GitHub's
COLLABORATOR association includes read-only collaborators. This module
checks actual repo permission via the installation token instead, with
OWNER as a fast-path that skips the extra API call.
"""
import hashlib
import hmac

_SIGNATURE_PREFIX = "sha256="
_AUTHORIZED_PERMISSIONS = {"write", "admin"}


def verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify X-Hub-Signature-256 (sha256=<hex hmac>) over the exact raw body."""
    if not signature_header or not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    provided_digest = signature_header[len(_SIGNATURE_PREFIX) :]
    expected_digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_digest, expected_digest)


async def is_authorized(
    github_client, repo: str, author_login: str, author_association: str
) -> bool:
    """True if author_login may issue run/gate commands on repo.

    OWNER is a fast-path (no API call). Everyone else must have write or
    admin permission per GET /repos/{repo}/collaborators/{login}/permission.
    """
    if author_association == "OWNER":
        return True
    permission = await github_client.get_permission(repo, author_login)
    return permission in _AUTHORIZED_PERMISSIONS
