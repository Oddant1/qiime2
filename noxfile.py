#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["nox>=2025.11.12"]
# ///

import nox


# [*((python-version, uv-resolution), [*tags])]
MATRIX = [
    (('3.10', 'lowest-direct'), ['test-min']),
    (('3.10', 'highest'), []),
    (('3.11', 'highest'), ['test-max']),
]



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
    session.install("ruff")
    session.run("ruff", "check", *session.posargs)



@nox.session(venv_backend="uv")
@nox.parametrize('python,resolution', [x[0] for x in MATRIX], tags=[x[1] for x in MATRIX])
def test(session: nox.Session, resolution) -> None:
    """
    Run the tests (can use `-t test-min` or `-t test-max` to filter)
    """
    setup_uv(session, resolution)
    session.run("pytest", *session.posargs, env={'QIIMETEST':"1"})
