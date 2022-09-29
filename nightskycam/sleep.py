import time
from .skythread import SkyThread


def sleep(skythread: SkyThread, duration: float, precision=0.02) -> None:

    start = time.time()
    while time.time() - start < duration:
        if not skythread._running:
            break
        time.sleep(precision)
