"""Database model"""
import crypt
import datetime
import dateutil
import logging
import simplejson as json
import sys

from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy import String
from sqlalchemy import Text

from usecase.db import exception
from usecase.utils import settings


BASE = declarative_base()
logger = logging.getLogger(__name__)
if sys.version_info > (3,):
    long = int
    basestring = str
    integer_types = (int,)
    string_types = (str, bytes)
else:
    integer_types = (int, long)
    string_types = (basestring,)


def convert_datetime_to_str(value):
    if isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return datetime.datetime(value).strftime('%Y-%m-%d %H:%M:%S')


def convert_str_to_datetime(value):
    if isinstance(value, string_types):
        return dateutil.parser.parse(value)
    else:
        return datetime.datetime(value)


COLUMN_TYPE_CONVERTER = {
    dict: json.loads,
    datetime.datetime: convert_str_to_datetime
}
REVERSE_COLUMN_TYPE_CONVERTER = {
    dict: json.dumps,
    datetime.datetime: convert_datetime_to_str
}


def convert_column_value(value, value_type):
    if value is None:
        return value
    try:
        if issubclass(value_type, string_types):
            if isinstance(value, string_types):
                return value
        elif isinstance(value, value_type):
            return value
        if value_type in COLUMN_TYPE_CONVERTER:
            logger.debug('found type %s in converts', value_type)
            return COLUMN_TYPE_CONVERTER[value_type](value)
        logger.debug('use %s default constructor', value_type)
        return value_type(value)
    except Exception as error:
        logger.exception(error)
        logger.error(
            'failed to convert %s to %s: %s',
            value, value_type, error
        )
        raise error


def reverse_convert_column_value(value, value_type):
    if value is None:
        return value
    try:
        if isinstance(value, string_types):
            return value
        if value_type in REVERSE_COLUMN_TYPE_CONVERTER:
            logger.debug('found type %s in reverse converts', value_type)
            return REVERSE_COLUMN_TYPE_CONVERTER[value_type](value)
        logger.debug('use %s default constructor', value_type)
        return str(value)
    except Exception as error:
        logger.exception(error)
        logger.error(
            'failed to convert %s from %s: %s',
            value, value_type, error
        )
        raise error


class HelperMixin(object):
    """Provides general fuctions for all table models."""

    @staticmethod
    def type_compatible(value, column_type):
        """Check if value type is compatible with the column type."""
        if value is None:
            return True
        if not hasattr(column_type, 'python_type'):
            return True
        column_python_type = column_type.python_type
        if isinstance(value, column_python_type):
            return True
        if issubclass(column_python_type, string_types):
            return isinstance(value, string_types)
        if issubclass(column_python_type, integer_types):
            return isinstance(value, integer_types)
        if issubclass(column_python_type, float):
            return isinstance(value, float)
        if issubclass(column_python_type, bool):
            return isinstance(value, bool)
        return False

    def validate(self):
        """Generate validate function to make sure the record is legal."""
        columns = self.__mapper__.columns
        for key, column in columns.items():
            value = getattr(self, key)
            if not self.type_compatible(value, column.type):
                raise exception.InvalidParameter(
                    'column %s value %r type is unexpected: %s' % (
                        key, value, column.type
                    )
                )

    def to_dict(self, fields=None):
        """General function to convert record to dict.

        Convert all columns not starting with '_' to
        {<column_name>: <column_value>}
        """
        keys = self.__mapper__.columns.keys()
        if fields:
            if isinstance(fields, string_types):
                fields = [fields]
            filters = []
            for field in fields:
                filters.extend(field.split(','))
            keys = [key for key in keys if key in filters]
        dict_info = {}
        for key in keys:
            if key.startswith('_'):
                continue
            try:
                value = getattr(self, key)
                if isinstance(value, string_types):
                    value = value.encode('utf-8')
            except Exception as error:
                logging.exception(error)
                raise error
            dict_info[key] = value
        return dict_info


class User(BASE, HelperMixin):
    """User table."""
    __tablename__ = 'user'
    __table_args__ = {
        'mysql_default_charset': 'utf8',
        'mysql_engine': 'InnoDB'
    }

    id = Column(Integer, primary_key=True)
    email = Column(String(80), unique=True, nullable=False)
    crypted_password = Column('password', String(225))
    firstname = Column(String(80))
    lastname = Column(String(80))
    is_admin = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    user_tokens = relationship(
        'UserToken',
        passive_deletes=True, passive_updates=True,
        cascade='all, delete-orphan',
        backref=backref('user')
    )

    def __str__(self):
        return 'User[%s]' % self.email

    @property
    def password(self):
        return '***********'

    @password.setter
    def password(self, password):
        # password stored in database is crypted.
        self.crypted_password = encrypt(password)


