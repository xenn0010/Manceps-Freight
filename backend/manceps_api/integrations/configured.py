"""The set of external-service clients one app instance uses, built from settings or injected by tests."""

from __future__ import annotations

from dataclasses import dataclass

from manceps_core.loads.evaluate import DieselLookup, MilesLookup

from ..settings import Settings
from .broker_lookup import BrokerLookup, broker_lookup_from_settings
from .dev_verifier import phone_verifier_from_settings
from .freight_data import diesel_from_settings, miles_from_settings
from .mailer import Mailer, mailer_from_settings
from .twilio_verify import Verifier


@dataclass(frozen=True)
class Integrations:
    """Configured clients; None means the feature is not configured and its routes answer 503."""

    verifier: Verifier | None = None
    mailer: Mailer | None = None
    broker_lookup: BrokerLookup | None = None
    miles: MilesLookup | None = None
    diesel: DieselLookup | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> Integrations:
        """Build every client whose credentials are present.

        Args:
            settings: Application settings.

        Returns:
            The integrations.
        """
        return cls(verifier=phone_verifier_from_settings(settings), mailer=mailer_from_settings(settings),
                   broker_lookup=broker_lookup_from_settings(settings), miles=miles_from_settings(settings),
                   diesel=diesel_from_settings(settings))
