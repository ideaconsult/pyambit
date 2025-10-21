import ast
import os.path
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import nexusformat.nexus.tree as nx
import numpy as np
import pandas as pd
import requests
import seaborn as sns
from IPython.display import display, HTML  # noqa: F401

# to_nexus is not added without this import
from pyambit import nexus_writer  # noqa: F401
from pyambit.datamodel import EffectRecord, Study, Substances

# + tags=["parameters"]
upstream = []
product = None
url = None
hierarchy = None
single_nexus = None
max_substances = None
papp_query = None
# -

Path(product["nexus"]).mkdir(parents=True, exist_ok=True)


def query(url="https://apps.ideaconsult.net/gracious/substance/", params={"max": 1}):
    substances = None
    headers = {"Accept": "application/json"}
    result = requests.get(url, params=params, headers=headers)
    if result.status_code == 200:
        response = result.json()
        substances = Substances.model_construct(**response)
        for substance in substances.substance:
            url_study = "{}/study?max=10000".format(substance.URI)
            if papp_query is not None:
                url_study = url_study + "&" + papp_query
            # print(url_study)
            study = requests.get(url_study, headers=headers)
            if study.status_code == 200:
                response_study = study.json()
                substance.study = Study.model_construct(**response_study).study

    return substances


def write_studies_nexus(substances, single_file=single_nexus, hierarchy=False):
    if single_file:
        nxroot = nx.NXroot()
        substances.to_nexus(nxroot, hierarchy=hierarchy)
        file = os.path.join(product["nexus"], "remote.nxs")
        nxroot.save(file, mode="w")
    else:
        for substance in substances.substance:
            for study in substance.study:
                file = os.path.join(product["nexus"], "study_{}.nxs".format(study.uuid))
                print(file)
                nxroot = nx.NXroot()
                try:
                    study.to_nexus(nxroot)
                    nxroot.save(file, mode="w")
                except Exception as err:  # noqa: F841
                    # print("error",file,str(err))
                    traceback.print_exc()
                # break


