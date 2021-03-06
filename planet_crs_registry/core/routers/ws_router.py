# -*- coding: utf-8 -*-
# Planet CRS Registry - The coordinates reference system registry for solar bodies
# Copyright (C) 2021 - CNES (Jean-Christophe Malapert for Pôle Surfaces Planétaires)
#
# This file is part of Planet CRS Registry.
#
# Planet CRS Registry is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License v3  as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Planet CRS Registry is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License v3  for more details.
#
# You should have received a copy of the GNU Lesser General Public License v3
# along with Planet CRS Registry.  If not, see <https://www.gnu.org/licenses/>.
"""Services router"""
import logging
import pathlib
import re
import smtplib
from email.mime.text import MIMEText
from typing import List
from typing import Optional

from fastapi import APIRouter
from fastapi import Path
from fastapi import Query
from fastapi import status
from starlette.exceptions import HTTPException
from tortoise import Tortoise
from tortoise.contrib.fastapi import HTTPNotFoundError
from tortoise.functions import Lower

from ..business import query_search
from ..business import WktDatabase
from ..models import CenterCs
from ..models import WKT_model
from ..models import Wkt_Pydantic
from planet_crs_registry.config import tortoise_config

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter()

LIMIT_QUERY = Query(
    50, description="Number of records to display", gt=-1, le=100
)
OFFSET_QUERY = Query(
    0, description="Number of records from which we start to display", gt=-1
)


@router.get(
    "/wkts",
    summary="Get information about WKTs.",
    response_model=List[Wkt_Pydantic],  # type: ignore
    description="Lists all WKTs regardless of version",
    tags=["Browse by WKT"],
)
async def get_wkts(
    limit: Optional[int] = LIMIT_QUERY, offset: Optional[int] = OFFSET_QUERY
) -> List[Wkt_Pydantic]:  # type: ignore
    """Lists all WKTs regardless of version.

    The number of WKTs to display is paginated.

    Args:
        limit (Optional[int], optional): Number of records to display.
        Defaults to 50.
        offset (Optional[int], optional): Number of record from which we start
        to display. Defaults to 0.

    Returns:
        List[Wkt_Pydantic]: The JSON representation of the list of all WKTs
    """
    return await Wkt_Pydantic.from_queryset(
        WKT_model.all().limit(limit).offset(offset)  # type: ignore
    )


@router.get(
    "/wkts/count",
    summary="Count the number of WKTs.",
    response_model=int,
    description="Count the number of WKT regardless of version",
    tags=["Browse by WKT"],
)
async def wkts_count() -> int:
    """Count the number of WKTs.

    Returns:
        int: The number of WKTs
    """
    return await WKT_model.all().count()


@router.get(
    "/versions",
    summary="Get the list of WKTs version.",
    response_model=List[int],
    description="List all available versions of the WKT based on IAU reports.",
    tags=["Browse by WKT version"],
)
async def get_versions() -> List[int]:
    """List all available versions of the WKT based on IAU reports

    Returns:
        List[int]: the list of versions
    """
    objs = (
        await WKT_model.all()
        .group_by("version")
        .order_by("version")
        .values("version")
    )
    versions = list()
    for obj in objs:
        versions.append(obj["version"])
    return versions


@router.get(
    "/versions/{version_id}",
    summary="Get information about WKTs for a given version",
    response_model=List[Wkt_Pydantic],  # type: ignore
    responses={status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError}},
    description="List WKTs for a given version",
    tags=["Browse by WKT version"],
)
async def get_version(
    version_id: int = Path(
        default=2015, description="Version of the WKT", gt=2014
    ),
    limit: Optional[int] = LIMIT_QUERY,
    offset: Optional[int] = OFFSET_QUERY,
) -> List[WKT_model]:
    """List WKTs for a given version.

    Args:
        version_id (int, optional): Version of the WKT to search.
        Defaults to 2015.
        limit (Optional[int], optional): Number of records to display.
        Defaults to 50.
        offset (Optional[int], optional): Number of records from which we
        start to display. Defaults to 0.

    Raises:
        HTTPException: Version not found

    Returns:
        List[WKT_model]: List of WKTs for a given version
    """
    obj = (
        await WKT_model.filter(version=version_id).limit(limit).offset(offset)  # type: ignore
    )
    if len(obj) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{version_id} not found",
        )
    return obj


@router.get(
    "/versions/{version_id}/count",
    summary="Count the number of WKTs for a given version",
    response_model=int,
    description="Count the number of WKTs for a given version",
    tags=["Browse by WKT version"],
)
async def version_count(
    version_id: int = Path(
        default=2015,
        description="Count the number of WKTs for a given version",
        gt=2014,
    )
) -> int:
    """Count the number of WKTs for a given version.

    Args:
        version_id (int, optional): version. Defaults to 2015.

    Returns:
        int: The number of WKTs for a given version
    """
    return await WKT_model.filter(version=version_id).count()


