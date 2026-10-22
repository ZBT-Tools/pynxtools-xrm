"""Actionable conversion errors shared by CLI and NOMAD."""


class MissingRequiredMetadata(ValueError):
    def __init__(self, target, missing):
        self.target = target
        self.missing = tuple(missing)
        super().__init__(
            f"Missing required metadata for {target}: {', '.join(missing)}"
        )


class MetadataConflict(ValueError):
    pass


class AmbiguousMetadataAssociation(ValueError):
    pass
