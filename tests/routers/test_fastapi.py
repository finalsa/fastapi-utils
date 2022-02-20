from typing import Optional
import logging
import logging.config
from fastapi.testclient import TestClient
import sys, os

import pytest_asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi_helpers import (
    DbConfig, 
    DefaultSettings, 
    DefaultModelRouter, 
    BaseCrud, 
    Worker,
    get_logger_default_config,
)


import databases
import pytest
import sqlalchemy
from fastapi import FastAPI

import ormar


settings = DefaultSettings()
settings.env = "test"
logging.config.dictConfig(get_logger_default_config(settings))
logger = logging.getLogger("fastapi")
db_config = DbConfig(settings, logger)



app = FastAPI()
metadata = sqlalchemy.MetaData()
database = databases.Database("sqlite:///test.db", force_rollback=True)
app.state.database = database


@app.on_event("startup")
async def startup() -> None:
    database_ = app.state.database
    if not database_.is_connected:
        await database_.connect()


@app.on_event("shutdown")
async def shutdown() -> None:
    database_ = app.state.database
    if database_.is_connected:
        await database_.disconnect()


class LocalMeta:
    metadata = metadata
    database = database


class Item(ormar.Model):
    class Meta(LocalMeta):
        pass

    id: int = ormar.Integer(primary_key=True)
    name: str = ormar.String(max_length=100)
    pydantic_int: Optional[int]

    async def load_data(self):
        return self



crud = BaseCrud(Item)

router = DefaultModelRouter(Item, crud)

@pytest_asyncio.fixture(autouse=True, scope="module")
def create_test_database():
    engine = sqlalchemy.create_engine("sqlite:///test.db")
    metadata.create_all(engine)
    yield
    metadata.drop_all(engine)


app = FastAPI(
    title="Tests",
    version=settings.version,
    on_startup=[db_config.connect_db],
    on_shutdown=[db_config.disconnect_db],
    openapi_url=settings.get_open_api_path()
)


app.include_router(router.router, )
worker = Worker(db_config, logger)


client = TestClient(app)


@pytest.mark.asyncio()
async def test_read_main():
    await crud.create(Item(name="test", id = 1))
    response = client.request("GET","/")
    assert len(response.json()) == 1
    assert response.status_code == 200

@pytest.mark.asyncio()
async def test_read_one():
    response = client.request("GET","/1/")
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_read_none():
    response = client.request("GET","/100/")
    assert response.status_code == 404


@pytest.mark.asyncio()
async def test_write_one():
    response = client.request("POST","/", json={"name": "test2"})
    assert response.status_code == 201

@pytest.mark.asyncio()
async def test_update_one():
    response = client.request("PUT","/1/", json={"name": "test3"})
    assert response.status_code == 202

@pytest.mark.asyncio()
async def test_update_none():
    response = client.request("PUT","/100/", json={"name": "test3"})
    assert response.status_code == 404

@pytest.mark.asyncio()
async def test_delete_one():
    response = client.request("DELETE","/1/")
    assert response.status_code == 202


@pytest.mark.asyncio()
async def test_delete_none():
    response = client.request("DELETE","/1000/")
    assert response.status_code == 404