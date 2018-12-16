import datetime
import logging

from flask_login import UserMixin

from usecase.db import database
from usecase.db import exception
from usecase.db import models


logger = logging.getLogger(__name__)


class UserWrapper(UserMixin):
    """Wrapper class provided to flask."""

    def __init__(
        self, id, email, crypted_password,
        active=True, is_admin=False,
        expire_timestamp=None, token='', **kwargs
    ):
        self.id = id
        self.email = email
        self.password = crypted_password
        self.active = active
        self.is_admin = is_admin
        self.expire_timestamp = expire_timestamp
        if not token:
            self.token = self.get_auth_token()
        else:
            self.token = token
        super(UserWrapper, self).__init__()

    def authenticate(self, password):
        if not models.encrypt(password, self.password) == self.password:
            raise exception.Unauthorized('%s password mismatch' % self.email)

    def get_auth_token(self):
        return models.encrypt(self.email)

    def is_active(self):
        return self.active

    def get_id(self):
        return self.token

    def is_authenticated(self):
        current_time = datetime.datetime.now()
        return (
            not self.expire_timestamp or
            current_time < self.expire_timestamp
        )

    def __str__(self):
        return '%s[email:%s,password:%s]' % (
            self.__class__.__name__, self.email, self.password
        )


def get_user_object(email, **kwargs):
    """get user and convert to UserWrapper object."""
    logger.debug('get user from email %s kwargs %s', email, kwargs)
    with database.session() as session:
        user = session.query(models.User).filter_by(email=email).first()
        if not user:
            # raise exception.Unauthorized(
            #     '%s unauthorized' % email
            # )
            return None
        user_dict = user.to_dict()
    user_dict.update(kwargs)
    return UserWrapper(**user_dict)


def get_user_object_from_token(token):
    logger.debug(
        'get user from token; %s', token
    )
    expire_timestamp = datetime.datetime.now()
    with database.session() as session:
        user_token = session.query(
            models.UserToken
        ).filter(
            models.UserToken.token == token,
            models.UserToken.expire_timestamp > expire_timestamp
        ).first()
        if not user_token:
            # raise exception.Unauthorized(
            #     'invalid user token: %s' % token
            # )
            return None
        user = session.query(
            models.User
        ).filter_by(id=user_token.user_id).first()
        if not user:
            # raise exception.Unauthorized(
            #     '%s unauthorized' % user_token.user_id
            # )
            return None
        expire_timestamp = user_token.expire_timestamp
        user_dict = user.to_dict()
    user_dict['token'] = token
    user_dict['expire_timestamp'] = expire_timestamp
    return UserWrapper(**user_dict)


def record_user_token(
    token, expire_timestamp, user
):
    """record user token in database."""
    logger.debug(
        'record user %s token %s expire timestamp %s',
        user, token, expire_timestamp
    )
    with database.session() as session:
        user_token = session.query(models.UserToken).filter_by(
            user_id=user.id, token=token
        ).first()
        if not user_token:
            user_token = models.UserToken(
                token=token, user_id=user.id,
                expire_timestamp=expire_timestamp
            )
            session.add(user_token)
        elif expire_timestamp > user_token.expire_timestamp:
            user_token.expire_timestamp = expire_timestamp


def clean_user_token(token, user):
    """clean user token in database."""
    logger.debug(
        'clear user %s token %s',
        user, token
    )
    with database.session() as session:
        session.query(models.UserToken).filter_by(
            token=token, user_id=user.id
        ).delete()
