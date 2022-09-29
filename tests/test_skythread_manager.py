import threading
import time
import typing
import nightskycam


def _get_configuration_getter():

    main_config: nightskycam.types.Configuration = {
        "period": 0.2,
        "id": 0,
    }
    dummy_config: nightskycam.types.Configuration = {}

    # creating the configuration getter that will
    # return this config
    thread_config: nightskycam.types.GlobalConfiguration = {
        "main": main_config,
        "nightskycam.skythreads.DummyThread": dummy_config,
    }
    config_getter = nightskycam.configuration_getter.DictConfigurationGetter(thread_config)

    return config_getter


def test_get_skythreads():

    # getting the configuration getter
    config_getter = _get_configuration_getter()

    # getting the corresponding threads
    thread_classes = nightskycam.configuration_file.get_skythreads(
        config_getter.get_global()
    )
    threads = [class_(config_getter) for class_ in thread_classes]

    # the config requests only "DummyThread"
    assert len(threads) == 1
    assert threads[0].__class__.__name__ == "DummyThread"


def test_deploy_tests():

    # getting the configuration getter
    config_getter = _get_configuration_getter()

    # checking nightskycam.deploy_tests does not raise an exception
    error: typing.Optional[str] = None
    try:
        nightskycam.manager.deploy_tests(config_getter)
    except Exception as e:
        error = str(e)

    assert error is None


# testing skythread_manager
def test_skythread_manager():

    # getting the configuration getter
    config_getter = _get_configuration_getter()

    # main control
    main_control = nightskycam.manager.MainControl()

    # starting the manager
    run_thread = threading.Thread(
        target=nightskycam.manager.run, args=(main_control, config_getter)
    )
    run_thread.start()
    time.sleep(0.5)

    # getting the DummyThread
    running_threads = nightskycam.running_threads.RunningThreads.skythreads
    dummy_thread: typing.Optional[nightskycam.DummyThread] = None
    for thread in running_threads:
        if "DummyThread" in thread.__class__.__name__:
            dummy_thread = thread
            break

    assert dummy_thread is not None

    time.sleep(0.5)

    status = dummy_thread.get_status()
    assert status.status == nightskycam.status.Status.running

    dummy_thread.set_error("test error")
    time.sleep(0.5)
    status = dummy_thread.get_status()
    assert status.status == nightskycam.status.Status.failure

    dummy_thread.set_error(None)
    time.sleep(0.5)
    status = dummy_thread.get_status()
    assert status.status == nightskycam.status.Status.running

    main_control.running = False
    run_thread.join()
