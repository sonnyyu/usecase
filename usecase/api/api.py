"""Define all the RestfulAPI entry points."""
import csv
import datetime
from io import BytesIO
import logging
import simplejson as json
import six
import sys

from oslo_config import cfg

import flask
from flask import request
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from usecase.api import admin_api
from usecase.api import app
from usecase.api import auth_handler
from usecase.api import exception_handler
from usecase.api import utils
from usecase.db import database
from usecase.db import models
from usecase.db import user as user_api
from usecase.utils import logsetting
from usecase.utils import settings
from usecase.utils import util


opts = [
    cfg.StrOpt(
        'logfile',
        help='log file name',
        default=settings.WEB_LOGFILE
    ),
    cfg.IntOpt(
        'server_port',
        help='flask server port',
        default=settings.SERVER_PORT
    ),
    cfg.BoolOpt(
        'server_debug',
        help='flask server in debug mode',
        default=settings.DEBUG
    )
]
CONF = util.CONF
CONF.register_cli_opts(opts)
logger = logging.getLogger(__name__)
if sys.version_info > (3,):
    long = int
    basestring = str
    integer_types = (int,)
    string_types = (str, bytes)
else:
    integer_types = (int, long)
    string_types = (basestring,)


def _clean_data(data, keys):
    """remove keys from dict."""
    for key in keys:
        if key in data:
            del data[key]


def _replace_data(data, key_mapping):
    """replace key names in dict."""
    for key, replaced_key in six.iteritems(key_mapping):
        if key in data:
            data[replaced_key] = data[key]
            del data[key]


def _get_data(data, key):
    """get key's value from request arg dict.

    When the value is list, return the element in the list
    if the list size is one. If the list size is greater than one,
    raise exception_handler.BadRequest.
    Example: data = {'a': ['b'], 'b': 5, 'c': ['d', 'e'], 'd': []}
             _get_data(data, 'a') == 'b'
             _get_data(data, 'b') == 5
             _get_data(data, 'c') raises exception_handler.BadRequest
             _get_data(data, 'd') == None
             _get_data(data, 'e') == None
    Usage: Used to parse the key-value pair in request.args to expected types.
           Depends on the different flask plugins and what kind of parameters
           passed in, the request.args format may be as below:
           {'a': 'b'} or {'a': ['b']}. _get_data forces translate the
           request.args to the format {'a': 'b'}. It raises exception when some
           parameter declares multiple times.
    """
    if key in data:
        if isinstance(data[key], list):
            if data[key]:
                if len(data[key]) == 1:
                    return data[key][0]
                else:
                    raise exception_handler.BadRequest(
                        '%s declared multi times %s in request' % (
                            key, data[key]
                        )
                    )
            else:
                return None
        else:
            return data[key]
    else:
        return None


def _encode_data(data):
    if isinstance(data, string_types):
        return data.encode('utf-8')
    elif isinstance(data, list):
        return [_encode_data(item) for item in data]
    elif isinstance(data, dict):
        return {
            _encode_data(key): _encode_data(value)
            for key, value in six.iteritems(data)
        }
    elif isinstance(data, tuple):
        return tuple(_encode_data(list(data)))
    return data


def _decode_data(data):
    if isinstance(data, string_types):
        return data.decode('utf-8')
    elif isinstance(data, list):
        return [_decode_data(item) for item in data]
    elif isinstance(data, dict):
        return {
            _decode_data(key): _decode_data(value)
            for key, value in six.iteritems(data)
        }
    elif isinstance(data, tuple):
        return tuple(_decode_data(list(data)))
    return data


def _get_request_data():
    """Convert reqeust data from string to python dict.

    If the request data is not json formatted, raises
    exception_handler.BadRequest.
    If the request data is not json formatted dict, raises
    exception_handler.BadRequest
    If the request data is empty, return default as empty dict.
    Usage: It is used to add or update a single resource.
    """
    if request.form:
        logger.debug('get data from form')
        data = request.form.to_dict()
        # for key in data:
        #     data[key] = data[key].encode('utf-8')
        return _encode_data(data)
    else:
        logger.debug('get data from payload')
        raw_data = request.data
        if raw_data:
            try:
                data = json.loads(raw_data, encoding='utf-8')
            except Exception as error:
                logger.exception(error)
                raise exception_handler.BadRequest(
                    'request data is not json formatted: %r' % raw_data
                )
            return data
        else:
            return {}


