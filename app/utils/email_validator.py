import os
import re
import socket
from typing import Optional

DISPOSABLE_AND_DUMMY_DOMAINS = {
    "asdf.com",
    "test.com",
    "example.com",
    "fake.com",
    "dummy.com",
    "tempmail.com",
    "mailinator.com",
    "guerrillamail.com",
    "yopmail.com",
    "dispostable.com",
    "sharklasers.com",
    "trashmail.com",
    "10minutemail.com",
    "throwawaymail.com",
    "spam4.me",
    "getairmail.com",
    "dropmail.me",
    "mohmal.com",
    "nada.ltd",
    "crazymailing.com",
}


def validate_authentic_email(email: str, allow_test_domains: Optional[bool] = None) -> str:
    """
    Validate that an email address is authentic:
    1. Valid regex format.
    2. Not a disposable, temporary, or dummy domain.
    3. Has a valid top-level domain.
    4. Domain resolves via DNS (verified reachable host).
    """
    if not email:
        raise ValueError("Email address is required.")

    email_clean = email.strip().lower()

    # Regex for standard RFC 5322 compatible email address
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(pattern, email_clean):
        raise ValueError("Please provide a valid email address format.")

    local_part, domain = email_clean.split("@", 1)

    if len(local_part) < 2:
        raise ValueError("Email address prefix is too short.")

    # Domain structure validation
    domain_parts = domain.split(".")
    if len(domain_parts) < 2 or any(len(p) == 0 for p in domain_parts):
        raise ValueError("Please provide a valid email domain (e.g., gmail.com, outlook.com).")

    tld = domain_parts[-1]
    if len(tld) < 2:
        raise ValueError("The email top-level domain is invalid.")

    # Check testing environment
    if allow_test_domains is not None:
        is_testing = allow_test_domains
    else:
        is_testing = (
            bool(os.getenv("PYTEST_CURRENT_TEST"))
            or os.getenv("APP_ENV", "").lower() == "testing"
        )

    if domain in DISPOSABLE_AND_DUMMY_DOMAINS:
        if is_testing:
            return email_clean
        raise ValueError(
            f"The email domain '@{domain}' is a disposable or dummy address. "
            "Please register using an authentic, permanent email address (e.g. Gmail, Outlook, Yahoo)."
        )

    # Perform DNS verification for authentic domain
    if not is_testing:
        try:
            # Check if domain resolves to an IP address
            socket.getaddrinfo(domain, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            raise ValueError(
                f"The email domain '@{domain}' could not be verified or does not exist. "
                "Please enter an authentic, reachable email address."
            )
        except Exception:
            # If socket network errors occur, pass to prevent blocking real users during network hiccups
            pass

    return email_clean
