import typing

GlobalConfiguration = typing.Dict[str, typing.Dict[str, typing.Any]]
Configuration = typing.Dict[str, typing.Any]


CV2Format = typing.Dict[str, int]
"""
A dictionary providing values of opencv2 save method 'params' key word argument,
e.g. {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}
"""

CV2Params = typing.List[typing.Tuple[int, int]]
"""
A configuration array for the 'params' key word argument
of the opencv2 save method,
e.g [(cv2.IMWRITE_JPEG_QUALITY,95),(IMWRITE_JPEG_PROGRESSIVE,0)]
"""


Metadata = typing.Dict[str, typing.Any]