def _bool_converter(value):
    """Convert string value to bool.

    This function is used to convert value in requeset args to expected type.
    If the key exists in request args but the value is not set, it means the
    value should be true.
    Examples:
       /<request_path>?is_admin parsed to {'is_admin', None} and it should
       be converted to {'is_admin': True}.
       /<request_path>?is_admin=0 parsed and converted to {'is_admin': False}.
       /<request_path>?is_admin=1 parsed and converted to {'is_admin': True}.
    """
    if not value:
        return True
    if value in ['False', 'false', '0']:
        return False
    if value in ['True', 'true', '1']:
        return True
    raise exception_handler.BadRequest(
        '%r type is not bool' % value
    )


def _int_converter(value):
    """Convert string value to int.

    We do not use the int converter default exception since we want to make
    sure the exact http response code.
    Raises: exception_handler.BadRequest if value can not be parsed to int.
    Examples:
       /<request_path>?count=10 parsed to {'count': '10'} and it should be
       converted to {'count': 10}.
    """
    try:
        return int(value)
    except Exception:
        raise exception_handler.BadRequest(
            '%r type is not int' % value
        )


def _get_request_args(as_list={}, **kwargs):
    """Get request args as dict.

    The value in the dict is converted to expected type.
    Args:
       kwargs: for each key, the value is the type converter.
    """
    args = request.args.to_dict(flat=False)
    for key, value in args.copy().items():
        is_list = as_list.get(key, False)
        logger.debug('request arg %s is list? %s', key, is_list)
        if not is_list:
            value = value[-1]
            args[key] = value
        if key in kwargs:
            converter = kwargs[key]
            if isinstance(value, list):
                args[key] = [converter(item) for item in value]
            else:
                args[key] = converter(value)
    return _encode_data(args)


@app.route("/info", methods=['GET'])
def status():
    return utils.make_json_response(
        200, 'OK'
    )


@app.route("/health", methods=['GET'])
def health():
    return utils.make_json_response(
        200, 'OK'
    )


@app.route("/metadata/database/models", methods=['GET'])
@login_required
def list_database_models():
    models = {}
    for model_name, model in six.iteritems(admin_api.MODELS):
        models[model_name] = model.__mapper__.columns.keys()
    return utils.make_json_response(
        200, models
    )


@app.route("/metadata/database/models/<model_name>", methods=['GET'])
@login_required
def list_database_model_fields(model_name):
    model = admin_api.MODELS[model_name]
    columns = {}
    for column_name, column in six.iteritems(model.__mapper__.columns):
        columns[model_name] = repr(column)
    return utils.make_json_response(
        200, columns
    )


@app.route("/database/<model_name>", methods=['GET'])
@login_required
def list_model(model_name):
    if model_name not in admin_api.MODELS:
        raise exception_handler.ItemNotFound(
            'model %s is not found' % model_name
        )
    model = admin_api.MODELS[model_name]
    field_mapping = {
        column.name: column.type.python_type
        for column in model.__table__.columns
    }
    args = _get_request_args()
    logger.debug('query model %s with %s', model_name, args)
    converted_args = {}
    for arg, value in six.iteritems(args):
        if arg not in field_mapping:
            raise exception_handler.NotAcceptable(
                'arg %s not in model fields %s' % (
                    arg, field_mapping.keys()
                )
            )
        if value:
            converted_args[arg] = models.convert_column_value(
                value, field_mapping[arg]
            )
    outputs = []
    with database.session() as session:
        result = session.query(
            model
        ).filter_by(**converted_args).all()
        for item in result:
            item_dict = item.to_dict()
            converted_dict = {}
            for key, value in six.iteritems(item_dict):
                converted_dict[key] = models.reverse_convert_column_value(
                    value, field_mapping[key]
                )
            outputs.append(converted_dict)
    return utils.make_json_response(
        200, outputs
    )


