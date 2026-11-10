"""Keys for the stored business registration numbers in tests (app/core/business_number_crypto.py).

Made with Fernet.generate_key() for the tests only; they protect no real data.
"""

TEST_BUSINESS_NUMBER_ENCRYPTION_KEY = "BPv6wXLkyKmt-7A7qXDXqK-BsT8HEjb5QS2K4qw_Fns="
TEST_BUSINESS_NUMBER_HMAC_KEY = "vClA_8_T6P9JDDo4iiSzfQV6u0Xm9499ueOCMmEAtkg="
# A second encryption key, for key rotation tests.
TEST_BUSINESS_NUMBER_NEXT_KEY = "4PhNxB6zQEewbcKE5bsSXuLd_Wp0Yo-4hlDlgLgDVl4="
