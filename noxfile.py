#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["nox>=2025.11.12"]
# ///

import nox



def setup_uv(session: nox.Session, resolution='highest') -> None:
    """
    IMPORTANT: make sure to set `venv_backend="uv"` on @nox.session(). 
    """
    session.run_install(
        "uv",
        "sync",
        "--extra=jupyter",
        f"--resolution={resolution}",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )


@nox.session(venv_backend="uv")
def lint(session: nox.Session) -> None:
    """
    Run the linters
    """
    setup_uv(session)
    session.install("flake8")
    session.run("flake8", *session.posargs)



@nox.session(venv_backend="uv", python=['3.10', '3.11'])
@nox.parametrize('resolution', ['lowest-direct', 'highest'], ids=['min', 'max'])
def test(session: nox.Session, resolution) -> None:
    """
    Run the tests with (min|max) of the listed dependencies in the pyproject.toml
    """
    setup_uv(session, resolution)
    session.run("pytest", *session.posargs, env={'QIIMETEST':"1"})
