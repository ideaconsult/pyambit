# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

| Name                                             |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/pyambit/\_\_init\_\_.py                      |        0 |        0 |    100% |           |
| src/pyambit/ambit\_deco.py                       |       10 |        0 |    100% |           |
| src/pyambit/datamodel.py                         |      893 |      168 |     81% |42, 52, 97, 121, 125, 138, 169, 193, 201, 223, 247, 254, 272, 319, 329, 331, 340, 361, 374-376, 379-381, 385-389, 419-421, 427, 434, 445, 447-449, 463, 476, 502, 507, 510, 531, 541, 548, 556, 569, 578-582, 616, 626, 661, 672, 691, 695, 721, 733, 765, 823, 825, 832, 845-861, 885, 963, 1000-1005, 1063-1064, 1099-1104, 1156-1171, 1246-1249, 1291-1296, 1322-1323, 1332, 1338, 1353, 1375-1382, 1392, 1406-1411, 1431-1439, 1457-1460, 1492-1501, 1538, 1554, 1591-1593, 1609, 1625-1650, 1690, 1714-1723, 1749-1765 |
| src/pyambit/nexus\_parser.py                     |      107 |      107 |      0% |     1-211 |
| src/pyambit/nexus\_spectra.py                    |       56 |       21 |     62% |23-24, 27-28, 51, 63, 78, 143-166 |
| src/pyambit/nexus\_writer.py                     |      329 |       60 |     82% |36, 46, 64, 66, 68, 102-103, 124-125, 134-136, 222-223, 257-258, 297, 307, 309, 315-316, 326-327, 333-335, 353-358, 406, 422-435, 451, 459-462, 466-467, 485, 515-516, 530-532, 539, 557, 562-563, 598, 636-637, 646 |
| src/pyambit/solr\_writer.py                      |      131 |       15 |     89% |21-22, 26, 34, 43, 59, 62-66, 100, 128, 174-176 |
| tests/pyambit/datamodel/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| tests/pyambit/datamodel/datamodel\_test.py       |      214 |        0 |    100% |           |
| tests/pyambit/datamodel/nexus\_writer\_test.py   |       51 |       12 |     76% |35-36, 39-40, 71-81 |
| tests/pyambit/datamodel/solr\_writer\_test.py    |       26 |        0 |    100% |           |
| tests/pyambit/datamodel/spectra\_writer\_test.py |       21 |        0 |    100% |           |
|                                        **TOTAL** | **1838** |  **383** | **79%** |           |


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