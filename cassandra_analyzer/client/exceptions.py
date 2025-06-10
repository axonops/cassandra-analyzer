"""
Custom exceptions for AxonOps API client
"""


class AxonOpsAPIError(Exception):
    """Base exception for AxonOps API errors"""
    pass


class AxonOpsAuthError(AxonOpsAPIError):
    """Authentication error"""
    pass


class AxonOpsConnectionError(AxonOpsAPIError):
    """Connection error"""
    pass


class AxonOpsNotFoundError(AxonOpsAPIError):
    """Resource not found error"""
    pass


class AxonOpsRateLimitError(AxonOpsAPIError):
    """Rate limit exceeded error"""
    pass