"""Minimal stand-ins for the two InkyPi modules the plugin imports.

Lets the plugin be imported and tested without an InkyPi checkout.
Call install() before importing isolarcloud.isolarcloud.
"""
import sys
import types


class StubBasePlugin:
    def __init__(self, config, **dependencies):
        self.config = config

    def get_plugin_id(self):
        return self.config.get("id")

    def get_plugin_dir(self, path=None):
        raise RuntimeError("get_plugin_dir must be patched in tests")

    def generate_settings_template(self):
        return {"settings_template": "isolarcloud/settings.html"}

    def render_image(self, dimensions, html_file, css_file=None, template_params=None):
        raise RuntimeError("render_image must be patched in tests")


def _no_session():
    raise RuntimeError("get_http_session must be patched in tests")


def install():
    base_plugin = types.ModuleType("plugins.base_plugin.base_plugin")
    base_plugin.BasePlugin = StubBasePlugin
    http_client = types.ModuleType("utils.http_client")
    http_client.get_http_session = _no_session

    modules = {
        "plugins": types.ModuleType("plugins"),
        "plugins.base_plugin": types.ModuleType("plugins.base_plugin"),
        "plugins.base_plugin.base_plugin": base_plugin,
        "utils": types.ModuleType("utils"),
        "utils.http_client": http_client,
    }
    for name, module in modules.items():
        sys.modules.setdefault(name, module)
