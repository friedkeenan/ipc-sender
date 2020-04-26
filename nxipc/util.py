def align(value, a, up=True):
    if up:
        return (value + a - 1) & ~(a - 1)
    else:
        return (value - (a - 1)) & ~(a - 1)

def bit(*args):
    ret = 0

    for arg in args:
        ret |= 1 << arg

    return ret