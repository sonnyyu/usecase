from usecase.api import login_manager

from usecase.db import user as user_api


def authenticate_user(email, password, **kwargs):
    """Authenticate a user by email and password."""
    user = user_api.get_user_object(
        email, **kwargs
    )
    user.authenticate(password)
    return user


@login_manager.header_loader
def load_user_from_header(header):
    """Return a user object from token."""
    return user_api.get_user_object_from_token(header)


@login_manager.user_loader
def load_user(token):
    return user_api.get_user_object_from_token(token)
