# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/ideaconsult/pyambit/blob/COVERAGE-REPORT/htmlcov/index.html)

| Name                                             |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/pyambit/\_\_init\_\_.py                      |        0 |        0 |    100% |           |
| src/pyambit/ambit\_deco.py                       |       10 |        0 |    100% |           |
| src/pyambit/datamodel.py                         |      893 |      168 |     81% |42, 52, 97, 121, 125, 138, 169, 193, 201, 223, 247, 254, 272, 319, 329, 331, 340, 362, 375-377, 380-382, 386-390, 420-422, 428, 444, 446-448, 455-456, 465, 478, 504, 509, 512, 533, 543, 550, 558, 571, 580-584, 618, 628, 663, 674, 693, 697, 723, 735, 767, 825, 827, 834, 847-863, 888, 966, 1003-1008, 1066-1067, 1102-1106, 1159-1174, 1249-1252, 1294-1299, 1325-1326, 1335, 1341, 1356, 1378-1385, 1395, 1409-1414, 1434-1442, 1460-1463, 1495-1504, 1541, 1557, 1594-1596, 1612, 1628-1653, 1693, 1717-1726, 1752-1768 |
| src/pyambit/nexus\_parser.py                     |      107 |      107 |      0% |     1-220 |
| src/pyambit/nexus\_spectra.py                    |       68 |       26 |     62% |24-25, 28-29, 53, 65, 81, 83, 93, 95, 97, 99, 165-188 |
| src/pyambit/nexus\_writer.py                     |      333 |       64 |     81% |36, 46, 64, 66, 68, 102-103, 124-125, 134-136, 222-223, 257-258, 297, 307, 309, 315-316, 326-327, 333-335, 353-358, 406, 422-441, 455, 463-466, 470-471, 489, 523-524, 538-540, 547, 566, 571-572, 607, 647-648, 657 |
| src/pyambit/solr\_writer.py                      |      131 |       15 |     89% |21-22, 26, 34, 43, 59, 62-66, 100, 128, 174-176 |
| tests/pyambit/datamodel/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| tests/pyambit/datamodel/datamodel\_test.py       |      214 |        0 |    100% |           |
| tests/pyambit/datamodel/nexus\_writer\_test.py   |       51 |       12 |     76% |35-36, 39-40, 71-81 |
| tests/pyambit/datamodel/solr\_writer\_test.py    |       26 |        0 |    100% |           |
| tests/pyambit/datamodel/spectra\_writer\_test.py |       21 |        0 |    100% |           |
|                                        **TOTAL** | **1854** |  **392** | **79%** |           |


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