import tempfile
import nightskycam
from pathlib import Path


def test_picture_thread():

    with tempfile.TemporaryDirectory() as target_dir_:
            
        target_dir = Path(target_dir_)
    
        config = {}

        main_config = {"period": 0.1}
        dummy_config = {
            "target_dir":target_dir,
            "picture_every":0.1,
            "start_record":None,
            "end_record":None,
            "width":400,
            "height":200,
        }

        config["main"] = main_config
        config["nightskycam.skythreads.DummyCameraThread"] = dummy_config

        config_getter = nightskycam.configuration_getter.DictConfigurationGetter(
            config
        )

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

            time.sleep(1)

            image_files = list(target_dir.glob("*.npy"))
            assert len(image_files)>5
            assert len(image_files)<12

            time.sleep(1)

            image_files2 = list(target_dir.glob("*.npy"))
            assert len(image_files2)>len(image_file)

        image = np.load(image_files[0])
        assert image.shape[0] == 400
        assert image.shape[1] == 200
