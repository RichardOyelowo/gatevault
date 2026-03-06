import warnings

class ShortKeyWarning(Warning):
    """Raised when secret key is below the recommended 32 bytes lenght"""
