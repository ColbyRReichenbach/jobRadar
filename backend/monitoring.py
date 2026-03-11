import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration


_SENTRY_CONFIGURED = False


def configure_sentry() -> bool:
    global _SENTRY_CONFIGURED

    if _SENTRY_CONFIGURED:
        return True

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")),
        release=os.getenv("APP_VERSION"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
        integrations=[FastApiIntegration()],
    )
    _SENTRY_CONFIGURED = True
    return True
