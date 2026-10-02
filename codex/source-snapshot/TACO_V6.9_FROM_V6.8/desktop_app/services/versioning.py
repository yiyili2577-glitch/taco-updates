import re


def version_tuple(value):
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))[:4]]
    return tuple((nums + [0, 0, 0, 0])[:4])


def is_newer(candidate, current):
    return version_tuple(candidate) > version_tuple(current)
