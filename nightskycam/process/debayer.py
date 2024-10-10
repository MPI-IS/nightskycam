import cv2
import nptyping as npt

DEBAYER_CODE = "COLOR_BAYER_BG2BGR"


def debayer(
    image: npt.NDArray, conversion_code: str = DEBAYER_CODE
) -> npt.NDArray:
    """
    debayer the image using cv2.COLOR_BAYER_BG3BGR
    """
    try:
        code = getattr(cv2, conversion_code)
    except AttributeError:
        raise ValueError(
            f"{conversion_code} is not a valid cv2 conversion code."
        )
    try:
        r = cv2.cvtColor(image, code)
    except Exception as e:
        raise e.__class__(f"failed to apply conversion code to the image: {e}")
    return r
