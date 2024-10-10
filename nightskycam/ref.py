import glob
import re
from typing import Dict, List, Tuple

for filename in glob.glob("**/*.py", recursive=True):
    print(filename)

    with open(filename, "r") as file:
        filedata = file.read()

    filedata = re.sub(r"list\[(.*?)\]", r"List[\1]", filedata)

    filedata = re.sub(r"tuple\[(.*?)\]", r"Tuple[\1]", filedata)

    filedata = re.sub(r"dict\[(.*?), (.*?)\]", r"Dict[\1, \2]", filedata)

    for imp in ("List", "Tuple", "Dict"):
        imp_ = f"from typing import {imp}"
        if imp in filedata and imp_ not in filedata:
            filedata = imp_ + "\n" + filedata
            print("\tadding import:", imp_)

    with open(filename, "w") as file:
        file.write(filedata)
