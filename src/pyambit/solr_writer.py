import json
from typing import Dict, Union

from pyambit.datamodel import (
    EffectArray,
    EffectRecord,
    EffectResult,
    ProtocolApplication,
    SubstanceRecord,
    Substances,
    Value,
)


class Ambit2Solr:

    def __init__(self, prefix: str):
        self.prefix = prefix

    def __enter__(self):
        self._solr = []
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Any cleanup code, if needed
        pass

    def prm2solr(self, params: Dict, key: str, value: Union[str, Value, None]):
        if isinstance(value, str):
            params["{}_s".format(key)] = value
        elif isinstance(value, int):
            params["{}_d".format(key)] = value
        elif isinstance(value, float):
            params["{}_d".format(key)] = value
        elif isinstance(value, Value):
            if value.loValue is not None:
                params["{}_d".format(key)] = value.loValue
            if value.unit is not None:
                params["{}_UNIT_s".format(key)] = value.unit

    def effectresult2solr(self, effect_result: EffectResult, solr_index=None):
        if solr_index is None:
            solr_index = {}
        if effect_result.loValue is not None:
            solr_index["loValue_d"] = effect_result.loValue
        if effect_result.loQualifier is not None:
            solr_index["loQualifier_s"] = effect_result.loQualifier
        if effect_result.upQualifier is not None:
            solr_index["upQualifier_s"] = effect_result.upQualifier
        if effect_result.upValue is not None:
            solr_index["upValue_d"] = effect_result.upValue
        if effect_result.unit is not None:
            solr_index["unit_s"] = effect_result.unit
        if effect_result.textValue is not None:
            solr_index["textValue_s"] = effect_result.textValue

    def effectrecord2solr(self, effect: EffectRecord, solr_index=None):
        if solr_index is None:
            solr_index = {}
        if isinstance(effect, EffectArray):
            # tbd - this is new in pyambit, we did not have array results implementation
            if effect.result is not None:  # EffectResult
                self.effectresult2solr(effect.result, solr_index)
            # e.g. vector search
            if effect.endpointtype == "embeddings":
                solr_index[effect.endpoint] = effect.signal.values.tolist()
        elif isinstance(effect, EffectRecord):
            # conditions
            if effect.result is not None:  # EffectResult
                self.effectresult2solr(effect.result, solr_index)

    def entry2solr(self, papp: ProtocolApplication):
        # One Solr document per effect (papp_solr.append(_solr) belongs
        # INSIDE this loop -- previously it and the _params block below sat
        # at the same indent as the "for prm in papp.parameters" loop,
        # outside "for effect in papp.effects" entirely. That meant only
        # the LAST effect's _solr survived to be appended (every earlier
        # effect's document was silently built and discarded), and with
        # zero effects _solr was never assigned at all, raising
        # UnboundLocalError -- confirmed via a real indexed_endpointtypes
        # filter producing a papp with no matching effects.
        papp_solr = []

        _params = {}
        for prm in papp.parameters:
            self.prm2solr(_params, prm, papp.parameters[prm])
        _params["document_uuid_s"] = papp.uuid
        _params["id"] = "{}/prm".format(papp.uuid)
        _params["topcategory_s"] = papp.protocol.topcategory
        _params["endpointcategory_s"] = (
            "UNKNOWN" if papp.protocol.category is None else papp.protocol.category.code
        )
        if "E.method" in papp.parameters:
            _params["E.method_s"] = papp.parameters["E.method"]
        _params["type_s"] = "params"

        for _id, effect in enumerate(papp.effects, start=1):
            _solr = {}
            _solr["id"] = "{}/{}".format(papp.uuid, _id)
            _solr["investigation_uuid_s"] = papp.investigation_uuid
            _solr["assay_uuid_s"] = papp.assay_uuid
            _solr["type_s"] = "study"
            _solr["document_uuid_s"] = papp.uuid

            _solr["topcategory_s"] = papp.protocol.topcategory
            _solr["endpointcategory_s"] = (
                "UNKNOWN"
                if papp.protocol.category is None
                else papp.protocol.category.code
            )
            _solr["guidance_s"] = papp.protocol.guideline
            # _solr["guidance_synonym_ss"] = ["FIX_0000058"]
            # _solr["E.method_synonym_ss"] = ["FIX_0000058"]
            _solr["endpoint_s"] = papp.protocol.endpoint
            _solr["effectendpoint_s"] = effect.endpoint
            _solr["effectendpoint_type_s"] = effect.endpointtype
            # _solr["effectendpoint_synonym_ss"] = ["CHMO_0000823"]
            _solr["reference_owner_s"] = papp.citation.owner
            _solr["reference_year_s"] = papp.citation.year
            _solr["reference_s"] = papp.citation.title
            _solr["updated_s"] = papp.updated
            if "E.method" in papp.parameters:
                _solr["E.method_s"] = papp.parameters["E.method"]
            self.effectrecord2solr(effect, _solr)

            _child_documents = []
            # Skip the conditions child doc entirely when the effect has no
            # real conditions -- the fixed bookkeeping fields (type_s,
            # topcategory_s, etc.) always populate it regardless, so
            # "empty" means effect.conditions has no entries, not that the
            # dict itself is falsy.
            if effect.conditions:
                _conditions = {"type_s": "conditions"}
                _conditions["topcategory_s"] = papp.protocol.topcategory
                _conditions["endpointcategory_s"] = (
                    "UNKNOWN"
                    if papp.protocol.category is None
                    else papp.protocol.category.code
                )
                _conditions["document_uuid_s"] = papp.uuid
                _conditions["id"] = "{}/cn".format(_solr["id"])
                for prm in effect.conditions:
                    self.prm2solr(_conditions, prm, effect.conditions[prm])
                _child_documents.append(_conditions)
            # _params belongs to the papp/study, not to each individual
            # effect -- attach it once, on the first effect-document, not
            # duplicated onto every one of this papp's effects.
            if _id == 1:
                _child_documents.append(_params)
            if _child_documents:
                _solr["_childDocuments_"] = _child_documents
            papp_solr.append(_solr)

        return papp_solr

    def composition2solr(self, substance: SubstanceRecord):
        """One type_s:composition child doc per substance.composition entry
        -- same Solr shape as the standard AMBIT composition index (id
        suffix "/c/{n}", s_uuid_hs, component_s from CompositionEntry.relation,
        ChemicalName_s/CASRN_s/InChIKey_s/InChI_s from Compound). formula_s
        has no equivalent in that convention (SMILES_s does, but Compound
        has no SMILES field to source it from) -- added here since RRUFF's
        composition (see pipeline_nexus/tasks/read_rruff.py) only ever
        carries name+formula, nothing else on Compound. Fields with no
        value are omitted rather than written as null, matching prm2solr's
        style elsewhere in this class.
        """
        docs = []
        if not substance.composition:
            return docs
        for _id, entry in enumerate(substance.composition, start=1):
            compound = entry.component.compound
            doc = {
                "id": "{}/c/{}".format(substance.i5uuid, _id),
                "s_uuid_hs": substance.i5uuid,
                "type_s": "composition",
            }
            if entry.relation is not None:
                doc["component_s"] = entry.relation
            if compound.name is not None:
                doc["ChemicalName_s"] = compound.name
            if compound.cas is not None:
                doc["CASRN_s"] = compound.cas
            if compound.inchikey is not None:
                doc["InChIKey_s"] = compound.inchikey
            if compound.inchi is not None:
                doc["InChI_s"] = compound.inchi
            if compound.formula is not None:
                doc["formula_s"] = compound.formula
            docs.append(doc)
        return docs

    def substancerecord2solr(self, substance: SubstanceRecord):
        """Returns None (no Solr document at all) if every one of the
        substance's studies produced zero effect-documents -- e.g. every
        effect got filtered out (see Spectra2Solr.entry2solr's
        indexed_endpointtypes). A substance with no studies underneath it
        has nothing searchable/useful attached and would otherwise show up
        in the index as an orphan record.
        """
        _solr = {}
        _solr["content_hss"] = []
        _solr["dbtag_hss"] = self.prefix
        _solr["name_hs"] = substance.name
        _solr["publicname_hs"] = substance.publicname
        _solr["owner_name_hs"] = substance.ownerName
        _solr["substanceType_hs"] = substance.substanceType
        _solr["type_s"] = "substance"
        _solr["s_uuid_hs"] = substance.i5uuid
        _solr["id"] = substance.i5uuid
        _studies = []
        for _papp in substance.study:
            _study_solr = self.entry2solr(_papp)
            for _study in _study_solr:
                _study["s_uuid_s"] = substance.i5uuid
                _study["type_s"] = "study"
                _study["name_s"] = substance.name
                _study["publicname_s"] = substance.publicname
                _study["substanceType_s"] = substance.substanceType
                _study["owner_name_s"] = substance.ownerName
            _studies.extend(_study_solr)
        if not _studies:
            return None
        # Composition docs are siblings of study docs in the same flat
        # _childDocuments_ list (Solr child docs aren't nested per type_s),
        # appended after studies so a substance with composition but zero
        # surviving studies still returns None above rather than becoming
        # an orphan composition-only document.
        _solr["_childDocuments_"] = _studies + self.composition2solr(substance)

        return _solr

    def substances2solr(self, substances: Substances, buffer=None):
        if buffer is None:
            buffer = []
        for substance in substances.substance:
            _solr = self.substancerecord2solr(substance)
            if _solr is not None:
                buffer.append(_solr)
        return buffer

    def to_json(self, substances: Substances):
        return self.substances2solr(substances)

    def write(self, substances, file_path):
        _json = self.to_json(substances)
        with open(file_path, "w") as file:
            json.dump(_json, file)
