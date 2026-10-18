from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskRef:
    """Identify a task type and the version of its input/output contract."""

    name: str
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("TaskRef name must be a string.")
        if not self.name.strip():
            raise ValueError("TaskRef name must not be blank.")
        if "\x00" in self.name:
            raise ValueError("TaskRef name must not contain NUL characters.")
        if type(self.version) is not int:
            raise TypeError("TaskRef version must be an integer.")
        if self.version <= 0:
            raise ValueError("TaskRef version must be a positive integer.")
