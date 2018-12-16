# coding=utf-8
import lazypy
import logging
import os
import os.path


logger = logging.getLogger(__name__)
# default setting
CONFIG_DIR = os.environ.get(
    'USECASE_CONFIG_DIR',
    '/etc/usecase'
)

PASSWORD_SALT = 'dsadsa'
DATABASE_TYPE = 'mysql'
DATABASE_USER = 'root'
DATABASE_PASSWORD = 'root'
DATABASE_IP = '127.0.0.1'
DATABASE_PORT = 3306
DATABASE_SERVER = lazypy.delay(
    lambda: '%s:%s' % (DATABASE_IP, DATABASE_PORT)
)
DATABASE_NAME = 'usecase'
DATABASE_URI = lazypy.delay(
    lambda: '%s://%s:%s@%s/%s?charset=utf8' % (
        lazypy.force(DATABASE_TYPE),
        lazypy.force(DATABASE_USER),
        lazypy.force(DATABASE_PASSWORD),
        lazypy.force(DATABASE_SERVER),
        lazypy.force(DATABASE_NAME)
    )
)

DATABASE_POOL_TYPE = 'instant'

DEBUG = True
SERVER_PORT = 80
DEFAULT_LOGLEVEL = 'debug'
DEFAULT_LOGDIR = '/var/log/usecase'
DEFAULT_LOGINTERVAL = 6
DEFAULT_LOGINTERVAL_UNIT = 'h'
DEFAULT_LOGFORMAT = (
    '%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s')
DEFAULT_LOGBACKUPCOUNT = 5
WEB_LOGFILE = 'web.log'
DB_MANAGE_LOGFILE = 'db_manage.log'

WEB_DIR = '/var/www/usecase_web'
USER_AUTH_HEADER_NAME = 'X-Auth-Token'
USER_TOKEN_DURATION = '2h'
ADMIN_EMAIL = 'admin@huawei.com'
ADMIN_PASSWORD = 'admin'

if (
    'USECASE_SETTINGS' in os.environ and
    os.environ['USECASE_SETTINGS']
):
    SETTINGS = os.environ['USECASE_SETTINGS']
else:
    SETTINGS = '%s/settings' % CONFIG_DIR
if os.path.exists(SETTINGS):
    try:
        logger.info('load settings from %s', SETTINGS)
        with open(SETTINGS) as f:
            code = compile(f.read(), SETTINGS, 'exec')
            exec(code, globals(), locals())
    except Exception as error:
        logger.exception(error)
        raise error
else:
    logger.error(
        'ignore unexisting setting file %s', SETTINGS
    )


CONFIG_VARS = vars()
for key, value in CONFIG_VARS.copy().items():
    if isinstance(value, lazypy.Promise):
        CONFIG_VARS[key] = lazypy.force(value)
