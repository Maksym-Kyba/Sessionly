from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from app.accounts.dependencies import get_current_psychologist_id
from app.accounts.models import Psychologist
from app.core.config import settings
from app.core.database import get_db
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def isolated_database_url() -> Iterator[URL]:
    if settings.test_database_url is None:
        raise RuntimeError(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL URL before running tests"
        )
    configured_url = make_url(settings.test_database_url)
    database_name = f"sessionly_test_{uuid4().hex}"
    admin_engine = create_engine(
        configured_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    test_url = configured_url.set(database=database_name)
    try:
        yield test_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def database_engine(isolated_database_url: URL):
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    original_database_url = settings.database_url
    settings.database_url = isolated_database_url.render_as_string(hide_password=False)
    try:
        command.upgrade(alembic_config, "head")
    finally:
        settings.database_url = original_database_url

    engine = create_engine(isolated_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_database(database_engine) -> Iterator[None]:
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE auth_sessions, google_identities, oauth_transactions, "
                "availability_slots, availability_rules, psychologists CASCADE"
            )
        )
    yield


@pytest.fixture
def psychologist(database_engine) -> Psychologist:
    factory = sessionmaker(bind=database_engine)
    with factory.begin() as session:
        psychologist = Psychologist(
            display_name="Test Psychologist",
            email="psychologist@example.test",
            time_zone="Europe/Kyiv",
        )
        session.add(psychologist)
        session.flush()
        session.expunge(psychologist)
    return psychologist


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def authenticated_client(database_engine, psychologist) -> Iterator[AsyncClient]:
    factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_psychologist_id] = lambda: psychologist.id
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def api_client(database_engine) -> Iterator[AsyncClient]:
    factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
