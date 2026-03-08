from src.gatevault.hashing import hash_password, verify_password


def test_hash_password():
    hashed = hash_password("very-secret-password")

    assert isinstance(hashed, str)
    assert not isinstance(hashed, bytes)
    assert hashed.startswith("$2b$") == True


def test_hash_password_unique_salt():
    h1 = hash_password("same_password")
    h2 = hash_password("same_password")

    # should be different becasue of salt uniqueness
    assert h1 != h2


def test_verify_password():
    hashed = hash_password("very-secret-password")

    assert verify_password("very-secret-password", hashed) == True
    assert verify_password("very-different-password", hashed) == False
    assert isinstance(verify_password("string", hashed), bool)
