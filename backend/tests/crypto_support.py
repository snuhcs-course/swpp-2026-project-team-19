"""Keys for the stored business registration numbers in tests (app/core/business_number_crypto.py).

Made with Fernet.generate_key() for the tests only; they protect no real data.
"""

import pytest

from app.core.business_number_crypto import ENCRYPTION_KEYS_ENV, HMAC_KEY_ENV

TEST_BUSINESS_NUMBER_ENCRYPTION_KEY = "BPv6wXLkyKmt-7A7qXDXqK-BsT8HEjb5QS2K4qw_Fns="
TEST_BUSINESS_NUMBER_HMAC_KEY = "vClA_8_T6P9JDDo4iiSzfQV6u0Xm9499ueOCMmEAtkg="
# A second encryption key, for key rotation tests.
TEST_BUSINESS_NUMBER_NEXT_KEY = "4PhNxB6zQEewbcKE5bsSXuLd_Wp0Yo-4hlDlgLgDVl4="
# Another lookup key, for lookup key rotation tests.
TEST_BUSINESS_NUMBER_NEXT_HMAC_KEY = "GbEltWSZnS24HDtXbenXvNOfshRfph-eJV4YSY89NtA="


# Key settings the server refuses, with a part of the message; the migration must refuse the same ones.
INVALID_KEY_SETTINGS = [
    pytest.param("", TEST_BUSINESS_NUMBER_HMAC_KEY, f"{ENCRYPTION_KEYS_ENV} is not set", id="no encryption key"),
    pytest.param(" , ", TEST_BUSINESS_NUMBER_HMAC_KEY, f"{ENCRYPTION_KEYS_ENV} is not set", id="only commas"),
    pytest.param(TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, "", f"{HMAC_KEY_ENV} is not set", id="no hmac key"),
    pytest.param("not-a-key", TEST_BUSINESS_NUMBER_HMAC_KEY, ENCRYPTION_KEYS_ENV, id="not base64"),
    pytest.param("c2hvcnQ=", TEST_BUSINESS_NUMBER_HMAC_KEY, ENCRYPTION_KEYS_ENV, id="too short"),
    pytest.param("키", TEST_BUSINESS_NUMBER_HMAC_KEY, ENCRYPTION_KEYS_ENV, id="not ascii"),
    pytest.param(TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, "c2hvcnQ=", HMAC_KEY_ENV, id="short hmac key"),
    pytest.param(TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, "not-a-key", HMAC_KEY_ENV, id="hmac key not base64"),
    pytest.param(TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, "키", HMAC_KEY_ENV, id="hmac key not ascii"),
    pytest.param(
        f"{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY},{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY}",
        TEST_BUSINESS_NUMBER_HMAC_KEY,
        "the same key twice",
        id="repeated key",
    ),
    pytest.param(
        f"{TEST_BUSINESS_NUMBER_NEXT_KEY},{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY}",
        TEST_BUSINESS_NUMBER_ENCRYPTION_KEY,
        "must differ",
        id="hmac key reused",
    ),
]
