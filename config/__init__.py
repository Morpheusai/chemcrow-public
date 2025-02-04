import os
import sys
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def deep_update(original, update):
    """
    Recursively update a dictionary.
    """
    for key, value in update.items():
        if isinstance(value, dict) and key in original and isinstance(original[key], dict):
            deep_update(original[key], value)
        else:
            original[key] = value
    return original

def read_config_yaml_multi_env(enable_multi_env=False):
    config_path = BASE_DIR + "/config.yaml"
    print(config_path)
    if not os.path.exists(config_path):
        print(f"{config_path} does not exist.")
        sys.exit(1)

    with open(config_path, 'r', encoding="utf-8") as f:
        config_yaml = yaml.safe_load(f)
        
    env = os.getenv("ENV", "dev")
    if enable_multi_env:
        env_config_path = BASE_DIR + "/config.{env}.yaml"
        with open(env_config_path, 'r') as f:
            env_config = yaml.safe_load(f)
        config_yaml = deep_update(config_yaml, env_config)
    return config_yaml

CONFIG_YAML = read_config_yaml_multi_env()