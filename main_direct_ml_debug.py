if __name__ == "__main__":
    from ok import OK

    from src.config import config

    config = config
    config["ocr"]["params"]["Global.with_openvino"] = False
    config["profile_name"] = "direct-ml"
    config["debug"] = True

    ok = OK(config)
    ok.start()