@app.route("/database/<model_name>", methods=['POST', 'PUT'])
@login_required
def create_model(model_name):
    if model_name not in admin_api.MODELS:
        raise exception_handler.ItemNotFound(
            'model %s is not found' % model_name
        )
    model = admin_api.MODELS[model_name]
    field_mapping = {
        column.name: column.type.python_type
        for column in model.__table__.columns
    }
    primary_fields = [
        column.name
        for column in model.__table__.primary_key
    ]
    data = _get_request_data()
    logger.debug('create model %s with %s', model_name, data)
    existing_raise_exception = data.pop('existing_raise_exception', None)
    creating_raise_exception = data.pop('creating_raise_exception', None)
    converted_data = {}
    for key, value in six.iteritems(data):
        if key not in field_mapping:
            raise exception_handler.NotAcceptable(
                'key %s not in model fields %s' % (
                    key, field_mapping.keys()
                )
            )
        if value is not None:
            converted_data[key] = models.convert_column_value(
                value, field_mapping[key]
            )
        else:
            converted_data[key] = value
    primary_data = {}
    for key in primary_fields:
        if key not in converted_data:
            raise exception_handler.NotAcceptable(
                'missing primary key %s in row data %s' % (
                    key, primary_fields
                )
            )
        primary_data[key] = converted_data[key]
    with database.session() as session:
        result = session.query(
            model
        ).filter_by(**primary_data).first()
        if result:
            if existing_raise_exception:
                raise exception_handler.ConflictObject(
                    'found existing result for primary keys %s' % primary_data
                )
            for key, value in six.iteritems(converted_data):
                if key not in primary_data:
                    setattr(result, key, value)
        else:
            if creating_raise_exception:
                raise exception_handler.ItemNotFound(
                    'not found result for primary keys %s' % primary_data
                )
            result = model(**converted_data)
            session.add(result)
        session.flush()
    return utils.make_json_response(
        200, {'status': True}
    )


@app.route("/database/<model_name>", methods=['DELETE'])
@login_required
def delete_model(model_name):
    if model_name not in admin_api.MODELS:
        raise exception_handler.ItemNotFound(
            'model %s is not found' % model_name
        )
    model = admin_api.MODELS[model_name]
    field_mapping = {
        column.name: column.type.python_type
        for column in model.__table__.columns
    }
    data = _get_request_data()
    logger.debug('delete model %s with %s', model_name, data)
    converted_data = {}
    for key, value in six.iteritems(data):
        if key not in field_mapping:
            raise exception_handler.NotAcceptable(
                'key %s not in model fields %s' % (
                    key, field_mapping.keys()
                )
            )
        if value is not None:
            converted_data[key] = models.convert_column_value(
                value, field_mapping[key]
            )
        else:
            converted_data[key] = value
    with database.session() as session:
        session.query(
            model
        ).filter_by(**converted_data).delete()
        session.flush()
    return utils.make_json_response(
        200, {'status': True}
    )


@app.route("/export/database/<model_name>", methods=['GET'])
@login_required
def download_model(model_name):
    logger.debug('download model %s', model_name)
    if model_name not in admin_api.MODELS:
        raise exception_handler.ItemNotFound(
            'model %s is not found' % model_name
        )
    model = admin_api.MODELS[model_name]
    field_mapping = {
        column.name: column.type.python_type
        for column in model.__table__.columns
    }
    primary_fields = [
        column.name
        for column in model.__table__.primary_key
    ]
    column_names = []
    rows = {}
    output = []
    column_names.extend(primary_fields)
    for column_name in field_mapping:
        if column_name not in primary_fields:
            column_names.append(column_name)
    with database.session() as session:
        result = session.query(
            model
        ).all()
        for item in result:
            item_dict = item.to_dict()
            item_keys = []
            found_all_primary_fields = True
            for primary_key in primary_fields:
                if primary_key not in item_dict:
                    logger.error(
                        'missing primary field %s in %s',
                        primary_key, item_dict
                    )
                    found_all_primary_fields = False
                    break
                item_keys.append(item_dict[primary_key])
            if not found_all_primary_fields:
                continue
            rows[tuple(item_keys)] = item_dict
    exported_keys = sorted(rows.keys())
    output.append(column_names)
    for exported_key in exported_keys:
        row = rows[exported_key]
        item = []
        for column_name in column_names:
            value = row.get(column_name, "") or ""
            value = models.reverse_convert_column_value(
                value, field_mapping[column_name]
            )
            item.append(value)
        output.append(item)
    string_buffer = BytesIO()
    writer = csv.writer(string_buffer)
    writer.writerows(output)
    return utils.make_csv_response(
        200, string_buffer.getvalue(),
        '%s.csv' % model_name
    )


