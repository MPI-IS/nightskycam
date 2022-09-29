import typing
from threading import Lock


class Locks:
    """
    Class maintaining a dictionary of locks.
    """

    _locks: typing.Dict[str, Lock] = {}

    @classmethod
    def get_lock(cls, key: str) -> Lock:
        """
        Returns the lock corresponding to the key
        (arbitrary string). If this key does not exists
        (i.e. this method has never been called with it as
        argument), the lock is created.
        """
        try:
            return cls._locks[key]
        except KeyError:
            lock = Lock()
            cls._locks[key] = lock
            return lock

    @classmethod
    def get_config_lock(cls) -> Lock:
        return cls.get_lock("config")
