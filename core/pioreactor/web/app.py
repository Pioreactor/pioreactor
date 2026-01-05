# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import typing as t
from base64 import b64decode
from datetime import datetime
from datetime import timezone

import paho.mqtt.client as mqtt
from flask import Flask
from flask import g
from flask import jsonify
from flask import request
from flask.json.provider import JSONProvider
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from paho.mqtt.enums import CallbackAPIVersion
from pioreactor.config import config as pioreactor_config
from pioreactor.config import get_leader_hostname
from pioreactor.logging import create_logger
from pioreactor.plugin_management import load_plugins
from pioreactor.version import __version__
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT

VERSION = __version__
HOSTNAME = get_unit_name()
NAME = f"pioreactor-{HOSTNAME}-api"


# set up logging
logger = create_logger(
    NAME, source="ui", experiment="$experiment", log_file_location=pioreactor_config["logging"]["ui_log_file"]
)


logger.debug(f"Starting {NAME}={VERSION} on {HOSTNAME}...")

client = mqtt.Client(client_id="pioreactor_ui", callback_api_version=CallbackAPIVersion.VERSION2)
client.username_pw_set(
    pioreactor_config.get("mqtt", "username", fallback="pioreactor"),
    pioreactor_config.get("mqtt", "password", fallback="raspberry"),
)


load_plugins()


def decode_base64(string: str) -> str:
    return b64decode(string).decode("utf-8")


def create_app():
    # load plugins
    app = Flask(NAME)
    app.logger = logger

    from pioreactor.web.unit_api import unit_api_bp

    app.register_blueprint(unit_api_bp)

    if am_I_leader():
        from pioreactor.web.api import api_bp
        from pioreactor.web.mcp import mcp_bp

        app.register_blueprint(api_bp)
        app.register_blueprint(mcp_bp)
        # we currently only need to communicate with MQTT for the leader.
        # don't even connect if a worker - if the leader is down, this will crash and restart the server over and over.
        broker_address = pioreactor_config.get("mqtt", "broker_address", fallback="localhost").split(";")[0]
        broker_port = pioreactor_config.getint("mqtt", "broker_port", fallback=1883)
        client.connect(
            host=broker_address,
            port=broker_port,
        )
        logger.debug(f"Starting MQTT client at {broker_address}:{broker_port}")
        client.loop_start()

    @app.teardown_appcontext
    def close_connection(exception) -> None:
        db = getattr(g, "_app_database", None)
        if db is not None:
            db.close()

        db = getattr(g, "_metadata_database", None)
        if db is not None:
            db.close()

    @app.errorhandler(404)
    def handle_not_found(e):
        # Return JSON for API requests

        # check if accessing /api/ when not leader. User had the wrong leader_hostname on their leader image. This would have helped them.
        if not am_I_leader() and request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": "Can't access /api/ endpoints when this unit isn't the leader. Did you mean /unit_api/?"
                    }
                ),
                404,
            )

        return jsonify({"error": e.description}), 404

    @app.errorhandler(400)
    def handle_bad_request(e):
        # Return JSON for API requests
        return jsonify({"error": e.description}), 400

    @app.errorhandler(403)
    def handle_not_auth(e):
        # Return JSON for API requests
        return jsonify({"error": e.description}), 403

    @app.errorhandler(500)
    def handle_server_error(e):
        return (
            jsonify({"error": f"{e.description}"}),
            500,
        )

    @app.errorhandler(502)
    def handle_bad_gateway(e):
        return (
            jsonify({"error": f"{e.description}"}),
            502,
        )

    app.json = MsgspecJsonProvider(app)
    app.get_json = app.json.loads

    return app


def msg_to_JSON(msg: str, task: str, level: str, timestamp: None | str = None, source: str = "ui") -> bytes:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return dumps(
        {
            "message": msg.strip(),
            "task": task,
            "source": source,
            "level": level,
            "timestamp": timestamp,
        }
    )


def publish_to_log(msg: str, task: str, level="DEBUG") -> None:
    publish_to_experiment_log(msg, "$experiment", task, level)


def publish_to_experiment_log(msg: str | t.Any, experiment: str, task: str, level="DEBUG") -> None:
    if not isinstance(msg, str):
        # attempt to serialize
        try:
            msg = dumps(msg)
        except TypeError:
            msg = str(msg)

    getattr(logger, level.lower())(msg)


def publish_to_error_log(msg, task: str) -> None:
    publish_to_log(msg, task, "ERROR")


