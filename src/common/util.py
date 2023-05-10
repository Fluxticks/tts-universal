def r_replace(string: str, _old: str, _new: str, count: int = 1) -> str:
    return _new.join(string.rsplit(_old, count))
