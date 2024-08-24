# + tags=["parameters"]
upstream = []
product = None
root_folder = None
template_metadata = None
output_folder = None
multidimensional = None
# -

import ramanchada2 as rc2
import os.path
import pandas as pd
import pyambit.datamodel as mx
import numpy as np 
from typing import Dict, List, Union
import matplotlib.pyplot as plt
import datetime
from pyambit.nexus_spectra import configure_papp
import uuid
import nexusformat.nexus.tree as nx

def read_template(template_path):
    
    df = pd.read_excel(template_path, sheet_name='Files')
    df['Path'] = df['Filename'].apply(lambda x: os.path.dirname(x))
    df['Basename'] = df['Filename'].apply(lambda x: os.path.basename(x))
    # zero values for laser power are error / empty values
    df['Laser power, mW'] = df['Laser power, mW'].replace(0, np.nan)
    df.dropna(axis=1,how='all',inplace=True)

    df_meta = pd.read_excel(template_path, sheet_name='Front sheet', skiprows=4)
    df_meta.dropna(axis=1,how='all',inplace=True)
    return df,df_meta

def process_files(root_folder,df,meta,multidimensional=False):
    substances = []
    for sample in df["Sample"].unique():
        substance = mx.SubstanceRecord(name=sample, publicname=sample, ownerName=provider)
        substance.i5uuid = "{}-{}".format(prefix, uuid.uuid5(uuid.NAMESPACE_OID, sample))        
        papp =  mx.ProtocolApplication(
            protocol=mx.Protocol(
                topcategory="P-CHEM",
                category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
            ),
            effects=[],
            )
        papp.nx_name = "{}".format(sample)
        configure_papp(
            papp,  instrument="{} {}".format(meta["Make"].values[0],meta["Model"].values[0]),  wavelength=meta["Wavelength, nm"].values[0], 
            provider=meta["Notes"].values[0],
            sample=sample,
            sample_provider=provider,
            investigation=investigation,
            citation =  mx.Citation(
                owner=meta["Notes"].values[0], title=investigation, year=2023),
            prefix=prefix,
            meta=None)        
        df_sample = df.loc[df["Sample"]==sample]
        #plt.figure()
        ax = None
        for subfolder in df_sample["Path"].unique():
            df_subfolder = df_sample.loc[df["Path"]==subfolder]

            replicate="Measurement #"
            spectra = []
            for index, row in df_subfolder.iterrows():
                try:
                    spe = rc2.spectrum.from_local_file(os.path.join(root_folder,row["Path"],row["Basename"]).strip())
                    spectra.append({"spe" : spe, "minx" : min(spe.x), "maxx" : max(spe.x), "bins" : len(spe.x), 
                                    "replicate" : row[replicate], "meta" : spe.meta, "basename" : row["Basename"]})
                    
                except Exception as err:
                    print(row["Filename"],err)

            df_spectra = pd.DataFrame(spectra) 
            #print(df_spectra.shape)       
            grouped = df_spectra.groupby(['minx', 'maxx', 'bins'])
            for group_keys, group_df in grouped:
                #print(row[replicate],sample,subfolder,row["Basename"],group_keys)
                #print(f"Group keys (minx, maxx, bins): {group_keys}")
                #print(group_df)
                #print("\n")
                
                unique_replicates = sorted(group_df['replicate'].unique())
                num_replicates = len(unique_replicates)
                if multidimensional:                
                    array_2d = np.empty((num_replicates,group_keys[2]))
                    for i, (index, row) in enumerate(group_df.iterrows()):
                        spe_y = row['spe'].y
                        spe_x = row['spe'].x
                        replicate_number = row['replicate']
                        # Fill the ith column with the spe.x values of the current replicate
                        column_index = unique_replicates.index(replicate_number)
                        array_2d[column_index,:] = spe_y
                        
                    #print(type(array_2d),array_2d)
                    data_dict: Dict[str, mx.ValueArray] = {
                        "Replicate": mx.ValueArray(values=np.array(unique_replicates), unit=None),
                        "Raman shift": mx.ValueArray(values=spe_x, unit="cm-1")
                    }   
                    papp.effects.append(mx.EffectArray(
                            endpoint="Intensity",
                            endpointtype="RAW_DATA",
                            signal=mx.ValueArray(values=array_2d, unit="a.u."),
                            axes=data_dict,
                            #conditions={replicate : row[replicate]} # , "Original file" : meta["Original file"]}
                    ))              
                else:
                    signal = None
                    signal_name = None
                    auxiliary= {}
                    data_dict: Dict[str, mx.ValueArray] = {}
                    
                    for i, (index, row) in enumerate(group_df.iterrows()):
                        spe_y = row['spe'].y
                        spe_x = row['spe'].x
                        replicate_number = row['replicate']
                        if signal is None:
                            signal_name = "Intensity"
                            signal = spe_y
                            data_dict : Dict[str, mx.ValueArray] = { "Raman shift": mx.ValueArray(values=spe_x, unit="cm-1")}
                        else:
                            auxiliary["{}".format(row["basename"])] = spe_y   
                    #print(papp.uuid,auxiliary)                           
                    ea = mx.EffectArray(
                            endpoint=signal_name,
                            endpointtype="RAW_DATA",
                            signal=mx.ValueArray(values=signal, unit="a.u.",auxiliary = auxiliary),
                            axes=data_dict,
                            #conditions={replicate : row[replicate]} # , "Original file" : meta["Original file"]}
                    )
                    ea.nx_name = "test" 
                    papp.effects.append(ea)
                    #print(spe.meta)
                    #ax = spe.plot(ax=ax,label="{} {}".format(row["Instrument/OP ID"],sample))
                    #data_dict: Dict[str, mx.ValueArray] = {
                    #        "Raman shift": mx.ValueArray(values=spe.x, unit="cm-1")
                    #        }
                    #papp.effects.append(mx.EffectArray(
                    #    endpoint="Intensity",
                    ##    endpointtype="RAW_DATA",
                   #     signal=mx.ValueArray(values=spe.y, unit="a.u."),
                   #     axes=data_dict,
                    #    conditions={replicate : row[replicate]}
                    #))    
                
        substance.study = [papp] 
        substances.append(substance)       
    return mx.Substances(substance=substances)

df,df_meta = read_template(os.path.join(root_folder,template_metadata))
# join file list and meta
result = pd.merge(df, df_meta, how='outer', left_on='Instrument/OP ID', right_on='Identifier (ID)')
#drop column with nans
result.dropna(axis=1,how='all',inplace=True)
result.columns

#read these from the template instead
investigation = "CHARISMA_STUDY_PEAK_FITTING"
provider = "CHARISMA"
prefix="CRMA"


col_id = "Identifier (ID)"
for id in result[col_id].unique():
    #if id!="S2":
    #    continue
    _tmp = result.loc[result[col_id]==id]
    _meta = df_meta.loc[df_meta[col_id]==id]
    
    not_meta_columns = _tmp.columns.difference(_meta.columns)
    substances = process_files(root_folder,_tmp[not_meta_columns],_meta,multidimensional=multidimensional)
    #print(substances.model_dump_json())
    nxroot = nx.NXroot()
    
    substances.to_nexus(nxroot)
    file = os.path.join(os.path.join(output_folder,"{}_spectra_{}.nxs".format("nD" if multidimensional else "1D",id)))
    print(file)
    nxroot.save(file, mode="w")