@router.get(
    "/versions/{version_id}/{wkt_id}",
    summary="Get a WKT for a given version.",
    description="Retrieve a WKT",
    tags=["Browse by WKT version"],
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError},
        status.HTTP_400_BAD_REQUEST: {"model": HTTPNotFoundError},
    },
)
async def get_wkt_version(
    version_id: int = Path(
        default=2015, description="Version of the WKT", gt=2014
    ),
    wkt_id: str = Path(
        default="IAU:2015:1000",
        description="Identifier of the WKT",
        regex="^.*:\d*:\d*$",  # noqa: W605  # pylint: disable=W1401
    ),
) -> str:
    """Get a WKT representation for both a given version and WKT Id

    Args:
        version_id (int, optional): Version of the WKT. Defaults to 2015.
        wkt_id (str, optional): Identifier of the WKT. Defaults to IAU:2015:1000.

    Raises:
        HTTPException: Version or WKT Id not found

    Returns:
        str: The WKT representation
    """
    wkt_obj: WKT_model = await query_search.get_wkt_obj(wkt_id)
    if wkt_obj.version != version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Wrong version {version_id} for this WKT {wkt_id}",
        )
    return wkt_obj.wkt


@router.get(
    "/wkts/{wkt_id}",
    summary="Get a WKT",
    response_model=str,
    responses={status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError}},
    description="Retrieve a WKT for a given WKT ID.",
    tags=["Browse by WKT"],
)
async def get_wkt(
    wkt_id: str = Path(
        default="IAU:2015:1000",
        title="ID of the WKT.",
        description="ID of the WKT following this pattern : IAU:<version>:<code>",
        regex="^.*:\d*:\d*",  # noqa: W605  # pylint: disable=W1401
    ),
) -> str:
    """Get a WKT representation for a given WKT identifier.

    Args:
        wkt_id (str, optional): ID of the WKT. Defaults to IAU:2015:1000.

    Returns:
        str: The WKT representation
    """
    wkt_obj: WKT_model = await query_search.get_wkt_obj(wkt_id)
    return wkt_obj.wkt


@router.get(
    "/solar_bodies",
    summary="Get solar bodies",
    description="Lists all available solar bodies",
    response_model=List[str],
    tags=["Browse by solar body"],
)
async def get_solar_bodies() -> List[str]:
    """List all solar bodies.

    Returns:
        List[str]: all solar bodies
    """
    objs = (
        await WKT_model.all()
        .group_by("solar_body")
        .order_by("solar_body")
        .values("solar_body")
    )
    solar_bodies = list()
    for obj in objs:
        solar_bodies.append(obj["solar_body"])
    return solar_bodies


@router.get(
    "/solar_bodies/count",
    summary="Count the number of solar bodies",
    description="Count all available solar bodies",
    response_model=int,
    tags=["Browse by solar body"],
)
async def solar_bodies_count() -> int:
    """Count the number of solar bodies.

    Returns:
        int: The number of solar bodies
    """
    objs = (
        await WKT_model.all()
        .group_by("solar_body")
        .order_by("solar_body")
        .values("solar_body")
    )
    solar_bodies = list()
    for obj in objs:
        solar_bodies.append(obj["solar_body"])
    return len(solar_bodies)


@router.get(
    "/solar_bodies/{solar_body}",
    summary="Get information about WKTs for a given solar body",
    description="Lists all WKTs for a given solar body",
    response_model=List[Wkt_Pydantic],  # type: ignore
    responses={status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError}},
    tags=["Browse by solar body"],
)
async def get_solar_body(
    solar_body: str,
    limit: Optional[int] = LIMIT_QUERY,
    offset: Optional[int] = OFFSET_QUERY,
) -> List[WKT_model]:
    """Lists all WKTs for a given solar body.

    Args:
        solar_body (str): solar body to search
        limit (Optional[int], optional): Number of records to display.
        Defaults to 50.
        offset (Optional[int], optional): Number of records from which we
        start to display. Defaults to 0.

    Raises:
        HTTPException: Solar body not found

    Returns:
        List[WKT_model]: all WKTs for a given solar body
    """
    obj = (
        await WKT_model.annotate(solar_body_lower=Lower("solar_body"))
        .filter(solar_body_lower=solar_body.lower())
        .limit(limit)  # type: ignore
        .offset(offset)  # type: ignore
    )
    if len(obj) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{solar_body} not found",
        )
    return obj


