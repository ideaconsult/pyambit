import numbers
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
    Investigation,
    Protocol,
    ProtocolApplication,
    SampleLink,
    SubstanceRecord,
    Substances,
    Value,
)

# Deriving the read-back from the writer's own routing table, rather than
# restating the mapping here, is what keeps the two from drifting -- the same
# reason nanodata's assay_index.py imports it (see nexus_param_field there).
from pyambit.nexus_writer import param_lookup

# The NeXus groups param_lookup can route a protocol-application parameter
# into. Everything else in an NXentry is not a parameter and is read
# elsewhere: NXdata/RAW_DATA hold the measured arrays, reference/investigation
# the citation and study label, and definition / collection_identifier /
# entry_identifier_uuid the entry's identity.
PARAM_GROUPS = (
    "instrument",
    "environment",
    "sample",
    "parameters",
    "experiment_documentation",
)

# Written by to_nexus from the ProtocolApplication itself, never from
# papp.parameters. Reading them back as parameters would invent keys the
# source never had, and they are already parsed into their own model fields.
NOT_PARAMETERS = {
    ("sample", "substance"),  # NXlink to /substance/<uuid>; owner.substance
    ("sample", "provider"),  # papp.owner.company.name
    ("experiment_documentation", "protocol"),  # papp.protocol, an attrs carrier
    ("experiment_documentation", "date"),  # papp.updated
}


def _scalar(field):
    """A parameter's python value, or None if this field is not one.

    Only scalars are parameters -- an array under one of the parameter groups
    is measured data that belongs to an effect, not a protocol parameter. A
    field carrying a `unit` attribute becomes a Value so that solr_writer's
    prm2solr emits the `_d` + `_UNIT_s` pair it already emits for wavelength,
    instead of flattening the quantity to a bare string.
    """
    try:
        value = field.nxvalue
    except Exception:  # noqa: BLE001 - unreadable field is simply not a parameter
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    # numpy scalars: np.float64 subclasses float, np.int64 does NOT subclass
    # int, and prm2solr dispatches on isinstance -- so an unconverted np.int64
    # would be silently dropped from the Solr document. numbers.Real catches
    # both; .item() hands back the plain python equivalent.
    if not isinstance(value, str):
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            return None
        value = value.item() if hasattr(value, "item") else value
    if isinstance(value, str):
        return value
    try:
        unit = field.attrs.get("unit")
    except Exception:  # noqa: BLE001
        unit = None
    # ProtocolApplication.parameters is Dict[str, Union[str, Value, None]], so
    # a bare number is not a legal value there (pydantic rejects the whole
    # papp -- MOMENTUM's "Number of cells per well" = 200000.0 is a real
    # example). A number is a quantity anyway: wrapping it means prm2solr
    # emits `<key>_d`, and `<key>_UNIT_s` when the field carried a unit,
    # instead of stringifying a measurement.
    return Value(loValue=value, unit=str(unit) if unit is not None else None)


def _collect_parameters(group, path, found):
    for name, node in group.items():
        if len(path) == 1 and (path[0], name) in NOT_PARAMETERS:
            continue
        if isinstance(node, nx.NXlink):
            continue
        if isinstance(node, nx.NXgroup):
            _collect_parameters(node, path + [name], found)
            continue
        value = _scalar(node)
        if value is None:
            continue
        full = path + [name]
        # A bare name that param_lookup would route back to exactly this path
        # is stored bare, so the round trip is exact AND prm2solr names the
        # field the way every other index names it (__input_file_s, not
        # experiment_documentation/__input_file_s). Anything the heuristic
        # would put somewhere else keeps its full path, so where it actually
        # lives in the file is never lost.
        try:
            routed = param_lookup(name, value) == full
        except Exception:  # noqa: BLE001 - odd name, keep the explicit path
            routed = False
        found[name if routed else "/".join(full)] = value
    return found


def parameters_from_nxentry(nxentry) -> Dict:
    """Every protocol-application parameter written into this entry.

    to_nexus routes each papp.parameters entry into one of PARAM_GROUPS (via
    param_lookup for a bare name, or verbatim for a key that is already a
    path). Nothing read them back: parse_entry recovered only E.method,
    wavelength and instrument, so __input_file and the whole
    exposure/medium/cell/instrument block reached the .nxs file and then
    vanished -- leaving the type_s:params Solr child with nothing but its own
    identity fields, and the folded study documents with no parameters to
    search on at all.
    """
    found: Dict = {}
    for group_name in PARAM_GROUPS:
        group = nxentry.get(group_name)
        if isinstance(group, nx.NXgroup):
            _collect_parameters(group, [group_name], found)
    return found


