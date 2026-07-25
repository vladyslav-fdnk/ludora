from .catalogue import router as catalogue_router
from .profile import router as profile_router
from .start import router as start_router

__all__ = ["catalogue_router", "profile_router", "start_router"]
