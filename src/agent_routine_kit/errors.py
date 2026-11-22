"""Errors for snapshots this kit cannot audit."""


class ContractError(ValueError):
    """The snapshot is not a supported contract object."""

    exit_code = 2
