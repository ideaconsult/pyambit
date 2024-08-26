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
        substance.study = []  
        df_sample = df.loc[df["Sample"]==sample] 
        grouped_path_instrument = df_sample.groupby(['Path', 'Instrument/OP ID'])
        for instrument_keys, df_subfolder in grouped_path_instrument:
            subfolder = instrument_keys[0].split("/")[0]
            instrument_id = instrument_keys[1]
            papp =  mx.ProtocolApplication(
                protocol=mx.Protocol(
                    topcategory="P-CHEM",
                    category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION"),
                ),
                effects=[],
                )

            _investigation = "{}.{}".format(subfolder,investigation)
            configure_papp(
                papp,  instrument="{} {}".format(meta["Make"].values[0],meta["Model"].values[0]),  
                wavelength=meta["Wavelength, nm"].values[0], 
                provider=meta["Notes"].values[0],
                sample=sample,
                sample_provider=provider,
                investigation=_investigation,
                citation =  mx.Citation(
                    owner=meta["Notes"].values[0], title=investigation, year=2023),
                prefix=prefix,
                meta=None)   
            papp.nx_name = "{} {} {}".format(subfolder,instrument_id, sample)                 
            replicate="Measurement #"
            spectra = []
            for index, row in df_subfolder.iterrows():
                try:
                    spe = rc2.spectrum.from_local_file(os.path.join(root_folder,instrument_keys[0],row["Basename"]).strip())
                    spectra.append({"spe" : spe, "minx" : min(spe.x), "maxx" : max(spe.x), "bins" : len(spe.x), 
                                    "replicate" : row[replicate], "meta" : spe.meta, "basename" : row["Basename"]})
                    
                except Exception as err:
                    print(row["Filename"],err)

            df_spectra = pd.DataFrame(spectra) 

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
                    ea = mx.EffectArray(
                            endpoint="Raman intensity",
                            endpointtype="RAW_DATA",
                            signal=mx.ValueArray(values=array_2d, unit="a.u."),
                            axes=data_dict,
                            #conditions={replicate : row[replicate]} # , "Original file" : meta["Original file"]}
                            conditions={ "grouped_by" : ', '.join(map(str, group_keys)) }
                    )
                    print(ea.nx_name )
                    ea.nx_name = f'{sample} {subfolder}'
                    papp.effects.append(ea)      
                else:
                    signal = None
                    signal_name = None
                    auxiliary= {}
                    data_dict: Dict[str, mx.ValueArray] = {}
                    
                    for i, (index, row) in enumerate(group_df.iterrows()):
                        spe_y = row['spe'].y
                        spe_x = row['spe'].x

                        _name = "Raman intensity"
                        _axes = ["Raman shift"]
                        _signal_meta = None
                        _spemeta = None
                        for key in row['spe'].meta.get_all_keys():
                            if key == "@signal":
                                _name = row['spe'].meta[key]
                            elif key == "@axes":
                                _axes = row['spe'].meta[key]
                            else:
                                if _spemeta is None:
                                    _spemeta = {}
                                _spemeta[f'META_{key}'] = str(row['spe'].meta[key])
                        #_name = row['spe'].meta["@signal"] if "@signal" in row['spe'].meta.get_all_keys() else "Raman intensity"
                        #_axes = row['spe'].meta["@axes"] if "@axes" in row['spe'].meta.get_all_keys() else ["Raman shift"]

                        replicate_number = row['replicate']
                        if signal is None:
                            
                            signal_endpointtype = "RAW_DATA" if _name == "" else _name
                            signal = spe_y
                            if _spemeta is None:
                                _spemeta={}
                            _signal_meta = _spemeta
                            _signal_meta["REPLICATE"] = str(replicate_number)
                            data_dict : Dict[str, mx.ValueArray] = { "Raman shift": mx.ValueArray(values=spe_x, unit="1/cm")}
                        else:
                            _spemeta["REPLICATE"] = str(replicate_number)
                            #auxiliary["{}".format(row["basename"])] = mx.MetaValueArray(values=spe_y,unit="a.u",conditions=_spemeta)
                            auxiliary["Replicate {}".format(row["replicate"])] = mx.MetaValueArray(values=spe_y,unit="a.u",conditions=_spemeta)
                    #print(papp.uuid,auxiliary)                           
                    ea = mx.EffectArray(
                            endpoint="Raman intensity",
                            endpointtype=signal_endpointtype,
                            signal=mx.ValueArray(values=signal, unit="a.u.",auxiliary = auxiliary,conditions=_signal_meta),
                            axes=data_dict,
                            #conditions={replicate : row[replicate]} # , "Original file" : meta["Original file"]}
                            conditions={ "grouped_by" : ', '.join(map(str, group_keys)) }
                    )
                    ea.nx_name = f'{sample} {subfolder}'
                    papp.effects.append(ea)
   
                
            substance.study.append(papp)
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


def byinstrument():
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

try:
    _tmp = result
    _meta = df_meta
    
    not_meta_columns = _tmp.columns.difference(_meta.columns)
    substances = process_files(root_folder,_tmp[not_meta_columns],_meta,multidimensional=multidimensional)
    #print(substances.model_dump_json())
    nxroot = nx.NXroot()
    
    substances.to_nexus(nxroot)
    file = os.path.join(os.path.join(output_folder,"{}_spectra_{}.nxs".format(investigation,"nD" if multidimensional else "1D")))
    print(file)
    nxroot.save(file, mode="w") 
except Exception as err:
    print(err)       