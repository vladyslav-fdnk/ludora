"""Backend API integration."""

from .client import BackendClient
from .schemas import Product, ProductPage

__all__ = ["BackendClient", "Product", "ProductPage"]
