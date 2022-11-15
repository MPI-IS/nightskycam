import tempfile
import threading
import time
import nightskycam
import numpy as np
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path


class _Active(Enum):
    active_default = 0
    active_date = 1
    inactive = 2

    
def _get_config(target_dir: Path, active: _Active)->nightskycam.configuration_getter.ConfigurationGetter:

    now = datetime.now()
    
    if active == _Active.active_default:
        start = "None"
        end = "None"

    if active == _Active.active_date:
        start = (now - timedelta(hours=1)).strftime("%H:%M")
        end =  (now + timedelta(hours=1)).strftime("%H:%M")

    if active == _Active.inactive:
        start = (now + timedelta(hours=1)).strftime("%H:%M")
        end =  (now + timedelta(hours=2)).strftime("%H:%M")
        
    config = {}
        
    main_config = {"period": 0.1}
    dummy_config = {
        "target_dir":target_dir,
        "picture_every":1,
        "start_record":start,
        "end_record":end,
        "width":400,
        "height":200,
    }
    config["main"] = main_config
    config["nightskycam.skythreads.DummyCameraThread"] = dummy_config

    return nightskycam.configuration_getter.DictConfigurationGetter(
        config
    )

    
def test_picture_thread_active_default():

    with tempfile.TemporaryDirectory() as target_dir_:
            
        target_dir = Path(target_dir_)
        config_getter = _get_config(target_dir, _Active.active_default)

        nightskycam.manager.deploy_tests(config_getter)

        with nightskycam.manager.MainControl() as main_control:

            thread = threading.Thread(
                target=nightskycam.manager.run,
                args=(
                    main_control,
                    config_getter,
                ),
            )
            thread.start()

            time.sleep(2)

            image_files = list(target_dir.glob("*.npy"))
            assert len(image_files)>=1
            assert len(image_files)<4

            time.sleep(1)

            image_files2 = list(target_dir.glob("*.npy"))
            assert len(image_files2)>len(image_files)

        image = np.load(image_files[0])
        assert image.shape[0] == 400
        assert image.shape[1] == 200


def test_picture_thread_active_date():

    with tempfile.TemporaryDirectory() as target_dir_:

        target_dir = Path(target_dir_)
        config_getter = _get_config(target_dir, _Active.active_date)

        nightskycam.manager.deploy_tests(config_getter)

        with nightskycam.manager.MainControl() as main_control:

            thread = threading.Thread(
                target=nightskycam.manager.run,
                args=(
                    main_control,
                    config_getter,
                ),
            )
            thread.start()

            time.sleep(2)

            image_files = list(target_dir.glob("*.npy"))
            assert len(image_files)>=1
            assert len(image_files)<4

            time.sleep(1)

            image_files2 = list(target_dir.glob("*.npy"))
            assert len(image_files2)>len(image_files)

        image = np.load(image_files[0])
        assert image.shape[0] == 400
        assert image.shape[1] == 200

        
def test_picture_thread_inactive():

    with tempfile.TemporaryDirectory() as target_dir_:
            
        target_dir = Path(target_dir_)
        config_getter = _get_config(target_dir, _Active.inactive)
        
        nightskycam.manager.deploy_tests(config_getter)

        with nightskycam.manager.MainControl() as main_control:

            thread = threading.Thread(
                target=nightskycam.manager.run,
                args=(
                    main_control,
                    config_getter,
                ),
            )
            thread.start()

            time.sleep(2)

            image_files = list(target_dir.glob("*.npy"))
            assert len(image_files) == 0


        
