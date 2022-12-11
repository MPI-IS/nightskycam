import asyncio
import websockets
import enum
from pathlib import Path

    
def _get_most_recent_file(
        directory: Path
)->typing.Optional[Path]:
    """
    returns the most recent (creation time) file in directory
    (not recursive), or None if directory does not contain any
    file.
    """
    files = [f for f in directory.glob("*") if f.is_file()]
    if not files:
        return None
    return sorted(files,lambda f: f.stat().st_mtime)[-1]

def _encode(filepath: Path)->str:

    # first part of the string is the filename
    filename = filepath.stem
    if "|" in filename:
        raise ValueError(
            f"can not encode {filepath}: "
            "'|' is not an allowed filename character"
        )
    
    # rest of the string is the content of the file
    with open(filepath,"r") as f:
        content = f.read()

    # file string: file name + file content
    return f"{filename}|{content}"

def _decode(received: str, target_dir: Path)->Path:
    """
    assumes the 'received' string has been generated
    by the _encode function.
    Read the file name and the file content from received,
    and create in 'target_dir' a file of the same name
    and content; and returns its path
    """
    try:
        pipe_index = received.index('|')
    except ValueError as e:
        raise ValueError(
            f"failing to decode received file content: "
            "encoding string missing the '|' character that splits "
            "the file name and the file content"
        )
    filename = received[:pipe_index]
    content = received[pipe_index+1:]
    path = target_dir / filename
    with open(path,"r+") as f:
        f.write(content)
    return path


async def send_files(directory: Path, websocket)->None:
    """
    For as long 'directory' contains files (not recursive),
    send the files through the websocket, always sending the 
    most recent first.
    Exits when either 'directory' no longer contains any file
    (returns None) or when sending the file fails, for any reason
    (the corresponding WebSocketError is raised). 
    If a file is sent with success, it is deleted from 'directory'.
    """
    while True:
        # getting the most recent file in directory
        to_upload: Path = _get_most_recent_file(directory)
        # directory contains no file, exiting
        if to_upload is None:
            return
        # encoding the file (file name + file content)
        encoded = _encode(to_upload)
        # sending the file
        await websocket.send(encoded)
        # file has been sent with success, we can
        # delete the local copy
        to_upload.unlink()

    

    
    
    

