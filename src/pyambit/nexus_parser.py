import h5py
import ramanchada2 as rc2


class NexusParser:
    def __init__(self):
        self.parsed_objects = {}

    def parse_data(self, entry, default=False, nxprocess=False):
        for attr in entry.attrs:
            print(attr, entry.attrs.get(attr))
        for _, item in entry.items():
            nx_class = item.attrs.get("NX_class", None)
            print("PROCESSED " if nxprocess else "", "DATA ", item.name, " ", nx_class)

    def parse_entry(self, entry, nxprocess=False, dataparser=None):
        print(dataparser)
        nx_class = entry.attrs.get("NX_class", None)
        default = entry.attrs.get("default", None)
        # print(entry.name, ' ', nx_class, default)
        for _, item in entry.items():
            nx_class = item.attrs.get("NX_class", None)
            if nx_class == "NXdata":
                if dataparser is None:
                    self.parse_data(item, entry.name == default, nxprocess)
                else:
                    print("dataparsre", dataparser)
                    dataparser(item, entry.name == default, nxprocess)

            elif nx_class == "NXenvironment":
                pass
            elif nx_class == "NXinstrument":
                pass
            elif nx_class == "NXcite":
                pass
            elif nx_class == "NXcollection":
                pass
            elif nx_class == "NXnote":
                pass
            elif nx_class == "NXsample":
                self.parse_sample(item)
            else:
                print("ENTRY ", item.name, " ", nx_class)

    def parse_sample(self, group):
        nx_class = group.attrs.get("NX_class", None)
        if nx_class == "NXsample_component":
            pass
        else:
            print(group.name, " ", nx_class)

    def parse(self, file_path: str, dataparser=None):
        with h5py.File(file_path, "r") as file:
            self.parse_h5(file, dataparser)

    def parse_h5(self, h5_file, dataparser=None):
        try:

            def iterate_groups(group, indent="", nxprocess=False):
                nx_class = group.attrs.get("NX_class", None)
                if nx_class == "NXentry" or nx_class == "NXsubentry":
                    self.parse_entry(group, nxprocess, dataparser)
                elif nx_class == "NXsample":
                    self.parse_sample(group)

                else:
                    for name, item in group.items():
                        nx_class = item.attrs.get("NX_class", None)
                        if isinstance(item, h5py.Group):
                            # print(indent + 'Group:', name, ' ', nx_class)
                            # Recursively call the function for nested groups
                            iterate_groups(
                                item,
                                indent + "  ",
                                nxprocess or nx_class == "NX_process",
                            )
                        else:
                            print(indent + "Dataset:", name, " ", nx_class)

            # Start the iteration from the root of the file
            iterate_groups(h5_file)
        except Exception as err:
            print(err)


class SpectrumParser(NexusParser):
    def __init__(self):
        super().__init__()
        # Replace the parent class field with the spectrum-specific field
        self.parsed_objects = {}

    def parse_data(self, entry, default=False, nxprocess=False):

        signal = entry.attrs.get("signal", None)
        # interpretation = entry.attrs.get("interpretation", None)
        axes = entry.attrs.get("axes", None)
        # print(default,signal,interpretation,axes,isinstance(entry[signal], h5py.Dataset))
        y = entry[signal][:]
        for axis in axes:
            x = entry[axis][:]
            break
        spe = rc2.spectrum.Spectrum(x=x, y=y)
        self.parsed_objects[str(entry)] = spe


# spectrum_parser = SpectrumParser()
# spectrum_parser.parse(file_path)

# Access the spectrum data
# for key in spectrum_parser.parsed_objects:
#    spe = spectrum_parser.parsed_objects[key]
#    print("Spectrum data", key, spe)
#    spe.plot()
