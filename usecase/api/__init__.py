import datetime

from flask import Flask
from flask_admin import Admin
from flask_bootstrap import Bootstrap
from flask_caching import Cache
from flask_login import LoginManager

from usecase.api import admin_api
from usecase.utils import settings
from usecase.utils import util


app = Flask(__name__, template_folder='../templates')
Bootstrap(app)
admin = Admin(
    app, name='usecase',
    template_mode='bootstrap3',
    index_view=admin_api.MyAdminIndexView()
)
app.config['CACHE_TYPE'] = 'filesystem'
app.config['CACHE_DIR'] = '/var/cache/usecase'
app.cache = Cache(app)
app.debug = settings.DEBUG
app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'

app.config['AUTH_HEADER_NAME'] = settings.USER_AUTH_HEADER_NAME
app.config['REMEMBER_COOKIE_DURATION'] = (
    datetime.timedelta(
        seconds=util.parse_time_interval(settings.USER_TOKEN_DURATION)
    )
)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)
