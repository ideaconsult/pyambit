import os.path
import tempfile
import uuid

import nexusformat.nexus.tree as nx
import numpy as np
import pyambit.datamodel as mx
from pyambit.nexus_spectra import spe2ambit


def test():
    tag = "test"
    prefix = "TEST"
    substance = mx.SubstanceRecord(name=tag, publicname=tag, ownerName="TEST")
    substance.i5uuid = "{}-{}".format(prefix, uuid.uuid5(uuid.NAMESPACE_OID, tag))

    papp = spe2ambit(
        x=np.random.rand(10),
        y=np.random.rand(10),
        meta={"test": "test"},
        instrument=None,
        wavelength=None,
        provider="FNMT",
        investigation="Round Robin 1",
        sample="PST",
        sample_provider="CHARISMA",
        prefix="CRMA",
        endpointtype="RAW_DATA",
        unit="cm-1",
    )

    substance.study = [papp]

    substances = mx.Substances(substance=[substance])
    nxroot = nx.NXroot()
    substances.to_nexus(nxroot)
    file = os.path.join(tempfile.gettempdir(), "spectra_{}.nxs".format(tag))
    print(file)
    nxroot.save(file, mode="w")
