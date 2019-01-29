__all__ = [
    'BaseError',
    'ExchangeError',
    'NotSupported',
    'BadResponse',
    'NullResponse',
    'AuthenticationError',
    'PermissionDenied',
    'AccountSuspended',
    'InsufficientFunds',
    'InvalidOrderBook',
    'OrderBookEmpty',
    'QuotationError',
    'InvalidOrder',
    'OrderNotFound',
    'CancelPending',
    'OrderNotPlaced',
    'OrderTooSmall',
    'InvalidAddress',
    'AddressPending',
    'InvalidWithdrawal',
    'NetworkError',
    'DDoSProtection',
    'RequestTimeout',
    'ExchangeNotAvailable',
    'InvalidNonce',
]


class BaseError(Exception):
    """Base class for all exceptions"""
    pass


class ExchangeError(BaseError):
    """"Raised when an exchange server replies with an error in JSON"""
    pass


class NotSupported(ExchangeError):
    """Raised if the endpoint is not offered/not yet supported by the exchange API"""
    pass


class BadResponse(ExchangeError):
    """Raised if the endpoint returns a bad response from the exchange API"""
    pass


class NullResponse(BadResponse):
    """Raised if the endpoint returns a null response from the exchange API"""
    pass


class AuthenticationError(ExchangeError):
    """Raised when API credentials are required but missing or wrong"""
    pass


class PermissionDenied(AuthenticationError):
    """Raised when API credentials are required but missing or wrong"""
    pass


class AccountSuspended(AuthenticationError):
    """Raised when user account has been suspended or deactivated by the exchange"""
    pass


class InsufficientFunds(ExchangeError):
    """Raised when you don't have enough currency on your account balance to place an order"""
    pass


class InvalidOrderBook(ExchangeError):
    """"Base class for all exceptions to the order book"""
    pass


class OrderBookEmpty(InvalidOrderBook):
    """Raised when the order book has no orders"""
    pass


class QuotationError(InvalidOrderBook):
    """Raised when the order book doesn't have enough volume to cover the quote"""
    pass


class InvalidOrder(ExchangeError):
    """"Base class for all order related exceptions"""
    pass


class OrderNotFound(InvalidOrder):
    """Raised when you are trying to fetch or cancel a non-existent order"""
    pass


class CancelPending(InvalidOrder):
    """Raised when an order that is already pending cancel is being canceled again"""
    pass


class OrderNotPlaced(InvalidOrder):
    """Raised when failing to place an order"""
    pass


class OrderTooSmall(InvalidOrder):
    """Raised when the order's amount is less than the minimum amount for the market"""
    pass


class InvalidAddress(ExchangeError):
    """Raised on invalid funding address"""
    pass


class AddressPending(InvalidAddress):
    """Raised when the address requested is pending (not ready yet, retry again later)"""
    pass


class InvalidWithdrawal(ExchangeError):
    """Raised when failing withdraw funds"""
    pass


class NetworkError(BaseError):
    """Base class for all errors related to networking"""
    pass


class DDoSProtection(NetworkError):
    """Raised whenever DDoS protection restrictions are enforced per user or region/location"""
    pass


class RequestTimeout(NetworkError):
    """Raised when the exchange fails to reply in .timeout time"""
    pass


class ExchangeNotAvailable(NetworkError):
    """Raised if a reply from an exchange contains keywords related to maintenance or downtime"""
    pass


class InvalidNonce(NetworkError):
    """Raised in case of a wrong or conflicting nonce number in private requests"""
    pass