def encrypt(password, salt=None):
    if not salt:
        salt = settings.PASSWORD_SALT
    return crypt.crypt(password, salt)


class UserToken(BASE, HelperMixin):
    """user token table."""
    __tablename__ = 'user_token'

    id = Column(Integer, primary_key=True)
    __table_args__ = {
        'mysql_default_charset': 'utf8',
        'mysql_engine': 'InnoDB'
    }

    user_id = Column(
        Integer,
        ForeignKey('user.id', onupdate='CASCADE', ondelete='CASCADE')
    )
    token = Column(String(256), unique=True, nullable=False)
    expire_timestamp = Column(DateTime, nullable=True)


class ShowCaseEn(BASE, HelperMixin):
    __tablename__ = 'showcaseen'
    __table_args__ = {
        'mysql_default_charset': 'utf8',
        'mysql_engine': 'InnoDB'
    }
    id = Column(
        BigInteger, primary_key=True,
        autoincrement=True
    )
    developer = Column(String(255))
    owner = Column(String(255))
    SPLEase = Column(String(255))
    alertvolume = Column(String(255))
    app = Column(String(255))
    category = Column(String(255))
    dashboard = Column(String(255))
    datasource = Column(String(255))
    description = Column(Text)
    displayapp = Column(Text)
    domain = Column(String(255))
    examples_label = Column(Text)
    examples_name = Column(String(255))
    gdpr = Column(String(255))
    gdprtext = Column(Text)
    hasSearch = Column(String(255))
    help = Column(Text)
    highlight = Column(String(255))
    howToImplement = Column(Text)
    ids_type = Column(String(255))
    images_label = Column(Text)
    images_name = Column(String(255))
    images_path = Column(String(255))
    journey = Column(Text)
    killchain = Column(Text)
    knownFP = Column(Text)
    mitre = Column(Text)
    name = Column(String(255), unique=True)
    name_label = Column(Text)
    operationalize = Column(Text)
    released = Column(String(255))
    relevance = Column(Text)
    similarUseCases = Column(Text)
    story = Column(Text)
    usecase = Column(Text)


class ShowCaseCn(BASE, HelperMixin):
    __tablename__ = 'showcasecn'
    __table_args__ = {
        'mysql_default_charset': 'utf8',
        'mysql_engine': 'InnoDB'
    }
    id = Column(
        BigInteger, primary_key=True,
        autoincrement=True
    )
    developer = Column(String(255))
    owner = Column(String(255))
    SPLEase = Column(String(255))
    alertvolume = Column(String(255))
    app = Column(String(255))
    category = Column(String(255))
    dashboard = Column(String(255))
    datasource = Column(String(255))
    description = Column(Text)
    displayapp = Column(Text)
    domain = Column(String(255))
    examples_label = Column(Text)
    examples_name = Column(String(255))
    gdpr = Column(String(255))
    gdprtext = Column(Text)
    hasSearch = Column(String(255))
    help = Column(Text)
    highlight = Column(String(255))
    howToImplement = Column(Text)
    ids_type = Column(String(255))
    images_label = Column(Text)
    images_name = Column(String(255))
    images_path = Column(String(255))
    journey = Column(Text)
    killchain = Column(Text)
    knownFP = Column(Text)
    mitre = Column(Text)
    name = Column(String(255), unique=True)
    name_label = Column(Text)
    operationalize = Column(Text)
    released = Column(String(255))
    relevance = Column(Text)
    similarUseCases = Column(Text)
    story = Column(Text)
    usecase = Column(Text)


class ShowCaseDemo(BASE, HelperMixin):
    __tablename__ = 'showcasedemo'
    __table_args__ = {
        'mysql_default_charset': 'utf8',
        'mysql_engine': 'InnoDB'
    }
    id = Column(
        BigInteger, primary_key=True,
        autoincrement=True
    )
    actions_UBASeverity = Column(Integer)
    cardinalityTest = Column(Text)
    change_type = Column(Text)
    description = Column(Text)
    examples_name = Column(
        String(255), unique=True
    )
    label = Column(Text)
    outlierPeerGroup = Column(String(255))
    outlierValueTracked1 = Column(Text)
    outlierValueTracked2 = Column(Text)
    outlierVariable = Column(String(255))
    outlierVariableSubject = Column(String(255))
    prereqs_field = Column(Text)
    prereqs_greaterorequalto = Column(Text)
    prereqs_name = Column(String(255))
    prereqs_override_auto_finalize = Column(Text)
    prereqs_resolution = Column(Text)
    prereqs_test = Column(Text)
    value = Column(Text)
