from datetime import datetime, timedelta
import typing
import socket


class Meta:
    @classmethod
    def get(cls) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:

        # getting current date and time as string
        date = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")

        # getting hostname
        hostname = socket.gethostname()

        # suitable filename
        filename = f"{hostname}_{date}"

        # metadata dictionary
        d = {"date": date, "hostname": hostname}

        return filename, d

    @classmethod
    def decode(cls, filename: str) -> typing.Tuple[str, str]:
        sindex = filename.find("_")
        if sindex < 0:
            raise ValueError(
                f"can not decode the filename {filename} into an hostname "
                f"and a date: no '_' character"
            )
        hostname = filename[:sindex]
        date_ = filename[sindex + 1 :]
        date = datetime.strptime(date_, "%d_%m_%Y_%H_%M_%S")
        if date.hour < 12:
            date_str = (date - timedelta(days=1)).strftime("%Y_%m_%d")
        else:
            date_str = date.strftime("%Y_%m_%d")
        return hostname, date_str
