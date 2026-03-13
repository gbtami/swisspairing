"""Project exceptions."""


class PairingError(RuntimeError):
    """Raised when a pairing step can not be completed as requested."""


class ExactSearchUnavailableError(PairingError):
    """Raised when the exact Dutch solver does not yet support a bracket shape."""
