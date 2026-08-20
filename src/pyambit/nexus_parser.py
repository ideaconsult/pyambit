import traceback
from typing import Dict

import nexusformat.nexus as nx

from pyambit.datamodel import (
    Citation,
    Component,
    CompositionEntry,
    Compound,
    EffectRecord,
    EffectResult,
    EndpointCategory,
    ExternalIdentifier,
    Protocol,
    ProtocolApplication,
    SampleLink,
    SubstanceRecord,
    Substances,
    Value,
)


class Nexus2Ambit:

    def __init__(self, domain: str, index_only: True):
        self.substances: Dict[str, SubstanceRecord] = {}
        self.domain = domain
        self.index_only = index_only

    def __enter__(self):
        self.clear()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Any cleanup code, if needed
        pass

    def clear(self):
        self.substances = {}

    def composition_from_nexus(self, nxentry: nx.NXentry) -> list:
        """Read back the NXsample_component children SubstanceRecord.to_nexus
        writes under a substance's NXsample entry (one child per
        CompositionEntry, named "{relation minus 'HAS_'}_{index}"). Returns
        None if the entry has none, matching CompositionEntry's own
        Optional[List[...]] contract rather than an empty list.
        """
        entries = []
        for _name, child in nxentry.items():
            if not isinstance(child, nx.NXsample_component):
                continue
            compound = Compound(
                name=child.get("name").nxvalue if "name" in child else None,
                # "chemical_formula" is the real NXDL field name (see
                # nexus_writer.py's matching fix); "formula" was the old,
                # schema-mismatched field this never round-tripped through.
                formula=(
                    child.get("chemical_formula").nxvalue
                    if "chemical_formula" in child
                    else None
                ),
                cas=child.attrs.get("cas"),
                einecs=child.attrs.get("einecs"),
                inchi=child.attrs.get("inchi"),
                inchikey=child.attrs.get("inchikey"),
            )
            description = child.get("description")
            entries.append(
                CompositionEntry(
                    component=Component(compound=compound),
                    # to_nexus writes the FULL relation string here (e.g.
                    # "HAS_COMPONENT"), not the "HAS_"-stripped form used
                    # only for the node's own name -- read it back verbatim.
                    relation=(
                        description.nxvalue if description is not None else "HAS_COMPONENT"
                    ),
                )
            )
        return entries or None

    def substance_from_nexus(self, nxentry: nx.NXentry) -> SubstanceRecord:
        try:
            # Written as two parallel string-array attrs by
            # nexus_writer.to_nexus (NeXus/HDF5 attrs can't hold a list of
            # structs directly) -- zip them back into ExternalIdentifier
            # pairs. Both absent is the normal case (most substances have
            # none); a length mismatch never happens since the writer only
            # ever writes both together from the same list. h5py collapses
            # a length-1 string array attr back to a bare str on read (not
            # a list), which would otherwise zip element-by-CHARACTER
            # instead of by-identifier -- wrap any bare str back into a
            # single-element list first (confirmed via a real write/read
            # round-trip with one external identifier).
            ext_types = nxentry.attrs.get("externalIdentifierTypes")
            ext_ids = nxentry.attrs.get("externalIdentifierIds")
            if isinstance(ext_types, str):
                ext_types = [ext_types]
            if isinstance(ext_ids, str):
                ext_ids = [ext_ids]
            external_identifiers = (
                [
                    ExternalIdentifier(type=ext_type, id=ext_id)
                    for ext_type, ext_id in zip(ext_types, ext_ids)
                ]
                if ext_types is not None and ext_ids is not None
                else None
            )
            record = SubstanceRecord(
                URI=None,
                ownerUUID=nxentry.attrs["ownerUUID"],
                ownerName=nxentry.attrs["ownerName"],
                i5uuid=nxentry.attrs["uuid"],
                name=nxentry["name"].nxdata,
                publicname=nxentry.attrs["publicname"],
                format="NeXus",
                substanceType=nxentry.attrs.get("substanceType", "CHEBI_59999"),
                referenceSubstance=None,
                externalIdentifiers=external_identifiers,
                study=[],
                composition=self.composition_from_nexus(nxentry),
            )
            return record
        except Exception as err:
            print(traceback.format_exc())
            raise err

    def parse_substances(self, nxentry: nx.NXentry):
        for _entry_name, entry in nxentry.items():
            if isinstance(entry, nx.NXsample):
                record: SubstanceRecord = self.substance_from_nexus(entry)
                if record.i5uuid not in self.substances:
                    self.substances[record.i5uuid] = record

    def parse_studies(self, nxroot: nx.NXroot, relative_path: str):
        # "substance" and "investigation" are shared top-level groups
        # written once and linked from real study entries (see
        # nexus_writer.to_nexus), not study entries themselves -- neither
        # has a "definition" field, so parse_entry would fail on them.
        for entry_name, entry in nxroot.items():
            if entry_name not in ("substance", "investigation"):
                papp: ProtocolApplication = self.parse_entry(entry, relative_path)
                if papp.owner.substance.uuid in self.substances:
                    self.substances[papp.owner.substance.uuid].study.append(papp)

    def parse(self, nxroot: nx.NXroot, relative_path: str):
        for entry_name, entry in nxroot.items():
            if entry_name == "substance":
                self.parse_substances(entry)
        self.parse_studies(nxroot, relative_path)

    def get_substances(self):
        return Substances(substance=self.substances.values())

    def parse_entry(
        self, nxentry: nx.NXentry, relative_path: str
    ) -> ProtocolApplication:
        dox = nxentry.get("experiment_documentation", None)
        protocol = None
        parameters = {}
        if dox is not None:
            _protocol = dox.get("protocol", None)
            if _protocol is None:
                pass
            else:
                protocol = Protocol(
                    topcategory=_protocol.attrs["topcategory"],
                    category=EndpointCategory(code=_protocol.attrs["code"]),
                    endpoint=(
                        _protocol.attrs["endpoint"]
                        if "endpoint" in _protocol.attrs
                        else None
                    ),
                    guideline=[_protocol.attrs["guideline"]],
                )
        if protocol is None:
            if nxentry["definition"].nxvalue == "NXraman":
                protocol = protocol = Protocol(
                    "P-CHEM", "ANALYTICAL_METHODS_SECTION", "", ["Raman spectroscopy"]
                )
                parameters["E.method"] = nxentry["definition"].nxvalue
            else:
                protocol = protocol = Protocol("P-CHEM", "UNKNOWN", "", ["UNKNOWN"])

        _reference = nxentry.get("reference")
        citation = Citation(
            year=_reference["year"].nxdata,
            title=_reference["title"].nxdata,
            owner=_reference["owner"].nxdata,
        )

        try:
            wl = nxentry["instrument/beam_incident/wavelength"].nxdata
            wl_unit = nxentry["instrument/beam_incident/wavelength"].attrs["unit"]
            parameters["wavelength"] = Value(loValue=wl, unit=wl_unit)
        except:  # noqa: B001,E722 FIXME
            parameters["wavelength"] = None

        try:
            instrument_model = nxentry["instrument/device_information/model"].nxvalue
            instrument_vendor = nxentry["instrument/device_information/vendor"].nxvalue
            parameters["instrument"] = "{} {}".format(
                instrument_vendor, instrument_model
            )
        except:  # noqa: B001,E722 FIXME
            pass

        try:
            parameters["E.method"] = nxentry[
                "experiment_documentation/E.method"
            ].nxvalue
        except Exception:
            parameters["E.method"] = nxentry["definition"].nxvalue

        # the sample
        try:
            _owner = SampleLink.create(
                sample_uuid=nxentry["sample/substance"].attrs["uuid"],
                sample_provider=nxentry["sample/provider"].nxdata,
            )
        except Exception as err:
            raise ValueError(err)

        papp: ProtocolApplication = ProtocolApplication(
            uuid=nxentry.get("entry_identifier_uuid").nxvalue,
            interpretationResult=None,
            interpretationCriteria=None,
            parameters=parameters,
            citation=citation,
            effects=[],
            owner=_owner,
            protocol=protocol,
            investigation_uuid=nxentry.get("collection_identifier").nxvalue,
            assay_uuid=nxentry.get("experiment_identifier").nxvalue,
            updated=None,
        )
        for endpointtype_name, enddpointtype_group in nxentry.items():

            if isinstance(enddpointtype_group, nx.NXsample):
                continue
            elif isinstance(enddpointtype_group, nx.NXcite):
                continue
            elif isinstance(enddpointtype_group, nx.NXinstrument):
                continue
            elif isinstance(enddpointtype_group, nx.NXcollection):
                continue
            elif isinstance(enddpointtype_group, nx.NXenvironment):
                continue
            elif isinstance(enddpointtype_group, nx.NXnote):
                continue
            elif isinstance(enddpointtype_group, nx.NXgroup):
                pass
            elif isinstance(enddpointtype_group, nx.NXprocess):
                pass
            else:
                continue
            for _name_data, data in enddpointtype_group.items():
                if isinstance(data, nx.NXdata):
                    if self.index_only:
                        papp.effects.append(
                            self.parse_effect(
                                endpointtype_name,
                                data,
                                relative_path,
                                nxentry["definition"].nxvalue,
                            )
                        )
                    else:
                        raise NotImplementedError("Not implemented")

        return papp

    def parse_effect(
        self,
        endpointtype_name,
        data: nx.NXentry,
        relative_path: str,
        nxdefinition: str = None,
    ) -> EffectRecord:
        if self.index_only:
            return EffectRecord(
                endpoint=data.attrs["signal"],
                endpointtype=endpointtype_name,
                result=EffectResult(
                    textValue="{}/{}#{}".format(self.domain, relative_path, data.nxpath)
                ),
                conditions={},
                idresult=None,
                endpointGroup=None,
                endpointSynonyms=[],
                sampleID=None,
            )
        else:
            raise NotImplementedError("Not implemented")
