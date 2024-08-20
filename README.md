# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

| Name                                             |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/pyambit/\_\_init\_\_.py                      |        0 |        0 |    100% |           |
| src/pyambit/ambit\_deco.py                       |       10 |        0 |    100% |           |
| src/pyambit/datamodel.py                         |      790 |      144 |     82% |42, 52, 90, 114, 118, 131, 163, 175, 186, 188, 192, 216, 229-231, 234-236, 240-244, 274-276, 282, 289, 300, 302-304, 318, 331, 351, 356, 359, 380, 390, 396, 403, 415, 424-427, 455, 465, 496, 507, 524, 528, 548, 560, 592, 649, 651, 658, 671-687, 711, 808-812, 867-868, 903-906, 1018-1021, 1063-1068, 1094-1095, 1104, 1110, 1125, 1139-1146, 1156, 1170-1175, 1195-1203, 1221-1224, 1256-1265, 1302, 1318, 1346-1348, 1364, 1380-1405, 1445, 1469-1478 |
| src/pyambit/nexus\_parser.py                     |       72 |       72 |      0% |     1-103 |
| src/pyambit/nexus\_spectra.py                    |       45 |       16 |     64% |42, 54, 128-151 |
| src/pyambit/nexus\_writer.py                     |      276 |       44 |     84% |52-53, 74-75, 77-79, 149-150, 182-183, 247, 249, 259-260, 270-271, 277-279, 296-301, 347, 363-375, 389, 397-400, 404-405, 422, 499, 530-531 |
| tests/pyambit/datamodel/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| tests/pyambit/datamodel/datamodel\_test.py       |      187 |        0 |    100% |           |
| tests/pyambit/datamodel/nexus\_writer\_test.py   |       37 |        3 |     92% |     55-57 |
| tests/pyambit/datamodel/spectra\_writer\_test.py |       21 |        0 |    100% |           |
|                                        **TOTAL** | **1438** |  **279** | **81%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/ideaconsult/pyambit/COVERAGE-REPORT/badge.svg)](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/ideaconsult/pyambit/COVERAGE-REPORT/endpoint.json)](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fideaconsult%2Fpyambit%2FCOVERAGE-REPORT%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.