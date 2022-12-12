import typing

# multiprocessing and not threading
# because of the postprocess thread
# which spawns a process
from multiprocessing import Lock
from multiprocessing.synchronize import Lock as LockBase


class Locks:
    """
    Class maintaining a dictionary of locks.
    """

    _locks: typing.Dict[str, LockBase] = {}

    @classmethod
    def get_lock(cls, key: str) -> LockBase:
        """
        Returns the lock corresponding to the key
        (arbitrary string). If this key does not exists
        (i.e. this method has never been called with it as
        argument), the lock is created.
        """
        try:
            return cls._locks[key]
        except KeyError:
            # Lock is not a class, but a function
            # which returns a LockBase
            lock = Lock()
            cls._locks[key] = lock
            return lock

    @classmethod
    def get_config_lock(cls) -> LockBase:
        return cls.get_lock("config")