def plot_dose_response(
    df: pd.DataFrame,
    concentration_col: str = "CONCENTRATION",
    time_col: str = "E.EXPOSURE_TIME",
    response_col: str = "loValue",
    response_unit_col: str = "unit",
    endpoint_col: str = "endpoint",
    endpoint_type_col: str = "endpointtype",
    logscale: bool = True,
    title: str = "Dose–Response Curves",
    xlabel: str = None,
    ylabel: str = None,
    show: bool = True,
    savepath: str = None,
):
    """
    Plot dose–response curves faceted by unique (endpoint, endpointtype, unit),
    arranged horizontally in one row.

    Keeps None/NaN endpoint types or units.
    Allows optional axis labels for concentration and time.

    Parameters
    ----------
    df : pd.DataFrame
        Input data with endpoints and concentration/time metadata.
    concentration_col : str
        Column containing concentration metadata (dict or JSON-like).
    time_col : str
        Column containing exposure time metadata (dict or JSON-like).
    response_col : str
        Numeric column for the response value.
    response_unit_col : str
        Column with response units.
    endpoint_col : str
        Endpoint name column.
    endpoint_type_col : str
        Endpoint type column.
    logscale : bool
        Whether to use a log scale for the x-axis.
    title : str
        Figure title.
    xlabel, ylabel : str or None
        Optional custom labels for x and y axes (defaults auto-detected).
    show : bool
        Whether to show the figure.
    savepath : str or None
        Path to save figure.
    """

    # --- helper to parse JSON/dict metadata ---
    def parse_meta(x):
        if isinstance(x, str):
            try:
                return ast.literal_eval(x)
            except Exception:
                return {}
        elif isinstance(x, dict):
            return x
        return {}

    # Parse metadata dicts for concentration and time
    df["_conc_dict"] = df[concentration_col].apply(parse_meta)
    df["_time_dict"] = df[time_col].apply(parse_meta) if time_col in df else None

    # Extract numeric values and units
    df["_conc_value"] = df["_conc_dict"].apply(lambda x: x.get("loValue", np.nan))
    df["_conc_unit"] = df["_conc_dict"].apply(lambda x: x.get("unit", None))
    if time_col is not None and df["_time_dict"] is not None:
        df["_time_value"] = df["_time_dict"].apply(lambda x: x.get("loValue", np.nan))
        df["_time_unit"] = df["_time_dict"].apply(lambda x: x.get("unit", None))
    else:
        df["_time_value"] = None
        df["_time_unit"] = None

    # Determine which dimension is x vs. series grouping
    x_col, series_col = "_conc_value", "_time_value"
    xunit_col, series_unit_col = "_conc_unit", "_time_unit"

    if time_col is not None and df["_time_value"].nunique(dropna=True) > df[
        "_conc_value"
    ].nunique(dropna=True):
        x_col, series_col = "_time_value", "_conc_value"
        xunit_col, series_unit_col = "_time_unit", "_conc_unit"
        _ = xlabel
        xlabel = ylabel
        ylabel = _

    # Convert response to numeric
    df["response"] = pd.to_numeric(df[response_col], errors="coerce")
    df = df.dropna(subset=[x_col, "response", endpoint_col])

    if df.empty:
        raise ValueError("No valid data found after cleaning.")

    # --- Summarize replicates (keep NaNs in group keys) ---
    summary = (
        df.groupby(
            [endpoint_col, endpoint_type_col, response_unit_col, series_col, x_col],
            dropna=False,
        )
        .agg(
            mean_response=("response", "mean"),
            sd_response=("response", "std"),
            n=("response", "count"),
        )
        .reset_index()
    )

    # --- Determine unique facets (endpoint+type+unit combos, keeping NaNs) ---
    facet_keys = summary[
        [endpoint_col, endpoint_type_col, response_unit_col]
    ].drop_duplicates(ignore_index=True)
    n_facets = len(facet_keys)

    fig, axes = plt.subplots(1, n_facets, figsize=(5 * n_facets, 4), sharey=False)
    if n_facets == 1:
        axes = [axes]

    # --- Plot each facet ---
    for ax, (_, facet) in zip(axes, facet_keys.iterrows()):
        endpoint = facet[endpoint_col]
        e_type = facet[endpoint_type_col]
        e_unit = facet[response_unit_col]

        facet_data = summary[
            (summary[endpoint_col] == endpoint)
            & (
                summary[endpoint_type_col].eq(e_type)
                | (summary[endpoint_type_col].isna() & pd.isna(e_type))
            )
            & (
                summary[response_unit_col].eq(e_unit)
                | (summary[response_unit_col].isna() & pd.isna(e_unit))
            )
        ]

        # plot each "series_col" group (e.g., exposure time)
        for series_val, group in facet_data.groupby(series_col, dropna=False):
            if isinstance(series_val, (int, float)) and not np.isnan(series_val):
                label = f"{series_val:g}"
                if series_unit_col in df:
                    unit_val = df[series_unit_col].dropna().unique()
                    if len(unit_val) > 0:
                        label += f" {unit_val[0]}"
            else:
                label = "NA"
            ax.errorbar(
                group[x_col],
                group["mean_response"],
                yerr=group["sd_response"],
                fmt="o-",
                capsize=4,
                label=label,
            )

        if logscale:
            ax.set_xscale("log")

        # Handle missing metadata gracefully
        e_type_label = e_type if pd.notna(e_type) else "unknown type"
        e_unit_label = e_unit if pd.notna(e_unit) else ""

        ax.set_title(f"{e_type_label}", fontsize=10)
        ax.set_ylabel(f"{endpoint} {e_unit_label}")
        ax.grid(True, linestyle="--", alpha=0.4)

        if len(facet_data[series_col].dropna()) > 1:
            ax.legend(title=series_col)

    # --- Label axes and layout ---
    xunit_val = df[xunit_col].dropna().unique()
    xunit_val = xunit_val[0] if len(xunit_val) > 0 else ""

    x_label_final = xlabel or x_col
    if xunit_val:
        x_label_final += f" [{xunit_val}]"

    axes[-1].set_xlabel(x_label_final)
    _t = title.split["\n"]
    fig.suptitle(_t[0], fontsize=12)
    fig.text(_t[1], fontsize=8)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if savepath:
        plt.savefig(savepath, dpi=300)
    if show:
        plt.show()

    plt.close(fig)
    return summary


