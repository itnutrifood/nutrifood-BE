from backend.apps.common.security import hash_password, verify_password


def hash_admin_password(password: str) -> str:
    return hash_password(password)


def verify_admin_password(password: str, encoded_password: str) -> bool:
    return verify_password(password, encoded_password)