def _make_dicts(cursor, row) -> dict:
    return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))


def _get_app_db_connection():
    db = getattr(g, "_app_database", None)
    if db is None:
        try:
            db = g._app_database = sqlite3.connect(pioreactor_config.get("storage", "database"))
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                logger.error("Database is locked, please close any other connections or restart.")
            elif "unable to open database file" in str(e):
                logger.error(
                    "Permissions on database are probably incorrect, ownership should be pioreactor:www-data on ALL sqlite files AND THE .pioreactor/storage DIR! ."
                )
            raise e

        db.create_function(
            "BASE64", 1, decode_base64
        )  # TODO: until next OS release which implements a native sqlite3 base64 function

        db.row_factory = _make_dicts
        db.executescript(
            """
            PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
            PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
            PRAGMA busy_timeout = 15000;
            PRAGMA foreign_keys = ON;
            PRAGMA cache_size = -4000;
        """
        )

    return db


def _get_temp_local_metadata_db_connection():
    db = getattr(g, "_local_metadata_database", None)
    if db is None:
        db = g._local_metadata_database = sqlite3.connect(
            f'file:{pioreactor_config.get("storage", "temporary_cache")}?mode=ro', uri=True
        )
        db.row_factory = _make_dicts
        db.executescript(
            """
            PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
            PRAGMA busy_timeout = 15000;
            PRAGMA cache_size = -4000;
            PRAGMA query_only = 1; -- forbid writes through this connection
        """
        )

    return db


def query_app_db(query: str, args=(), one: bool = False) -> dict[str, t.Any] | list[dict[str, t.Any]] | None:
    assert am_I_leader()
    con = _get_app_db_connection()
    try:
        con.execute("PRAGMA query_only = 1")
        cur = con.execute(query, args)
        rv = cur.fetchall()
        cur.close()
    finally:
        # Restore to default to allow mutations via modify_app_db within same request
        try:
            con.execute("PRAGMA query_only = 0")
        except Exception:
            pass
    if one:
        return rv[0] if rv else None
    return rv


def query_temp_local_metadata_db(
    query: str, args=(), one: bool = False
) -> dict[str, t.Any] | list[dict[str, t.Any]] | None:
    cur = _get_temp_local_metadata_db_connection().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def modify_app_db(statement: str, args=()) -> int:
    assert am_I_leader()
    con = _get_app_db_connection()
    cur = con.cursor()
    try:
        cur.execute(statement, args)
        con.commit()
    except sqlite3.IntegrityError as e:
        print(e)
        return 0
    except Exception as e:
        print(e)
        con.rollback()  # TODO: test
        raise e
    finally:
        row_changes = cur.rowcount
        cur.close()
    return row_changes


class MsgspecJsonProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return dumps(obj)

    def loads(self, obj, type=None, **kwargs):
        if type is not None:
            return loads(obj, type=type)
        else:
            return loads(obj)


def get_all_workers_in_experiment(experiment: str) -> list[str]:
    if experiment == UNIVERSAL_EXPERIMENT:
        r = query_app_db("SELECT pioreactor_unit FROM workers")
    else:
        r = query_app_db(
            "SELECT pioreactor_unit FROM experiment_worker_assignments WHERE experiment = ?",
            (experiment,),
        )
    assert isinstance(r, list)
    return [unit["pioreactor_unit"] for unit in r]


def get_all_workers() -> list[str]:
    result = query_app_db(
        """
        SELECT w.pioreactor_unit as unit
        FROM workers w
        ORDER BY w.added_at DESC
        """
    )
    assert result is not None and isinstance(result, list)
    return list(r["unit"] for r in result)


def get_all_active_workers() -> list[str]:
    result = query_app_db(
        """
        SELECT w.pioreactor_unit as unit
        FROM workers w
        WHERE w.is_active=1
        ORDER BY w.added_at DESC
        """
    )
    assert result is not None and isinstance(result, list)
    return list(r["unit"] for r in result)


def get_all_units() -> list[str]:
    result = query_app_db(
        f"""SELECT DISTINCT pioreactor_unit FROM (
            SELECT "{get_leader_hostname()}" AS pioreactor_unit
                UNION
            SELECT pioreactor_unit FROM workers
        );"""
    )
    assert result is not None and isinstance(result, list)
    return list(r["pioreactor_unit"] for r in result)


if __name__ == "__main__":
    create_app().run()
