try:
    from app.routes.alerts import router as alerts_router
    from app.routes.user import router as user_router
    from app.routes.prices import router as prices_router
    from app.routes.admin import router as admin_router
    from app.routes.symbols import router as symbols_router
    from app.routes.telegram import router as telegram_router
except ImportError:
    alerts_router = None
    user_router = None
    prices_router = None
    admin_router = None
    symbols_router = None
    telegram_router = None
