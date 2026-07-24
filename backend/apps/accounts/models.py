from dataclasses import dataclass


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str
    email_verified: bool
    first_name: str | None
    last_name: str | None
    sign_in_provider: str
    roles: frozenset[str]
