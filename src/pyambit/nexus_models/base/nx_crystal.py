# GENERATED FILE - DO NOT EDIT.
# Regenerate with: poetry run python dev-tools/gen_nexus_models.py --appdef NXraman
# Source: NeXus application definition "NXraman", resolved via
# pynxtools.nexus.nexus_tree.generate_tree_from (walks the NXDL `extends` chain).

from __future__ import annotations

from typing import ClassVar, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from pyambit.datamodel import Value


class NXCrystal(BaseModel):
    """Use as many crystals as necessary to describe"""

    model_config = ConfigDict(populate_by_name=True)
    NX_CLASS: ClassVar[str] = 'NXcrystal'

    pass
