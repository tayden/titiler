"""TiTiler STAC Demo endpoint."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Type, Union

import pkg_resources
from rio_tiler_crs import STACReader

from ..dependencies import DefaultDependency
from ..models.dataset import Info, Metadata
from .factory import TMSTilerFactory

from fastapi import Depends, Query

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates

template_dir = pkg_resources.resource_filename("titiler", "templates")
templates = Jinja2Templates(directory=template_dir)


@dataclass
class AssetsBidxParams(DefaultDependency):
    """Asset and Band indexes parameters."""

    assets: Optional[str] = Query(
        None,
        title="Asset indexes",
        description="comma (',') delimited asset names (might not be an available options of some readers)",
    )
    bidx: Optional[str] = Query(
        None, title="Band indexes", description="comma (',') delimited band indexes",
    )

    def __post_init__(self):
        """Post Init."""
        if self.assets is not None:
            self.kwargs["assets"] = self.assets.split(",")
        if self.bidx is not None:
            self.kwargs["indexes"] = tuple(
                int(s) for s in re.findall(r"\d+", self.bidx)
            )


@dataclass
class AssetsBidxExprParams(DefaultDependency):
    """Assets, Band Indexes and Expression parameters."""

    assets: Optional[str] = Query(
        None,
        title="Asset indexes",
        description="comma (',') delimited asset names (might not be an available options of some readers)",
    )
    expression: Optional[str] = Query(
        None,
        title="Band Math expression",
        description="rio-tiler's band math expression (e.g B1/B2)",
    )
    bidx: Optional[str] = Query(
        None, title="Band indexes", description="comma (',') delimited band indexes",
    )

    def __post_init__(self):
        """Post Init."""
        if self.assets is not None:
            self.kwargs["assets"] = self.assets.split(",")
        if self.expression is not None:
            self.kwargs["expression"] = self.expression
        if self.bidx is not None:
            self.kwargs["indexes"] = tuple(
                int(s) for s in re.findall(r"\d+", self.bidx)
            )


@dataclass
class STACTiler(TMSTilerFactory):
    """Custom Tiler Class for STAC."""

    reader: Type[STACReader] = STACReader

    layer_dependency: Type[DefaultDependency] = AssetsBidxExprParams

    # Overwrite _info method to return the list of assets when no assets is passed.
    def info(self):
        """Register /info endpoint."""

        @self.router.get(
            "/info",
            response_model=Union[List[str], Dict[str, Info]],
            response_model_exclude={"minzoom", "maxzoom", "center"},
            response_model_exclude_none=True,
            responses={200: {"description": "Return dataset's basic info."}},
        )
        def info(
            src_path=Depends(self.path_dependency),
            asset_params=Depends(AssetsBidxParams),
            kwargs: Dict = Depends(self.additional_dependency),
        ):
            """Return basic info."""
            reader = src_path.reader or self.reader
            with reader(src_path.url, **self.reader_options) as src_dst:
                if not asset_params.kwargs.get("assets"):
                    return src_dst.assets
                info = src_dst.info(**asset_params.kwargs, **kwargs)
            return info

    # Overwrite _metadata method because the STACTiler output model is different
    # cogMetadata -> Dict[str, cogMetadata]
    def metadata(self):
        """Register /metadata endpoint."""

        @self.router.get(
            "/metadata",
            response_model=Dict[str, Metadata],
            response_model_exclude={"minzoom", "maxzoom", "center"},
            response_model_exclude_none=True,
            responses={200: {"description": "Return dataset's metadata."}},
        )
        def metadata(
            src_path=Depends(self.path_dependency),
            asset_params=Depends(AssetsBidxParams),
            metadata_params=Depends(self.metadata_dependency),
            kwargs: Dict = Depends(self.additional_dependency),
        ):
            """Return metadata."""
            reader = src_path.reader or self.reader
            with reader(src_path.url, **self.reader_options) as src_dst:
                info = src_dst.metadata(
                    metadata_params.pmin,
                    metadata_params.pmax,
                    **asset_params.kwargs,
                    **metadata_params.kwargs,
                    **kwargs,
                )
            return info


stac = STACTiler(router_prefix="stac")


@stac.router.get("/viewer", response_class=HTMLResponse)
def stac_demo(request: Request):
    """STAC Viewer."""
    return templates.TemplateResponse(
        name="stac_index.html",
        context={
            "request": request,
            "tilejson": stac.url_for(request, "tilejson"),
            "metadata": stac.url_for(request, "info"),
        },
        media_type="text/html",
    )


router = stac.router
