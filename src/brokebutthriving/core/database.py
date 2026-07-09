"""Database core connection configuration and session dependencies."""
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from brokebutthriving.core.config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


# Dependency generator yielding a SQLModel Session context
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

