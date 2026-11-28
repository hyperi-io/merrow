# reference

How a reference repo plugs into merrow. A reference repo holds data, never code: identity colours, labels, aliases and diagram sources for its realms. merrow loads layers in order, base then org then personal, and a later layer overrides an earlier one.

A reference repo is whatever config lists, under any name. `hyperi-merrow` is one example. It is a directory listed under `references` in config. It holds the data file named by `reference_file` (`merrow.yaml` by default), which merrow layers over its own base config. Other data files, such as `objects.yaml`, are found through `config.data_file`: the last reference repo that has the file wins, else merrow's own (`src/merrow/config.py`).
