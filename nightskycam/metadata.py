from datetime import datetime
import typing
import toml
import socket


class Meta:
    @classmethod
    def get(cls) -> typing.Tuple[str, typing.Dict[str,typing.Any]]:

        # getting current date and time as string
        date = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")

        # getting hostname
        hostname = socket.gethostname()

        # suitable filename
        filename = f"{hostname}_{date}"

        # metadata dictionary
        d = {"date": date, "hostname": hostname}

        return filename, d
