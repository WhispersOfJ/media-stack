"""SQLAlchemy models for the evolved control-panel backend. Imported here
so Base.metadata sees every table before Alembic autogenerate or
create_all runs - see core/db.py."""
from models.user import User  # noqa: F401
from models.setting import Setting  # noqa: F401
from models.api_key import ApiKey  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