@router.get(
    "/solar_bodies/{solar_body}/count",
    summary="Count the number of WKTs for a given solar body",
    description="Count the number of WKTs for a given solar body",
    response_model=int,
    responses={status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError}},
    tags=["Browse by solar body"],
)
async def get_solar_body_count(
    solar_body: str,
    limit: Optional[int] = LIMIT_QUERY,
    offset: Optional[int] = OFFSET_QUERY,
) -> int:
    """Count the number of WKT for a give solar body.

    Args:
        solar_body (str): solar body to search
        limit (Optional[int], optional): Number of records to display.
        Defaults to 50.
        offset (Optional[int], optional): Number of records from which we
        start to display. Defaults to 0.

    Returns:
        int: the number of WKT for a give solar body
    """
    obj = (
        await WKT_model.annotate(solar_body_lower=Lower("solar_body"))
        .filter(solar_body_lower=solar_body.lower())
        .limit(limit)  # type: ignore
        .offset(offset)  # type: ignore
        .count()
    )
    return obj


@router.get(
    "/solar_bodies/{solar_body}/{wkt_id}",
    summary="Get a WKT for a given solar body.",
    description="Retrieve a WKT",
    tags=["Browse by solar body"],
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError},
        status.HTTP_400_BAD_REQUEST: {"model": HTTPNotFoundError},
    },
)
async def get_wkt_body(
    solar_body: str,
    wkt_id: str = Path(
        default="IAU:2015:1000",
        description="Identifier of the WKT",
        regex="^.*:\d*:\d*$",  # noqa: W605  # pylint: disable=W1401
    ),
) -> str:
    """Get a WKT representation for both a given solar body and a WKT identifier.

    Args:
        solar_body (str): solar body
        wkt_id (str, optional): Identifier of the WKT. Defaults to IAU:2015:1000.

    Raises:
        HTTPException: solar body not found

    Returns:
        str: The WKT representation
    """
    wkt_obj: WKT_model = await query_search.get_wkt_obj(wkt_id)
    if wkt_obj.solar_body.lower() != solar_body.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{wkt_id} not found for {solar_body}",
        )
    return wkt_obj.wkt


@router.get(
    "/search",
    summary="Search a WKT by keyword",
    description="Search a WKT by keyword",
    tags=["Search"],
    response_model=List[Wkt_Pydantic],  # type: ignore
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError},
    },
)
async def search(
    search_term_kw: str,
    limit: int = LIMIT_QUERY,
    offset: int = OFFSET_QUERY,
) -> List[WKT_model]:
    """Search WKTs for a given keyword.

    Args:
        search_term_kw (str): Term to search
        limit (int, optional):  Number of records to display.. Defaults to LIMIT_QUERY.
        offset (int, optional): Number of records from which we start to display. Defaults to OFFSET_QUERY.

    Returns:
        List[WKT_model]: WKTs matching the keyword
    """
    return await query_search.search_term(search_term_kw, limit, offset)


@router.get(
    "/search/count",
    summary="Count WKT by keyword",
    description="Count WKT by keyword",
    tags=["Search"],
    response_model=int,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPNotFoundError},
    },
)
async def search_count(
    search_term_kw: str,
) -> int:
    """Count the number of results matching WKTs for a given keyword.

    Args:
        search_term_kw (str): keyword

    Returns:
        int: The number of results matching WKTs for a given keyword
    """
    return await query_search.search_term_count(search_term_kw)


@router.on_event("startup")
async def startup_event():
    """Startup the server."""
    pattern = "sqlite://(?P<db_name>.*)"
    match = re.match(pattern, tortoise_config.db_url)
    file = None
    if match is not None:
        file = pathlib.Path(match.group("db_name"))

    if file is None or not file.exists():
        await Tortoise.init(
            db_url=tortoise_config.db_url, modules=tortoise_config.modules
        )
        await Tortoise.generate_schemas()
        wkt = WktDatabase()
        index = wkt.index
        logger.info("nb records : %s", len(index))
        for record in index:
            wkt_data = {
                "id": f"IAU:{record.iau_version}:{record.iau_code}",
                "version": int(record.iau_version),
                "code": int(record.iau_code),
                "solar_body": re.match(r"[^\s]+", record.datum).group(0),
                "datum_name": record.datum,
                "ellipsoid_name": record.ellipsoid,
                "projection_name": record.projcrs,
                "wkt": record.wkt,
            }
            await WKT_model.create(**wkt_data)
        logger.info("Database loaded")
    else:
        logger.info("loading the db")


@router.on_event("shutdown")
async def close_orm():
    """Shutdown the server"""
    await Tortoise.close_connections()
