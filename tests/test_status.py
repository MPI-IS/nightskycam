import threading
import toml
import time
import nightskycam
import tempfile
from pathlib import Path


def test_status_thread():

    with tempfile.TemporaryDirectory() as tmp_dir_:
        with tempfile.TemporaryDirectory() as final_dir_:

            tmp_dir = Path(tmp_dir_)
            final_dir = Path(final_dir_)

            config = {}

            main_config = {"period": 0.1}
            dummy_config = {}
            status_config = {
                "update_every": 0.1,
                "tmp_dir": str(tmp_dir),
                "final_dir": str(final_dir),
            }

            config["main"] = main_config
            config["nightskycam.skythreads.DummyThread"] = dummy_config
            config["nightskycam.skythreads.StatusThread"] = status_config

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

                status_file = final_dir / "dummy.status"
                assert status_file.is_file()

                content = toml.load(status_file)
                assert content["status"] == "running"

                dummy_thread = [
                    st
                    for st in nightskycam.running_threads.RunningThreads.skythreads
                    if st.__class__.__name__ == "DummyThread"
                ][0]

                dummy_thread.set_error("test error")

                time.sleep(1)

                content = toml.load(status_file)
                assert content["status"] == "failure"

            thread.join()