@app.route("/import/database/<model_name>", methods=['POST'])
@login_required
def upload_model(model_name):
    if model_name not in admin_api.MODELS:
        raise exception_handler.ItemNotFound(
            'model %s is not found' % model_name
        )
    model = admin_api.MODELS[model_name]
    field_mapping = {
        column.name: column.type.python_type
        for column in model.__table__.columns
    }
    args = _get_request_args()
    args.update(_get_request_data())
    logger.debug('upload model %s with %s', model_name, args)
    use_default_primary_fields = bool(int(
        args.pop('use_default_primary_fields', "1")
    ))
    primary_fields = args.pop('primary_fields', [])
    if use_default_primary_fields:
        primary_fields = [
            column.name
            for column in model.__table__.primary_key
        ]
    elif isinstance(primary_fields, basestring):
        primary_fields = primary_fields.split(',')
    logger.debug('primary fields: %s', primary_fields)
    converted_args = {}
    for arg, value in six.iteritems(args):
        if arg in field_mapping:
            converted_args[arg] = models.convert_column_value(
                value, field_mapping[arg]
            )
    data = []
    request_files = request.files.items(multi=True)
    if not request_files:
        raise exception_handler.NotAcceptable(
            'no csv file to upload'
        )
    logger.debug('upload csv files: %s', request_files)
    for filename, upload in request_files:
        fields = None
        reader = csv.reader(upload)
        for row in reader:
            if not row:
                continue
            row = [
                item.strip()
                for item in row
            ]
            if not fields:
                fields = row
                for field in fields:
                    if (field not in field_mapping):
                        raise exception_handler.NotAcceptable(
                            "unknown field %r which should be in %r" % (
                                field, field_mapping.keys()
                            )
                        )
            else:
                row = dict(zip(fields, row))
                row_data = {}
                for key, value in six.iteritems(row):
                    if value:
                        row_data[key] = models.convert_column_value(
                            value, field_mapping[key]
                        )
                row_data.update(converted_args)
                data.append(row_data)
    with database.session() as session:
        for row_data in data:
            if primary_fields:
                primary_data = {}
                missing_primary = False
                for key in primary_fields:
                    if key not in row_data:
                        # logger.error(
                        #     'missing primary key %s in row data %s',
                        #     key, row_data
                        # )
                        missing_primary = True
                        break
                    primary_data[key] = row_data[key]
                if missing_primary:
                    continue
                result = session.query(
                    model
                ).filter_by(**primary_data).first()
                if result:
                    for key, value in six.iteritems(row_data):
                        if key not in primary_data:
                            setattr(result, key, value)
                else:
                    result = model(**row_data)
                    session.add(result)
            else:
                    result = model(**row_data)
                    session.add(result)
        session.flush()
    return utils.make_json_response(
        200, 'OK'
    )


@app.route("/", methods=['GET'])
def index():
    # return utils.make_template_response(200, {}, 'index.html')
    return flask.redirect(flask.url_for('admin.index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Here we use a class of some kind to represent and validate our
    # client-side form data. For example, WTForms is a library that will
    # handle this for us, and we use a custom LoginForm to validate.
    if request.method == 'GET':
        return utils.make_template_response(200, {}, 'login.html')
    data = _get_request_data()
    if 'email' not in data or 'password' not in data:
        raise exception_handler.BadRequest(
            'missing email or password in data'
        )
    expire_timestamp = (
        datetime.datetime.now() + app.config['REMEMBER_COOKIE_DURATION']
    )
    data['expire_timestamp'] = expire_timestamp
    user = auth_handler.authenticate_user(**data)
    logger.debug('user %s', user)
    logger.debug('user expire timestamp: %s', user.expire_timestamp)
    logger.debug('user token: %s', user.token)
    if not user.active:
        raise exception_handler.UserDisabled(
            '%s is not activated' % user.email
        )
    if not login_user(user, remember=data.get('remember', False)):
        raise exception_handler.UserDisabled('failed to login: %s' % user)
    user_api.record_user_token(
        user.token, user.expire_timestamp, user=user
    )
    flask.flash('Logged in successfully.')
    next = request.args.get('next')
    return flask.redirect(next or flask.url_for('admin.index'))


@app.route("/logout")
@login_required
def logout():
    user_api.clean_user_token(current_user.token, current_user)
    logout_user()
    return flask.redirect(flask.url_for('login'))


def init(argv=None):
    util.init(argv)
    logsetting.init(CONF.logfile)
    database.init()
    database.init_data()
    admin_api.init()
    app.debug = CONF.server_debug
    return app


def run_server():
    app.run(
        host='0.0.0.0', port=CONF.server_port,
        debug=CONF.server_debug
    )


if __name__ == '__main__':
    init()
    run_server()