def plot_chemical_concentrations(
    df: pd.DataFrame,
    value_col: str = "loValue",
    category_col: str = "textValue",
    endpoint_col: str = "endpoint",
    unit_col: str = "unit",
    show_points: bool = True,
    log_scale: bool = False,
    title: str = "Endpoint Measurements per Chemical",
    figsize: tuple = (8, 3),
    palette: str = "pastel",
):
    """
    Plot bar plots of mean endpoint values per chemical/material,
    faceted by endpoint and unit. Optionally overlays individual data points.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing numeric values, endpoints, units, and categories.
    value_col : str
        Column with numeric measurement values.
    category_col : str
        Column with chemical/material identifier (e.g., textValue).
    endpoint_col : str
        Column specifying the measured endpoint (e.g., "LDH release").
    unit_col : str
        Column specifying measurement units.
    show_points : bool
        Whether to overlay individual measurements as strip plot.
    log_scale : bool
        If True, y-axis will be logarithmic.
    title : str
        Figure title.
    figsize : tuple
        Figure size for one facet (width, height).
    palette : str
        Seaborn color palette.
    """

    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    # Ensure categorical variables are strings for matplotlib
    for col in [category_col, endpoint_col, unit_col]:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("nan", "")

    # Identify unique combinations of endpoint × unit
    combos = (
        df[[endpoint_col, unit_col]]
        .drop_duplicates()
        .fillna("")
        .to_records(index=False)
    )

    n_facets = len(combos)
    fig, axes = plt.subplots(
        1, n_facets, figsize=(figsize[0] * n_facets, figsize[1]), squeeze=False
    )
    axes = axes.flatten()

    for ax, (endpoint, unit) in zip(axes, combos):
        sub_df = df[(df[endpoint_col] == endpoint) & (df[unit_col] == unit)]

        if sub_df.empty:
            continue

        # Compute summary stats
        summary = (
            sub_df.groupby(category_col, dropna=False)[value_col]
            .agg(["mean", "std"])
            .reset_index()
        )

        colors = sns.color_palette(palette, len(summary))

        ax.bar(
            summary[category_col],
            summary["mean"],
            yerr=summary["std"],
            capsize=4,
            color=colors,
        )

        if show_points:
            sns.stripplot(
                x=category_col,
                y=value_col,
                data=sub_df,
                color="black",
                size=5,
                jitter=True,
                ax=ax,
            )

        ylabel = f"{endpoint}"
        if unit and unit != "None":
            ylabel += f" [{unit}]"

        ax.set_ylabel(ylabel)
        ax.set_xlabel("")
        ax.set_title(f"{endpoint} ({unit if unit != 'None' else ''})")
        ax.grid(True, linestyle="--", alpha=0.4)

        if log_scale:
            ax.set_yscale("log")

    _t = title.split["\n"]
    fig.suptitle(_t[0], fontsize=12)
    fig.text(_t[1], fontsize=8)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


