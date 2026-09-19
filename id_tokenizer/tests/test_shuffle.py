import pytest
from id_tokenizer.shuffle import (
    factor_decode,
    factor_encode,
    faux_uuid_to_int,
    int_to_faux_uuid,
    shuffle_decode,
    shuffle_encode,
)


def test_shuffle_roundtrip():
    salt = "secret-key"
    for val in [0, 1, 42, 123, 9999, 100000]:
        encoded = shuffle_encode(val, min_digits=4, salt=salt)
        assert len(encoded) >= 4
        decoded = shuffle_decode(encoded, min_digits=4, salt=salt)
        assert decoded == val


def test_shuffle_different_salts():
    val = 1234
    enc1 = shuffle_encode(val, salt="salt1")
    enc2 = shuffle_encode(val, salt="salt2")
    assert enc1 != enc2


def test_faux_uuid_roundtrip():
    salt = "db-salt-xyz"
    for val in [1, 2, 42, 999999, 2**64 - 1]:
        faux = int_to_faux_uuid(val, salt=salt)
        assert len(faux) == 36
        decoded = faux_uuid_to_int(faux, salt=salt)
        assert decoded == val


def test_factor_encoding():
    val = 42
    enc = factor_encode(val, factor=97)
    assert enc == 42 * 97
    assert factor_decode(enc, factor=97) == val

    with pytest.raises(ValueError, match="not divisible"):
        factor_decode(enc + 1, factor=97)