class Nexus2Ambit:

    def __init__(self, domain: str, index_only: True):
        self.substances: Dict[str, SubstanceRecord] = {}
        # Investigations seen so far, keyed by uuid. nexus_writer writes the
        # title/description ONCE per uuid into a shared top-level
        # `investigation/<uuid>` group and links every entry to it, so the
        # label has to be collected here and handed back to each
        # ProtocolApplication that references it -- otherwise the authored
        # prose is written to the file and never read by anything.
        self.investigations: Dict[str, Investigation] = {}
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
        self.investigations = {}

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

    def investigation_from_nexus(self, nxentry) -> Investigation:
        """One `investigation/<uuid>` group back into an Investigation.

        `description` is read as a FIELD (where nexus_writer now writes it,
        matching NXcite's NXDL) but also from the attributes, so files
        written by the earlier code -- which stored it as an attr, where no
        viewer showed it -- still resolve.
        """
        uuid = nxentry.attrs.get("uuid")
        if uuid is None:
            return None

        def _text(name):
            if name in nxentry:
                value = nxentry[name].nxvalue
                return value.decode() if isinstance(value, bytes) else str(value)
            value = nxentry.attrs.get(name)
            if value is None:
                return None
            return value.decode() if isinstance(value, bytes) else str(value)

        return Investigation(
            uuid=str(uuid),
            title=_text("title"),
            description=_text("description"),
        )

    def parse_investigations(self, nxentry):
        """Collect every `investigation/<uuid>` label in the file. Written
        once per uuid and linked from each entry, so it is read here rather
        than per entry (see parse_entry, which attaches it by uuid)."""
        for _name, entry in nxentry.items():
            try:
                investigation = self.investigation_from_nexus(entry)
            except Exception:  # noqa: BLE001 -- a label is never fatal
                continue
            if investigation is None:
                continue
            # First one wins, matching nexus_writer's own never-overwrite
            # rule, so parsing many files of one investigation is stable.
            self.investigations.setdefault(investigation.uuid, investigation)

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
        # Both shared top-level groups are read BEFORE the study entries,
        # so a papp can be handed the substance and the investigation label
        # it links to (parse_studies -> parse_entry resolves both by uuid).
        for entry_name, entry in nxroot.items():
            if entry_name == "substance":
                self.parse_substances(entry)
            elif entry_name == "investigation":
                self.parse_investigations(entry)
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

        # Citation.year is Optional, so a file that never had a publication year
        # is valid -- and to_nexus writes nothing for a None year, leaving the
        # NXcite group without that field. Reading it unconditionally made every
        # such file unparseable (NeXusError: Invalid path), which is how the
        # whole Template Designer corpora became unreadable: such a
        # template carries no year, so TemplateDesignerParser sets None.
        _reference = nxentry.get("reference")

        def _cite(field, default=None):
            if _reference is None or field not in _reference:
                return default
            return _reference[field].nxdata

        citation = Citation(
            year=_cite("year"),
            title=_cite("title", ""),
            owner=_cite("owner", ""),
        )

        # Read every parameter back out of the groups to_nexus put them in,
        # BEFORE the special cases below, so those still win: they compose
        # values the generic sweep cannot (instrument = "vendor model") or
        # fall back to `definition`, and that behaviour is unchanged.
        parameters.update(parameters_from_nxentry(nxentry))

        try:
            wl = nxentry["instrument/beam_incident/wavelength"].nxdata
            wl_unit = nxentry["instrument/beam_incident/wavelength"].attrs["unit"]
            parameters["wavelength"] = Value(loValue=wl, unit=wl_unit)
        except:  # noqa: B001,E722 FIXME
            # setdefault, not assignment: the sweep above may already have
            # read a perfectly good wavelength (one written without a `unit`
            # attribute, say), and overwriting it with None would lose it.
            parameters.setdefault("wavelength", None)

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

        # ProtocolApplication.investigation_uuid is Union[str, Investigation]:
        # hand back the labelled object when this file carried one (so the
        # authored title/description reach every consumer, not just whoever
        # reopens the NeXus file), and the bare uuid otherwise.
        _investigation_uuid = nxentry.get("collection_identifier").nxvalue
        if isinstance(_investigation_uuid, bytes):
            _investigation_uuid = _investigation_uuid.decode()
        _investigation = self.investigations.get(
            str(_investigation_uuid), _investigation_uuid
        )

        papp: ProtocolApplication = ProtocolApplication(
            uuid=nxentry.get("entry_identifier_uuid").nxvalue,
            interpretationResult=None,
            interpretationCriteria=None,
            parameters=parameters,
            citation=citation,
            effects=[],
            owner=_owner,
            protocol=protocol,
            investigation_uuid=_investigation,
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