try:
    substances = query(
        url=url, params={"max": 1 if max_substances is None else max_substances}
    )
    _json = substances.model_dump(exclude_none=False)
    new_substances = Substances.model_construct(**_json)
    # new_substances = Substances(**_json)
    # test roundtrip
    assert substances == new_substances

    file = os.path.join(product["json"])
    # print(file)
    with open(file, "w", encoding="utf-8") as file:
        file.write(substances.model_dump_json(exclude_none=True))
    df_papps = None
    for s in substances.substance:
        if s.study is None:
            continue
        for pa in s.study:
            method = pa.parameters.get("E.method", None)
            cell = pa.parameters.get("E.cell_type", "")
            for ea in pa.effects:
                ea.conditions = EffectRecord.clean_parameters(ea.conditions)
                _tagc = "CONCENTRATION"
                # this allows to split numeric concentrations into nxdata
                if _tagc in ea.conditions and (isinstance(ea.conditions[_tagc], str)):
                    if "TREATMENT" not in ea.conditions:
                        ea.conditions["TREATMENT"] = "control"

            effectarrays_only, df = pa.convert_effectrecords2array()
            _file = os.path.join(product["nexus"], "study_{}.xlsx".format(pa.uuid))

            df["papp_uuid"] = pa.uuid
            df["investigation_uuid"] = pa.investigation_uuid
            df["assay_uuid"] = pa.assay_uuid
            df["substance_uuid"] = s.i5uuid
            df.to_excel(_file, index=False)

            _input_file = pa.parameters.get("__input_file", "")
            if "CONCENTRATION" in df.columns:
                concentration_col = "CONCENTRATION"
                try:
                    if "E.EXPOSURE_TIME" in df.columns:
                        time_col = "E.EXPOSURE_TIME"
                    elif "TIME" in df.columns:
                        time_col = "TIME"
                    else:
                        time_col = None

                    summary = plot_dose_response(
                        df,
                        concentration_col=concentration_col,
                        time_col=time_col,
                        response_col="loValue",
                        response_unit_col="unit",
                        endpoint_col="endpoint",
                        logscale=False,
                        title=f"[{s.name}] {pa.protocol.category.code if method is None else method} {cell} ({pa.citation.owner})\n{_input_file}",  # noqa: B950
                        show=True,
                        savepath=None,
                        xlabel="concentration",
                        ylabel="time",
                    )
                except Exception:
                    print(pa.uuid)
                    traceback.print_exc()
            elif "CONCENTRATION" in df["endpoint"].unique():
                plot_chemical_concentrations(
                    df,
                    title=f"[{s.name}] {pa.protocol.category.code if method is None else method} ({pa.citation.owner})\n{_input_file}",  # noqa: B950
                )
            else:
                print(
                    f"Not dose response [{pa.uuid} {s.name}] {method} ({pa.citation.owner})  {df.columns} {df.shape}"  # noqa: B950
                )

            df = df[
                ["substance_uuid", "assay_uuid", "papp_uuid", "investigation_uuid"]
            ].drop_duplicates()
            # print(df.shape)
            df["papp"] = pa.model_dump_json()
            df["papp_topcategory"] = pa.protocol.topcategory
            df["papp_category"] = pa.protocol.category.code
            df["papp_endpoint"] = pa.protocol.endpoint
            df["papp_guideline"] = (
                None
                if pa.protocol.guideline is None
                else "".join(pa.protocol.guideline)
            )
            df["papp_citation_title"] = pa.citation.title
            df["papp_citation_owner"] = pa.citation.owner
            df["papp_citation_year"] = pa.citation.year
            df_papps = (
                df if df_papps is None else pd.concat([df_papps, df], ignore_index=True)
            )
            # print(_file)
            # display(df.dropna(axis=1, how="all"))
            # for ea in effectarrays_only:
            #    print(">>>", ea.endpoint, ea.endpointtype)
            #    for axis in ea.axes:
            #        print(axis, ea.axes[axis])
            #    print(">signal> ", ea.signal)
            #    for c in ea.conditions:
            #        print(c, ea.conditions[c])
            # break
    write_studies_nexus(substances, single_file=single_nexus, hierarchy=hierarchy)
    df_papps.to_excel(
        os.path.join(product["nexus"], "protocol_applications.xlsx"), index=False
    )
except Exception:
    traceback.print_exc()
