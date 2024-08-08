## Introduction

This project uses several tools to enhance developer collaboration and ensure high code quality.

- [Poetry](https://python-poetry.org/): Dependency and virtual environment management.
- [Black](https://github.com/psf/black): Enforces consistent code formatting.
  - Different developers may have different habits (or no habits at all!) in code formatting. This can not only lead to frustration, but also waste valuable time, especially with poorly formatted code. Black solves this problem by applying a common formatting. It promises that any changes it makes will **not** change the resulting byte-code.
- [µsort](https://github.com/facebook/usort): Safe, minimal import sorting for Python projects.
- [Flake8](https://flake8.pycqa.org/): Linter for identifying syntax and style errors.
  - Black will prevent linter errors related to formatting, but these are not all possible errors that a linter may catch.
- [Pre-commit](https://pre-commit.com/): Git hooks for automated code quality checks.
  - Git supports [hooks](https://git-scm.com/docs/githooks)—programs that can be run at specific points in the workflow, e.g., when `git commit` is used. The `pre-commit` hook is particularly useful for running programs like the ones above automatically. This not only helps to keep the commit history cleaner, but, most importantly, saves time by catching trivial mistakes early.

## Best practices

- **Do not commit to `main` directly**. Please use [feature branches](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow) and [pull requests](https://help.github.com/articles/about-pull-requests/). Only urgent fixes that are small enough may be directly merged to `main` without a pull request.

- **Rebase regularly**. If your feature branch has conflicts with `main`, you will be asked to rebase it before merging. Getting into the habit of [rebasing](https://git-scm.com/docs/git-rebase) your feature branches on a regular basis while still working on them will save you from the hassle of dealing with massive and probably hard-to-deal-with conflicts later.

- **Avoid merge commits when pulling**. If you made local commits on a branch, but there have also been new commits to it on GitHub, you will not be able to pull the branch cleanly (i.e., fast-forward it). By default, Git will try to incorporate the remote commits to your local branch with a merge commit. Do **not** do this. Either use `git pull --rebase` or run the following to change the default:

For the current repo only:
```sh
git config pull.rebase true
```

For all Git repos on this system:
```sh
git config --global pull.rebase true
```

## Tool requirements

You will need working Python and Poetry. For Python, the recommended way of handling different Python versions is [pyenv](https://github.com/pyenv/pyenv) on UNIX-like systems (Linux, BSD, macOS) and [pyenv-win](https://github.com/pyenv-win/pyenv-win) for Windows. For Poetry, the recommended way to install on both UNIX-like and Windows systems is [pipx](https://pipx.pypa.io/).

### UNIX-like systems

Install `pyenv` and `pipx` through your package manager, e.g., on Arch Linux:
```sh
pacman -Syu pyenv python-pipx
```

Install Poetry through `pipx` ([details](https://python-poetry.org/docs/#installation)):
```sh
pipx install poetry
```

Install the Python version from `.python-version` in the project root, e.g.:
```sh
pyenv install 3.12
```

### Windows

Follow the instructions carefully. If it says PowerShell, use PowerShell, not Command Prompt, and vice versa. If it says to run the command in a new window and not use an existing one, do it. Don't skip steps. Paying careful attention will save you and your colleagues valuable time.

Assuming you have 64-bit Windows, **PowerShell** means "Windows PowerShell", **not** "Windows PowerShell (x86)" or "Windows PowerShell ISE". If you can't find it in the Start menu, try searching for it. All modern Windows versions install PowerShell by default. You shouldn't need to install it separately.

Both PowerShell and Command Prompt should be run as a regular user, **not** "as administrator".

#### Setting PowerShell ExecutionPolicy

Some of the following steps depend on running PowerShell scripts. To enable this, in **PowerShell** run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

*Notice: If you want later to return to the default policy, run the above command, substituting `Default` for `RemoteSigned`.*

#### Installing pyenv-win

In **PowerShell** (can use the existing window) run:
```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"
```

**IMPORTANT**: Do not install `pyenv-win` with Scoop. This installs an older version that doesn't support “latest” type Python versions, e.g., `3.12` that becomes `3.12.3` automatically.

For reference: https://pyenv-win.github.io/pyenv-win/docs/installation.html

#### Installing Python

Open *new* **Command Prompt** (do not use a previously opened window) and run:
```sh
pyenv install 3.12
```

In the same **Command Prompt**, set the default (global) Python version:
```sh
pyenv global 3.12
```

Check the `.python-version` file in the project root. If the version there is different, use `pyenv install` to install it as well (but do not run `pyenv global` again).

#### Installing Scoop

In **PowerShell** (can use the existing window), run:
```powershell
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
```

For reference: https://scoop.sh/

#### Installing pipx

Open *new* **Command Prompt** (do not use a previously opened window) and run:
```sh
scoop install pipx
```

Then run:
```sh
pipx ensurepath
```

For reference: https://pipx.pypa.io/stable/installation/

#### Installing Poetry

In **Command Prompt** (can use the existing window) run:
```sh
pipx install poetry
```

If you use Visual Studio Code, run:
```sh
poetry config virtualenvs.in-project true
```

For reference: https://python-poetry.org/docs/#installation

## Start developing

```sh
git clone git@github.com:ideaconsult/pyambit.git
```
```sh
cd pyambit
```
```sh
poetry install
```
```sh
poetry run pre-commit install
```

## Running the formatters & linters

**IMPORTANT**: This is run automatically against the changed files on `git commit`. If hooks like `usort` or `black` fail and change some files, review the changes with `git diff` and add the changed files with `git add`. Then either run `git commit` or `poetry run pre-commit` again, depending on what you were doing.

Run against changed files:
```sh
poetry run pre-commit
```

Run against all files:
```sh
poetry run pre-commit run --all-files
```

## Running the tests & coverage report

Run tests:
```sh
poetry run pytest
```

Run tests with coverage report:
```sh
poetry run pytest --cov
```

## Switching Python versions

Install the desired Python version with `pyenv`:
```sh
pyenv install 3.9
```

Switch the environment to the desired version:
```sh
pyenv shell 3.9 && poetry env use 3.9 && poetry install
```

**IMPORTANT**: On Windows, run this compound command in **Command Prompt**, **not** PowerShell (alternatively, in PowerShell, you must execute the commands separated by `&&` independently, one after another).

Check the virtualenv version:
```sh
poetry env info
```

## Specific IDE/editor notes

For Visual Studio Code to recognize the Poetry virtual environment you may need to set:
```sh
poetry config virtualenvs.in-project true
```

You will need to run `poetry install` again after this.
