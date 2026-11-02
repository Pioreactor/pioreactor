# -*- coding: utf-8 -*-
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("already_excluded", [False, True])
@pytest.mark.parametrize("proxy_exists", [False, True])
@pytest.mark.parametrize("module_loaded", [False, True])
def test_proxy_migration_repairs_partial_configuration(
    tmp_path: Path, already_excluded: bool, proxy_exists: bool, module_loaded: bool
) -> None:
    root = Path(__file__).resolve().parents[2]
    assets = root / "core/update_scripts/upcoming"
    config = tmp_path / "ui.conf"
    route = (assets / "browser-mqtt-proxy.conf").read_text(encoding="utf-8")
    config.write_text(
        'exclude = "|/exports($|/)'
        + ("|/mqtt$)" if already_excluded else ")")
        + '"\n'
        + (route if proxy_exists else ""),
        encoding="utf-8",
    )
    (tmp_path / "browser-mqtt-proxy.conf").write_text(route, encoding="utf-8")
    lighttpd = tmp_path / "lighttpd"
    lighttpd.write_text(
        "#!/bin/bash\n"
        + f"[ $(grep -Fc 'proxy.header =' '{config}') -le 1 ] || exit 1\n"
        + 'if [ "$1" = -p ]; then\n'
        + f"if {'true' if module_loaded else 'false'} || grep -q mod_proxy '{config}'; then\n"
        + "echo 'server.modules = ( \"mod_proxy\" )'\nelse\necho 'server.modules = ( \"mod_rewrite\" )'\nfi\nfi\nexit 0\n",
        encoding="utf-8",
    )
    lighttpd.chmod(0o755)
    script = (
        (assets / "90_browser_mqtt_proxy.sh")
        .read_text(encoding="utf-8")
        .replace("CONFIG=/etc/lighttpd/conf-available/50-pioreactorui.conf", f"CONFIG={config}")
        .replace("/usr/sbin/lighttpd", str(lighttpd))
        .replace('chown root:root "$TEMP"', ":")
    )
    target = tmp_path / "update.sh"
    target.write_text(script, encoding="utf-8")
    subprocess.run(["bash", str(target)], check=True, capture_output=True)
    installed = config.read_text(encoding="utf-8")
    assert installed.count('server.modules += ( "mod_proxy" )') == (0 if module_loaded else 1)
    assert installed.count('$HTTP["url"] == "/mqtt"') == 1
    assert "|/mqtt$)" in installed

    subprocess.run(["bash", str(target)], check=True, capture_output=True)
    assert config.read_text(encoding="utf-8") == installed
